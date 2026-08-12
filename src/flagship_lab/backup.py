from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from decimal import Decimal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, func, insert, select, text

from .core import Database, canonical_json, utc_now, verify_audit_chain
from .object_store import ObjectStore, StoredObject
from .sql_models import AuditEvent, Base


@dataclass(frozen=True)
class BackupResult:
    stored: StoredObject
    tables: dict[str, int]
    plaintext_sha256: str


class BackupService:
    """Encrypted, immutable logical backups with restore verification.

    This complements, but does not replace, PostgreSQL WAL/PITR infrastructure.
    """

    FORMAT = "flagship-logical-backup/v1"

    def __init__(self, db: Database, store: ObjectStore, encryption_key: bytes,
                 *, retention_days: int = 30):
        if len(encryption_key) != 32:
            raise ValueError("backup encryption key must be exactly 32 bytes")
        self.db, self.store, self.aes = db, store, AESGCM(encryption_key)
        self.retention_days = retention_days

    def create(self, backup_id: str) -> BackupResult:
        tables: dict[str, list[dict]] = {}
        with self.db.connect() as conn:
            for table in Base.metadata.sorted_tables:
                tables[table.name] = [self._json_row(dict(row)) for row in conn.execute(
                    select(table).order_by(*table.primary_key.columns)).mappings()]
        payload = {"format": self.FORMAT, "created_at": utc_now(), "backup_id": backup_id,
                   "tables": tables, "counts": {name: len(rows) for name, rows in tables.items()}}
        plaintext = canonical_json(payload).encode()
        digest = hashlib.sha256(plaintext).hexdigest()
        nonce = os.urandom(12)
        ciphertext = self.aes.encrypt(nonce, plaintext, self.FORMAT.encode())
        envelope = canonical_json({"format": self.FORMAT, "algorithm": "AES-256-GCM",
            "nonce": base64.b64encode(nonce).decode(), "plaintext_sha256": digest,
            "ciphertext": base64.b64encode(ciphertext).decode()}).encode()
        stored = self.store.put_immutable(f"backups/{backup_id}.json.enc", envelope,
                                          "application/octet-stream", self.retention_days)
        return BackupResult(stored, payload["counts"], digest)

    def restore(self, stored: StoredObject, destination: Database) -> dict:
        envelope = json.loads(self.store.get(stored.key, stored.version_id))
        if envelope.get("format") != self.FORMAT or envelope.get("algorithm") != "AES-256-GCM":
            raise ValueError("unsupported backup envelope")
        try:
            plaintext = self.aes.decrypt(base64.b64decode(envelope["nonce"]),
                                         base64.b64decode(envelope["ciphertext"]), self.FORMAT.encode())
        except Exception as exc:
            raise ValueError("backup authentication failed") from exc
        if hashlib.sha256(plaintext).hexdigest() != envelope["plaintext_sha256"]:
            raise ValueError("backup plaintext hash mismatch")
        payload = json.loads(plaintext)
        destination.initialize()
        with destination.connect() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(delete(table))
            for table in Base.metadata.sorted_tables:
                rows = payload["tables"].get(table.name, [])
                if rows:
                    conn.execute(insert(table), rows)
            if conn.dialect.name == "postgresql":
                for table in Base.metadata.sorted_tables:
                    integer_pk = next((column for column in table.primary_key.columns if str(column.type).startswith("INTEGER")), None)
                    if integer_pk is not None:
                        conn.execute(text("SELECT setval(pg_get_serial_sequence(:table,:column), "
                            "COALESCE((SELECT MAX(" + integer_pk.name + ") FROM " + table.name + "),1), true)"),
                            {"table": table.name, "column": integer_pk.name})
        verification = self.verify(destination, payload["counts"])
        if not verification["valid"]:
            raise ValueError(f"restored database verification failed: {verification}")
        return verification

    @staticmethod
    def verify(db: Database, expected_counts: dict[str, int]) -> dict:
        counts, chains = {}, {}
        with db.connect() as conn:
            for table in Base.metadata.sorted_tables:
                counts[table.name] = conn.execute(select(func.count()).select_from(table)).scalar_one()
            tenants = conn.execute(select(AuditEvent.tenant_id).distinct()).scalars().all()
            for tenant in tenants:
                valid, events, broken = verify_audit_chain(conn, tenant)
                chains[tenant] = {"valid": valid, "events": events, "broken_hash": broken}
        return {"valid": counts == expected_counts and all(item["valid"] for item in chains.values()),
                "counts": counts, "audit_chains": chains}

    @staticmethod
    def _json_row(row: dict) -> dict:
        return {key: str(value) if isinstance(value, Decimal) else value for key, value in row.items()}
