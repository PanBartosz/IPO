"""Add admin override and lock columns to essay_scores

Revision ID: 5f3c2de1f4b0
Revises: 3d22d9b5c4f1
Create Date: 2025-02-16 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5f3c2de1f4b0"
down_revision = "3d22d9b5c4f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("essay_scores") as batch_op:
        batch_op.add_column(sa.Column("admin_override", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("locked_by_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("essay_scores") as batch_op:
        batch_op.alter_column("admin_override", server_default=None)
        batch_op.alter_column("locked_by_admin", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("essay_scores") as batch_op:
        batch_op.drop_column("locked_by_admin")
        batch_op.drop_column("admin_override")
