from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class TaxTransactionRow(Base):
    __tablename__ = "tax_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    seller_tax_id: Mapped[str | None] = mapped_column(String(100))
    buyer_tax_id: Mapped[str | None] = mapped_column(String(100))
    invoice_date: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    tax_rate: Mapped[float] = mapped_column(Float, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[str] = mapped_column(String(40), nullable=False)


class TaxRuleRun(Base):
    __tablename__ = "tax_rule_runs"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_version: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[str] = mapped_column(String(40), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(40))
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TaxFinding(Base):
    __tablename__ = "tax_findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("tax_rule_runs.run_id"), nullable=False)
    transaction_id: Mapped[int | None] = mapped_column(Integer)
    invoice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)


class RegulationDocument(Base):
    __tablename__ = "regulation_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[str] = mapped_column(String(20), nullable=False)
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (Index("uq_reg_doc_version", "document_key", "version_hash", unique=True),)


class ControlEventRow(Base):
    __tablename__ = "control_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[str] = mapped_column(String(200), nullable=False)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    approved: Mapped[int] = mapped_column(Integer, nullable=False)
    privileged: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ControlCase(Base):
    __tablename__ = "control_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    control_id: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")


class GraphEntity(Base):
    __tablename__ = "graph_entities"
    entity_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    attributes_json: Mapped[str] = mapped_column(Text, nullable=False)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    relation: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)

