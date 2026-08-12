import base64
import json
import sys

import pytest

from flagship_lab.core import Database
from flagship_lab.operations import main
from flagship_lab.taxflow import TaxFlowService


def test_operations_cli_creates_restore_metadata(tmp_path, monkeypatch, capsys):
    path = tmp_path / "source.db"; db = Database(path); db.initialize(); TaxFlowService(db).ingest([]); db.dispose()
    store = tmp_path / "operations"
    monkeypatch.setenv("FLAGSHIP_DATABASE_URL", str(path))
    monkeypatch.setenv("FLAGSHIP_OPERATIONS_STORE", str(store))
    monkeypatch.setenv("FLAGSHIP_BACKUP_KEY_BASE64", base64.b64encode(b"k" * 32).decode())
    monkeypatch.setenv("FLAGSHIP_TEXTFILE_DIR", str(tmp_path / "metrics"))
    monkeypatch.setattr(sys, "argv", ["flagship-operations", "backup-create", "nightly", "--retention-days", "30"])
    main()
    output = json.loads(capsys.readouterr().out)
    assert output["tables"]["audit_events"] == 1
    assert (store / "backup-nightly.restore.json").exists()
    assert 'flagship_operation_success{operation="backup_create"} 1' in (tmp_path / "metrics" / "flagship_backup_create.prom").read_text()


def test_operations_cli_records_failure_before_propagating(tmp_path, monkeypatch):
    path = tmp_path / "source.db"; db = Database(path); db.initialize(); db.dispose()
    monkeypatch.setenv("FLAGSHIP_DATABASE_URL", str(path))
    monkeypatch.setenv("FLAGSHIP_OPERATIONS_STORE", str(tmp_path / "operations"))
    monkeypatch.setenv("FLAGSHIP_TEXTFILE_DIR", str(tmp_path / "metrics"))
    monkeypatch.delenv("FLAGSHIP_BACKUP_KEY_BASE64", raising=False)
    monkeypatch.setattr(sys, "argv", ["flagship-operations", "backup-create", "nightly"])
    with pytest.raises(SystemExit, match="required"):
        main()
    assert 'flagship_operation_success{operation="backup_create"} 0' in (tmp_path / "metrics" / "flagship_backup_create.prom").read_text()
