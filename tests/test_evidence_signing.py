from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from flagship_lab.core import Database
from flagship_lab.evidence import export_tax_run, verify_evidence_package
from flagship_lab.taxflow import TaxFlowService, TaxTransaction


def test_ed25519_evidence_signature_is_publicly_verifiable(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption())
    public_pem = private_key.public_key().public_bytes(serialization.Encoding.PEM,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo)
    db = Database(tmp_path / "evidence.db")
    db.initialize()
    service = TaxFlowService(db, "alpha")
    service.ingest([TaxTransaction("E-1", "S", "B", "2026-01-01", "100", "0.13", "13")])
    run = service.run_rules()
    package = tmp_path / "evidence.zip"
    with db.connect() as conn:
        manifest = export_tax_run(conn, run["run_id"], package, tenant_id="alpha",
                                  signing_private_key_pem=private_pem, key_id="test-ed25519-v1")
    assert manifest["signature"]["algorithm"] == "Ed25519"
    assert verify_evidence_package(package, require_signature=True, signing_public_key_pem=public_pem) == (True, [])
    other_public = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    assert "signature_mismatch" in verify_evidence_package(
        package, require_signature=True, signing_public_key_pem=other_public)[1]
