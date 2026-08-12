from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .controlpulse import ControlEvent, ControlPulseService
from .core import Database, verify_audit_chain
from .regintel import RegIntelService
from .riskgraph import Edge, Entity, RiskGraphService
from .taxflow import TaxFlowService, generate_transactions
from .server import serve
from .event_stream import ControlStreamProcessor, JsonlEventStream
from .regintel_eval import DEMO_CASES, load_demo_corpus
from .risk_model import (
    generate_temporal_graph_dataset,
    save_model_artifacts,
    train_temporal_baseline,
    validate_entity_holdout,
)


def demo(db_path: str) -> dict:
    db = Database(db_path)
    db.initialize()

    tax = TaxFlowService(db)
    tax.ingest(generate_transactions(500, seed=7, anomaly_rate=0.08))
    tax_result = tax.run_rules()

    reg = RegIntelService(db)
    reg.add_document(
        "demo-vat-001", "增值税演示规则", "https://example.invalid/vat", "2026-01-01",
        "本演示材料规定：发票税额应当依据不含税金额和适用税率计算。材料仅用于软件测试，不构成税务建议。",
    )
    reg_result = reg.answer("发票税额如何计算")

    controls = ControlPulseService(db)
    control_result = controls.ingest_and_evaluate(
        ControlEvent("EVT-1", "DEPLOYMENT", "admin", "production", "2026-08-11T23:30:00+08:00", False, True, "SUCCESS", {"change_id": None})
    )

    graph = RiskGraphService(db)
    graph.add_entities([
        Entity("ORG-A", "ORGANIZATION", {}), Entity("ORG-B", "ORGANIZATION", {}), Entity("ORG-C", "ORGANIZATION", {}), Entity("ACC-1", "BANK_ACCOUNT", {})
    ])
    graph.add_edges([
        Edge("ORG-A", "ACC-1", "OWNS_ACCOUNT", 0, "2026-08-01", {}),
        Edge("ORG-B", "ACC-1", "OWNS_ACCOUNT", 0, "2026-08-01", {}),
        Edge("ORG-A", "ORG-B", "PAYS", 1000, "2026-08-01", {}),
        Edge("ORG-B", "ORG-C", "PAYS", 1000, "2026-08-02", {}),
        Edge("ORG-C", "ORG-A", "PAYS", 1000, "2026-08-03", {}),
    ])
    graph_result = graph.investigate()

    with db.connect() as conn:
        chain = verify_audit_chain(conn)
    return {"taxflow": tax_result, "regintel": reg_result, "controlpulse": control_result, "riskgraph": graph_result, "audit_chain": {"valid": chain[0], "events": chain[1]}}


