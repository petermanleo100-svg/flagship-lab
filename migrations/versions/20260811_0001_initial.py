"""Initial portable schema.

Revision ID: 20260811_0001
"""

from alembic import op

from flagship_lab.sql_models import Base


revision = "20260811_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

