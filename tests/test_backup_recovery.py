import pytest
from fastapi.testclient import TestClient

from flagship_lab.backup import BackupService
from flagship_lab.core import Database
from flagship_lab.fastapi_app import create_app
from flagship_lab.object_store import LocalWormObjectStore
from flagship_lab.taxflow import TaxFlowService, TaxTransaction


def test_encrypted_backup_restores_new_database_and_business_continues(tmp_path):
    source = Database(tmp_path / "source.db"); source.initialize()
    TaxFlowService(source, "alpha").ingest([
        TaxTransaction("B-1", None, "B", "2026-01-01", "100", "0.13", "13")])
    TaxFlowService(source, "alpha").run_rules()
    store = LocalWormObjectStore(tmp_path / "backups")
    service = BackupService(source, store, b"x" * 32)
    backup = service.create("daily-001")
    restored = Database(tmp_path / "restored.db")
    verification = service.restore(backup.stored, restored)
    assert verification["valid"] and verification["audit_chains"]["alpha"]["valid"]
    tax = TaxFlowService(restored, "alpha")
    tax.ingest([TaxTransaction("B-2", "S", "B", "2026-01-02", "10", "0.13", "1.3")])
    assert tax.run_rules()["transactions"] == 2


def test_wrong_backup_key_is_rejected_before_restore(tmp_path):
    source = Database(tmp_path / "source.db"); source.initialize()
    store = LocalWormObjectStore(tmp_path / "store")
    backup = BackupService(source, store, b"a" * 32).create("encrypted")
    with pytest.raises(ValueError, match="authentication failed"):
        BackupService(source, store, b"b" * 32).restore(backup.stored, Database(tmp_path / "target.db"))


def test_readiness_returns_503_when_database_dependency_fails(tmp_path, monkeypatch):
    app = create_app(str(tmp_path / "ready.db"), "recovery-test-secret-at-least-32-characters")
    def unavailable(_db): raise RuntimeError("database unavailable")
    monkeypatch.setattr("flagship_lab.fastapi_app.database_health", unavailable)
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["dependency"] == "database"
