"""Change optimizer_type default from miprov2 to gepa.

Revision ID: 014
Revises: 013
"""

from alembic import op

revision = "014"
down_revision = "013"


def upgrade() -> None:
    op.alter_column(
        "tasks",
        "optimizer_type",
        server_default="gepa",
    )


def downgrade() -> None:
    op.alter_column(
        "tasks",
        "optimizer_type",
        server_default="miprov2",
    )
