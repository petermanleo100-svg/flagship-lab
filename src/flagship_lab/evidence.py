from __future__ import annotations

import hashlib
import hmac
import json
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Connection

from .core import canonical_json, sha256_json, utc_now
from .sql_models import AuditEvent, TaxFinding, TaxRuleRun, TaxRunWorkflow


def _bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode("utf-8")


def export_tax_run(conn: Connection, run_id: str, output: str | Path, signing_secret: str | None = None,
                   key_id: str = "unsigned", tenant_id: str = "default") -> dict:
    run = conn.execute(select(TaxRuleRun).where(
        TaxRuleRun.run_id == run_id, TaxRuleRun.tenant_id == tenant_id)).mappings().one_or_none()
    if run is None:
        raise ValueError("unknown run_id")
    findings = [dict(row) for row in conn.execute(select(TaxFinding).where(
        TaxFinding.run_id == run_id, TaxFinding.tenant_id == tenant_id).order_by(TaxFinding.id)).mappings()]
    audit = [dict(row) for row in conn.execute(select(AuditEvent).where(
        AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.id)).mappings()]
    workflow = conn.execute(select(TaxRunWorkflow).where(
        TaxRunWorkflow.run_id == run_id, TaxRunWorkflow.tenant_id == tenant_id)).mappings().one_or_none()
    payloads = {"run.json": _bytes(dict(run)), "findings.json": _bytes(findings),
                "audit_events.json": _bytes(audit), "review.json": _bytes(dict(workflow) if workflow else None)}
    manifest = {"format": "flagship-evidence/v1", "module": "taxflow", "tenant_id": tenant_id,
                "entity_id": run_id, "created_at": utc_now(),
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}}
    manifest["manifest_hash"] = sha256_json(manifest)
    if signing_secret is not None:
        value = hmac.new(signing_secret.encode(), canonical_json(manifest).encode(), hashlib.sha256).hexdigest()
        manifest["signature"] = {"algorithm": "HMAC-SHA256", "key_id": key_id, "value": value}
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", _bytes(manifest))
    return manifest


def verify_evidence_package(path: str | Path, signing_secret: str | None = None,
                            require_signature: bool = False) -> tuple[bool, list[str]]:
    errors: list[str] = []
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        signature = manifest.pop("signature", None)
        if require_signature and signature is None:
            errors.append("signature_missing")
        if signature is not None and signing_secret is not None:
            expected = hmac.new(signing_secret.encode(), canonical_json(manifest).encode(), hashlib.sha256).hexdigest()
            if signature.get("algorithm") != "HMAC-SHA256" or not hmac.compare_digest(str(signature.get("value", "")), expected):
                errors.append("signature_mismatch")
        supplied_hash = manifest.pop("manifest_hash", None)
        if sha256_json(manifest) != supplied_hash:
            errors.append("manifest_hash_mismatch")
        for name, expected in manifest.get("files", {}).items():
            try:
                actual = hashlib.sha256(archive.read(name)).hexdigest()
            except KeyError:
                errors.append(f"missing:{name}")
                continue
            if actual != expected:
                errors.append(f"hash_mismatch:{name}")
    return not errors, errors
