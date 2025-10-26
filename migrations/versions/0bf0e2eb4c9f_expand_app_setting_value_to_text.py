"""Expand app setting value column to Text

Revision ID: 0bf0e2eb4c9f
Revises: 7f2c0a4b9ef3
Create Date: 2025-02-15 15:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0bf0e2eb4c9f"
down_revision = "7f2c0a4b9ef3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("app_settings") as batch_op:
        batch_op.alter_column("value", type_=sa.Text(), existing_nullable=True)


def downgrade():
    with op.batch_alter_table("app_settings") as batch_op:
        batch_op.alter_column("value", type_=sa.String(length=500), existing_nullable=True)
