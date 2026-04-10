"""Add mode column to tasks.

Revision ID: 011
Revises: 010
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("mode", sa.String(), server_default="optimize_only", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tasks", "mode")
