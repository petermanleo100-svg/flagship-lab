from __future__ import annotations

import random
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Iterable

from .core import Database, append_audit_event, canonical_json, sha256_json, utc_now
from .tax_rules import DEFAULT_RULE_PACK, evaluate_rule, validate_rule_pack


RULE_VERSION = "tax-rules/2026.08.2"


@dataclass(frozen=True)
class TaxTransaction:
    invoice_id: str
    seller_tax_id: str | None
    buyer_tax_id: str | None
    invoice_date: str
    amount: float
    tax_rate: float
    tax_amount: float
    currency: str = "CNY"


@dataclass(frozen=True)
class Finding:
    transaction_id: int | None
    invoice_id: str
    rule_code: str
    severity: str
    explanation: str
    evidence: dict


def generate_transactions(rows: int, seed: int = 20260811, anomaly_rate: float = 0.04) -> list[TaxTransaction]:
    rng = random.Random(seed)
    start = date(2026, 1, 1)
    data: list[TaxTransaction] = []
    rates = [0.0, 0.03, 0.06, 0.09, 0.13]
    for i in range(rows):
        amount = round(rng.uniform(50, 100_000), 2)
        rate = rng.choice(rates)
        tx = TaxTransaction(
            invoice_id=f"INV-{i:09d}",
            seller_tax_id=f"SELLER-{rng.randint(1, 3000):05d}",
            buyer_tax_id=f"BUYER-{rng.randint(1, 5000):05d}",
            invoice_date=str(start + timedelta(days=rng.randint(0, 210))),
            amount=amount,
            tax_rate=rate,
            tax_amount=round(amount * rate, 2),
        )
        if rng.random() < anomaly_rate:
            anomaly = rng.choice(["missing_tax_id", "tax_mismatch", "duplicate", "extreme_amount"])
            if anomaly == "missing_tax_id":
                tx = TaxTransaction(**{**asdict(tx), "seller_tax_id": None})
            elif anomaly == "tax_mismatch":
                tx = TaxTransaction(**{**asdict(tx), "tax_amount": round(tx.tax_amount + 17.31, 2)})
            elif anomaly == "duplicate" and data:
                tx = TaxTransaction(**{**asdict(tx), "invoice_id": data[-1].invoice_id})
            else:
                tx = TaxTransaction(**{**asdict(tx), "amount": 9_500_000.0, "tax_amount": 1_235_000.0})
        data.append(tx)
    return data


class TaxFlowService:
    def __init__(self, db: Database):
        self.db = db

    def ingest(self, transactions: Iterable[TaxTransaction]) -> int:
        rows = list(transactions)
        with self.db.connect() as conn:
            conn.executemany(
                """INSERT INTO tax_transactions
                   (invoice_id,seller_tax_id,buyer_tax_id,invoice_date,amount,tax_rate,tax_amount,currency,source_hash,ingested_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        tx.invoice_id,
                        tx.seller_tax_id,
                        tx.buyer_tax_id,
                        tx.invoice_date,
                        tx.amount,
                        tx.tax_rate,
                        tx.tax_amount,
                        tx.currency,
                        sha256_json(asdict(tx)),
                        utc_now(),
                    )
                    for tx in rows
                ],
            )
            append_audit_event(conn, "taxflow", "BATCH_INGESTED", str(uuid.uuid4()), {"rows": len(rows)})
        return len(rows)

    def run_rules(self, rule_version: str | None = None, rule_pack: dict | None = None) -> dict:
        pack = rule_pack or DEFAULT_RULE_PACK
        validate_rule_pack(pack)
        effective_version = rule_version or f"{pack['pack_id']}/{pack['version']}"
        run_id = str(uuid.uuid4())
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO tax_rule_runs(run_id,rule_version,started_at) VALUES (?,?,?)",
                (run_id, effective_version, utc_now()),
            )
            rows = list(conn.execute("SELECT * FROM tax_transactions ORDER BY id"))
            duplicate_ids = {
                row["invoice_id"]
                for row in conn.execute(
                    "SELECT invoice_id FROM tax_transactions GROUP BY invoice_id HAVING COUNT(*) > 1"
                )
            }
            findings: list[Finding] = []
            for row in rows:
                findings.extend(self._evaluate_row(row, duplicate_ids, pack))
            conn.executemany(
                """INSERT INTO tax_findings
                   (run_id,transaction_id,invoice_id,rule_code,severity,explanation,evidence_json)
                   VALUES (?,?,?,?,?,?,?)""",
                [
                    (run_id, f.transaction_id, f.invoice_id, f.rule_code, f.severity, f.explanation, canonical_json(f.evidence))
                    for f in findings
                ],
            )
            conn.execute(
                """UPDATE tax_rule_runs SET completed_at=?,transaction_count=?,finding_count=?
                   WHERE run_id=?""",
                (utc_now(), len(rows), len(findings), run_id),
            )
            append_audit_event(
                conn,
                "taxflow",
                "RULE_RUN_COMPLETED",
                run_id,
                {"rule_version": effective_version, "transactions": len(rows), "findings": len(findings), "rule_pack_hash": sha256_json(pack)},
            )
        return {"run_id": run_id, "rule_version": effective_version, "transactions": len(rows), "findings": len(findings), "rule_pack_hash": sha256_json(pack)}

    @staticmethod
    def _evaluate_row(row: sqlite3.Row, duplicate_ids: set[str], pack: dict) -> list[Finding]:
        result: list[Finding] = []
        base = {"source_hash": row["source_hash"], "invoice_date": row["invoice_date"]}
        context = {"duplicate_invoice_ids": duplicate_ids}
        for rule in pack["rules"]:
            matched, evidence = evaluate_rule(rule, row, context)
            if matched:
                result.append(Finding(row["id"], row["invoice_id"], rule["code"], rule["severity"], rule["message"], {**base, **evidence}))
        return result

    def findings(self, run_id: str) -> list[dict]:
        with self.db.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM tax_findings WHERE run_id=? ORDER BY id", (run_id,))]
