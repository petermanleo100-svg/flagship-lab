from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_sqlite_upgrade_downgrade_roundtrip(tmp_path):
    root = Path(__file__).resolve().parents[1]
    database = tmp_path / "migration.db"
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    assert {"audit_events", "tax_transactions", "regulation_documents", "control_events", "graph_entities"} <= tables
    command.downgrade(config, "base")
    remaining = set(inspect(engine).get_table_names())
    assert remaining <= {"alembic_version"}

