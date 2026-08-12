from __future__ import annotations

import random
import uuid
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from sqlalchemy import and_, func, insert, select, update

from .core import Database, append_audit_event, canonical_json, sha256_json, utc_now
from .sql_models import IdempotencyRecord, TaxFinding, TaxRuleRun, TaxRunWorkflow, TaxTransactionRow
from .tax_rules import DEFAULT_RULE_PACK, evaluate_rule, validate_rule_pack


MONEY_QUANTUM = Decimal("0.0001")
RATE_QUANTUM = Decimal("0.000001")


def money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def rate(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class TaxTransaction:
    invoice_id: str
    seller_tax_id: str | None
    buyer_tax_id: str | None
    invoice_date: str
    amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    currency: str = "CNY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", money(self.amount))
        object.__setattr__(self, "tax_rate", rate(self.tax_rate))
        object.__setattr__(self, "tax_amount", money(self.tax_amount))


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
    rates = [Decimal("0"), Decimal("0.03"), Decimal("0.06"), Decimal("0.09"), Decimal("0.13")]
    for i in range(rows):
        amount = money(f"{rng.uniform(50, 100_000):.4f}")
        tax_rate = rng.choice(rates)
        tx = TaxTransaction(
            invoice_id=f"INV-{i:09d}",
            seller_tax_id=f"SELLER-{rng.randint(1, 3000):05d}",
            buyer_tax_id=f"BUYER-{rng.randint(1, 5000):05d}",
            invoice_date=str(start + timedelta(days=rng.randint(0, 210))),
            amount=amount,
            tax_rate=tax_rate,
            tax_amount=money(amount * tax_rate),
        )
        if rng.random() < anomaly_rate:
            anomaly = rng.choice(["missing_tax_id", "tax_mismatch", "duplicate", "extreme_amount"])
            values = asdict(tx)
            if anomaly == "missing_tax_id":
                values["seller_tax_id"] = None
            elif anomaly == "tax_mismatch":
                values["tax_amount"] = money(tx.tax_amount + Decimal("17.31"))
            elif anomaly == "duplicate" and data:
                values["invoice_id"] = data[-1].invoice_id
            else:
                values.update(amount=money("9500000"), tax_amount=money("1235000"))
            tx = TaxTransaction(**values)
        data.append(tx)
    return data


