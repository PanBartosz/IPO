"""add temporary access codes

Revision ID: a2b4c6d8e0f1
Revises: f1a2b3c4d5e6
Create Date: 2026-05-02 00:00:00.000000
"""

from __future__ import annotations

import secrets

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "a2b4c6d8e0f1"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


STUDENT_INDEX = "ix_students_temporary_access_code_unique"
TEACHER_INDEX = "ix_teachers_temporary_access_code_unique"


def _code(reserved: set[str]) -> str:
    for _ in range(100):
        value = secrets.token_urlsafe(8)
        if value not in reserved:
            reserved.add(value)
            return value
    value = secrets.token_hex(16)
    reserved.add(value)
    return value


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _populate_missing_codes(bind, table_name: str) -> None:
    existing = {
        row[0]
        for row in bind.execute(
            sa.text(f"SELECT temporary_access_code FROM {table_name} WHERE temporary_access_code IS NOT NULL")
        )
        if row[0]
    }
    rows = bind.execute(
        sa.text(f"SELECT id FROM {table_name} WHERE temporary_access_code IS NULL ORDER BY id")
    ).fetchall()
    for row in rows:
        bind.execute(
            sa.text(f"UPDATE {table_name} SET temporary_access_code = :code WHERE id = :id"),
            {"code": _code(existing), "id": row[0]},
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    student_columns = _column_names(inspector, "students")
    if "temporary_access_code" not in student_columns:
        op.add_column("students", sa.Column("temporary_access_code", sa.String(length=64), nullable=True))

    teacher_columns = _column_names(inspector, "teachers")
    if "temporary_access_code" not in teacher_columns:
        op.add_column("teachers", sa.Column("temporary_access_code", sa.String(length=64), nullable=True))

    inspector = inspect(bind)
    if "temporary_access_code" in _column_names(inspector, "students"):
        _populate_missing_codes(bind, "students")
        if STUDENT_INDEX not in _index_names(inspector, "students"):
            op.create_index(STUDENT_INDEX, "students", ["temporary_access_code"], unique=True)

    inspector = inspect(bind)
    if "temporary_access_code" in _column_names(inspector, "teachers"):
        _populate_missing_codes(bind, "teachers")
        if TEACHER_INDEX not in _index_names(inspector, "teachers"):
            op.create_index(TEACHER_INDEX, "teachers", ["temporary_access_code"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if STUDENT_INDEX in _index_names(inspector, "students"):
        op.drop_index(STUDENT_INDEX, table_name="students")
    if TEACHER_INDEX in _index_names(inspector, "teachers"):
        op.drop_index(TEACHER_INDEX, table_name="teachers")

    inspector = inspect(bind)
    if "temporary_access_code" in _column_names(inspector, "students"):
        op.drop_column("students", "temporary_access_code")
    if "temporary_access_code" in _column_names(inspector, "teachers"):
        op.drop_column("teachers", "temporary_access_code")
