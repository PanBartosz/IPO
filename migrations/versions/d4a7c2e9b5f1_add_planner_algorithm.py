"""add planner algorithm selector

Revision ID: d4a7c2e9b5f1
Revises: b3d4f6a7c8d9
Create Date: 2026-04-28 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d4a7c2e9b5f1"
down_revision = "b3d4f6a7c8d9"
branch_labels = None
depends_on = None


DEFAULT_ALGORITHM = "STRICT_FOUR_WITH_BACKUPS"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("assignment_batches")}

    if "planner_algorithm" not in columns:
        op.add_column(
            "assignment_batches",
            sa.Column(
                "planner_algorithm",
                sa.String(length=40),
                nullable=False,
                server_default=DEFAULT_ALGORITHM,
            ),
        )
        op.alter_column("assignment_batches", "planner_algorithm", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("assignment_batches")}

    if "planner_algorithm" in columns:
        op.drop_column("assignment_batches", "planner_algorithm")
