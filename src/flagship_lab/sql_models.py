from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


TENANT_LENGTH = 64
MONEY = Numeric(20, 4)
RATE = Numeric(9, 6)


class Base(DeclarativeBase):
    pass


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, default="default", index=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_hash", name="uq_audit_tenant_hash"),
        Index("ix_audit_tenant_id", "tenant_id", "id"),
    )


class TaxTransactionRow(Base):
    __tablename__ = "tax_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, default="default", index=True)
    invoice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    seller_tax_id: Mapped[str | None] = mapped_column(String(100))
    buyer_tax_id: Mapped[str | None] = mapped_column(String(100))
    invoice_date: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[str] = mapped_column(String(40), nullable=False)
    __table_args__ = (Index("ix_tax_tenant_invoice", "tenant_id", "invoice_id"),)


class TaxRuleRun(Base):
    __tablename__ = "tax_rule_runs"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, default="default", index=True)
    rule_version: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_pack_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[str] = mapped_column(String(40), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(40))
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TaxFinding(Base):
    __tablename__ = "tax_findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, default="default", index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("tax_rule_runs.run_id", ondelete="CASCADE"), nullable=False)
    transaction_id: Mapped[int | None] = mapped_column(Integer)
    invoice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (Index("ix_tax_findings_tenant_run", "tenant_id", "run_id"),)


class TaxRunWorkflow(Base):
    __tablename__ = "tax_run_workflow"
    run_id: Mapped[str] = mapped_column(ForeignKey("tax_rule_runs.run_id", ondelete="CASCADE"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, default="default", index=True)
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING_REVIEW")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[str | None] = mapped_column(String(40))
    decision_comment: Mapped[str | None] = mapped_column(Text)


class RegulationDocument(Base):
    __tablename__ = "regulation_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, default="default", index=True)
    document_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[str] = mapped_column(String(20), nullable=False)
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "document_key", "version_hash", name="uq_reg_tenant_version"),)


class ControlEventRow(Base):
    __tablename__ = "control_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, default="default", index=True)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[str] = mapped_column(String(200), nullable=False)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    approved: Mapped[int] = mapped_column(Integer, nullable=False)
    privileged: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "event_id", name="uq_control_event_tenant"),)


class ControlCase(Base):
    __tablename__ = "control_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, default="default", index=True)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    control_id: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ControlCaseTransition(Base):
    __tablename__ = "control_case_transitions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, default="default", index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("control_cases.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    __table_args__ = (Index("ix_control_transition_tenant_case", "tenant_id", "case_id", "id"),)


class GraphEntity(Base):
    __tablename__ = "graph_entities"
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True, default="default")
    entity_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    attributes_json: Mapped[str] = mapped_column(Text, nullable=False)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, default="default", index=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    relation: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        Index("ix_graph_tenant_source", "tenant_id", "source_id"),
        Index("ix_graph_tenant_target", "tenant_id", "target_id"),
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), primary_key=True)
    operation: Mapped[str] = mapped_column(String(100), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(TENANT_LENGTH), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    published_at: Mapped[str | None] = mapped_column(String(40))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (Index("ix_outbox_unpublished", "published_at", "id"),)
