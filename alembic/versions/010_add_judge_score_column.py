"""Add judge_score column to prompt_versions.

Revision ID: 010
Revises: 009
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"


def upgrade() -> None:
    op.add_column("prompt_versions", sa.Column("judge_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("prompt_versions", "judge_score")
