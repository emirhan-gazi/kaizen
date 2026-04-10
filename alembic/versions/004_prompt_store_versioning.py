"""prompt_store_versioning

Revision ID: 004
Revises: 003
Create Date: 2026-04-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prompt_versions", sa.Column("dspy_version", sa.String(), nullable=True))
    op.add_column("feedback_entries", sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("tasks", sa.Column("feedback_retention_limit", sa.Integer(), server_default=sa.text("1000"), nullable=False))
    op.create_index("ix_feedback_entries_is_archived", "feedback_entries", ["task_id", "is_archived"])


def downgrade() -> None:
    op.drop_index("ix_feedback_entries_is_archived", table_name="feedback_entries")
    op.drop_column("tasks", "feedback_retention_limit")
    op.drop_column("feedback_entries", "is_archived")
    op.drop_column("prompt_versions", "dspy_version")
