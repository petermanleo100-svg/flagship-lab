from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol

from sqlalchemy import select, update

from .core import Database, utc_now
from .sql_models import OutboxEvent


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
                OutboxEvent.published_at.is_(None), OutboxEvent.attempts < self.max_attempts
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
                except Exception:
                    conn.execute(update(OutboxEvent).where(
                        OutboxEvent.id == row["id"], OutboxEvent.published_at.is_(None)
                    ).values(attempts=row["attempts"] + 1))
                    failed += 1
                else:
                    conn.execute(update(OutboxEvent).where(
                        OutboxEvent.id == row["id"], OutboxEvent.published_at.is_(None)
                    ).values(published_at=utc_now(), attempts=row["attempts"] + 1))
                    published += 1
        return {"selected": len(rows), "published": published, "failed": failed}
