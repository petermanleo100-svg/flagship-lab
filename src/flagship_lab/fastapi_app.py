from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .auth import issue_token, require_roles
from .controlpulse import ControlEvent, ControlPulseService
from .core import Database, verify_audit_chain
from .evidence import export_tax_run
from .regintel import RegIntelService
from .riskgraph import Edge, Entity, RiskGraphService
from .taxflow import TaxFlowService, TaxTransaction


class TokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    roles: list[str]
    ttl_minutes: int = Field(default=60, ge=1, le=480)


class TaxTransactionIn(BaseModel):
    invoice_id: str = Field(min_length=1, max_length=100)
    seller_tax_id: str | None = None
    buyer_tax_id: str | None = None
    invoice_date: str
    amount: float = Field(ge=0)
    tax_rate: float = Field(ge=0, le=1)
    tax_amount: float = Field(ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)


class RuleRunRequest(BaseModel):
    rule_version: str | None = None
    rule_pack: dict[str, Any] | None = None


class RegulationDocumentIn(BaseModel):
    document_key: str
    title: str
    source_url: str
    published_at: str
    content: str = Field(min_length=1)


class QueryIn(BaseModel):
    query: str = Field(min_length=1)


class ControlEventIn(BaseModel):
    event_id: str
    event_type: str
    actor: str
    resource: str
    occurred_at: str
    approved: bool
    privileged: bool
    outcome: str
    payload: dict[str, Any] = Field(default_factory=dict)


class EntityIn(BaseModel):
    entity_id: str
    entity_type: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class EdgeIn(BaseModel):
    source_id: str
    target_id: str
    relation: str
    amount: float = 0
    occurred_at: str
    evidence: dict[str, Any] = Field(default_factory=dict)


def create_app(db_path: str, jwt_secret: str, allow_dev_tokens: bool = False) -> FastAPI:
    if len(jwt_secret) < 32:
        raise ValueError("jwt_secret must contain at least 32 characters")
    db = Database(db_path)
    db.initialize()
    tax = TaxFlowService(db)
    reg = RegIntelService(db)
    controls = ControlPulseService(db)
    graph = RiskGraphService(db)

    can_view = require_roles(jwt_secret, "viewer", "analyst", "reviewer", "admin")
    can_analyze = require_roles(jwt_secret, "analyst", "admin")
    can_review = require_roles(jwt_secret, "reviewer", "admin")
    admin_only = require_roles(jwt_secret, "admin")

    app = FastAPI(
        title="Flagship Lab API",
        version="0.2.0",
        description="Auditable tax technology, regulatory intelligence, IT controls, and graph risk API.",
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.2.0", "modules": ["taxflow", "regintel", "controlpulse", "riskgraph"]}

    @app.post("/auth/dev-token")
    def dev_token(request: TokenRequest):
        if not allow_dev_tokens:
            raise HTTPException(status_code=404, detail="development token endpoint disabled")
        return {"access_token": issue_token(request.subject, request.roles, jwt_secret, request.ttl_minutes), "token_type": "bearer"}

    @app.post("/tax/transactions", status_code=201)
    def ingest_tax(items: list[TaxTransactionIn], claims: dict = Depends(can_analyze)):
        count = tax.ingest([TaxTransaction(**item.model_dump()) for item in items])
        return {"ingested": count, "actor": claims["sub"]}

    @app.post("/tax/runs", status_code=201)
    def run_tax(request: RuleRunRequest, claims: dict = Depends(can_analyze)):
        result = tax.run_rules(request.rule_version, request.rule_pack)
        result["actor"] = claims["sub"]
        return result

    @app.get("/tax/findings")
    def tax_findings(run_id: str, claims: dict = Depends(can_view)):
        return tax.findings(run_id)

    @app.get("/evidence/tax/{run_id}", response_class=FileResponse)
    def tax_evidence(run_id: str, claims: dict = Depends(can_review)):
        output = Path(db.path).parent / "evidence" / f"tax-{run_id}.zip"
        try:
            with db.connect() as conn:
                export_tax_run(conn, run_id, output)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return FileResponse(output, media_type="application/zip", filename=output.name)

    @app.post("/reg/documents", status_code=201)
    def add_reg_document(request: RegulationDocumentIn, claims: dict = Depends(can_analyze)):
        return {"version_hash": reg.add_document(**request.model_dump()), "actor": claims["sub"]}

    @app.post("/reg/answer")
    def answer_reg(request: QueryIn, claims: dict = Depends(can_view)):
        return reg.answer(request.query)

    @app.post("/controls/events", status_code=201)
    def add_control_event(request: ControlEventIn, claims: dict = Depends(can_analyze)):
        return {"cases": controls.ingest_and_evaluate(ControlEvent(**request.model_dump())), "actor": claims["sub"]}

    @app.get("/controls/cases")
    def control_cases(claims: dict = Depends(can_review)):
        return controls.open_cases()

    @app.post("/graph/entities", status_code=201)
    def add_entities(items: list[EntityIn], claims: dict = Depends(can_analyze)):
        graph.add_entities([Entity(**item.model_dump()) for item in items])
        return {"upserted": len(items), "actor": claims["sub"]}

    @app.post("/graph/edges", status_code=201)
    def add_edges(items: list[EdgeIn], claims: dict = Depends(can_analyze)):
        graph.add_edges([Edge(**item.model_dump()) for item in items])
        return {"inserted": len(items), "actor": claims["sub"]}

    @app.get("/graph/findings")
    def graph_findings(claims: dict = Depends(can_view)):
        return graph.investigate()

    @app.get("/audit/verify")
    def audit_verify(claims: dict = Depends(can_review)):
        with db.connect() as conn:
            valid, count, broken = verify_audit_chain(conn)
        return {"valid": valid, "events": count, "broken_hash": broken}

    @app.get("/admin/config-check")
    def config_check(claims: dict = Depends(admin_only)):
        return {"jwt_secret_configured": True, "development_tokens_enabled": allow_dev_tokens}

    return app

