from __future__ import annotations

import os
import base64
import subprocess
import sys
from pathlib import Path

import pytest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url

from flagship_lab.core import Database, verify_audit_chain
from flagship_lab.sql_models import AuditEvent, Base, TaxTransactionRow
from flagship_lab.taxflow import TaxFlowService, TaxTransaction
from flagship_lab.backup import BackupService
from flagship_lab.object_store import LocalWormObjectStore
from flagship_lab.preflight import PreflightError, TENANT_TABLES, run_preflight


ROOT = Path(__file__).parents[1]


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


def test_postgres_backup_restores_to_clean_schema(postgres_db, tmp_path):
    TaxFlowService(postgres_db, "recovery").ingest([
        TaxTransaction("PG-BACKUP", "S", "B", "2026-01-01", "100", "0.13", "13")])
    service = BackupService(postgres_db, LocalWormObjectStore(tmp_path / "backup"), b"p" * 32)
    backup = service.create("postgres-ci")
    # A separate schema in the same PostgreSQL instance provides an isolated restore target.
    with postgres_db.engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS recovery_target CASCADE"))
        conn.execute(text("CREATE SCHEMA recovery_target"))
    target_url = postgres_db.url + "?options=-csearch_path%3Drecovery_target"
    target = Database(target_url)
    try:
        result = service.restore(backup.stored, target)
        assert result["valid"] and result["audit_chains"]["recovery"]["valid"]
    finally:
        target.dispose()
        with postgres_db.engine.begin() as conn:
            conn.execute(text("DROP SCHEMA recovery_target CASCADE"))


def test_postgres_latest_migration_rollback_preserves_business_data(postgres_db):
    with postgres_db.engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS rollback_target CASCADE"))
        conn.execute(text("CREATE SCHEMA rollback_target"))
    target_url = make_url(postgres_db.url).set(query={"options": "-csearch_path=rollback_target"})
    rendered_url = target_url.render_as_string(hide_password=False)
    target = Database(rendered_url, create_schema=False)
    environment = {**os.environ, "FLAGSHIP_DATABASE_URL": rendered_url}
    try:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=environment, check=True)
        TaxFlowService(target, "rollback").ingest([
            TaxTransaction("PG-ROLLBACK", "S", "B", "2026-01-01", "100", "0.13", "13")])
        target.dispose()
        subprocess.run([sys.executable, "-m", "alembic", "downgrade", "20260812_0004"], cwd=ROOT, env=environment, check=True)
        with target.engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM tax_transactions WHERE invoice_id='PG-ROLLBACK'")).scalar_one() == 1
            assert not conn.execute(text("SELECT relrowsecurity FROM pg_class WHERE relname='tax_transactions' AND relnamespace='rollback_target'::regnamespace")).scalar_one()
        target.dispose()
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=environment, check=True)
        with target.engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM tax_transactions WHERE invoice_id='PG-ROLLBACK'")).scalar_one() == 1
            state = conn.execute(text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='tax_transactions' AND relnamespace='rollback_target'::regnamespace")).one()
            assert state == (True, True)
    finally:
        target.dispose()
        with postgres_db.engine.begin() as conn:
            conn.execute(text("DROP SCHEMA rollback_target CASCADE"))


def test_postgres_rls_blocks_unscoped_and_cross_tenant_queries(postgres_db):
    alpha = TaxFlowService(postgres_db, "rls-alpha")
    beta = TaxFlowService(postgres_db, "rls-beta")
    alpha.ingest([TaxTransaction("RLS-A", "S", "B", "2026-01-01", "1", "0", "0")])
    beta.ingest([TaxTransaction("RLS-B", "S", "B", "2026-01-01", "1", "0", "0")])
    with postgres_db.engine.begin() as conn:
        conn.execute(text("DROP ROLE IF EXISTS flagship_rls_test"))
        conn.execute(text("CREATE ROLE flagship_rls_test LOGIN PASSWORD 'rls-test-password' NOSUPERUSER NOBYPASSRLS"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO flagship_rls_test"))
        conn.execute(text("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO flagship_rls_test"))
        conn.execute(text("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO flagship_rls_test"))
        for table in ("tax_transactions", "audit_events", "outbox_events"):
            conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
            conn.execute(text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
            conn.execute(text(f'''CREATE POLICY tenant_isolation ON "{table}"
                USING (tenant_id = current_setting('flagship.tenant_id', true))
                WITH CHECK (tenant_id = current_setting('flagship.tenant_id', true))'''))
    app_url = postgres_db.engine.url.set(username="flagship_rls_test", password="rls-test-password")
    app_db = Database(app_url.render_as_string(hide_password=False), create_schema=False)
    try:
        with app_db.connect() as conn:
            assert conn.execute(select(func.count()).select_from(TaxTransactionRow)).scalar_one() == 0
        with app_db.connect("rls-alpha") as conn:
            rows = conn.execute(select(TaxTransactionRow.invoice_id)).scalars().all()
            assert rows == ["RLS-A"]
        with pytest.raises(Exception):
            with app_db.connect("rls-alpha") as conn:
                conn.execute(TaxTransactionRow.__table__.insert().values(
                    tenant_id="rls-beta", invoice_id="ATTACK", invoice_date="2026-01-01", amount=1,
                    tax_rate=0, tax_amount=0, currency="CNY", source_hash="x", ingested_at="now"))
    finally:
        app_db.dispose()
        with postgres_db.engine.begin() as conn:
            conn.execute(text("DROP OWNED BY flagship_rls_test"))
            conn.execute(text("DROP ROLE flagship_rls_test"))


def test_production_preflight_accepts_runtime_role_and_rejects_owner(postgres_db):
    with postgres_db.engine.begin() as conn:
        # This fixture rebuilds ORM tables after Alembic, so recreate the exact
        # migration security state before exercising the admission contract.
        for table in TENANT_TABLES:
            conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
            conn.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        conn.execute(text("DROP ROLE IF EXISTS flagship_preflight"))
        conn.execute(text("CREATE ROLE flagship_preflight LOGIN PASSWORD 'preflight-password' NOSUPERUSER NOBYPASSRLS"))
        conn.execute(text("GRANT CONNECT ON DATABASE flagship TO flagship_preflight"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO flagship_preflight"))
        conn.execute(text("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO flagship_preflight"))
        conn.execute(text("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO flagship_preflight"))
    runtime_url = postgres_db.engine.url.set(username="flagship_preflight", password="preflight-password")
    try:
        result = run_preflight(
            runtime_url.render_as_string(hide_password=False),
            issuer="https://id.example",
            audience="flagship-lab",
            jwks_url="https://id.example/jwks",
            backup_key_base64=base64.b64encode(b"k" * 32).decode(),
        )
        assert result["valid"] and result["database"]["user"] == "flagship_preflight"
        with pytest.raises(PreflightError, match="superuser"):
            run_preflight(
                postgres_db.url,
                issuer="https://id.example",
                audience="flagship-lab",
                jwks_url="https://id.example/jwks",
                backup_key_base64=base64.b64encode(b"k" * 32).decode(),
            )
    finally:
        with postgres_db.engine.begin() as conn:
            conn.execute(text("DROP OWNED BY flagship_preflight"))
            conn.execute(text("DROP ROLE flagship_preflight"))
