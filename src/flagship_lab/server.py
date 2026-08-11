from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .controlpulse import ControlEvent, ControlPulseService
from .core import Database, verify_audit_chain
from .regintel import RegIntelService
from .riskgraph import Edge, Entity, RiskGraphService
from .taxflow import TaxFlowService, TaxTransaction


class FlagshipApplication:
    def __init__(self, db_path: str):
        self.db = Database(db_path)
        self.db.initialize()
        self.tax = TaxFlowService(self.db)
        self.reg = RegIntelService(self.db)
        self.controls = ControlPulseService(self.db)
        self.graph = RiskGraphService(self.db)

    def dispatch(self, method: str, raw_path: str, body: dict | list | None) -> tuple[int, dict | list]:
        parsed = urlparse(raw_path)
        query = parse_qs(parsed.query)
        if method == "GET" and parsed.path == "/health":
            return HTTPStatus.OK, {"status": "ok", "modules": ["taxflow", "regintel", "controlpulse", "riskgraph"]}
        if method == "GET" and parsed.path == "/audit/verify":
            with self.db.connect() as conn:
                valid, count, broken = verify_audit_chain(conn)
            return HTTPStatus.OK, {"valid": valid, "events": count, "broken_hash": broken}
        if method == "POST" and parsed.path == "/tax/transactions":
            items = body if isinstance(body, list) else (body or {}).get("transactions", [])
            count = self.tax.ingest([TaxTransaction(**item) for item in items])
            return HTTPStatus.CREATED, {"ingested": count}
        if method == "POST" and parsed.path == "/tax/runs":
            return HTTPStatus.CREATED, self.tax.run_rules((body or {}).get("rule_version"))
        if method == "GET" and parsed.path == "/tax/findings":
            run_id = (query.get("run_id") or [""])[0]
            return HTTPStatus.OK, self.tax.findings(run_id)
        if method == "POST" and parsed.path == "/reg/documents":
            payload = body or {}
            version = self.reg.add_document(**payload)
            return HTTPStatus.CREATED, {"version_hash": version}
        if method == "POST" and parsed.path == "/reg/answer":
            return HTTPStatus.OK, self.reg.answer((body or {}).get("query", ""))
        if method == "POST" and parsed.path == "/controls/events":
            return HTTPStatus.CREATED, {"cases": self.controls.ingest_and_evaluate(ControlEvent(**(body or {})))}
        if method == "GET" and parsed.path == "/controls/cases":
            return HTTPStatus.OK, self.controls.open_cases()
        if method == "POST" and parsed.path == "/graph/entities":
            items = body if isinstance(body, list) else (body or {}).get("entities", [])
            self.graph.add_entities([Entity(**item) for item in items])
            return HTTPStatus.CREATED, {"upserted": len(items)}
        if method == "POST" and parsed.path == "/graph/edges":
            items = body if isinstance(body, list) else (body or {}).get("edges", [])
            self.graph.add_edges([Edge(**item) for item in items])
            return HTTPStatus.CREATED, {"inserted": len(items)}
        if method == "GET" and parsed.path == "/graph/findings":
            return HTTPStatus.OK, self.graph.investigate()
        return HTTPStatus.NOT_FOUND, {"error": "route_not_found", "method": method, "path": parsed.path}


def make_handler(app: FlagshipApplication):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FlagshipLab/0.1"

        def do_GET(self):  # noqa: N802
            self._handle("GET")

        def do_POST(self):  # noqa: N802
            self._handle("POST")

        def _handle(self, method: str):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length)) if length else None
                status, payload = app.dispatch(method, self.path, body)
            except (TypeError, ValueError, KeyError) as exc:
                status, payload = HTTPStatus.BAD_REQUEST, {"error": "invalid_request", "detail": str(exc)}
            except Exception as exc:
                status, payload = HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error", "detail": type(exc).__name__}
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format, *args):
            return

    return Handler


def create_server(db_path: str, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    app = FlagshipApplication(db_path)
    return ThreadingHTTPServer((host, port), make_handler(app))


def serve(db_path: str, host: str = "127.0.0.1", port: int = 8080) -> None:
    server = create_server(db_path, host, port)
    print(f"Flagship Lab listening on http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
