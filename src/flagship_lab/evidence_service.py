from __future__ import annotations

from dataclasses import asdict

from .core import Database, append_audit_event
from .evidence import build_tax_run_package
from .object_store import ObjectStore, StoredObject
from .signing import EvidenceSigner


class EvidenceService:
    def __init__(self, db: Database, store: ObjectStore, signer: EvidenceSigner, *, retention_days: int = 2555):
        if retention_days < 1:
            raise ValueError("retention_days must be positive")
        self.db, self.store, self.signer = db, store, signer
        self.retention_days = retention_days

    def preserve_tax_run(self, tenant_id: str, run_id: str) -> StoredObject:
        key = f"{tenant_id}/tax/{run_id}.zip"
        with self.db.connect(tenant_id) as conn:
            package, manifest = build_tax_run_package(conn, run_id, tenant_id, self.signer)
            stored = self.store.put_immutable(key, package, "application/zip", self.retention_days)
            append_audit_event(conn, "evidence", "EVIDENCE_PRESERVED", run_id,
                {"object": asdict(stored), "manifest_hash": manifest["manifest_hash"]}, tenant_id)
        return stored

    def read(self, stored: StoredObject) -> bytes:
        return self.store.get(stored.key, stored.version_id)
