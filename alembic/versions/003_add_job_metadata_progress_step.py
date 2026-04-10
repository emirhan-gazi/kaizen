"""Add job_metadata, progress_step to optimization_jobs; teacher_model, judge_model, module_type, cost_budget to tasks.

Revision ID: 003
Revises: 002
Create Date: 2026-04-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "optimization_jobs",
        sa.Column("job_metadata", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "optimization_jobs",
        sa.Column("progress_step", sa.String(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("teacher_model", sa.String(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("judge_model", sa.String(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("module_type", sa.String(), nullable=False, server_default="predict"),
    )
    op.add_column(
        "tasks",
        sa.Column("cost_budget", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "cost_budget")
    op.drop_column("tasks", "module_type")
    op.drop_column("tasks", "judge_model")
    op.drop_column("tasks", "teacher_model")
    op.drop_column("optimization_jobs", "progress_step")
    op.drop_column("optimization_jobs", "job_metadata")
