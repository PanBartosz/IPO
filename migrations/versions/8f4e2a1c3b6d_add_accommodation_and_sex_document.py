"""Add accommodation fields and official document sex.

Revision ID: 8f4e2a1c3b6d
Revises: 6f1a9d3c2b7e
Create Date: 2026-01-11
"""

from alembic import op
import sqlalchemy as sa


revision = "8f4e2a1c3b6d"
down_revision = "6f1a9d3c2b7e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("students") as batch_op:
        batch_op.add_column(sa.Column("sex_document", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("accommodation_room_sharing", sa.String(length=32), nullable=True))

    with op.batch_alter_table("teachers") as batch_op:
        batch_op.add_column(sa.Column("sex_document", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("accommodation_room_sharing", sa.String(length=32), nullable=True))

    op.execute(sa.text("UPDATE students SET sex_document = 'female' WHERE lower(gender) = 'female'"))
    op.execute(sa.text("UPDATE students SET sex_document = 'male' WHERE lower(gender) = 'male'"))
    op.execute(sa.text("UPDATE teachers SET sex_document = 'female' WHERE lower(gender) = 'female'"))
    op.execute(sa.text("UPDATE teachers SET sex_document = 'male' WHERE lower(gender) = 'male'"))

    with op.batch_alter_table("students") as batch_op:
        batch_op.drop_column("gender")

    with op.batch_alter_table("teachers") as batch_op:
        batch_op.drop_column("gender")


def downgrade():
    with op.batch_alter_table("students") as batch_op:
        batch_op.add_column(
            sa.Column("gender", sa.String(length=10), nullable=False, server_default="Other")
        )

    with op.batch_alter_table("teachers") as batch_op:
        batch_op.add_column(
            sa.Column("gender", sa.String(length=10), nullable=False, server_default="Other")
        )

    op.execute(sa.text("UPDATE students SET gender = 'Female' WHERE sex_document = 'female'"))
    op.execute(sa.text("UPDATE students SET gender = 'Male' WHERE sex_document = 'male'"))
    op.execute(sa.text("UPDATE teachers SET gender = 'Female' WHERE sex_document = 'female'"))
    op.execute(sa.text("UPDATE teachers SET gender = 'Male' WHERE sex_document = 'male'"))

    with op.batch_alter_table("students") as batch_op:
        batch_op.alter_column("gender", server_default=None)
        batch_op.drop_column("accommodation_room_sharing")
        batch_op.drop_column("sex_document")

    with op.batch_alter_table("teachers") as batch_op:
        batch_op.alter_column("gender", server_default=None)
        batch_op.drop_column("accommodation_room_sharing")
        batch_op.drop_column("sex_document")