class TaxFlowService:
    def __init__(self, db: Database, tenant_id: str = "default"):
        self.db = db
        self.tenant_id = tenant_id

    def _idempotent_response(self, conn, operation: str, key: str | None, request_hash: str) -> dict | None:
        if key is None:
            return None
        if not key.strip() or len(key) > 100:
            raise ValueError("idempotency key must contain 1-100 characters")
        if conn.dialect.name == "postgresql":
            from sqlalchemy import text
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
                         {"scope": f"idempotency:{self.tenant_id}:{operation}:{key}"})
        record = conn.execute(select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == self.tenant_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == key,
        )).mappings().one_or_none()
        if record is None:
            return None
        if record["request_hash"] != request_hash:
            raise ValueError("idempotency key was already used with a different request")
        import json
        return json.loads(record["response_json"])

    def _store_idempotent_response(self, conn, operation: str, key: str | None,
                                   request_hash: str, response: dict) -> None:
        if key is not None:
            conn.execute(insert(IdempotencyRecord).values(
                tenant_id=self.tenant_id, operation=operation, idempotency_key=key,
                request_hash=request_hash, response_json=canonical_json(response),
                status_code=201, created_at=utc_now(),
            ))

    def ingest(self, transactions: Iterable[TaxTransaction], idempotency_key: str | None = None) -> int:
        rows = list(transactions)
        request_hash = sha256_json([asdict(row) for row in rows])
        now = utc_now()
        with self.db.connect(self.tenant_id) as conn:
            replay = self._idempotent_response(conn, "tax.ingest", idempotency_key, request_hash)
            if replay is not None:
                return int(replay["ingested"])
            if rows:
                conn.execute(
                    insert(TaxTransactionRow),
                    [
                        {
                            "tenant_id": self.tenant_id,
                            **asdict(tx),
                            "source_hash": sha256_json(asdict(tx)),
                            "ingested_at": now,
                        }
                        for tx in rows
                    ],
                )
            append_audit_event(
                conn, "taxflow", "BATCH_INGESTED", str(uuid.uuid4()), {"rows": len(rows)}, self.tenant_id
            )
            self._store_idempotent_response(conn, "tax.ingest", idempotency_key,
                                            request_hash, {"ingested": len(rows)})
        return len(rows)

    def run_rules(self, rule_version: str | None = None, rule_pack: dict | None = None,
                  idempotency_key: str | None = None) -> dict:
        pack = rule_pack or DEFAULT_RULE_PACK
        validate_rule_pack(pack)
        effective_version = rule_version or f"{pack['pack_id']}/{pack['version']}"
        request_hash = sha256_json({"rule_version": effective_version, "rule_pack": pack})
        run_id = str(uuid.uuid4())
        with self.db.connect(self.tenant_id) as conn:
            replay = self._idempotent_response(conn, "tax.run_rules", idempotency_key, request_hash)
            if replay is not None:
                return replay
            conn.execute(
                insert(TaxRuleRun).values(
                    run_id=run_id,
                    tenant_id=self.tenant_id,
                    rule_version=effective_version,
                    rule_pack_json=canonical_json(pack),
                    started_at=utc_now(),
                )
            )
            rows = list(
                conn.execute(
                    select(TaxTransactionRow)
                    .where(TaxTransactionRow.tenant_id == self.tenant_id)
                    .order_by(TaxTransactionRow.id)
                ).mappings()
            )
            duplicate_ids = set(
                conn.execute(
                    select(TaxTransactionRow.invoice_id)
                    .where(TaxTransactionRow.tenant_id == self.tenant_id)
                    .group_by(TaxTransactionRow.invoice_id)
                    .having(func.count() > 1)
                ).scalars()
            )
            findings: list[Finding] = []
            for row in rows:
                findings.extend(self._evaluate_row(row, duplicate_ids, pack))
            if findings:
                conn.execute(
                    insert(TaxFinding),
                    [
                        {
                            "tenant_id": self.tenant_id,
                            "run_id": run_id,
                            "transaction_id": finding.transaction_id,
                            "invoice_id": finding.invoice_id,
                            "rule_code": finding.rule_code,
                            "severity": finding.severity,
                            "explanation": finding.explanation,
                            "evidence_json": canonical_json(finding.evidence),
                        }
                        for finding in findings
                    ],
                )
            conn.execute(
                update(TaxRuleRun)
                .where(TaxRuleRun.run_id == run_id)
                .values(completed_at=utc_now(), transaction_count=len(rows), finding_count=len(findings))
            )
            append_audit_event(
                conn,
                "taxflow",
                "RULE_RUN_COMPLETED",
                run_id,
                {
                    "rule_version": effective_version,
                    "transactions": len(rows),
                    "findings": len(findings),
                    "rule_pack_hash": sha256_json(pack),
                },
                self.tenant_id,
            )
            response = {"run_id": run_id, "rule_version": effective_version,
                        "transactions": len(rows), "findings": len(findings),
                        "rule_pack_hash": sha256_json(pack)}
            self._store_idempotent_response(conn, "tax.run_rules", idempotency_key, request_hash, response)
            return response

    def request_review(self, run_id: str, requested_by: str) -> dict:
        if not requested_by.strip():
            raise ValueError("requested_by is required")
        with self.db.connect(self.tenant_id) as conn:
            exists = conn.execute(
                select(TaxRuleRun.run_id).where(
                    TaxRuleRun.run_id == run_id, TaxRuleRun.tenant_id == self.tenant_id
                )
            ).scalar_one_or_none()
            if exists is None:
                raise ValueError("unknown run_id")
            current = conn.execute(
                select(TaxRunWorkflow).where(
                    TaxRunWorkflow.run_id == run_id, TaxRunWorkflow.tenant_id == self.tenant_id
                )
            ).mappings().one_or_none()
            if current is None:
                conn.execute(
                    insert(TaxRunWorkflow).values(
                        run_id=run_id,
                        tenant_id=self.tenant_id,
                        requested_by=requested_by,
                        status="PENDING_REVIEW",
                        version=1,
                    )
                )
                append_audit_event(
                    conn, "taxflow", "REVIEW_REQUESTED", run_id, {"requested_by": requested_by}, self.tenant_id
                )
            return dict(
                conn.execute(
                    select(TaxRunWorkflow).where(
                        TaxRunWorkflow.run_id == run_id, TaxRunWorkflow.tenant_id == self.tenant_id
                    )
                ).mappings().one()
            )

    def review_run(self, run_id: str, reviewer: str, decision: str, comment: str) -> dict:
        normalized = decision.upper()
        if normalized not in {"APPROVE", "REJECT"}:
            raise ValueError("decision must be APPROVE or REJECT")
        if not comment.strip():
            raise ValueError("review comment is required")
        with self.db.connect(self.tenant_id) as conn:
            row = conn.execute(
                select(TaxRunWorkflow).where(
                    TaxRunWorkflow.run_id == run_id, TaxRunWorkflow.tenant_id == self.tenant_id
                )
            ).mappings().one_or_none()
            if row is None:
                raise ValueError("review was not requested")
            if row["status"] != "PENDING_REVIEW":
                raise ValueError("review is already final")
            if row["requested_by"] == reviewer:
                raise ValueError("four-eyes control requires an independent reviewer")
            status = "APPROVED" if normalized == "APPROVE" else "REJECTED"
            result = conn.execute(
                update(TaxRunWorkflow)
                .where(
                    TaxRunWorkflow.run_id == run_id,
                    TaxRunWorkflow.tenant_id == self.tenant_id,
                    TaxRunWorkflow.status == "PENDING_REVIEW",
                    TaxRunWorkflow.version == row["version"],
                )
                .values(
                    status=status,
                    version=row["version"] + 1,
                    reviewed_by=reviewer,
                    reviewed_at=utc_now(),
                    decision_comment=comment,
                )
            )
            if result.rowcount != 1:
                raise ValueError("concurrent review conflict")
            append_audit_event(
                conn,
                "taxflow",
                "REVIEW_DECIDED",
                run_id,
                {"status": status, "reviewed_by": reviewer, "comment": comment},
                self.tenant_id,
            )
            return dict(
                conn.execute(select(TaxRunWorkflow).where(
                    TaxRunWorkflow.run_id == run_id, TaxRunWorkflow.tenant_id == self.tenant_id
                )).mappings().one()
            )

    def workflow(self, run_id: str) -> dict | None:
        with self.db.connect(self.tenant_id) as conn:
            row = conn.execute(
                select(TaxRunWorkflow).where(
                    TaxRunWorkflow.run_id == run_id, TaxRunWorkflow.tenant_id == self.tenant_id
                )
            ).mappings().one_or_none()
            return dict(row) if row else None

    @staticmethod
    def _evaluate_row(row, duplicate_ids: set[str], pack: dict) -> list[Finding]:
        result: list[Finding] = []
        base = {"source_hash": row["source_hash"], "invoice_date": row["invoice_date"]}
        context = {"duplicate_invoice_ids": duplicate_ids}
        for rule_definition in pack["rules"]:
            matched, evidence = evaluate_rule(rule_definition, row, context)
            if matched:
                result.append(
                    Finding(
                        row["id"], row["invoice_id"], rule_definition["code"], rule_definition["severity"],
                        rule_definition["message"], {**base, **evidence},
                    )
                )
        return result

    def findings(self, run_id: str) -> list[dict]:
        with self.db.connect(self.tenant_id) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    select(TaxFinding)
                    .where(TaxFinding.run_id == run_id, TaxFinding.tenant_id == self.tenant_id)
                    .order_by(TaxFinding.id)
                ).mappings()
            ]
