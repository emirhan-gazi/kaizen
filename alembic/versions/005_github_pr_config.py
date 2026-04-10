"""Add GitHub PR config columns to tasks.

Revision ID: 005
Revises: 004
Create Date: 2026-04-01
"""

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("github_repo", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("github_base_branch", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("prompt_path", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("prompt_format", sa.String(), nullable=True))
    op.add_column(
        "tasks", sa.Column("github_token_encrypted", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tasks", "github_token_encrypted")
    op.drop_column("tasks", "prompt_format")
    op.drop_column("tasks", "prompt_path")
    op.drop_column("tasks", "github_base_branch")
    op.drop_column("tasks", "github_repo")
