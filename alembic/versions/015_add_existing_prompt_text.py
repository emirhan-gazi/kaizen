"""Add existing_prompt_text column to tasks for local prompt seeding.

Revision ID: 015
Revises: 014
"""

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("existing_prompt_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "existing_prompt_text")
