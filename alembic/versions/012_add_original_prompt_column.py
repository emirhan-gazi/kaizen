"""Add original_prompt column to prompt_versions.

Revision ID: 012
Revises: 011
"""

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"


def upgrade() -> None:
    op.add_column("prompt_versions", sa.Column("original_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("prompt_versions", "original_prompt")
