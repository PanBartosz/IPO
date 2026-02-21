"""add static pages and attachments

Revision ID: 9f3b2d1e7a4c
Revises: 8f4e2a1c3b6d
Create Date: 2026-02-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "9f3b2d1e7a4c"
down_revision = "8f4e2a1c3b6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "static_pages" not in inspector.get_table_names():
        op.create_table(
            "static_pages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("slug", sa.String(length=160), nullable=False),
            sa.Column("html_body", sa.Text(), nullable=False),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("updated_by", sa.String(length=120), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )

    if "static_page_attachments" not in inspector.get_table_names():
        op.create_table(
            "static_page_attachments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("page_id", sa.Integer(), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("stored_filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("uploaded_by", sa.String(length=120), nullable=True),
            sa.ForeignKeyConstraint(["page_id"], ["static_pages.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("stored_filename"),
        )

    indexes = {index["name"] for index in inspector.get_indexes("static_page_attachments")}
    if "ix_static_page_attachment_page_id" not in indexes:
        op.create_index(
            "ix_static_page_attachment_page_id",
            "static_page_attachments",
            ["page_id"],
        )
    if "ix_static_page_attachment_stored_filename" not in indexes:
        op.create_index(
            "ix_static_page_attachment_stored_filename",
            "static_page_attachments",
            ["stored_filename"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "static_page_attachments" in inspector.get_table_names():
        indexes = {index["name"] for index in inspector.get_indexes("static_page_attachments")}
        if "ix_static_page_attachment_stored_filename" in indexes:
            op.drop_index("ix_static_page_attachment_stored_filename", table_name="static_page_attachments")
        if "ix_static_page_attachment_page_id" in indexes:
            op.drop_index("ix_static_page_attachment_page_id", table_name="static_page_attachments")
        op.drop_table("static_page_attachments")

    if "static_pages" in inspector.get_table_names():
        op.drop_table("static_pages")
