from __future__ import annotations

import pytest

from flagship_lab.controlpulse import ControlEvent, ControlPulseService
from flagship_lab.core import Database, verify_audit_chain
from flagship_lab.taxflow import TaxFlowService, generate_transactions


def test_tax_review_requires_independent_reviewer_and_is_final(tmp_path):
    db = Database(tmp_path / "governance.db")
    db.initialize()
    service = TaxFlowService(db)
    service.ingest(generate_transactions(30, seed=3, anomaly_rate=0.1))
    run = service.run_rules()
    service.request_review(run["run_id"], "alice")
    with pytest.raises(ValueError, match="independent reviewer"):
        service.review_run(run["run_id"], "alice", "APPROVE", "self review is prohibited")
    approved = service.review_run(run["run_id"], "bob", "APPROVE", "independent sample passed")
    assert approved["status"] == "APPROVED"
    with pytest.raises(ValueError, match="already final"):
        service.review_run(run["run_id"], "carol", "REJECT", "late decision")


def test_control_case_close_requires_independent_actor_and_audits_transitions(tmp_path):
    db = Database(tmp_path / "controls.db")
    db.initialize()
    service = ControlPulseService(db)
    service.ingest_and_evaluate(
        ControlEvent(
            "CASE-1",
            "DEPLOYMENT",
            "release-owner",
            "production",
            "2026-08-11T23:00:00+08:00",
            False,
            True,
            "SUCCESS",
            {},
        )
    )
    case_id = service.open_cases()[0]["id"]
    service.transition_case(case_id, "reviewer", "IN_REVIEW", "triage complete")
    service.transition_case(case_id, "release-owner", "REMEDIATED", "approval evidence attached")
    with pytest.raises(ValueError, match="independent closer"):
        service.transition_case(case_id, "release-owner", "CLOSED", "self close")
    service.transition_case(case_id, "reviewer", "CLOSED", "evidence independently verified")
    assert len(service.case_history(case_id)) == 3
    with db.connect() as conn:
        valid, events, broken = verify_audit_chain(conn)
    assert valid and events >= 4 and broken is None
