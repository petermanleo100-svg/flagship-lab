from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)


SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    event_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS tax_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id TEXT NOT NULL,
    seller_tax_id TEXT,
    buyer_tax_id TEXT,
    invoice_date TEXT NOT NULL,
    amount REAL NOT NULL,
    tax_rate REAL NOT NULL,
    tax_amount REAL NOT NULL,
    currency TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tax_invoice ON tax_transactions(invoice_id);

CREATE TABLE IF NOT EXISTS tax_rule_runs (
    run_id TEXT PRIMARY KEY,
    rule_version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    transaction_count INTEGER NOT NULL DEFAULT 0,
    finding_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tax_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES tax_rule_runs(run_id),
    transaction_id INTEGER,
    invoice_id TEXT NOT NULL,
    rule_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    explanation TEXT NOT NULL,
    evidence_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regulation_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_key TEXT NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    published_at TEXT NOT NULL,
    version_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    UNIQUE(document_key, version_hash)
);

CREATE TABLE IF NOT EXISTS control_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    resource TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    approved INTEGER NOT NULL,
    privileged INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    evidence_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    control_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    explanation TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN'
);

CREATE TABLE IF NOT EXISTS graph_entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    attributes_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    occurred_at TEXT NOT NULL,
    evidence_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_graph_source ON graph_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_graph_target ON graph_edges(target_id);
"""


def append_audit_event(
    conn: sqlite3.Connection,
    module: str,
    event_type: str,
    entity_id: str,
    payload: dict[str, Any],
) -> str:
    previous = conn.execute(
        "SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    previous_hash = previous["event_hash"] if previous else "GENESIS"
    occurred_at = utc_now()
    material = {
        "module": module,
        "event_type": event_type,
        "entity_id": entity_id,
        "occurred_at": occurred_at,
        "payload": payload,
        "previous_hash": previous_hash,
    }
    event_hash = sha256_json(material)
    conn.execute(
        """INSERT INTO audit_events
           (module,event_type,entity_id,occurred_at,payload_json,previous_hash,event_hash)
           VALUES (?,?,?,?,?,?,?)""",
        (module, event_type, entity_id, occurred_at, canonical_json(payload), previous_hash, event_hash),
    )
    return event_hash


def verify_audit_chain(conn: sqlite3.Connection) -> tuple[bool, int, str | None]:
    previous_hash = "GENESIS"
    count = 0
    for row in conn.execute("SELECT * FROM audit_events ORDER BY id"):
        payload = json.loads(row["payload_json"])
        material = {
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

