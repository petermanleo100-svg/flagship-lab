from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from flagship_lab.core import Database
from flagship_lab.taxflow import TaxFlowService, TaxTransaction


def _config(path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    return config


def test_alembic_environment_accepts_percent_encoded_database_options(monkeypatch):
    config = Config()
    encoded = "postgresql+psycopg://user:pass@db/app?options=-csearch_path%3Drestore_target"
    config.set_main_option("sqlalchemy.url", encoded.replace("%", "%%"))
    assert config.get_main_option("sqlalchemy.url") == encoded


def test_frozen_migration_chain_builds_runnable_enterprise_schema(tmp_path, monkeypatch):
    monkeypatch.delenv("FLAGSHIP_DATABASE_URL", raising=False)
    path = tmp_path / "migration.db"
    command.upgrade(_config(path), "head")
    inspector = inspect(create_engine(f"sqlite:///{path.as_posix()}"))
    assert {"tenant_id", "rule_pack_json"} <= {item["name"] for item in inspector.get_columns("tax_rule_runs")}
    assert {"idempotency_records", "outbox_events"} <= set(inspector.get_table_names())
    db = Database(path, create_schema=False)
    service = TaxFlowService(db, "migration-test")
    service.ingest([TaxTransaction("M-1", "S", "B", "2026-01-01", "100", "0.13", "13")])
    assert service.run_rules()["transactions"] == 1
    db.dispose()


def test_upgrade_from_phase2_preserves_existing_rows(tmp_path, monkeypatch):
    monkeypatch.delenv("FLAGSHIP_DATABASE_URL", raising=False)
    path = tmp_path / "upgrade.db"
    config = _config(path)
    command.upgrade(config, "20260811_0002")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO tax_transactions
            (invoice_id,seller_tax_id,buyer_tax_id,invoice_date,amount,tax_rate,tax_amount,currency,source_hash,ingested_at)
            VALUES ('LEGACY','S','B','2026-01-01',100.25,0.13,13.0325,'CNY','hash','2026-01-01')"""))
    engine.dispose()
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT invoice_id,tenant_id,amount FROM tax_transactions")).mappings().one()
    assert row["invoice_id"] == "LEGACY"
    assert row["tenant_id"] == "default"
    assert str(row["amount"]) == "100.25"


def test_latest_migration_downgrades_and_reapplies_without_domain_data_loss(tmp_path, monkeypatch):
    monkeypatch.delenv("FLAGSHIP_DATABASE_URL", raising=False)
    path = tmp_path / "rollback.db"; config = _config(path)
    command.upgrade(config, "head")
    db = Database(path, create_schema=False)
    TaxFlowService(db, "rollback").ingest([
        TaxTransaction("ROLLBACK", "S", "B", "2026-01-01", "100", "0.13", "13")])
    db.dispose()
    command.downgrade(config, "20260812_0003")
    inspector = inspect(create_engine(f"sqlite:///{path.as_posix()}"))
    assert "consumer_receipts" not in inspector.get_table_names()
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM tax_transactions WHERE invoice_id='ROLLBACK'")).scalar_one() == 1
