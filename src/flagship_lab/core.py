from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import Engine, create_engine, event, func, insert, select, text
from sqlalchemy.engine import Connection, URL
from sqlalchemy.pool import NullPool, StaticPool

from .sql_models import AuditEvent, Base, OutboxEvent


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _database_url(value: str | Path) -> str:
    raw = str(value)
    if "://" in raw:
        return raw
    path = Path(raw).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


class Database:
    """Single SQLAlchemy runtime for SQLite development and PostgreSQL production."""

    def __init__(self, path_or_url: str | Path, *, create_schema: bool = True):
        self.url = _database_url(path_or_url)
        self.path = self.url.removeprefix("sqlite:///") if self.url.startswith("sqlite:///") else self.url
        self.create_schema = create_schema
        options: dict[str, Any] = {"pool_pre_ping": True}
        if self.url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False, "timeout": 30}
            if self.url.endswith(":memory:"):
                options["poolclass"] = StaticPool
            else:
                # File-backed SQLite is a development/test adapter. NullPool closes the
                # file handle after every unit of work and avoids Windows teardown locks.
                options["poolclass"] = NullPool
        else:
            options.update(pool_size=10, max_overflow=20, pool_recycle=1800)
        self.engine: Engine = create_engine(self.url, **options)
        if self.url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._configure_sqlite)

    @staticmethod
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection

    def initialize(self) -> None:
        if self.create_schema:
            Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()


def append_outbox_event(
    conn: Connection, tenant_id: str, topic: str, aggregate_id: str, payload: dict[str, Any]
) -> None:
    conn.execute(
        insert(OutboxEvent).values(
            tenant_id=tenant_id,
            topic=topic,
            aggregate_id=aggregate_id,
            payload_json=canonical_json(payload),
            created_at=utc_now(),
            attempts=0,
        )
    )


def append_audit_event(
    conn: Connection,
    module: str,
    event_type: str,
    entity_id: str,
    payload: dict[str, Any],
    tenant_id: str = "default",
) -> str:
    # One transaction-scoped advisory lock serializes each tenant's chain on PostgreSQL.
    if conn.dialect.name == "postgresql":
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:scope))"), {"scope": f"audit:{tenant_id}"})
    previous = conn.execute(
        select(AuditEvent.event_hash)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    previous_hash = previous or "GENESIS"
    occurred_at = utc_now()
    material = {
        "tenant_id": tenant_id,
        "module": module,
        "event_type": event_type,
        "entity_id": entity_id,
        "occurred_at": occurred_at,
        "payload": payload,
        "previous_hash": previous_hash,
    }
    event_hash = sha256_json(material)
    conn.execute(
        insert(AuditEvent).values(
            tenant_id=tenant_id,
            module=module,
            event_type=event_type,
            entity_id=entity_id,
            occurred_at=occurred_at,
            payload_json=canonical_json(payload),
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
    )
    append_outbox_event(
        conn,
        tenant_id,
        "audit.event.created",
        entity_id,
        {"module": module, "event_type": event_type, "event_hash": event_hash},
    )
    return event_hash


def verify_audit_chain(conn: Connection, tenant_id: str = "default") -> tuple[bool, int, str | None]:
    previous_hash = "GENESIS"
    count = 0
    rows = conn.execute(
        select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.id)
    ).mappings()
    for row in rows:
        payload = json.loads(row["payload_json"])
        material = {
            "tenant_id": tenant_id,
            "module": row["module"],
            "event_type": row["event_type"],
            "entity_id": row["entity_id"],
            "occurred_at": row["occurred_at"],
            "payload": payload,
            "previous_hash": row["previous_hash"],
        }
        if row["previous_hash"] != previous_hash or sha256_json(material) != row["event_hash"]:
            return False, count, row["event_hash"]
        previous_hash = row["event_hash"]
        count += 1
    return True, count, None


def database_health(db: Database) -> dict[str, Any]:
    with db.connect() as conn:
        conn.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    return {"database": "up", "dialect": db.dialect}
