"""add teacher veteran level

Revision ID: 5d46f6500a9a
Revises: c1e9c4c3b5d6
Create Date: 2024-08-25 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "5d46f6500a9a"
down_revision = "c1e9c4c3b5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("teachers")}

    has_level_column = "prior_ipo_assessor_level" in columns
    if not has_level_column:
        op.add_column(
            "teachers",
            sa.Column(
                "prior_ipo_assessor_level",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
        has_level_column = True

    if has_level_column and "prior_ipo_assessor" in columns:
        op.execute(
            """
            UPDATE teachers
            SET prior_ipo_assessor_level = 1
            WHERE prior_ipo_assessor = TRUE
            """
        )

    if has_level_column:
        op.alter_column("teachers", "prior_ipo_assessor_level", server_default=None)


def downgrade() -> None:
    op.execute(
        """
        UPDATE teachers
        SET prior_ipo_assessor = TRUE
        WHERE prior_ipo_assessor_level > 0
        """
    )
    op.drop_column("teachers", "prior_ipo_assessor_level")
