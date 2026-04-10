"""Add prompt_file and prompt_locator columns to tasks.

Revision ID: 007
Revises: 006
Create Date: 2026-04-07
"""

import sqlalchemy as sa

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("prompt_file", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("prompt_locator", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "prompt_locator")
    op.drop_column("tasks", "prompt_file")
