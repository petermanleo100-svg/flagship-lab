from __future__ import annotations

import os

import pytest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import delete, func, select

from flagship_lab.core import Database, verify_audit_chain
from flagship_lab.sql_models import AuditEvent, Base, TaxTransactionRow
from flagship_lab.taxflow import TaxFlowService, TaxTransaction


@pytest.fixture()
def postgres_db():
    url = os.environ.get("FLAGSHIP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FLAGSHIP_TEST_POSTGRES_URL is only required by the PostgreSQL CI job")
    db = Database(url)
    Base.metadata.drop_all(db.engine)
    db.initialize()
    yield db
    db.dispose()


def test_postgres_runtime_decimal_tenant_and_audit(postgres_db):
    alpha = TaxFlowService(postgres_db, "alpha")
    beta = TaxFlowService(postgres_db, "beta")
    alpha.ingest([TaxTransaction("PG-1", None, "B", "2026-01-01", "100.0000", "0.130000", "13.0000")])
    run = alpha.run_rules()
    assert run["transactions"] == 1
    assert len(alpha.findings(run["run_id"])) == 1
    assert beta.run_rules()["transactions"] == 0
    with postgres_db.connect() as conn:
        assert verify_audit_chain(conn, "alpha")[0]
        assert verify_audit_chain(conn, "beta")[0]


def test_postgres_concurrent_audit_chain_and_idempotency_are_serialized(postgres_db):
    service = TaxFlowService(postgres_db, "concurrent")
    transaction = TaxTransaction("CONCURRENT", "S", "B", "2026-01-01", "100", "0.13", "13")

    def same_ingest(_index):
        return service.ingest([transaction], "same-import-key")

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(same_ingest, range(16))) == [1] * 16
    with postgres_db.connect() as conn:
        assert conn.execute(select(func.count()).select_from(TaxTransactionRow).where(
            TaxTransactionRow.tenant_id == "concurrent")).scalar_one() == 1

    def unique_audit(index):
        service.ingest([], f"audit-{index}")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(unique_audit, range(24)))
    with postgres_db.connect() as conn:
        valid, events, broken = verify_audit_chain(conn, "concurrent")
    assert valid and events == 25 and broken is None
