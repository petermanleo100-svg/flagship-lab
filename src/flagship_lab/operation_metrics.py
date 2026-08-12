from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path


_OPERATION = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def record_operation(path: str | Path, operation: str, success: bool, *, now: float | None = None) -> None:
    if not _OPERATION.fullmatch(operation):
        raise ValueError("operation must be a bounded Prometheus label token")
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True);previous=target.read_text(encoding="utf-8") if target.exists() else ""
    pattern=re.compile(rf'^flagship_operation_last_success_timestamp_seconds\{{operation="{operation}"\}} ([0-9.]+)$',re.MULTILINE);match=pattern.search(previous);timestamp=float(time.time() if now is None else now);last_success=timestamp if success else (float(match.group(1)) if match else None)
    lines=['# HELP flagship_operation_success Whether the latest operation succeeded.','# TYPE flagship_operation_success gauge',f'flagship_operation_success{{operation="{operation}"}} {1 if success else 0}','# HELP flagship_operation_last_run_timestamp_seconds Unix time of the latest operation attempt.','# TYPE flagship_operation_last_run_timestamp_seconds gauge',f'flagship_operation_last_run_timestamp_seconds{{operation="{operation}"}} {timestamp:.3f}']
    if last_success is not None:lines+=['# HELP flagship_operation_last_success_timestamp_seconds Unix time of the latest successful operation.','# TYPE flagship_operation_last_success_timestamp_seconds gauge',f'flagship_operation_last_success_timestamp_seconds{{operation="{operation}"}} {last_success:.3f}']
    handle,temporary=tempfile.mkstemp(prefix=f".{target.name}.",dir=target.parent,text=True)
    try:
        with os.fdopen(handle,"w",encoding="utf-8",newline="\n") as stream:stream.write("\n".join(lines)+"\n");stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
