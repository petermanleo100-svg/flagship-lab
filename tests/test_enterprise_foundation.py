from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from flagship_lab.core import Database, verify_audit_chain
from flagship_lab.fastapi_app import create_app
from flagship_lab.sql_models import TaxTransactionRow
from flagship_lab.taxflow import TaxFlowService, TaxTransaction


SECRET = "enterprise-foundation-test-secret-at-least-32-characters"


def _token(client: TestClient, tenant: str, role: str = "analyst") -> str:
    response = client.post("/auth/dev-token", json={"subject": f"{tenant}-{role}", "tenant_id": tenant, "roles": [role]})
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_api_enforces_tenant_isolation_for_tax_findings_and_audit(tmp_path):
    client = TestClient(create_app(str(tmp_path / "tenant.db"), SECRET, allow_dev_tokens=True))
    alpha = _token(client, "alpha")
    beta = _token(client, "beta")
    alpha_reviewer = _token(client, "alpha", "reviewer")
    beta_reviewer = _token(client, "beta", "reviewer")
    transaction = [{"invoice_id": "A-1", "seller_tax_id": None, "buyer_tax_id": "B",
                    "invoice_date": "2026-01-01", "amount": "100.0000", "tax_rate": "0.130000",
                    "tax_amount": "13.0000", "currency": "CNY"}]
    assert client.post("/tax/transactions", json=transaction, headers=_headers(alpha)).status_code == 201
    alpha_run = client.post("/tax/runs", json={}, headers=_headers(alpha)).json()["run_id"]
    assert len(client.get(f"/tax/findings?run_id={alpha_run}", headers=_headers(alpha_reviewer)).json()) == 1
    assert client.get(f"/tax/findings?run_id={alpha_run}", headers=_headers(beta_reviewer)).json() == []
    beta_run = client.post("/tax/runs", json={}, headers=_headers(beta)).json()
    assert beta_run["transactions"] == 0
    alpha_audit = client.get("/audit/verify", headers=_headers(alpha_reviewer)).json()
    beta_audit = client.get("/audit/verify", headers=_headers(beta_reviewer)).json()
    assert alpha_audit["valid"] and beta_audit["valid"]
    assert alpha_audit["events"] > beta_audit["events"]


def test_decimal_values_round_trip_without_binary_float_drift(tmp_path):
    db = Database(tmp_path / "decimal.db")
    db.initialize()
    TaxFlowService(db).ingest([
        TaxTransaction("PRECISION", "S", "B", "2026-01-01", Decimal("0.1001"),
                       Decimal("0.130000"), Decimal("0.0130"))
    ])
    with db.connect() as conn:
        row = conn.execute(select(TaxTransactionRow).where(
            TaxTransactionRow.invoice_id == "PRECISION")).mappings().one()
        assert row["amount"] == Decimal("0.1001")
        assert row["tax_rate"] == Decimal("0.130000")


def test_readiness_checks_database_and_tenant_chains_are_independent(tmp_path):
    path = tmp_path / "ready.db"
    app = create_app(str(path), SECRET)
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "up"
    db = Database(path)
    with db.connect() as conn:
        assert verify_audit_chain(conn, "alpha") == (True, 0, None)
        assert verify_audit_chain(conn, "beta") == (True, 0, None)


def test_tax_write_idempotency_replays_and_rejects_key_reuse(tmp_path):
    client = TestClient(create_app(str(tmp_path / "idempotency.db"), SECRET, allow_dev_tokens=True))
    analyst = _token(client, "alpha")
    headers = {**_headers(analyst), "Idempotency-Key": "import-2026-001"}
    first_body = [{"invoice_id": "IDEMP-1", "seller_tax_id": "S", "buyer_tax_id": "B",
                   "invoice_date": "2026-01-01", "amount": "10.0000", "tax_rate": "0.130000",
                   "tax_amount": "1.3000", "currency": "CNY"}]
    assert client.post("/tax/transactions", json=first_body, headers=headers).json()["ingested"] == 1
    assert client.post("/tax/transactions", json=first_body, headers=headers).json()["ingested"] == 1
    changed = [{**first_body[0], "invoice_id": "IDEMP-2"}]
    assert client.post("/tax/transactions", json=changed, headers=headers).status_code == 409
    run_headers = {**_headers(analyst), "Idempotency-Key": "run-2026-001"}
    first = client.post("/tax/runs", json={}, headers=run_headers).json()
    replay = client.post("/tax/runs", json={}, headers=run_headers).json()
    assert replay["run_id"] == first["run_id"]
