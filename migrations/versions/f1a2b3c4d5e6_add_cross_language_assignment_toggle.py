"""add cross language assignment toggle

Revision ID: f1a2b3c4d5e6
Revises: e6b7c8d9a012
Create Date: 2026-05-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f1a2b3c4d5e6"
down_revision = "e6b7c8d9a012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("assignment_batches")}

    if "planner_allow_cross_language_assignments" not in columns:
        op.add_column(
            "assignment_batches",
            sa.Column(
                "planner_allow_cross_language_assignments",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        op.alter_column(
            "assignment_batches",
            "planner_allow_cross_language_assignments",
            server_default=None,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("assignment_batches")}

    if "planner_allow_cross_language_assignments" in columns:
        op.drop_column("assignment_batches", "planner_allow_cross_language_assignments")
