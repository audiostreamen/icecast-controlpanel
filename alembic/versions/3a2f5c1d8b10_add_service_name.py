"""add service.name

Revision ID: 3a2f5c1d8b10
Revises: e8a1e3c9a2a1
Create Date: 2025-09-17 01:32:00

"""
from alembic import op
import sqlalchemy as sa


revision = '3a2f5c1d8b10'
down_revision = 'e8a1e3c9a2a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('services') as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(length=128), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('services') as batch_op:
        batch_op.drop_column('name')

