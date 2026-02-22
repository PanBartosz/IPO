"""add invitation batch drafts

Revision ID: b3d4f6a7c8d9
Revises: 9f3b2d1e7a4c
Create Date: 2026-02-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "b3d4f6a7c8d9"
down_revision = "9f3b2d1e7a4c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "invitation_batch_drafts" not in inspector.get_table_names():
        op.create_table(
            "invitation_batch_drafts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(length=120), nullable=False),
            sa.Column("batch_type", sa.String(length=32), nullable=False),
            sa.Column("source_filename", sa.String(length=255), nullable=False),
            sa.Column("file_sha256", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ready_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skip_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("executed_at", sa.DateTime(), nullable=True),
            sa.Column("result_payload", sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    indexes = {index["name"] for index in inspector.get_indexes("invitation_batch_drafts")}
    if "ix_invitation_batch_draft_created_by" not in indexes:
        op.create_index(
            "ix_invitation_batch_draft_created_by",
            "invitation_batch_drafts",
            ["created_by"],
        )
    if "ix_invitation_batch_draft_status" not in indexes:
        op.create_index(
            "ix_invitation_batch_draft_status",
            "invitation_batch_drafts",
            ["status"],
        )
    if "ix_invitation_batch_draft_created_at" not in indexes:
        op.create_index(
            "ix_invitation_batch_draft_created_at",
            "invitation_batch_drafts",
            ["created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "invitation_batch_drafts" in inspector.get_table_names():
        indexes = {index["name"] for index in inspector.get_indexes("invitation_batch_drafts")}
        if "ix_invitation_batch_draft_created_at" in indexes:
            op.drop_index("ix_invitation_batch_draft_created_at", table_name="invitation_batch_drafts")
        if "ix_invitation_batch_draft_status" in indexes:
            op.drop_index("ix_invitation_batch_draft_status", table_name="invitation_batch_drafts")
        if "ix_invitation_batch_draft_created_by" in indexes:
            op.drop_index("ix_invitation_batch_draft_created_by", table_name="invitation_batch_drafts")
        op.drop_table("invitation_batch_drafts")
