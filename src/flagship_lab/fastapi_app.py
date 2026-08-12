from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .auth import HMACTokenVerifier, TokenVerifier, issue_token, require_verified_roles
from .controlpulse import ControlEvent, ControlPulseService
from .core import Database, database_health, verify_audit_chain
from .evidence import export_tax_run
from .regintel import RegIntelService
from .riskgraph import Edge, Entity, RiskGraphService
from .taxflow import TaxFlowService, TaxTransaction


class TokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    tenant_id: str = Field(default="default", min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    roles: list[str]
    ttl_minutes: int = Field(default=60, ge=1, le=480)


class TaxTransactionIn(BaseModel):
    invoice_id: str = Field(min_length=1, max_length=100)
    seller_tax_id: str | None = None
    buyer_tax_id: str | None = None
    invoice_date: str
    amount: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    tax_rate: Decimal = Field(ge=0, le=1, max_digits=9, decimal_places=6)
    tax_amount: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
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
    amount: Decimal = Decimal("0")
    occurred_at: str
    evidence: dict[str, Any] = Field(default_factory=dict)


def create_app(
    db_path: str,
    jwt_secret: str,
    allow_dev_tokens: bool = False,
    evidence_signing_secret: str | None = None,
    token_verifier: TokenVerifier | None = None,
    evidence_signing_private_key_pem: str | bytes | None = None,
) -> FastAPI:
    if len(jwt_secret) < 32:
        raise ValueError("jwt_secret must contain at least 32 characters")
    signing_secret = evidence_signing_secret or jwt_secret
    if len(signing_secret) < 32:
        raise ValueError("evidence_signing_secret must contain at least 32 characters")
    db = Database(db_path)
    db.initialize()
    verifier = token_verifier or HMACTokenVerifier(jwt_secret)
    can_view = require_verified_roles(verifier, "viewer", "analyst", "reviewer", "admin")
    can_analyze = require_verified_roles(verifier, "analyst", "admin")
    can_review = require_verified_roles(verifier, "reviewer", "admin")
    admin_only = require_verified_roles(verifier, "admin")

    app = FastAPI(
        title="Flagship Lab API",
        version="0.4.0",
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

    @app.get("/health/live")
    def liveness():
        return {"status": "ok", "version": "0.4.0"}

    @app.get("/health/ready")
    def readiness():
        try:
            return {"status": "ready", "version": "0.4.0", **database_health(db)}
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"status": "not_ready", "dependency": "database"}) from exc

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.4.0", "modules": ["taxflow", "regintel", "controlpulse", "riskgraph"]}

    @app.post("/auth/dev-token")
    def dev_token(request: TokenRequest):
        if not allow_dev_tokens:
            raise HTTPException(status_code=404, detail="development token endpoint disabled")
        return {"access_token": issue_token(request.subject, request.roles, jwt_secret, request.ttl_minutes,
                                              request.tenant_id), "token_type": "bearer"}

    @app.post("/tax/transactions", status_code=201)
    def ingest_tax(items: list[TaxTransactionIn], claims: dict = Depends(can_analyze),
                   idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        tax = TaxFlowService(db, claims["tenant_id"])
        try:
            count = tax.ingest([TaxTransaction(**item.model_dump()) for item in items], idempotency_key)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ingested": count, "actor": claims["sub"]}

    @app.post("/tax/runs", status_code=201)
    def run_tax(request: RuleRunRequest, claims: dict = Depends(can_analyze),
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        tax = TaxFlowService(db, claims["tenant_id"])
        try:
            result = tax.run_rules(request.rule_version, request.rule_pack, idempotency_key)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        result["actor"] = claims["sub"]
        workflow = tax.workflow(result["run_id"])
        result["workflow"] = workflow or tax.request_review(result["run_id"], claims["sub"])
        return result

    @app.post("/tax/runs/{run_id}/review")
    def review_tax_run(run_id: str, request: ReviewDecisionIn, claims: dict = Depends(can_review)):
        tax = TaxFlowService(db, claims["tenant_id"])
        try:
            return tax.review_run(run_id, claims["sub"], request.decision, request.comment)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/tax/findings")
    def tax_findings(run_id: str, claims: dict = Depends(can_view)):
        tax = TaxFlowService(db, claims["tenant_id"])
        return tax.findings(run_id)

    @app.get("/evidence/tax/{run_id}", response_class=FileResponse)
    def tax_evidence(run_id: str, claims: dict = Depends(can_review)):
        tax = TaxFlowService(db, claims["tenant_id"])
        output = Path("work/evidence") / claims["tenant_id"] / f"tax-{run_id}.zip"
        try:
            workflow = tax.workflow(run_id)
            if workflow is None or workflow["status"] != "APPROVED":
                raise HTTPException(status_code=409, detail="tax run requires independent approval")
            with db.connect() as conn:
                export_tax_run(conn, run_id, output, signing_secret=signing_secret,
                               key_id="flagship-api-signing-v1", tenant_id=claims["tenant_id"],
                               signing_private_key_pem=evidence_signing_private_key_pem)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return FileResponse(output, media_type="application/zip", filename=output.name)

    @app.post("/reg/documents", status_code=201)
    def add_reg_document(request: RegulationDocumentIn, claims: dict = Depends(can_analyze)):
        reg = RegIntelService(db, claims["tenant_id"])
        return {"version_hash": reg.add_document(**request.model_dump()), "actor": claims["sub"]}

    @app.post("/reg/answer")
    def answer_reg(request: QueryIn, claims: dict = Depends(can_view)):
        reg = RegIntelService(db, claims["tenant_id"])
        return reg.answer(request.query)

    @app.post("/controls/events", status_code=201)
    def add_control_event(request: ControlEventIn, claims: dict = Depends(can_analyze)):
        controls = ControlPulseService(db, claims["tenant_id"])
        return {"cases": controls.ingest_and_evaluate(ControlEvent(**request.model_dump())), "actor": claims["sub"]}

    @app.get("/controls/cases")
    def control_cases(claims: dict = Depends(can_review)):
        controls = ControlPulseService(db, claims["tenant_id"])
        return controls.open_cases()

    @app.post("/controls/cases/{case_id}/transition")
    def transition_control_case(
        case_id: int, request: ControlTransitionIn, claims: dict = Depends(can_review)
    ):
        controls = ControlPulseService(db, claims["tenant_id"])
        try:
            return controls.transition_case(case_id, claims["sub"], request.to_status, request.reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/controls/cases/{case_id}/history")
    def control_case_history(case_id: int, claims: dict = Depends(can_review)):
        controls = ControlPulseService(db, claims["tenant_id"])
        return controls.case_history(case_id)

    @app.post("/graph/entities", status_code=201)
    def add_entities(items: list[EntityIn], claims: dict = Depends(can_analyze)):
        graph = RiskGraphService(db, claims["tenant_id"])
        graph.add_entities([Entity(**item.model_dump()) for item in items])
        return {"upserted": len(items), "actor": claims["sub"]}

    @app.post("/graph/edges", status_code=201)
    def add_edges(items: list[EdgeIn], claims: dict = Depends(can_analyze)):
        graph = RiskGraphService(db, claims["tenant_id"])
        graph.add_edges([Edge(**item.model_dump()) for item in items])
        return {"inserted": len(items), "actor": claims["sub"]}

    @app.get("/graph/findings")
    def graph_findings(claims: dict = Depends(can_view)):
        graph = RiskGraphService(db, claims["tenant_id"])
        return graph.investigate()

    @app.get("/audit/verify")
    def audit_verify(claims: dict = Depends(can_review)):
        with db.connect() as conn:
            valid, count, broken = verify_audit_chain(conn, claims["tenant_id"])
        return {"valid": valid, "events": count, "broken_hash": broken}

    @app.get("/admin/config-check")
    def config_check(claims: dict = Depends(admin_only)):
        return {
            "jwt_secret_configured": True,
            "evidence_signing_key_separated": evidence_signing_secret is not None and signing_secret != jwt_secret,
            "development_tokens_enabled": allow_dev_tokens,
            "external_token_verifier": token_verifier is not None,
            "asymmetric_evidence_signing": evidence_signing_private_key_pem is not None,
        }

    return app
