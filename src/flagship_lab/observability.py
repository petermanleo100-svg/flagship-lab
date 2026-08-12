from __future__ import annotations

import json
import logging
import threading
from collections import Counter
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": record.levelname,
                   "logger": record.name, "message": record.getMessage()}
        for field in ("request_id", "method", "path", "status_code", "duration_ms", "tenant_id"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, str, int]] = Counter()
        self._durations: Counter[tuple[str, str]] = Counter()

    def observe_request(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        route = self._normalize(path)
        with self._lock:
            self._requests[(method, route, status_code)] += 1
            self._durations[(method, route)] += duration_seconds

    @staticmethod
    def _normalize(path: str) -> str:
        segments = path.strip("/").split("/")
        return "/" + "/".join("{id}" if segment.isdigit() or len(segment) == 36 else segment for segment in segments)

    def render(self) -> str:
        lines = ["# HELP flagship_http_requests_total HTTP requests.",
                 "# TYPE flagship_http_requests_total counter"]
        with self._lock:
            for (method, route, status), count in sorted(self._requests.items()):
                lines.append(f'flagship_http_requests_total{{method="{method}",route="{route}",status="{status}"}} {count}')
            lines.extend(["# HELP flagship_http_request_duration_seconds_sum Cumulative request duration.",
                          "# TYPE flagship_http_request_duration_seconds_sum counter"])
            for (method, route), duration in sorted(self._durations.items()):
                lines.append(f'flagship_http_request_duration_seconds_sum{{method="{method}",route="{route}"}} {duration:.6f}')
        return "\n".join(lines) + "\n"
