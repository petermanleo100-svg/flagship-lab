from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time

from .core import Database
from .outbox import KafkaPublisher, OutboxPublisher


def run_outbox_worker(db: Database, publisher, *, poll_seconds: float = 1.0,
                      batch_size: int = 100, max_attempts: int = 10, stop=None) -> None:
    stopping = stop or (lambda: False)
    worker = OutboxPublisher(db, publisher, max_attempts=max_attempts)
    logger = logging.getLogger("flagship.outbox")
    while not stopping():
        result = worker.publish_batch(batch_size)
        logger.info("outbox_batch", extra=result)
        if result["selected"] == 0:
            time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Flagship reliable worker")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    database_url = os.environ.get("FLAGSHIP_DATABASE_URL")
    brokers = os.environ.get("FLAGSHIP_KAFKA_BOOTSTRAP_SERVERS")
    if not database_url or not brokers:
        raise SystemExit("FLAGSHIP_DATABASE_URL and FLAGSHIP_KAFKA_BOOTSTRAP_SERVERS are required")
    try:
        from confluent_kafka import Producer
    except ImportError as exc:
        raise SystemExit("install the 'kafka' optional dependency to run this worker") from exc
    stopped = False
    def handle_signal(_signum, _frame):
        nonlocal stopped; stopped = True
    signal.signal(signal.SIGTERM, handle_signal); signal.signal(signal.SIGINT, handle_signal)
    producer = Producer({"bootstrap.servers": brokers, "enable.idempotence": True, "acks": "all",
                         "compression.type": "zstd", "client.id": "flagship-outbox"})
    run_outbox_worker(Database(database_url, create_schema=False), KafkaPublisher(producer),
                      poll_seconds=args.poll_seconds, batch_size=args.batch_size, stop=lambda: stopped)


if __name__ == "__main__":
    main()
