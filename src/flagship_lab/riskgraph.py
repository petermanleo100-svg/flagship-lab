from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .core import Database, append_audit_event, canonical_json


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
    amount: float
    occurred_at: str
    evidence: dict


class RiskGraphService:
    def __init__(self, db: Database):
        self.db = db

    def add_entities(self, entities: list[Entity]) -> None:
        with self.db.connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO graph_entities(entity_id,entity_type,attributes_json) VALUES (?,?,?)",
                [(e.entity_id, e.entity_type, canonical_json(e.attributes)) for e in entities],
            )
            append_audit_event(conn, "riskgraph", "ENTITIES_UPSERTED", "batch", {"count": len(entities)})

    def add_edges(self, edges: list[Edge]) -> None:
        with self.db.connect() as conn:
            conn.executemany(
                """INSERT INTO graph_edges(source_id,target_id,relation,amount,occurred_at,evidence_json)
                   VALUES (?,?,?,?,?,?)""",
                [(e.source_id, e.target_id, e.relation, e.amount, e.occurred_at, canonical_json(e.evidence)) for e in edges],
            )
            append_audit_event(conn, "riskgraph", "EDGES_ADDED", "batch", {"count": len(edges)})

    def investigate(self) -> list[dict]:
        with self.db.connect() as conn:
            entities = {row["entity_id"]: dict(row) for row in conn.execute("SELECT * FROM graph_entities")}
            edges = [dict(row) for row in conn.execute("SELECT * FROM graph_edges")]
        findings: list[dict] = []
        account_owners: dict[str, list[str]] = defaultdict(list)
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            adjacency[edge["source_id"]].add(edge["target_id"])
            if edge["relation"] == "OWNS_ACCOUNT":
                account_owners[edge["target_id"]].append(edge["source_id"])
        for account, owners in account_owners.items():
            distinct = sorted(set(owners))
            if len(distinct) > 1:
                findings.append({
                    "risk_code": "SHARED_ACCOUNT",
                    "score": min(100, 55 + 10 * len(distinct)),
                    "entities": distinct + [account],
                    "explanation": f"账户{account}由{len(distinct)}个不同实体共同关联",
                    "evidence": {"owners": distinct},
                })
        cycles = self._cycles_of_three(adjacency)
        for cycle in cycles:
            findings.append({
                "risk_code": "CIRCULAR_RELATION",
                "score": 85,
                "entities": cycle,
                "explanation": "检测到三节点闭环关系：" + " → ".join(cycle + [cycle[0]]),
                "evidence": {"cycle": cycle},
            })
        return sorted(findings, key=lambda x: (-x["score"], x["risk_code"], x["entities"]))

    @staticmethod
    def _cycles_of_three(adjacency: dict[str, set[str]]) -> list[list[str]]:
        canonical: set[tuple[str, str, str]] = set()
        for a, neighbors in adjacency.items():
            for b in neighbors:
                for c in adjacency.get(b, set()):
                    if a != b and b != c and a in adjacency.get(c, set()):
                        rotations = [(a, b, c), (b, c, a), (c, a, b)]
                        canonical.add(min(rotations))
        return [list(cycle) for cycle in sorted(canonical)]
