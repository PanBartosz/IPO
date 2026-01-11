"""add delegation leader invite flag

Revision ID: 6f1a9d3c2b7e
Revises: 4c2a6d9c8f10
Create Date: 2025-12-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "6f1a9d3c2b7e"
down_revision = "4c2a6d9c8f10"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "delegation_invites" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("delegation_invites")}
    if "delegation_leader" in columns:
        return

    with op.batch_alter_table("delegation_invites") as batch_op:
        batch_op.add_column(sa.Column("delegation_leader", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    with op.batch_alter_table("delegation_invites") as batch_op:
        batch_op.alter_column("delegation_leader", server_default=None)


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "delegation_invites" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("delegation_invites")}
    if "delegation_leader" not in columns:
        return
    with op.batch_alter_table("delegation_invites") as batch_op:
        batch_op.drop_column("delegation_leader")
