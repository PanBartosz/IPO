"""add password reset token table

Revision ID: 1b8f4f0a3d1a
Revises: 
Create Date: 2024-06-12 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "1b8f4f0a3d1a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    password_reset_audience = sa.Enum("student", "teacher", name="passwordresetaudience")
    password_reset_audience.create(bind, checkfirst=True)

    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    if "password_reset_tokens" not in existing_tables:
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("audience", password_reset_audience, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=True),
            sa.Column("teacher_id", sa.Integer(), nullable=True),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "(student_id IS NOT NULL AND teacher_id IS NULL) OR "
                "(student_id IS NULL AND teacher_id IS NOT NULL)",
                name="ck_password_reset_token_audience_target",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token", name="uq_password_reset_token"),
            sa.ForeignKeyConstraint(
                ["student_id"],
                ["students.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["teacher_id"],
                ["teachers.id"],
                ondelete="CASCADE",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "password_reset_tokens" in inspector.get_table_names():
        op.drop_table("password_reset_tokens")

    password_reset_audience = sa.Enum("student", "teacher", name="passwordresetaudience")
    password_reset_audience.drop(bind, checkfirst=True)
