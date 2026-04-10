"""Create core tables.

Revision ID: 001
Revises:
Create Date: 2026-03-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "name",
            sa.String,
            unique=True,
            nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "schema_json",
            postgresql.JSONB,
            nullable=True,
        ),
        sa.Column(
            "feedback_threshold",
            sa.Integer,
            server_default="50",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    op.create_table(
        "feedback_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id"),
            nullable=False,
        ),
        sa.Column(
            "inputs", postgresql.JSONB, nullable=True
        ),
        sa.Column("output", sa.Text, nullable=True),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("source", sa.String, nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB, nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_feedback_entries_task_created",
        "feedback_entries",
        ["task_id", "created_at"],
    )

    op.create_table(
        "prompt_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id"),
            nullable=False,
        ),
        sa.Column(
            "version_number", sa.Integer, nullable=False
        ),
        sa.Column("prompt_text", sa.Text, nullable=True),
        sa.Column(
            "dspy_state_json",
            postgresql.JSONB,
            nullable=True,
        ),
        sa.Column("eval_score", sa.Float, nullable=True),
        sa.Column(
            "status",
            sa.String,
            server_default="draft",
        ),
        sa.Column("optimizer", sa.String, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    op.create_table(
        "optimization_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id"),
            nullable=False,
        ),
        sa.Column(
            "prompt_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_versions.id"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String,
            server_default="PENDING",
        ),
        sa.Column(
            "triggered_by", sa.String, nullable=True
        ),
        sa.Column(
            "feedback_count", sa.Integer, nullable=True
        ),
        sa.Column("pr_url", sa.Text, nullable=True),
        sa.Column(
            "error_message", sa.Text, nullable=True
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "key_hash",
            sa.Text,
            unique=True,
            nullable=False,
        ),
        sa.Column("label", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_table("optimization_jobs")
    op.drop_table("prompt_versions")
    op.drop_index(
        "ix_feedback_entries_task_created",
        table_name="feedback_entries",
    )
    op.drop_table("feedback_entries")
    op.drop_table("tasks")
