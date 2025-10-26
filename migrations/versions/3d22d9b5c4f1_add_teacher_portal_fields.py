"""Add teacher portal credentials and score finalization fields

Revision ID: 3d22d9b5c4f1
Revises: 0bf0e2eb4c9f
Create Date: 2025-02-15 16:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3d22d9b5c4f1"
down_revision = "0bf0e2eb4c9f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("teachers") as batch_op:
        batch_op.add_column(sa.Column("portal_username", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("portal_password_hash", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("portal_token", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("portal_last_login", sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint("uq_teachers_portal_username", ["portal_username"])
        batch_op.create_unique_constraint("uq_teachers_portal_token", ["portal_token"])

    with op.batch_alter_table("essay_scores") as batch_op:
        batch_op.add_column(sa.Column("teacher_finalized", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("teacher_finalized_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE essay_scores SET teacher_finalized = FALSE WHERE teacher_finalized IS NULL")
    with op.batch_alter_table("essay_scores") as batch_op:
        batch_op.alter_column("teacher_finalized", server_default=None)


def downgrade():
    with op.batch_alter_table("essay_scores") as batch_op:
        batch_op.drop_column("teacher_finalized_at")
        batch_op.drop_column("teacher_finalized")

    with op.batch_alter_table("teachers") as batch_op:
        batch_op.drop_constraint("uq_teachers_portal_token", type_="unique")
        batch_op.drop_constraint("uq_teachers_portal_username", type_="unique")
        batch_op.drop_column("portal_last_login")
        batch_op.drop_column("portal_token")
        batch_op.drop_column("portal_password_hash")
        batch_op.drop_column("portal_username")
