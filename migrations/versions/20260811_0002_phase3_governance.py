"""Add Phase 3 governance workflow tables.

Revision ID: 20260811_0002
"""

import sqlalchemy as sa
from alembic import op


revision = "20260811_0002"
down_revision = "20260811_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "tax_run_workflow" not in tables:
        op.create_table(
            "tax_run_workflow",
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.Column("requested_by", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="PENDING_REVIEW"),
            sa.Column("reviewed_by", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.Text(), nullable=True),
            sa.Column("decision_comment", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["run_id"], ["tax_rule_runs.run_id"]),
            sa.PrimaryKeyConstraint("run_id"),
        )
    if "control_case_transitions" not in tables:
        op.create_table(
            "control_case_transitions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("case_id", sa.Integer(), nullable=False),
            sa.Column("from_status", sa.Text(), nullable=False),
            sa.Column("to_status", sa.Text(), nullable=False),
            sa.Column("actor", sa.Text(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("occurred_at", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["case_id"], ["control_cases.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_control_case_transitions_case",
            "control_case_transitions",
            ["case_id", "id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "control_case_transitions" in tables:
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("control_case_transitions")}
        if "idx_control_case_transitions_case" in indexes:
            op.drop_index("idx_control_case_transitions_case", table_name="control_case_transitions")
        op.drop_table("control_case_transitions")
    if "tax_run_workflow" in tables:
        op.drop_table("tax_run_workflow")
