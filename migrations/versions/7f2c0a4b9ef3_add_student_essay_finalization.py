"""Add essay finalization fields to students

Revision ID: 7f2c0a4b9ef3
Revises: 9b6b55f3fbc2
Create Date: 2025-02-15 14:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7f2c0a4b9ef3"
down_revision = "9b6b55f3fbc2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("students") as batch_op:
        batch_op.add_column(sa.Column("essay_finalized", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("essay_finalized_at", sa.DateTime(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE students SET essay_finalized = FALSE WHERE essay_finalized IS NULL"
        )
    )
    with op.batch_alter_table("students") as batch_op:
        batch_op.alter_column("essay_finalized", server_default=None)


def downgrade():
    with op.batch_alter_table("students") as batch_op:
        batch_op.drop_column("essay_finalized_at")
        batch_op.drop_column("essay_finalized")
