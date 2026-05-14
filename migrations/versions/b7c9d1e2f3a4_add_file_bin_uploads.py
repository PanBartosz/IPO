"""add file bin uploads

Revision ID: b7c9d1e2f3a4
Revises: a2b4c6d8e0f1
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "b7c9d1e2f3a4"
down_revision = "a2b4c6d8e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "file_bin_uploads" not in inspector.get_table_names():
        op.create_table(
            "file_bin_uploads",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("staff_name", sa.String(length=120), nullable=False),
            sa.Column("room", sa.String(length=120), nullable=True),
            sa.Column("student_identifier", sa.String(length=255), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("stored_filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("submitted_ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("reviewed", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("reviewed_by", sa.String(length=120), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("admin_note", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("stored_filename"),
        )
        inspector = inspect(bind)

    indexes = {index["name"] for index in inspector.get_indexes("file_bin_uploads")}
    if "ix_file_bin_upload_reviewed" not in indexes:
        op.create_index("ix_file_bin_upload_reviewed", "file_bin_uploads", ["reviewed"])
    if "ix_file_bin_upload_created_at" not in indexes:
        op.create_index("ix_file_bin_upload_created_at", "file_bin_uploads", ["created_at"])
    if "ix_file_bin_upload_student_identifier" not in indexes:
        op.create_index(
            "ix_file_bin_upload_student_identifier",
            "file_bin_uploads",
            ["student_identifier"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "file_bin_uploads" not in inspector.get_table_names():
        return

    indexes = {index["name"] for index in inspector.get_indexes("file_bin_uploads")}
    if "ix_file_bin_upload_student_identifier" in indexes:
        op.drop_index("ix_file_bin_upload_student_identifier", table_name="file_bin_uploads")
    if "ix_file_bin_upload_created_at" in indexes:
        op.drop_index("ix_file_bin_upload_created_at", table_name="file_bin_uploads")
    if "ix_file_bin_upload_reviewed" in indexes:
        op.drop_index("ix_file_bin_upload_reviewed", table_name="file_bin_uploads")
    op.drop_table("file_bin_uploads")
