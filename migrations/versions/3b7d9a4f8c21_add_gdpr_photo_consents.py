"""add gdpr notice acknowledgement and photo consent fields

Revision ID: 3b7d9a4f8c21
Revises: 2d9c7f4e1a3b
Create Date: 2025-03-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "3b7d9a4f8c21"
down_revision = "2d9c7f4e1a3b"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("students") as batch_op:
        batch_op.add_column(sa.Column("gdpr_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("gdpr_acknowledged_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("photo_consent", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("photo_consent_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("teachers") as batch_op:
        batch_op.add_column(sa.Column("gdpr_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("gdpr_acknowledged_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("photo_consent", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("photo_consent_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("students") as batch_op:
        batch_op.alter_column("gdpr_acknowledged", server_default=None)
        batch_op.alter_column("photo_consent", server_default=None)

    with op.batch_alter_table("teachers") as batch_op:
        batch_op.alter_column("gdpr_acknowledged", server_default=None)
        batch_op.alter_column("photo_consent", server_default=None)


def downgrade():
    with op.batch_alter_table("teachers") as batch_op:
        batch_op.drop_column("photo_consent_at")
        batch_op.drop_column("photo_consent")
        batch_op.drop_column("gdpr_acknowledged_at")
        batch_op.drop_column("gdpr_acknowledged")

    with op.batch_alter_table("students") as batch_op:
        batch_op.drop_column("photo_consent_at")
        batch_op.drop_column("photo_consent")
        batch_op.drop_column("gdpr_acknowledged_at")
        batch_op.drop_column("gdpr_acknowledged")
