"""Dead letters and idempotent consumer receipts.

Revision ID: 20260812_0004
"""
import sqlalchemy as sa
from alembic import op

revision = "20260812_0004"
down_revision = "20260812_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("outbox_events") as batch:
        batch.add_column(sa.Column("last_error", sa.Text()))
        batch.add_column(sa.Column("dead_lettered_at", sa.String(40)))
    op.create_table("dead_letter_events", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("outbox_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("tenant_id", sa.String(64), nullable=False), sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False), sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=False), sa.Column("failed_at", sa.String(40), nullable=False),
        sa.Column("replayed_at", sa.String(40)))
    op.create_index("ix_dead_letter_events_tenant_id", "dead_letter_events", ["tenant_id"])
    op.create_table("consumer_receipts", sa.Column("consumer_name", sa.String(100), primary_key=True),
        sa.Column("event_id", sa.String(100), primary_key=True), sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("processed_at", sa.String(40), nullable=False))
    op.create_index("ix_consumer_receipts_tenant_id", "consumer_receipts", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("consumer_receipts"); op.drop_table("dead_letter_events")
    with op.batch_alter_table("outbox_events") as batch:
        batch.drop_column("dead_lettered_at"); batch.drop_column("last_error")
