from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import insert, select, update

from .core import Database, append_audit_event, canonical_json, sha256_json, utc_now
from .sql_models import ControlCase, ControlCaseTransition, ControlEventRow


@dataclass(frozen=True)
class ControlEvent:
    event_id: str
    event_type: str
    actor: str
    resource: str
    occurred_at: str
    approved: bool
    privileged: bool
    outcome: str
    payload: dict


class ControlPulseService:
    def __init__(self, db: Database, tenant_id: str = "default"):
        self.db = db
        self.tenant_id = tenant_id

    def ingest_and_evaluate(self, event: ControlEvent) -> list[dict]:
        evidence_hash = sha256_json(asdict(event))
        cases = self._evaluate(event, evidence_hash)
        with self.db.connect(self.tenant_id) as conn:
            existing = conn.execute(
                select(ControlEventRow.id).where(
                    ControlEventRow.tenant_id == self.tenant_id,
                    ControlEventRow.event_id == event.event_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return [
                    dict(row)
                    for row in conn.execute(
                        select(
                            ControlCase.control_id,
                            ControlCase.severity,
                            ControlCase.explanation,
                            ControlCase.evidence_hash,
                        ).where(
                            ControlCase.tenant_id == self.tenant_id,
                            ControlCase.event_id == event.event_id,
                        ).order_by(ControlCase.id)
                    ).mappings()
                ]
            conn.execute(insert(ControlEventRow).values(
                tenant_id=self.tenant_id, event_id=event.event_id, event_type=event.event_type,
                actor=event.actor, resource=event.resource, occurred_at=event.occurred_at,
                approved=int(event.approved), privileged=int(event.privileged), outcome=event.outcome,
                payload_json=canonical_json(event.payload), evidence_hash=evidence_hash,
            ))
            if cases:
                conn.execute(insert(ControlCase), [{
                    "tenant_id": self.tenant_id, "event_id": event.event_id,
                    "control_id": item["control_id"], "severity": item["severity"],
                    "explanation": item["explanation"], "evidence_hash": evidence_hash,
                    "status": "OPEN", "version": 1,
                } for item in cases])
            append_audit_event(conn, "controlpulse", "EVENT_EVALUATED", event.event_id,
                               {"evidence_hash": evidence_hash, "case_count": len(cases)}, self.tenant_id)
        return cases

    @staticmethod
    def _evaluate(event: ControlEvent, evidence_hash: str) -> list[dict]:
        cases: list[dict] = []
        hour = datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00")).hour
        if event.privileged and (hour < 7 or hour >= 22):
            cases.append({"control_id": "AC-PRIV-001", "severity": "HIGH", "explanation": "特权操作发生在非工作时段", "evidence_hash": evidence_hash})
        if event.event_type == "DEPLOYMENT" and not event.approved:
            cases.append({"control_id": "CM-APPROVAL-001", "severity": "HIGH", "explanation": "生产变更缺少审批", "evidence_hash": evidence_hash})
        if event.event_type == "BACKUP" and event.outcome != "SUCCESS":
            cases.append({"control_id": "OP-BACKUP-001", "severity": "HIGH", "explanation": "备份任务失败", "evidence_hash": evidence_hash})
        if event.event_type == "LOGIN" and event.outcome == "SUCCESS" and event.payload.get("account_status") == "DISABLED":
            cases.append({"control_id": "AC-TERM-001", "severity": "CRITICAL", "explanation": "已停用账号登录成功", "evidence_hash": evidence_hash})
        return cases

    def open_cases(self) -> list[dict]:
        with self.db.connect(self.tenant_id) as conn:
            return [dict(row) for row in conn.execute(
                select(ControlCase).where(ControlCase.tenant_id == self.tenant_id, ControlCase.status != "CLOSED")
                .order_by(ControlCase.id)
            ).mappings()]

    def transition_case(self, case_id: int, actor: str, to_status: str, reason: str) -> dict:
        allowed = {"OPEN": {"IN_REVIEW"}, "IN_REVIEW": {"REMEDIATED"}, "REMEDIATED": {"CLOSED"}, "CLOSED": {"OPEN"}}
        target = to_status.upper()
        if not reason.strip():
            raise ValueError("transition reason is required")
        with self.db.connect(self.tenant_id) as conn:
            row = conn.execute(
                select(ControlCase, ControlEventRow.actor.label("event_actor"))
                .join(ControlEventRow, (ControlEventRow.tenant_id == ControlCase.tenant_id) & (ControlEventRow.event_id == ControlCase.event_id))
                .where(ControlCase.id == case_id, ControlCase.tenant_id == self.tenant_id)
            ).mappings().one_or_none()
            if row is None:
                raise ValueError("unknown case_id")
            current = row["status"]
            if target not in allowed.get(current, set()):
                raise ValueError(f"invalid transition {current}->{target}")
            if target == "CLOSED" and actor == row["event_actor"]:
                raise ValueError("four-eyes control requires an independent closer")
            result = conn.execute(update(ControlCase).where(
                ControlCase.id == case_id, ControlCase.tenant_id == self.tenant_id,
                ControlCase.status == current, ControlCase.version == row["version"],
            ).values(status=target, version=row["version"] + 1))
            if result.rowcount != 1:
                raise ValueError("concurrent case transition conflict")
            occurred_at = utc_now()
            conn.execute(insert(ControlCaseTransition).values(
                tenant_id=self.tenant_id, case_id=case_id, from_status=current, to_status=target,
                actor=actor, reason=reason, occurred_at=occurred_at,
            ))
            append_audit_event(conn, "controlpulse", "CASE_TRANSITIONED", str(case_id),
                               {"from": current, "to": target, "actor": actor, "reason": reason}, self.tenant_id)
            return {"case_id": case_id, "from_status": current, "to_status": target, "actor": actor}

    def case_history(self, case_id: int) -> list[dict]:
        with self.db.connect(self.tenant_id) as conn:
            return [dict(row) for row in conn.execute(
                select(ControlCaseTransition).where(
                    ControlCaseTransition.tenant_id == self.tenant_id,
                    ControlCaseTransition.case_id == case_id,
                ).order_by(ControlCaseTransition.id)
            ).mappings()]
