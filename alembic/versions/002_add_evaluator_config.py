"""Add evaluator_config to tasks.

Revision ID: 002
Revises: 001
Create Date: 2026-04-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("evaluator_config", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "evaluator_config")
