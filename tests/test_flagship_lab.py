from __future__ import annotations

import tempfile
import json
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from flagship_lab.controlpulse import ControlEvent, ControlPulseService
from flagship_lab.core import Database, verify_audit_chain
from flagship_lab.regintel import RegIntelService
from flagship_lab.riskgraph import Edge, Entity, RiskGraphService
from flagship_lab.taxflow import TaxFlowService, TaxTransaction
from flagship_lab.server import create_server


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tempdir.name) / "test.db")
        self.db.initialize()

    def tearDown(self):
        self.tempdir.cleanup()


class TaxFlowTests(DatabaseTestCase):
    def test_rules_detect_seeded_findings(self):
        service = TaxFlowService(self.db)
        service.ingest([
            TaxTransaction("INV-1", None, "BUYER-1", "2026-01-01", 100, 0.13, 13),
            TaxTransaction("INV-2", "SELLER-1", "BUYER-1", "2026-01-01", 100, 0.13, 15),
            TaxTransaction("INV-DUP", "SELLER-1", "BUYER-1", "2026-01-01", 100, 0.13, 13),
            TaxTransaction("INV-DUP", "SELLER-2", "BUYER-2", "2026-01-02", 100, 0.13, 13),
            TaxTransaction("INV-HIGH", "SELLER-1", "BUYER-1", "2026-01-01", 9_000_000, 0.13, 1_170_000),
        ])
        run = service.run_rules()
        findings = service.findings(run["run_id"])
        codes = [f["rule_code"] for f in findings]
        self.assertIn("TAX_ID_REQUIRED", codes)
        self.assertIn("VAT_RECALC", codes)
        self.assertEqual(codes.count("DUPLICATE_INVOICE"), 2)
        self.assertIn("EXTREME_AMOUNT", codes)


class RegIntelTests(DatabaseTestCase):
    def test_answer_has_citation_and_unknown_query_refuses(self):
        service = RegIntelService(self.db)
        service.add_document("d1", "发票税额规则", "https://example.invalid/d1", "2026-01-01", "发票税额依据金额与适用税率计算。")
        answer = service.answer("发票税额")
        self.assertFalse(answer["refused"])
        self.assertEqual(answer["citations"][0]["title"], "发票税额规则")
        refused = service.answer("火星房地产税")
        self.assertTrue(refused["refused"])


class ControlPulseTests(DatabaseTestCase):
    def test_unapproved_privileged_deployment_creates_two_cases(self):
        service = ControlPulseService(self.db)
        cases = service.ingest_and_evaluate(
            ControlEvent("e1", "DEPLOYMENT", "root", "prod", "2026-08-11T23:00:00+08:00", False, True, "SUCCESS", {})
        )
        self.assertEqual({c["control_id"] for c in cases}, {"AC-PRIV-001", "CM-APPROVAL-001"})
        self.assertEqual(len(service.open_cases()), 2)


class RiskGraphTests(DatabaseTestCase):
    def test_shared_account_and_cycle_are_explained(self):
        service = RiskGraphService(self.db)
        service.add_entities([
            Entity("A", "ORG", {}), Entity("B", "ORG", {}), Entity("C", "ORG", {}), Entity("X", "ACCOUNT", {})
        ])
        service.add_edges([
            Edge("A", "X", "OWNS_ACCOUNT", 0, "2026-01-01", {}),
            Edge("B", "X", "OWNS_ACCOUNT", 0, "2026-01-01", {}),
            Edge("A", "B", "PAYS", 1, "2026-01-01", {}),
            Edge("B", "C", "PAYS", 1, "2026-01-01", {}),
            Edge("C", "A", "PAYS", 1, "2026-01-01", {}),
        ])
        findings = service.investigate()
        self.assertEqual({f["risk_code"] for f in findings}, {"SHARED_ACCOUNT", "CIRCULAR_RELATION"})
        self.assertTrue(all(f["explanation"] and f["evidence"] for f in findings))


class AuditChainTests(DatabaseTestCase):
    def test_cross_module_chain_is_valid(self):
        tax = TaxFlowService(self.db)
        tax.ingest([TaxTransaction("I", "S", "B", "2026-01-01", 100, 0.13, 13)])
        tax.run_rules()
        with self.db.connect() as conn:
            valid, count, broken = verify_audit_chain(conn)
        self.assertTrue(valid)
        self.assertGreaterEqual(count, 2)
        self.assertIsNone(broken)


class HttpApiTests(DatabaseTestCase):
    def test_health_endpoint(self):
        server = create_server(self.db.path, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/health", timeout=3) as response:
                payload = json.loads(response.read())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(set(payload["modules"]), {"taxflow", "regintel", "controlpulse", "riskgraph"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
