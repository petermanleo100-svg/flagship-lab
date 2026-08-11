from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path

from .controlpulse import ControlEvent, ControlPulseService
from .core import canonical_json, sha256_json, utc_now


class JsonlEventStream:
    """Append-only local event stream with offsets and a hash chain.

    This is a deterministic development adapter for the future Redpanda/Kafka port.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event: ControlEvent) -> dict:
        with self._lock:
            records = list(self.read_from(0))
            offset = records[-1]["offset"] + 1 if records else 0
            previous_hash = records[-1]["record_hash"] if records else "GENESIS"
            record = {
                "offset": offset,
                "recorded_at": utc_now(),
                "event": asdict(event),
                "previous_hash": previous_hash,
            }
            record["record_hash"] = sha256_json(record)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(canonical_json(record) + "\n")
                handle.flush()
            return record

    def read_from(self, offset: int) -> list[dict]:
        if not self.path.exists():
            return []
        result = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if int(record["offset"]) >= offset:
                    result.append(record)
        return result

    def verify(self) -> tuple[bool, int, str | None]:
        previous = "GENESIS"
        expected_offset = 0
        for record in self.read_from(0):
            supplied = record["record_hash"]
            material = dict(record)
            material.pop("record_hash")
            if record["offset"] != expected_offset or record["previous_hash"] != previous or sha256_json(material) != supplied:
                return False, expected_offset, supplied
            previous = supplied
            expected_offset += 1
        return True, expected_offset, None


class ControlStreamProcessor:
    def __init__(self, stream: JsonlEventStream, service: ControlPulseService, checkpoint_path: str | Path):
        self.stream = stream
        self.service = service
        self.checkpoint_path = Path(checkpoint_path)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint(self) -> int:
        if not self.checkpoint_path.exists():
            return 0
        return int(json.loads(self.checkpoint_path.read_text(encoding="utf-8"))["next_offset"])

    def process_available(self, max_records: int | None = None) -> dict:
        start = self.checkpoint()
        records = self.stream.read_from(start)
        if max_records is not None:
            records = records[:max_records]
        cases = 0
        next_offset = start
        for record in records:
            event = ControlEvent(**record["event"])
            cases += len(self.service.ingest_and_evaluate(event))
            next_offset = int(record["offset"]) + 1
            self._write_checkpoint(next_offset)
        return {"start_offset": start, "next_offset": next_offset, "processed": len(records), "cases": cases}

    def replay(self) -> dict:
        self._write_checkpoint(0)
        return self.process_available()

    def _write_checkpoint(self, next_offset: int) -> None:
        temp = self.checkpoint_path.with_suffix(self.checkpoint_path.suffix + ".tmp")
        temp.write_text(json.dumps({"next_offset": next_offset}), encoding="utf-8")
        temp.replace(self.checkpoint_path)

