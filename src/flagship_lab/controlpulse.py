from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from .core import Database, append_audit_event, canonical_json, sha256_json, utc_now


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
    def __init__(self, db: Database):
        self.db = db

    def ingest_and_evaluate(self, event: ControlEvent) -> list[dict]:
        evidence_hash = sha256_json(asdict(event))
        cases = self._evaluate(event, evidence_hash)
        with self.db.connect() as conn:
            existing = conn.execute("SELECT event_id FROM control_events WHERE event_id=?", (event.event_id,)).fetchone()
            if existing:
                return [dict(row) for row in conn.execute(
                    "SELECT control_id,severity,explanation,evidence_hash FROM control_cases WHERE event_id=? ORDER BY id",
                    (event.event_id,),
                )]
            conn.execute(
                """INSERT INTO control_events
                   (event_id,event_type,actor,resource,occurred_at,approved,privileged,outcome,payload_json,evidence_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    event.event_id, event.event_type, event.actor, event.resource, event.occurred_at,
                    int(event.approved), int(event.privileged), event.outcome, canonical_json(event.payload), evidence_hash,
                ),
            )
            conn.executemany(
                """INSERT INTO control_cases(event_id,control_id,severity,explanation,evidence_hash)
                   VALUES (?,?,?,?,?)""",
                [(event.event_id, c["control_id"], c["severity"], c["explanation"], evidence_hash) for c in cases],
            )
            append_audit_event(
                conn, "controlpulse", "EVENT_EVALUATED", event.event_id,
                {"evidence_hash": evidence_hash, "case_count": len(cases)},
            )
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
        with self.db.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM control_cases WHERE status!='CLOSED' ORDER BY id")]

    def transition_case(self, case_id: int, actor: str, to_status: str, reason: str) -> dict:
        allowed = {
            "OPEN": {"IN_REVIEW"},
            "IN_REVIEW": {"REMEDIATED"},
            "REMEDIATED": {"CLOSED"},
            "CLOSED": {"OPEN"},
        }
        target = to_status.upper()
        if not reason.strip():
            raise ValueError("transition reason is required")
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT c.*, e.actor AS event_actor
                   FROM control_cases c JOIN control_events e ON e.event_id=c.event_id
                   WHERE c.id=?""",
                (case_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown case_id")
            current = row["status"]
            if target not in allowed.get(current, set()):
                raise ValueError(f"invalid transition {current}->{target}")
            if target == "CLOSED" and actor == row["event_actor"]:
                raise ValueError("four-eyes control requires an independent closer")
            occurred_at = utc_now()
            conn.execute("UPDATE control_cases SET status=? WHERE id=?", (target, case_id))
            conn.execute(
                """INSERT INTO control_case_transitions
                   (case_id,from_status,to_status,actor,reason,occurred_at)
                   VALUES (?,?,?,?,?,?)""",
                (case_id, current, target, actor, reason, occurred_at),
            )
            append_audit_event(
                conn,
                "controlpulse",
                "CASE_TRANSITIONED",
                str(case_id),
                {"from": current, "to": target, "actor": actor, "reason": reason},
            )
            return {"case_id": case_id, "from_status": current, "to_status": target, "actor": actor}

    def case_history(self, case_id: int) -> list[dict]:
        with self.db.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM control_case_transitions WHERE case_id=? ORDER BY id", (case_id,)
                )
            ]
