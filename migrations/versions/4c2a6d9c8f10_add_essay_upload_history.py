"""add essay upload history

Revision ID: 4c2a6d9c8f10
Revises: 3b7d9a4f8c21
Create Date: 2025-03-01 00:00:00.000000
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "4c2a6d9c8f10"
down_revision = "3b7d9a4f8c21"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    table_exists = "essay_uploads" in inspector.get_table_names()

    if not table_exists:
        op.create_table(
            "essay_uploads",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("word_count", sa.Integer(), nullable=True),
            sa.Column("word_counted_at", sa.DateTime(), nullable=True),
            sa.Column("finalized_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_essay_upload_student_id", "essay_uploads", ["student_id"])
        op.create_index("ix_essay_upload_filename", "essay_uploads", ["filename"])
        table_exists = True
    else:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("essay_uploads")}
        if "ix_essay_upload_student_id" not in existing_indexes:
            op.create_index("ix_essay_upload_student_id", "essay_uploads", ["student_id"])
        if "ix_essay_upload_filename" not in existing_indexes:
            op.create_index("ix_essay_upload_filename", "essay_uploads", ["filename"])

    if not table_exists:
        return

    connection = op.get_bind()
    now = datetime.utcnow()
    connection.execute(
        sa.text(
            """
            INSERT INTO essay_uploads (
                created_at,
                updated_at,
                student_id,
                filename,
                word_count,
                word_counted_at,
                finalized_at
            )
            SELECT
                COALESCE(s.uploaded_at, :now) AS created_at,
                COALESCE(s.uploaded_at, :now) AS updated_at,
                s.id AS student_id,
                s.uploaded_filename AS filename,
                s.essay_word_count AS word_count,
                s.essay_word_counted_at AS word_counted_at,
                CASE
                    WHEN s.essay_finalized THEN s.essay_finalized_at
                    ELSE NULL
                END AS finalized_at
            FROM students s
            WHERE s.uploaded_filename IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM essay_uploads eu
                  WHERE eu.student_id = s.id
                    AND eu.filename = s.uploaded_filename
              )
            """
        ),
        {"now": now},
    )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "essay_uploads" not in inspector.get_table_names():
        return
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("essay_uploads")}
    if "ix_essay_upload_filename" in existing_indexes:
        op.drop_index("ix_essay_upload_filename", table_name="essay_uploads")
    if "ix_essay_upload_student_id" in existing_indexes:
        op.drop_index("ix_essay_upload_student_id", table_name="essay_uploads")
    op.drop_table("essay_uploads")
