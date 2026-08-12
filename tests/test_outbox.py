from __future__ import annotations

from sqlalchemy import func, select

from flagship_lab.core import Database
from flagship_lab.outbox import OutboxPublisher
from flagship_lab.sql_models import OutboxEvent
from flagship_lab.taxflow import TaxFlowService, TaxTransaction


def test_outbox_publishes_committed_audit_events_once(tmp_path):
    db = Database(tmp_path / "outbox.db")
    db.initialize()
    TaxFlowService(db, "alpha").ingest([
        TaxTransaction("O-1", "S", "B", "2026-01-01", "100", "0.13", "13")
    ])
    delivered = []
    worker = OutboxPublisher(db, delivered.append)
    first = worker.publish_batch()
    second = worker.publish_batch()
    assert first == {"selected": 1, "published": 1, "failed": 0}
    assert second == {"selected": 0, "published": 0, "failed": 0}
    assert delivered[0].tenant_id == "alpha"
    assert delivered[0].topic == "audit.event.created"


def test_outbox_failure_increments_attempt_and_can_retry(tmp_path):
    db = Database(tmp_path / "retry.db")
    db.initialize()
    TaxFlowService(db).ingest([])
    attempts = 0

    def flaky(_event):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("broker unavailable")

    worker = OutboxPublisher(db, flaky, max_attempts=3)
    assert worker.publish_batch()["failed"] == 1
    assert worker.publish_batch()["published"] == 1
    with db.connect() as conn:
        row = conn.execute(select(OutboxEvent)).mappings().one()
    assert row["attempts"] == 2 and row["published_at"] is not None
