from __future__ import annotations

import os

import pytest
from sqlalchemy import delete

from flagship_lab.core import Database, verify_audit_chain
from flagship_lab.sql_models import Base
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
