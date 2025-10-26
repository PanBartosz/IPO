"""Convert teacher message creator/updater to string

Revision ID: e3b4a0b2b1a4
Revises: 
Create Date: 2025-10-25 17:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3b4a0b2b1a4'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('teacher_messages') as batch_op:
        batch_op.alter_column('creator_id',
                              existing_type=sa.Integer(),
                              type_=sa.String(length=120),
                              existing_nullable=True)
        batch_op.alter_column('updater_id',
                              existing_type=sa.Integer(),
                              type_=sa.String(length=120),
                              existing_nullable=True)


def downgrade():
    with op.batch_alter_table('teacher_messages') as batch_op:
        batch_op.alter_column('creator_id',
                              existing_type=sa.String(length=120),
                              type_=sa.Integer(),
                              existing_nullable=True)
        batch_op.alter_column('updater_id',
                              existing_type=sa.String(length=120),
                              type_=sa.Integer(),
                              existing_nullable=True)
