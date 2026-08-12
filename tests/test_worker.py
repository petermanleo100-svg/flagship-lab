from flagship_lab.core import Database
from flagship_lab.taxflow import TaxFlowService
from flagship_lab.worker import run_outbox_worker


def test_worker_drains_batch_and_stops_without_sleep(tmp_path):
    db = Database(tmp_path / "worker.db"); db.initialize(); TaxFlowService(db).ingest([])
    delivered = []
    run_outbox_worker(db, delivered.append, poll_seconds=0, stop=lambda: len(delivered) == 1)
    assert delivered[0].topic == "audit.event.created"
