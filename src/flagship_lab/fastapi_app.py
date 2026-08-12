from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
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


class ReviewDecisionIn(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    comment: str = Field(min_length=3, max_length=500)


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


class ControlTransitionIn(BaseModel):
    to_status: str = Field(pattern="^(OPEN|IN_REVIEW|REMEDIATED|CLOSED)$")
    reason: str = Field(min_length=3, max_length=500)


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


def create_app(
    db_path: str,
    jwt_secret: str,
    allow_dev_tokens: bool = False,
    evidence_signing_secret: str | None = None,
) -> FastAPI:
    if len(jwt_secret) < 32:
        raise ValueError("jwt_secret must contain at least 32 characters")
    signing_secret = evidence_signing_secret or jwt_secret
    if len(signing_secret) < 32:
        raise ValueError("evidence_signing_secret must contain at least 32 characters")
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
        version="0.3.0",
        description="Auditable tax technology, regulatory intelligence, IT controls, and graph risk API.",
    )

    @app.middleware("http")
    async def request_trace(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Server-Timing"] = f"app;dur={(perf_counter() - started) * 1000:.2f}"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.3.0", "modules": ["taxflow", "regintel", "controlpulse", "riskgraph"]}

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
        result["workflow"] = tax.request_review(result["run_id"], claims["sub"])
        return result

    @app.post("/tax/runs/{run_id}/review")
    def review_tax_run(run_id: str, request: ReviewDecisionIn, claims: dict = Depends(can_review)):
        try:
            return tax.review_run(run_id, claims["sub"], request.decision, request.comment)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/tax/findings")
    def tax_findings(run_id: str, claims: dict = Depends(can_view)):
        return tax.findings(run_id)

    @app.get("/evidence/tax/{run_id}", response_class=FileResponse)
    def tax_evidence(run_id: str, claims: dict = Depends(can_review)):
        output = Path(db.path).parent / "evidence" / f"tax-{run_id}.zip"
        try:
            workflow = tax.workflow(run_id)
            if workflow is None or workflow["status"] != "APPROVED":
                raise HTTPException(status_code=409, detail="tax run requires independent approval")
            with db.connect() as conn:
                export_tax_run(conn, run_id, output, signing_secret=signing_secret, key_id="flagship-api-hmac-v1")
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

    @app.post("/controls/cases/{case_id}/transition")
    def transition_control_case(
        case_id: int, request: ControlTransitionIn, claims: dict = Depends(can_review)
    ):
        try:
            return controls.transition_case(case_id, claims["sub"], request.to_status, request.reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/controls/cases/{case_id}/history")
    def control_case_history(case_id: int, claims: dict = Depends(can_review)):
        return controls.case_history(case_id)

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
        return {
            "jwt_secret_configured": True,
            "evidence_signing_key_separated": evidence_signing_secret is not None and signing_secret != jwt_secret,
            "development_tokens_enabled": allow_dev_tokens,
        }

    return app
