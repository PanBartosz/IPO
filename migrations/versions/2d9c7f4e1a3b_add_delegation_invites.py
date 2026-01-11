"""add delegation invites

Revision ID: 2d9c7f4e1a3b
Revises: 7a2c1d8d0c3c
Create Date: 2025-03-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "2d9c7f4e1a3b"
down_revision = "7a2c1d8d0c3c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    invite_role = sa.Enum("student", "teacher", name="delegationinviterole")
    invite_role.create(bind, checkfirst=True)

    if "delegation_invites" not in inspector.get_table_names():
        op.create_table(
            "delegation_invites",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column("role", invite_role, nullable=False),
            sa.Column("country", sa.String(length=100), nullable=False),
            sa.Column("first_name", sa.String(length=80), nullable=True),
            sa.Column("last_name", sa.String(length=80), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("invited_by_id", sa.Integer(), nullable=True),
            sa.Column("student_id", sa.Integer(), nullable=True),
            sa.Column("teacher_id", sa.Integer(), nullable=True),
            sa.Column("opened_at", sa.DateTime(), nullable=True),
            sa.Column("accepted_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("email_sent_at", sa.DateTime(), nullable=True),
            sa.Column("email_error", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["invited_by_id"], ["teachers.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token"),
        )
        op.create_index(
            "ix_delegation_invite_token",
            "delegation_invites",
            ["token"],
        )
        op.create_index(
            "ix_delegation_invite_country_role",
            "delegation_invites",
            ["country", "role"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "delegation_invites" in inspector.get_table_names():
        op.drop_index("ix_delegation_invite_country_role", table_name="delegation_invites")
        op.drop_index("ix_delegation_invite_token", table_name="delegation_invites")
        op.drop_table("delegation_invites")

    invite_role = sa.Enum("student", "teacher", name="delegationinviterole")
    invite_role.drop(bind, checkfirst=True)
