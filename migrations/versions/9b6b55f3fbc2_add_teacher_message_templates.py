"""Add teacher message templates

Revision ID: 9b6b55f3fbc2
Revises: e3b4a0b2b1a4
Create Date: 2025-02-15 12:00:00.000000
"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9b6b55f3fbc2"
down_revision = "e3b4a0b2b1a4"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_name = "teacher_message_templates"

    if not inspector.has_table(table_name):
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("category", sa.String(length=80), nullable=True),
            sa.UniqueConstraint("name", name="uq_teacher_message_templates_name"),
        )

    template_table = sa.table(
        "teacher_message_templates",
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
        sa.column("name", sa.String(length=120)),
        sa.column("title", sa.String(length=200)),
        sa.column("body", sa.Text()),
        sa.column("category", sa.String(length=80)),
    )

    now = datetime.utcnow()
    existing_names = {
        row[0]
        for row in bind.execute(sa.text("SELECT name FROM teacher_message_templates"))
    }
    seed_entries = [
        {
            "created_at": now,
            "updated_at": now,
            "name": "Request teacher to change room",
            "title": "Teacher needed in another room",
            "body": "{teacher_name}, please proceed to {room} for essay assessment.",
            "category": "Logistics",
        },
        {
            "created_at": now,
            "updated_at": now,
            "name": "Collect essay from logistics desk",
            "title": "Essay collection needed",
            "body": "{teacher_name}, a new essay is ready for you at the logistics desk.",
            "category": "Logistics",
        },
        {
            "created_at": now,
            "updated_at": now,
            "name": "Stage briefing reminder",
            "title": "Stage briefing reminder",
            "body": "Teachers assigned to Stage {stage_number}, please gather in briefing room {room} at {time}.",
            "category": "Briefing",
        },
        {
            "created_at": now,
            "updated_at": now,
            "name": "Scoring deadline reminder",
            "title": "Reminder: scoring deadline approaching",
            "body": "Please ensure your outstanding essays are scored before {deadline}.",
            "category": "Schedule",
        },
    ]
    rows_to_insert = [entry for entry in seed_entries if entry["name"] not in existing_names]
    if rows_to_insert:
        op.bulk_insert(template_table, rows_to_insert)


def downgrade():
    op.drop_table("teacher_message_templates")
