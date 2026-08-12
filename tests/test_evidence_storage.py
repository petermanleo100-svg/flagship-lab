from __future__ import annotations

import io
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from flagship_lab.core import Database
from flagship_lab.evidence_service import EvidenceService
from flagship_lab.object_store import LocalWormObjectStore, S3ObjectLockStore
from flagship_lab.signing import AwsKmsSigner, Ed25519Signer
from flagship_lab.taxflow import TaxFlowService, TaxTransaction


def approved_run(db):
    tax = TaxFlowService(db, "alpha")
    tax.ingest([TaxTransaction("E-1", "S", "B", "2026-01-01", "100", "0.13", "13")])
    run = tax.run_rules(); tax.request_review(run["run_id"], "alice")
    tax.review_run(run["run_id"], "bob", "APPROVE", "evidence verified")
    return run["run_id"]


def test_evidence_service_preserves_signed_versioned_worm_object(tmp_path):
    key = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    db = Database(tmp_path / "evidence.db"); db.initialize(); run_id = approved_run(db)
    service = EvidenceService(db, LocalWormObjectStore(tmp_path / "objects"), Ed25519Signer(key, "local-v1"), retention_days=365)
    stored = service.preserve_tax_run("alpha", run_id)
    assert stored.version_id == stored.sha256 and stored.size > 0
    with zipfile.ZipFile(io.BytesIO(service.read(stored))) as archive:
        assert archive.getinfo("manifest.json")
    with pytest.raises(ValueError, match="escapes|invalid"):
        service.store.put_immutable("../escape", b"x", "text/plain", 1)


class FakeKms:
    def sign(self, **request):
        assert request["MessageType"] == "RAW"
        return {"KeyId": request["KeyId"], "Signature": b"kms-signature"}


class FakeS3:
    def put_object(self, **request):
        assert request["ObjectLockMode"] == "COMPLIANCE"
        assert request["ChecksumSHA256"]
        return {"VersionId": "version-1"}


def test_kms_and_s3_adapters_request_managed_key_and_compliance_retention():
    signature = AwsKmsSigner(FakeKms(), "arn:kms:key/1").sign(b"manifest")
    assert signature.key_id == "arn:kms:key/1"
    stored = S3ObjectLockStore(FakeS3(), "evidence-bucket").put_immutable(
        "alpha/tax/run.zip", b"package", "application/zip", 365)
    assert stored.version_id == "version-1" and stored.retain_until
