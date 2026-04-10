"""Add feedback_source and auto_eval columns to tasks.

Revision ID: 008
Revises: 007
Create Date: 2026-04-07
"""

import sqlalchemy as sa

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("feedback_source", sa.String(), server_default="sdk", nullable=False),
    )
    op.add_column(
        "tasks",
        sa.Column("auto_eval", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tasks", "auto_eval")
    op.drop_column("tasks", "feedback_source")
