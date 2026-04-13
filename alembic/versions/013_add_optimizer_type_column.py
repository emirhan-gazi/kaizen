"""Add optimizer_type and gepa_config columns to tasks.

Revision ID: 013
Revises: 012
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "013"
down_revision = "012"


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("optimizer_type", sa.String(), server_default="miprov2", nullable=False),
    )
    op.add_column(
        "tasks",
        sa.Column("gepa_config", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "gepa_config")
    op.drop_column("tasks", "optimizer_type")
