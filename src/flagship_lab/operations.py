from __future__ import annotations

import argparse
import base64
import json
import os
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import select

from .backup import BackupService
from .core import Database
from .object_store import LocalWormObjectStore, StoredObject
from .outbox import OutboxPublisher
from .sql_models import DeadLetterEvent


def encryption_key() -> bytes:
    encoded = os.environ.get("FLAGSHIP_BACKUP_KEY_BASE64")
    if not encoded:
        raise SystemExit("FLAGSHIP_BACKUP_KEY_BASE64 is required")
    try:
        key = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise SystemExit("FLAGSHIP_BACKUP_KEY_BASE64 must be valid base64") from exc
    if len(key) != 32:
        raise SystemExit("decoded backup key must be exactly 32 bytes")
    return key


def main() -> None:
    parser = argparse.ArgumentParser(description="Flagship audited operations")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup-create")
    backup.add_argument("backup_id")
    backup.add_argument("--retention-days", type=int, default=30)
    restore = commands.add_parser("backup-restore")
    restore.add_argument("metadata_file")
    restore.add_argument("--target-url", required=True)
    commands.add_parser("dlq-list")
    replay = commands.add_parser("dlq-replay")
    replay.add_argument("dead_letter_id", type=int)
    args = parser.parse_args()
    database_url = os.environ.get("FLAGSHIP_DATABASE_URL")
    store_path = os.environ.get("FLAGSHIP_OPERATIONS_STORE", "work/operations-store")
    if not database_url:
        raise SystemExit("FLAGSHIP_DATABASE_URL is required")
    db = Database(database_url, create_schema=False)
    store = LocalWormObjectStore(store_path)
    if args.command == "backup-create":
        result = BackupService(db, store, encryption_key(), retention_days=args.retention_days).create(args.backup_id)
        metadata = Path(store_path) / f"backup-{args.backup_id}.restore.json"
        metadata.write_text(json.dumps(asdict(result.stored), indent=2), encoding="utf-8")
        print(json.dumps({"stored": asdict(result.stored), "tables": result.tables,
                          "restore_metadata": str(metadata)}, indent=2))
    elif args.command == "backup-restore":
        stored = StoredObject(**json.loads(Path(args.metadata_file).read_text(encoding="utf-8")))
        target = Database(args.target_url)
        print(json.dumps(BackupService(db, store, encryption_key()).restore(stored, target), indent=2))
    elif args.command == "dlq-list":
        with db.connect() as conn:
            rows = [dict(row) for row in conn.execute(select(DeadLetterEvent).where(
                DeadLetterEvent.replayed_at.is_(None)).order_by(DeadLetterEvent.id)).mappings()]
        print(json.dumps(rows, indent=2))
    else:
        OutboxPublisher(db, lambda _event: None).replay_dead_letter(args.dead_letter_id)
        print(json.dumps({"dead_letter_id": args.dead_letter_id, "status": "queued_for_replay"}))


if __name__ == "__main__":
    main()
