"""Add traces table.

Revision ID: 006
Revises: 005
Create Date: 2026-04-07
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id", UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=False
        ),
        sa.Column("prompt_text", sa.Text()),
        sa.Column("response_text", sa.Text()),
        sa.Column("model", sa.String()),
        sa.Column("tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("source_file", sa.String()),
        sa.Column("source_variable", sa.String()),
        sa.Column("score", sa.Float()),
        sa.Column("scored_by", sa.String()),
        sa.Column("metadata", JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_traces_task_created", "traces", ["task_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_traces_task_created")
    op.drop_table("traces")
