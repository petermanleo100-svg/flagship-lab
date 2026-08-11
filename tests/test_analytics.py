from __future__ import annotations

from flagship_lab.controlpulse import ControlEvent, ControlPulseService
from flagship_lab.core import Database
from flagship_lab.event_stream import ControlStreamProcessor, JsonlEventStream
from flagship_lab.regintel import RegIntelService
from flagship_lab.regintel_eval import DEMO_CASES, load_demo_corpus
from flagship_lab.risk_model import generate_temporal_graph_dataset, train_temporal_baseline


def test_regintel_hybrid_evaluation_is_reproducible(tmp_path):
    db = Database(tmp_path / "reg.db")
    db.initialize()
    service = RegIntelService(db)
    load_demo_corpus(service)
    metrics = service.evaluate(DEMO_CASES, k=3)
    assert metrics["cases"] == 12
    assert metrics["recall_at_3"] >= 0.9
    assert metrics["mrr"] >= 0.85
    assert metrics == service.evaluate(DEMO_CASES, k=3)


def test_risk_model_uses_strict_time_split_and_reports_limitations():
    dataset = generate_temporal_graph_dataset(entities=80, months=6, seed=42)
    _, metrics = train_temporal_baseline(dataset, train_through_month=4, seed=42)
    assert metrics["train_months"] == [1, 4]
    assert metrics["test_months"] == [5, 6]
    assert 0 <= metrics["average_precision"] <= 1
    assert 0 <= metrics["recall_at_top_5_percent"] <= 1
    assert len(metrics["feature_importance"]) == 8
    assert metrics["limitations"]


def test_control_stream_checkpoint_replay_and_idempotency(tmp_path):
    db = Database(tmp_path / "controls.db")
    db.initialize()
    service = ControlPulseService(db)
    stream = JsonlEventStream(tmp_path / "events.jsonl")
    events = [
        ControlEvent("E-1", "DEPLOYMENT", "admin", "prod", "2026-01-01T23:00:00+08:00", False, True, "SUCCESS", {}),
        ControlEvent("E-2", "BACKUP", "agent", "db", "2026-01-02T02:00:00+08:00", True, True, "FAILED", {}),
    ]
    for event in events:
        stream.append(event)
    assert stream.verify() == (True, 2, None)
    processor = ControlStreamProcessor(stream, service, tmp_path / "checkpoint.json")
    first = processor.process_available(max_records=1)
    assert first["processed"] == 1
    assert first["next_offset"] == 1
    second = processor.process_available()
    assert second["processed"] == 1
    assert processor.checkpoint() == 2
    before = len(service.open_cases())
    replay = processor.replay()
    assert replay["processed"] == 2
    assert len(service.open_cases()) == before


def test_control_stream_detects_tampering(tmp_path):
    stream = JsonlEventStream(tmp_path / "events.jsonl")
    stream.append(ControlEvent("E", "LOGIN", "a", "r", "2026-01-01T10:00:00+08:00", True, False, "SUCCESS", {}))
    content = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    (tmp_path / "events.jsonl").write_text(content.replace('"actor":"a"', '"actor":"x"'), encoding="utf-8")
    valid, count, broken = stream.verify()
    assert not valid
    assert count == 0
    assert broken