def benchmark(db_path: str, rows: int) -> dict:
    path = Path(db_path)
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing benchmark database: {path}")
    db = Database(path)
    db.initialize()
    service = TaxFlowService(db)
    started = time.perf_counter()
    transactions = generate_transactions(rows, seed=20260811, anomaly_rate=0.04)
    generated = time.perf_counter()
    service.ingest(transactions)
    ingested = time.perf_counter()
    result = service.run_rules()
    finished = time.perf_counter()
    return {
        **result,
        "generate_seconds": round(generated - started, 4),
        "ingest_seconds": round(ingested - generated, 4),
        "rule_seconds": round(finished - ingested, 4),
        "rows_per_second": round(rows / max(finished - started, 1e-9), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Flagship Lab platform runner")
    sub = parser.add_subparsers(dest="command", required=True)
    demo_parser = sub.add_parser("demo")
    demo_parser.add_argument("--db", default="work/demo.db")
    bench_parser = sub.add_parser("benchmark")
    bench_parser.add_argument("--db", default="work/benchmark.db")
    bench_parser.add_argument("--rows", type=int, default=100_000)
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--db", default="work/server.db")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8080)
    api_parser = sub.add_parser("api")
    api_parser.add_argument("--db", default="work/api.db")
    api_parser.add_argument("--host", default="127.0.0.1")
    api_parser.add_argument("--port", type=int, default=8000)
    api_parser.add_argument("--allow-dev-tokens", action="store_true")
    reg_eval_parser = sub.add_parser("reg-eval")
    reg_eval_parser.add_argument("--db", default="work/reg-eval.db")
    reg_eval_parser.add_argument("--k", type=int, default=3)
    risk_parser = sub.add_parser("risk-benchmark")
    risk_parser.add_argument("--entities", type=int, default=400)
    risk_parser.add_argument("--months", type=int, default=12)
    risk_parser.add_argument("--train-through", type=int, default=8)
    risk_parser.add_argument("--output-dir", default="artifacts/risk-model")
    stream_parser = sub.add_parser("control-stream-demo")
    stream_parser.add_argument("--db", default="work/control-stream.db")
    stream_parser.add_argument("--stream", default="work/control-events.jsonl")
    stream_parser.add_argument("--checkpoint", default="work/control-checkpoint.json")
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.db, args.host, args.port)
        return
    if args.command == "api":
        import uvicorn
        from .auth import OIDCJWKSTokenVerifier
        from .fastapi_app import create_app

        secret = os.environ.get("FLAGSHIP_JWT_SECRET", "")
        issuer = os.environ.get("FLAGSHIP_OIDC_ISSUER")
        audience = os.environ.get("FLAGSHIP_OIDC_AUDIENCE")
        jwks_url = os.environ.get("FLAGSHIP_OIDC_JWKS_URL")
        verifier = None
        if issuer or audience or jwks_url:
            if not all((issuer, audience, jwks_url)):
                raise SystemExit("FLAGSHIP_OIDC_ISSUER, FLAGSHIP_OIDC_AUDIENCE and FLAGSHIP_OIDC_JWKS_URL are required together")
            verifier = OIDCJWKSTokenVerifier(issuer, audience, jwks_url)
            secret = secret or "development-token-endpoint-disabled-000"
        elif not secret:
            raise SystemExit("Configure OIDC/JWKS or FLAGSHIP_JWT_SECRET (development only)")
        signing_secret = os.environ.get("FLAGSHIP_EVIDENCE_SIGNING_SECRET")
        private_key_path = os.environ.get("FLAGSHIP_EVIDENCE_PRIVATE_KEY_FILE")
        private_key_pem = Path(private_key_path).read_bytes() if private_key_path else None
        uvicorn.run(
            create_app(os.environ.get("FLAGSHIP_DATABASE_URL", args.db), secret, args.allow_dev_tokens,
                       signing_secret, verifier, private_key_pem,
                       initialize_schema=os.environ.get("FLAGSHIP_DATABASE_URL") is None),
            host=args.host,
            port=args.port,
        )
        return
    if args.command == "reg-eval":
        db = Database(args.db)
        db.initialize()
        service = RegIntelService(db)
        load_demo_corpus(service)
        print(json.dumps(service.evaluate(DEMO_CASES, args.k), ensure_ascii=False, indent=2))
        return
    if args.command == "risk-benchmark":
        dataset = generate_temporal_graph_dataset(args.entities, args.months)
        model, metrics = train_temporal_baseline(dataset, args.train_through)
        metrics["entity_holdout_validation"] = validate_entity_holdout(dataset, args.train_through)
        metrics["artifacts"] = save_model_artifacts(model, metrics, args.output_dir)
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        return
    if args.command == "control-stream-demo":
        db = Database(args.db)
        db.initialize()
        service = ControlPulseService(db)
        stream = JsonlEventStream(args.stream)
        demo_events = [
            ControlEvent("STREAM-1", "DEPLOYMENT", "release-bot", "production", "2026-08-11T23:00:00+08:00", False, True, "SUCCESS", {}),
            ControlEvent("STREAM-2", "BACKUP", "backup-agent", "erp-db", "2026-08-12T02:00:00+08:00", True, True, "FAILED", {}),
            ControlEvent("STREAM-3", "LOGIN", "former-user", "finance", "2026-08-12T10:00:00+08:00", False, False, "SUCCESS", {"account_status": "DISABLED"}),
        ]
        for event in demo_events:
            stream.append(event)
        processor = ControlStreamProcessor(stream, service, args.checkpoint)
        result = processor.process_available()
        result["stream_verification"] = stream.verify()
        result["open_cases"] = len(service.open_cases())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    result = demo(args.db) if args.command == "demo" else benchmark(args.db, args.rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
