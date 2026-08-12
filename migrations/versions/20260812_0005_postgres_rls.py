"""PostgreSQL tenant row-level security.

Revision ID: 20260812_0005
"""
from alembic import op

revision = "20260812_0005"
down_revision = "20260812_0004"
branch_labels = None
depends_on = None

TABLES = ("audit_events", "tax_transactions", "tax_rule_runs", "tax_findings", "tax_run_workflow",
          "regulation_documents", "control_events", "control_cases", "control_case_transitions",
          "graph_entities", "graph_edges", "idempotency_records", "outbox_events", "dead_letter_events",
          "consumer_receipts")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'''CREATE POLICY tenant_isolation ON "{table}"
            USING (tenant_id = current_setting('flagship.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('flagship.tenant_id', true))''')


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in reversed(TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
