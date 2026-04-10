"""Add git provider columns to tasks and migrate github_* data.

Revision ID: 009
Revises: 008
Create Date: 2026-04-07
"""

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("git_provider", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("git_base_url", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("git_token_encrypted", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("git_project", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("git_repo", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("git_base_branch", sa.String(), nullable=True))

    # Migrate existing github_* data into git_* columns
    op.execute(
        "UPDATE tasks SET "
        "git_provider = 'github', "
        "git_repo = github_repo, "
        "git_base_branch = github_base_branch, "
        "git_token_encrypted = github_token_encrypted "
        "WHERE github_repo IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("tasks", "git_base_branch")
    op.drop_column("tasks", "git_repo")
    op.drop_column("tasks", "git_project")
    op.drop_column("tasks", "git_token_encrypted")
    op.drop_column("tasks", "git_base_url")
    op.drop_column("tasks", "git_provider")
