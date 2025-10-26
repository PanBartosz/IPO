"""Add admin status fields and assignment grading locks

Revision ID: 8c12d2f0e3b1
Revises: 5f3c2de1f4b0
Create Date: 2025-02-18 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8c12d2f0e3b1"
down_revision = "5f3c2de1f4b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("essay_scores") as batch_op:
        batch_op.add_column(sa.Column("admin_entered", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("admin_updated_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("essay_scores") as batch_op:
        batch_op.alter_column("admin_entered", server_default=None)

    with op.batch_alter_table("essay_assignments") as batch_op:
        batch_op.add_column(sa.Column("stage1_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("stage2_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("essay_assignments") as batch_op:
        batch_op.alter_column("stage1_locked", server_default=None)
        batch_op.alter_column("stage2_locked", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("essay_assignments") as batch_op:
        batch_op.drop_column("stage2_locked")
        batch_op.drop_column("stage1_locked")

    with op.batch_alter_table("essay_scores") as batch_op:
        batch_op.drop_column("admin_updated_at")
        batch_op.drop_column("admin_entered")
