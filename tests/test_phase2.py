from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from flagship_lab.auth import decode_token, issue_token
from flagship_lab.evidence import verify_evidence_package
from flagship_lab.fastapi_app import create_app
from flagship_lab.tax_rules import DEFAULT_RULE_PACK, validate_rule_pack


SECRET = "phase2-test-secret-must-be-at-least-32-characters"


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "phase2.db"), SECRET, allow_dev_tokens=True)
    return TestClient(app)


def token(client: TestClient, role: str) -> str:
    response = client.post("/auth/dev-token", json={"subject": f"test-{role}", "roles": [role]})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_header(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def test_jwt_has_required_claims_and_rejects_unknown_role():
    encoded = issue_token("alice", ["analyst"], SECRET)
    claims = decode_token(encoded, SECRET)
    assert claims["sub"] == "alice"
    assert claims["roles"] == ["analyst"]
    with pytest.raises(ValueError):
        issue_token("mallory", ["superuser"], SECRET)


def test_rule_pack_validation_rejects_duplicate_codes():
    pack = json.loads(json.dumps(DEFAULT_RULE_PACK))
    pack["rules"].append(dict(pack["rules"][0]))
    with pytest.raises(ValueError, match="unique"):
        validate_rule_pack(pack)


def test_fastapi_rbac_and_openapi(client: TestClient):
    health = client.get("/health", headers={"X-Request-ID": "phase3-trace-test"})
    assert health.status_code == 200
    assert health.headers["x-request-id"] == "phase3-trace-test"
    assert health.headers["server-timing"].startswith("app;dur=")
    schema = client.get("/openapi.json").json()
    assert "/tax/runs" in schema["paths"]
    assert client.post("/tax/runs", json={}).status_code == 401
    viewer = token(client, "viewer")
    assert client.post("/tax/runs", json={}, headers=auth_header(viewer)).status_code == 403
    assert client.get("/admin/config-check", headers=auth_header(viewer)).status_code == 403


def test_end_to_end_tax_run_and_verified_evidence(client: TestClient, tmp_path):
    analyst = token(client, "analyst")
    reviewer = token(client, "reviewer")
    transactions = [
        {"invoice_id": "A-1", "seller_tax_id": None, "buyer_tax_id": "B", "invoice_date": "2026-01-01", "amount": 100, "tax_rate": 0.13, "tax_amount": 13, "currency": "CNY"},
        {"invoice_id": "A-2", "seller_tax_id": "S", "buyer_tax_id": "B", "invoice_date": "2026-01-01", "amount": 100, "tax_rate": 0.13, "tax_amount": 99, "currency": "CNY"},
    ]
    ingest = client.post("/tax/transactions", json=transactions, headers=auth_header(analyst))
    assert ingest.status_code == 201
    run = client.post("/tax/runs", json={}, headers=auth_header(analyst))
    assert run.status_code == 201
    run_id = run.json()["run_id"]
    assert run.json()["rule_pack_hash"]
    findings = client.get(f"/tax/findings?run_id={run_id}", headers=auth_header(reviewer))
    assert {item["rule_code"] for item in findings.json()} == {"TAX_ID_REQUIRED", "VAT_RECALC"}
    denied = client.get(f"/evidence/tax/{run_id}", headers=auth_header(analyst))
    assert denied.status_code == 403
    pending = client.get(f"/evidence/tax/{run_id}", headers=auth_header(reviewer))
    assert pending.status_code == 409
    review = client.post(
        f"/tax/runs/{run_id}/review",
        json={"decision": "APPROVE", "comment": "规则运行证据与发现抽样复核通过"},
        headers=auth_header(reviewer),
    )
    assert review.status_code == 200
    assert review.json()["status"] == "APPROVED"
    evidence = client.get(f"/evidence/tax/{run_id}", headers=auth_header(reviewer))
    assert evidence.status_code == 200
    package = tmp_path / "evidence.zip"
    package.write_bytes(evidence.content)
    assert verify_evidence_package(package, SECRET, require_signature=True) == (True, [])
    assert verify_evidence_package(package, "wrong-secret", require_signature=True)[1] == ["signature_mismatch"]
    with zipfile.ZipFile(package) as archive:
        review_payload = json.loads(archive.read("review.json"))
    assert review_payload["reviewed_by"] == "test-reviewer"

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(io.BytesIO(evidence.content)) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "findings.json":
                data += b"tampered"
            target.writestr(info.filename, data)
    valid, errors = verify_evidence_package(tampered)
    assert not valid
    assert "hash_mismatch:findings.json" in errors


def test_control_case_lifecycle_and_four_eyes_api(client: TestClient):
    analyst = token(client, "analyst")
    reviewer = token(client, "reviewer")
    event = {
        "event_id": "LIFE-1",
        "event_type": "DEPLOYMENT",
        "actor": "release-owner",
        "resource": "production",
        "occurred_at": "2026-08-11T23:00:00+08:00",
        "approved": False,
        "privileged": True,
        "outcome": "SUCCESS",
        "payload": {},
    }
    assert client.post("/controls/events", json=event, headers=auth_header(analyst)).status_code == 201
    cases = client.get("/controls/cases", headers=auth_header(reviewer)).json()
    case_id = cases[0]["id"]
    for status, reason in [
        ("IN_REVIEW", "已分派控制责任人与调查范围"),
        ("REMEDIATED", "已补充审批记录并完成补偿性控制"),
        ("CLOSED", "独立复核证据后确认整改关闭"),
    ]:
        response = client.post(
            f"/controls/cases/{case_id}/transition",
            json={"to_status": status, "reason": reason},
            headers=auth_header(reviewer),
        )
        assert response.status_code == 200
    history = client.get(f"/controls/cases/{case_id}/history", headers=auth_header(reviewer)).json()
    assert [item["to_status"] for item in history] == ["IN_REVIEW", "REMEDIATED", "CLOSED"]


def test_expired_or_malformed_token_is_unauthorized(client: TestClient):
    assert client.get("/audit/verify", headers=auth_header("not-a-jwt")).status_code == 401
