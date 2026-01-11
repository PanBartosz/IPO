"""Add registration consents and essay word count.

Revision ID: 7a2c1d8d0c3c
Revises: 5d46f6500a9a
Create Date: 2025-12-20
"""

from alembic import op
import sqlalchemy as sa


revision = "7a2c1d8d0c3c"
down_revision = "5d46f6500a9a"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("students") as batch_op:
        batch_op.add_column(sa.Column("accepted_ethics", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("accepted_ethics_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("essay_word_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("essay_word_counted_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("teachers") as batch_op:
        batch_op.add_column(sa.Column("accepted_ethics", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("accepted_ethics_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("declared_assessor_competence", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.add_column(sa.Column("declared_assessor_competence_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("students") as batch_op:
        batch_op.alter_column("accepted_ethics", server_default=None)

    with op.batch_alter_table("teachers") as batch_op:
        batch_op.alter_column("accepted_ethics", server_default=None)
        batch_op.alter_column("declared_assessor_competence", server_default=None)


def downgrade():
    with op.batch_alter_table("teachers") as batch_op:
        batch_op.drop_column("declared_assessor_competence_at")
        batch_op.drop_column("declared_assessor_competence")
        batch_op.drop_column("accepted_ethics_at")
        batch_op.drop_column("accepted_ethics")

    with op.batch_alter_table("students") as batch_op:
        batch_op.drop_column("essay_word_counted_at")
        batch_op.drop_column("essay_word_count")
        batch_op.drop_column("accepted_ethics_at")
        batch_op.drop_column("accepted_ethics")
