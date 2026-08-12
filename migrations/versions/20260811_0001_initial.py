"""Frozen initial schema.

Revision ID: 20260811_0001
"""

import sqlalchemy as sa
from alembic import op

revision = "20260811_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("audit_events", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("module", sa.String(50), nullable=False), sa.Column("event_type", sa.String(100), nullable=False),
                    sa.Column("entity_id", sa.String(100), nullable=False), sa.Column("occurred_at", sa.String(40), nullable=False),
                    sa.Column("payload_json", sa.Text(), nullable=False), sa.Column("previous_hash", sa.String(64), nullable=False),
                    sa.Column("event_hash", sa.String(64), nullable=False, unique=True))
    op.create_table("tax_transactions", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("invoice_id", sa.String(100), nullable=False), sa.Column("seller_tax_id", sa.String(100)),
                    sa.Column("buyer_tax_id", sa.String(100)), sa.Column("invoice_date", sa.String(20), nullable=False),
                    sa.Column("amount", sa.Float(), nullable=False), sa.Column("tax_rate", sa.Float(), nullable=False),
                    sa.Column("tax_amount", sa.Float(), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
                    sa.Column("source_hash", sa.String(64), nullable=False), sa.Column("ingested_at", sa.String(40), nullable=False))
    op.create_index("ix_tax_transactions_invoice_id", "tax_transactions", ["invoice_id"])
    op.create_table("tax_rule_runs", sa.Column("run_id", sa.String(36), primary_key=True),
                    sa.Column("rule_version", sa.String(100), nullable=False), sa.Column("started_at", sa.String(40), nullable=False),
                    sa.Column("completed_at", sa.String(40)), sa.Column("transaction_count", sa.Integer(), nullable=False),
                    sa.Column("finding_count", sa.Integer(), nullable=False))
    op.create_table("tax_findings", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("run_id", sa.String(36), sa.ForeignKey("tax_rule_runs.run_id"), nullable=False),
                    sa.Column("transaction_id", sa.Integer()), sa.Column("invoice_id", sa.String(100), nullable=False),
                    sa.Column("rule_code", sa.String(100), nullable=False), sa.Column("severity", sa.String(20), nullable=False),
                    sa.Column("explanation", sa.Text(), nullable=False), sa.Column("evidence_json", sa.Text(), nullable=False))
    op.create_table("regulation_documents", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("document_key", sa.String(100), nullable=False), sa.Column("title", sa.String(300), nullable=False),
                    sa.Column("source_url", sa.Text(), nullable=False), sa.Column("published_at", sa.String(20), nullable=False),
                    sa.Column("version_hash", sa.String(64), nullable=False), sa.Column("content", sa.Text(), nullable=False))
    op.create_index("uq_reg_doc_version", "regulation_documents", ["document_key", "version_hash"], unique=True)
    op.create_table("control_events", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("event_id", sa.String(100), nullable=False, unique=True),
                    sa.Column("event_type", sa.String(100), nullable=False), sa.Column("actor", sa.String(100), nullable=False),
                    sa.Column("resource", sa.String(200), nullable=False), sa.Column("occurred_at", sa.String(40), nullable=False),
                    sa.Column("approved", sa.Integer(), nullable=False), sa.Column("privileged", sa.Integer(), nullable=False),
                    sa.Column("outcome", sa.String(50), nullable=False), sa.Column("payload_json", sa.Text(), nullable=False),
                    sa.Column("evidence_hash", sa.String(64), nullable=False))
    op.create_table("control_cases", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("event_id", sa.String(100), nullable=False), sa.Column("control_id", sa.String(100), nullable=False),
                    sa.Column("severity", sa.String(20), nullable=False), sa.Column("explanation", sa.Text(), nullable=False),
                    sa.Column("evidence_hash", sa.String(64), nullable=False),
                    sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"))
    op.create_table("graph_entities", sa.Column("entity_id", sa.String(100), nullable=False),
                    sa.Column("entity_type", sa.String(50), nullable=False), sa.Column("attributes_json", sa.Text(), nullable=False),
                    sa.PrimaryKeyConstraint("entity_id", name="pk_graph_entities"))
    op.create_table("graph_edges", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("source_id", sa.String(100), nullable=False), sa.Column("target_id", sa.String(100), nullable=False),
                    sa.Column("relation", sa.String(100), nullable=False), sa.Column("amount", sa.Float(), nullable=False),
                    sa.Column("occurred_at", sa.String(40), nullable=False), sa.Column("evidence_json", sa.Text(), nullable=False))
    op.create_index("ix_graph_edges_source_id", "graph_edges", ["source_id"])
    op.create_index("ix_graph_edges_target_id", "graph_edges", ["target_id"])


def downgrade() -> None:
    for table in ("graph_edges", "graph_entities", "control_cases", "control_events", "regulation_documents",
                  "tax_findings", "tax_rule_runs", "tax_transactions", "audit_events"):
        op.drop_table(table)
