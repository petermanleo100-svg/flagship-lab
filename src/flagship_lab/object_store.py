from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    version_id: str
    sha256: str
    size: int
    retain_until: str


class ObjectStore(Protocol):
    def put_immutable(self, key: str, data: bytes, content_type: str, retention_days: int) -> StoredObject: ...
    def get(self, key: str, version_id: str | None = None) -> bytes: ...


def safe_key(key: str) -> str:
    normalized = key.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    if not normalized or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("invalid object key")
    return normalized


class LocalWormObjectStore:
    """Create-only local adapter with integrity metadata and enforced retention."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        target = (self.root / safe_key(key)).resolve()
        if self.root not in target.parents:
            raise ValueError("object key escapes store root")
        return target

    def put_immutable(self, key: str, data: bytes, content_type: str, retention_days: int) -> StoredObject:
        if retention_days < 1:
            raise ValueError("retention_days must be positive")
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(data).hexdigest()
        version_id = digest
        version_path = path.with_name(f"{path.name}.{version_id}")
        metadata_path = version_path.with_suffix(version_path.suffix + ".metadata.json")
        if version_path.exists():
            existing = version_path.read_bytes()
            if not hashlib.sha256(existing).hexdigest() == digest:
                raise ValueError("immutable object collision")
            return StoredObject(**json.loads(metadata_path.read_text(encoding="utf-8")))
        retain_until = (datetime.now(timezone.utc) + timedelta(days=retention_days)).isoformat()
        stored = StoredObject(key=safe_key(key), version_id=version_id, sha256=digest,
                              size=len(data), retain_until=retain_until)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(version_path, flags, 0o440)
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        metadata_path.write_text(json.dumps(asdict(stored), sort_keys=True), encoding="utf-8")
        return stored

    def get(self, key: str, version_id: str | None = None) -> bytes:
        path = self._path(key)
        if version_id is None:
            matches = sorted(path.parent.glob(f"{path.name}.*"))
            matches = [item for item in matches if not item.name.endswith(".metadata.json")]
            if len(matches) != 1:
                raise FileNotFoundError(key)
            target = matches[0]
        else:
            target = path.with_name(f"{path.name}.{version_id}")
        data = target.read_bytes()
        metadata = json.loads(target.with_suffix(target.suffix + ".metadata.json").read_text(encoding="utf-8"))
        if hashlib.sha256(data).hexdigest() != metadata["sha256"]:
            raise ValueError("stored object integrity check failed")
        return data


class S3ObjectLockStore:
    """S3 adapter requiring bucket versioning and Object Lock compliance mode."""

    def __init__(self, s3_client, bucket: str, prefix: str = "evidence"):
        self.client, self.bucket, self.prefix = s3_client, bucket, prefix.strip("/")

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{safe_key(key)}" if self.prefix else safe_key(key)

    def put_immutable(self, key: str, data: bytes, content_type: str, retention_days: int) -> StoredObject:
        if retention_days < 1:
            raise ValueError("retention_days must be positive")
        digest = hashlib.sha256(data).hexdigest()
        retain_until = datetime.now(timezone.utc) + timedelta(days=retention_days)
        response = self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data,
            ContentType=content_type, ChecksumSHA256=base64_sha256(data), ObjectLockMode="COMPLIANCE",
            ObjectLockRetainUntilDate=retain_until, Metadata={"sha256": digest})
        version_id = response.get("VersionId")
        if not version_id:
            raise RuntimeError("S3 Object Lock store must return a version id")
        return StoredObject(safe_key(key), version_id, digest, len(data), retain_until.isoformat())

    def get(self, key: str, version_id: str | None = None) -> bytes:
        request = {"Bucket": self.bucket, "Key": self._key(key)}
        if version_id:
            request["VersionId"] = version_id
        response = self.client.get_object(**request)
        data = response["Body"].read()
        expected = response.get("Metadata", {}).get("sha256")
        if expected and hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("stored object integrity check failed")
        return data


def base64_sha256(data: bytes) -> str:
    import base64
    return base64.b64encode(hashlib.sha256(data).digest()).decode()
