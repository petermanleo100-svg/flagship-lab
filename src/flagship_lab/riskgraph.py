from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .core import Database, append_audit_event, canonical_json
from .sql_models import GraphEdge, GraphEntity
from .taxflow import money


@dataclass(frozen=True)
class Entity:
    entity_id: str
    entity_type: str
    attributes: dict


@dataclass(frozen=True)
class Edge:
    source_id: str
    target_id: str
    relation: str
    amount: Decimal | str | int | float
    occurred_at: str
    evidence: dict


class RiskGraphService:
    def __init__(self, db: Database, tenant_id: str = "default"):
        self.db = db
        self.tenant_id = tenant_id

    def add_entities(self, entities: list[Entity]) -> None:
        with self.db.connect() as conn:
            values = [{"tenant_id": self.tenant_id, "entity_id": item.entity_id,
                       "entity_type": item.entity_type, "attributes_json": canonical_json(item.attributes)} for item in entities]
            if values:
                statement = (pg_insert(GraphEntity) if conn.dialect.name == "postgresql" else sqlite_insert(GraphEntity))
                statement = statement.values(values).on_conflict_do_update(
                    index_elements=["tenant_id", "entity_id"],
                    set_={"entity_type": statement.excluded.entity_type, "attributes_json": statement.excluded.attributes_json},
                )
                conn.execute(statement)
            append_audit_event(conn, "riskgraph", "ENTITIES_UPSERTED", "batch", {"count": len(entities)}, self.tenant_id)

    def add_edges(self, edges: list[Edge]) -> None:
        with self.db.connect() as conn:
            if edges:
                conn.execute(insert(GraphEdge), [{
                    "tenant_id": self.tenant_id, "source_id": item.source_id, "target_id": item.target_id,
                    "relation": item.relation, "amount": money(item.amount), "occurred_at": item.occurred_at,
                    "evidence_json": canonical_json(item.evidence),
                } for item in edges])
            append_audit_event(conn, "riskgraph", "EDGES_ADDED", "batch", {"count": len(edges)}, self.tenant_id)

    def investigate(self) -> list[dict]:
        with self.db.connect() as conn:
            entities = {row["entity_id"]: dict(row) for row in conn.execute(
                select(GraphEntity).where(GraphEntity.tenant_id == self.tenant_id)).mappings()}
            edges = [dict(row) for row in conn.execute(
                select(GraphEdge).where(GraphEdge.tenant_id == self.tenant_id)).mappings()]
        findings: list[dict] = []
        account_owners: dict[str, list[str]] = defaultdict(list)
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            if edge["source_id"] not in entities or edge["target_id"] not in entities:
                continue
            adjacency[edge["source_id"]].add(edge["target_id"])
            if edge["relation"] == "OWNS_ACCOUNT":
                account_owners[edge["target_id"]].append(edge["source_id"])
        for account, owners in account_owners.items():
            distinct = sorted(set(owners))
            if len(distinct) > 1:
                findings.append({"risk_code": "SHARED_ACCOUNT", "score": min(100, 55 + 10 * len(distinct)),
                                 "entities": distinct + [account], "explanation": f"账户 {account} 由 {len(distinct)} 个不同实体共同关联",
                                 "evidence": {"owners": distinct}})
        for cycle in self._cycles_of_three(adjacency):
            findings.append({"risk_code": "CIRCULAR_RELATION", "score": 85, "entities": cycle,
                             "explanation": "检测到三节点闭环关系：" + " → ".join(cycle + [cycle[0]]),
                             "evidence": {"cycle": cycle}})
        return sorted(findings, key=lambda item: (-item["score"], item["risk_code"], item["entities"]))

    @staticmethod
    def _cycles_of_three(adjacency: dict[str, set[str]]) -> list[list[str]]:
        canonical: set[tuple[str, str, str]] = set()
        for a, neighbors in adjacency.items():
            for b in neighbors:
                for c in adjacency.get(b, set()):
                    if a != b and b != c and a in adjacency.get(c, set()):
                        canonical.add(min((a, b, c), (b, c, a), (c, a, b)))
        return [list(cycle) for cycle in sorted(canonical)]
