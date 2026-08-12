import json

from sqlalchemy import func, select

from flagship_lab.core import Database
from flagship_lab.outbox import EventEnvelope, IdempotentConsumer, KafkaPublisher, OutboxPublisher
from flagship_lab.sql_models import ConsumerReceipt, DeadLetterEvent, OutboxEvent
from flagship_lab.taxflow import TaxFlowService


def test_outbox_moves_exhausted_event_to_dead_letter_and_replays(tmp_path):
    db = Database(tmp_path / "dlq.db"); db.initialize(); TaxFlowService(db).ingest([])
    failures = 0
    def unavailable(_event):
        nonlocal failures; failures += 1; raise RuntimeError("broker offline")
    worker = OutboxPublisher(db, unavailable, max_attempts=2)
    assert worker.publish_batch()["failed"] == 1
    assert worker.publish_batch()["failed"] == 1
    assert worker.publish_batch()["selected"] == 0
    with db.connect() as conn:
        dead = conn.execute(select(DeadLetterEvent)).mappings().one()
        outbox = conn.execute(select(OutboxEvent)).mappings().one()
    assert outbox["dead_lettered_at"] and "broker offline" in dead["failure_reason"]
    worker.replay_dead_letter(dead["id"])
    delivered = []
    assert OutboxPublisher(db, delivered.append).publish_batch()["published"] == 1


def test_idempotent_consumer_executes_handler_once(tmp_path):
    db = Database(tmp_path / "consumer.db"); db.initialize()
    event = EventEnvelope(42, "alpha", "audit.event.created", "run", {"x": 1}, "now")
    executions = []
    consumer = IdempotentConsumer(db, "audit-indexer")
    assert consumer.process(event, lambda item, _conn: executions.append(item.id))
    assert not consumer.process(event, lambda item, _conn: executions.append(item.id))
    assert executions == [42]
    with db.connect() as conn:
        assert conn.execute(select(func.count()).select_from(ConsumerReceipt)).scalar_one() == 1


class FakeProducer:
    def __init__(self): self.call = None
    def produce(self, *args, **kwargs): self.call = (args, kwargs); kwargs["on_delivery"](None, object())
    def flush(self, _timeout): return 0


def test_kafka_adapter_uses_event_id_key_and_tenant_headers():
    producer = FakeProducer(); publisher = KafkaPublisher(producer)
    publisher.publish(EventEnvelope(9, "alpha", "audit.created", "R1", {"ok": True}, "now"))
    args, kwargs = producer.call
    assert args[0] == "flagship.audit.created"
    assert kwargs["key"] == "9"
    assert kwargs["headers"]["tenant_id"] == "alpha"
    assert json.loads(kwargs["value"])["ok"] is True
