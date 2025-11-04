"""add communication campaign tables

Revision ID: c1e9c4c3b5d6
Revises: 1b8f4f0a3d1a
Create Date: 2024-07-20 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "c1e9c4c3b5d6"
down_revision = "1b8f4f0a3d1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    communication_status = sa.Enum(
        "draft",
        "queued",
        "sending",
        "sent",
        "failed",
        name="communicationstatus",
    )
    communication_audience = sa.Enum(
        "teacher",
        "student",
        "both",
        name="communicationaudience",
    )
    communication_recipient_role = sa.Enum(
        "teacher",
        "student",
        name="communicationrecipientrole",
    )
    communication_recipient_status = sa.Enum(
        "pending",
        "sent",
        "failed",
        name="communicationrecipientstatus",
    )

    communication_status.create(bind, checkfirst=True)
    communication_audience.create(bind, checkfirst=True)
    communication_recipient_role.create(bind, checkfirst=True)
    communication_recipient_status.create(bind, checkfirst=True)

    if "communication_campaigns" not in inspector.get_table_names():
        op.create_table(
            "communication_campaigns",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("subject", sa.String(length=255), nullable=False),
            sa.Column("html_body", sa.Text(), nullable=False),
            sa.Column("text_body", sa.Text(), nullable=False),
            sa.Column("audience", communication_audience, nullable=False),
            sa.Column("country_filter", sa.JSON(), nullable=True),
            sa.Column("include_absent", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", communication_status, nullable=False, server_default="draft"),
            sa.Column("total_recipients", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("sent_by", sa.String(length=120), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_communication_campaign_status",
            "communication_campaigns",
            ["status"],
        )

    if "communication_recipients" not in inspector.get_table_names():
        op.create_table(
            "communication_recipients",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("campaign_id", sa.Integer(), nullable=False),
            sa.Column("role", communication_recipient_role, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=True),
            sa.Column("teacher_id", sa.Integer(), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("first_name", sa.String(length=80), nullable=True),
            sa.Column("last_name", sa.String(length=80), nullable=True),
            sa.Column("country", sa.String(length=100), nullable=True),
            sa.Column("status", communication_recipient_status, nullable=False, server_default="pending"),
            sa.Column("message_id", sa.String(length=120), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "campaign_id",
                "role",
                "student_id",
                "teacher_id",
                name="uq_communication_recipient_target",
            ),
            sa.UniqueConstraint("campaign_id", "email", name="uq_communication_recipient_email"),
            sa.ForeignKeyConstraint(
                ["campaign_id"],
                ["communication_campaigns.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["student_id"],
                ["students.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["teacher_id"],
                ["teachers.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_communication_recipient_campaign_status",
            "communication_recipients",
            ["campaign_id", "status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "communication_recipients" in inspector.get_table_names():
        op.drop_index("ix_communication_recipient_campaign_status", table_name="communication_recipients")
        op.drop_table("communication_recipients")

    if "communication_campaigns" in inspector.get_table_names():
        op.drop_index("ix_communication_campaign_status", table_name="communication_campaigns")
        op.drop_table("communication_campaigns")

    communication_recipient_status = sa.Enum(
        "pending",
        "sent",
        "failed",
        name="communicationrecipientstatus",
    )
    communication_recipient_role = sa.Enum(
        "teacher",
        "student",
        name="communicationrecipientrole",
    )
    communication_audience = sa.Enum(
        "teacher",
        "student",
        "both",
        name="communicationaudience",
    )
    communication_status = sa.Enum(
        "draft",
        "queued",
        "sending",
        "sent",
        "failed",
        name="communicationstatus",
    )

    communication_recipient_status.drop(bind, checkfirst=True)
    communication_recipient_role.drop(bind, checkfirst=True)
    communication_audience.drop(bind, checkfirst=True)
    communication_status.drop(bind, checkfirst=True)
