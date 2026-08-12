from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from .core import Database, utc_now
from .sql_models import ConsumerReceipt, DeadLetterEvent, OutboxEvent


@dataclass(frozen=True)
class EventEnvelope:
    id: int
    tenant_id: str
    topic: str
    aggregate_id: str
    payload: dict
    created_at: str


class EventPublisher(Protocol):
    def publish(self, event: EventEnvelope) -> None: ...


class OutboxPublisher:
    """Publishes transactionally persisted events with bounded retries.

    PostgreSQL workers use SKIP LOCKED so multiple replicas can drain the same
    outbox without double-claiming a row. Publication remains at-least-once;
    consumers must deduplicate using the stable envelope id.
    """

    def __init__(self, db: Database, publisher: EventPublisher | Callable[[EventEnvelope], None],
                 *, max_attempts: int = 10):
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.db = db
        self.publisher = publisher
        self.max_attempts = max_attempts

    def publish_batch(self, limit: int = 100) -> dict[str, int]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        published = failed = 0
        with self.db.connect() as conn:
            statement = select(OutboxEvent).where(
                OutboxEvent.published_at.is_(None), OutboxEvent.dead_lettered_at.is_(None),
                OutboxEvent.attempts < self.max_attempts
            ).order_by(OutboxEvent.id).limit(limit)
            if conn.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            rows = list(conn.execute(statement).mappings())
            for row in rows:
                envelope = EventEnvelope(row["id"], row["tenant_id"], row["topic"], row["aggregate_id"],
                                         json.loads(row["payload_json"]), row["created_at"])
                try:
                    if callable(self.publisher):
                        self.publisher(envelope)
                    else:
                        self.publisher.publish(envelope)
                except Exception as exc:
                    attempts = row["attempts"] + 1
                    error = f"{type(exc).__name__}: {exc}"[:2000]
                    conn.execute(update(OutboxEvent).where(
                        OutboxEvent.id == row["id"], OutboxEvent.published_at.is_(None)
                    ).values(attempts=attempts, last_error=error,
                             dead_lettered_at=utc_now() if attempts >= self.max_attempts else None))
                    if attempts >= self.max_attempts:
                        conn.execute(insert(DeadLetterEvent).values(
                            outbox_id=row["id"], tenant_id=row["tenant_id"], topic=row["topic"],
                            aggregate_id=row["aggregate_id"], payload_json=row["payload_json"],
                            failure_reason=error, failed_at=utc_now()))
                    failed += 1
                else:
                    conn.execute(update(OutboxEvent).where(
                        OutboxEvent.id == row["id"], OutboxEvent.published_at.is_(None)
                    ).values(published_at=utc_now(), attempts=row["attempts"] + 1))
                    published += 1
        return {"selected": len(rows), "published": published, "failed": failed}

    def replay_dead_letter(self, dead_letter_id: int) -> None:
        with self.db.connect() as conn:
            row = conn.execute(select(DeadLetterEvent).where(
                DeadLetterEvent.id == dead_letter_id, DeadLetterEvent.replayed_at.is_(None)
            )).mappings().one_or_none()
            if row is None:
                raise ValueError("unknown or already replayed dead letter")
            conn.execute(update(OutboxEvent).where(OutboxEvent.id == row["outbox_id"]).values(
                attempts=0, last_error=None, dead_lettered_at=None))
            conn.execute(update(DeadLetterEvent).where(DeadLetterEvent.id == dead_letter_id).values(
                replayed_at=utc_now()))


class KafkaPublisher:
    """Adapter for Kafka-compatible producers supporting produce/poll/flush."""

    def __init__(self, producer, topic_prefix: str = "flagship"):
        self.producer, self.topic_prefix = producer, topic_prefix.rstrip(".")

    def publish(self, event: EventEnvelope) -> None:
        error = []
        def delivered(err, _message):
            if err is not None:
                error.append(err)
        topic = f"{self.topic_prefix}.{event.topic}"
        self.producer.produce(topic, key=str(event.id), value=json.dumps(event.payload).encode(),
                              headers={"event_id": str(event.id), "tenant_id": event.tenant_id,
                                       "aggregate_id": event.aggregate_id}, on_delivery=delivered)
        self.producer.flush(10)
        if error:
            raise RuntimeError(f"Kafka delivery failed: {error[0]}")


class IdempotentConsumer:
    def __init__(self, db: Database, consumer_name: str):
        if not consumer_name.strip():
            raise ValueError("consumer_name is required")
        self.db, self.consumer_name = db, consumer_name

    def process(self, event: EventEnvelope, handler: Callable[[EventEnvelope, object], None]) -> bool:
        """Run handler and receipt in one DB transaction. Returns False for a duplicate."""
        with self.db.connect() as conn:
            exists = conn.execute(select(ConsumerReceipt.event_id).where(
                ConsumerReceipt.consumer_name == self.consumer_name,
                ConsumerReceipt.event_id == str(event.id))).scalar_one_or_none()
            if exists is not None:
                return False
            handler(event, conn)
            conn.execute(insert(ConsumerReceipt).values(
                consumer_name=self.consumer_name, event_id=str(event.id),
                tenant_id=event.tenant_id, processed_at=utc_now()))
        return True
