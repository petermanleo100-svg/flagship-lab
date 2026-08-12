"""Tenant, precision, concurrency, idempotency and outbox foundation.

Revision ID: 20260812_0003
"""

import sqlalchemy as sa
from alembic import op

revision = "20260812_0003"
down_revision = "20260811_0002"
branch_labels = None
depends_on = None

TENANT_TABLES = ("audit_events", "tax_transactions", "tax_rule_runs", "tax_findings", "tax_run_workflow",
                 "regulation_documents", "control_events", "control_cases", "control_case_transitions",
                 "graph_entities", "graph_edges")


def upgrade() -> None:
    for table in TENANT_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"))
    with op.batch_alter_table("tax_transactions") as batch:
        batch.alter_column("amount", type_=sa.Numeric(20, 4), existing_type=sa.Float())
        batch.alter_column("tax_rate", type_=sa.Numeric(9, 6), existing_type=sa.Float())
        batch.alter_column("tax_amount", type_=sa.Numeric(20, 4), existing_type=sa.Float())
        batch.create_index("ix_tax_tenant_invoice", ["tenant_id", "invoice_id"])
    with op.batch_alter_table("tax_rule_runs") as batch:
        batch.add_column(sa.Column("rule_pack_json", sa.Text(), nullable=False, server_default="{}"))
    with op.batch_alter_table("tax_run_workflow") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    with op.batch_alter_table("control_cases") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    with op.batch_alter_table("graph_edges") as batch:
        batch.alter_column("amount", type_=sa.Numeric(20, 4), existing_type=sa.Float())
        batch.create_index("ix_graph_tenant_source", ["tenant_id", "source_id"])
        batch.create_index("ix_graph_tenant_target", ["tenant_id", "target_id"])
    with op.batch_alter_table("graph_entities") as batch:
        batch.drop_constraint("pk_graph_entities", type_="primary")
        batch.create_primary_key("pk_graph_entities", ["tenant_id", "entity_id"])
    op.create_index("ix_audit_tenant_id", "audit_events", ["tenant_id", "id"])
    op.create_index("ix_tax_findings_tenant_run", "tax_findings", ["tenant_id", "run_id"])
    op.create_index("ix_control_transition_tenant_case", "control_case_transitions", ["tenant_id", "case_id", "id"])
    op.create_table("idempotency_records",
                    sa.Column("tenant_id", sa.String(64), primary_key=True),
                    sa.Column("operation", sa.String(100), primary_key=True),
                    sa.Column("idempotency_key", sa.String(100), primary_key=True),
                    sa.Column("request_hash", sa.String(64), nullable=False), sa.Column("response_json", sa.Text(), nullable=False),
                    sa.Column("status_code", sa.Integer(), nullable=False), sa.Column("created_at", sa.String(40), nullable=False))
    op.create_table("outbox_events", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("tenant_id", sa.String(64), nullable=False), sa.Column("topic", sa.String(100), nullable=False),
                    sa.Column("aggregate_id", sa.String(100), nullable=False), sa.Column("payload_json", sa.Text(), nullable=False),
                    sa.Column("created_at", sa.String(40), nullable=False), sa.Column("published_at", sa.String(40)),
                    sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_outbox_events_tenant_id", "outbox_events", ["tenant_id"])
    op.create_index("ix_outbox_unpublished", "outbox_events", ["published_at", "id"])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("idempotency_records")
    for table in reversed(TENANT_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("tenant_id")
