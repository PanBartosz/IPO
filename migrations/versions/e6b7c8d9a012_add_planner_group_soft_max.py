"""add planner group soft max

Revision ID: e6b7c8d9a012
Revises: d4a7c2e9b5f1
Create Date: 2026-05-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e6b7c8d9a012"
down_revision = "d4a7c2e9b5f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("assignment_batches")}

    if "planner_group_soft_max" not in columns:
        op.add_column(
            "assignment_batches",
            sa.Column("planner_group_soft_max", sa.Integer(), nullable=False, server_default="5"),
        )
        op.alter_column("assignment_batches", "planner_group_soft_max", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("assignment_batches")}

    if "planner_group_soft_max" in columns:
        op.drop_column("assignment_batches", "planner_group_soft_max")
