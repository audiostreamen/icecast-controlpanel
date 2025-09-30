"""initial schema

Revision ID: e8a1e3c9a2a1
Revises: 
Create Date: 2025-09-17 00:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8a1e3c9a2a1'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'services',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('svc_type', sa.String(length=64), nullable=False, server_default='Icecast 2 KH'),
        sa.Column('owner', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('uid', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('port', sa.Integer(), nullable=False, server_default=sa.text('8000')),
        sa.Column('admin_pass', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('source_pass', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('relay_pass', sa.String(length=255), nullable=False, server_default=''),
    )

    op.create_table(
        'service_limits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('service_id', sa.Integer(), sa.ForeignKey('services.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('mounts', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('autodj', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('bitrate', sa.Integer(), nullable=False, server_default=sa.text('320')),
        sa.Column('listeners', sa.Integer(), nullable=False, server_default=sa.text('100')),
        sa.Column('bandwidth', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('storage', sa.Integer(), nullable=False, server_default=sa.text('11000')),
    )

    op.create_table(
        'service_features',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('service_id', sa.Integer(), sa.ForeignKey('services.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('hist', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('proxy', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('geoip', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('auth', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('multi', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('public', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('social', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('record', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )

    op.create_table(
        'service_icecast',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('service_id', sa.Integer(), sa.ForeignKey('services.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('public_server', sa.String(length=64), nullable=False, server_default='Default (bron bepaalt)'),
        sa.Column('intro_path', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('yp_url', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('redirect_path', sa.String(length=256), nullable=False, server_default=''),
    )

    op.create_table(
        'service_autodj',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('service_id', sa.Integer(), sa.ForeignKey('services.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('autodj_type', sa.String(length=32), nullable=False, server_default='liquidsoap'),
        sa.Column('fade_in', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('fade_out', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('fade_min', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('smart_fade', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('replay_gain', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )

    op.create_table(
        'service_relay',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('service_id', sa.Integer(), sa.ForeignKey('services.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('relay_type', sa.String(length=64), nullable=False, server_default='Uitgeschakeld'),
    )


def downgrade() -> None:
    op.drop_table('service_relay')
    op.drop_table('service_autodj')
    op.drop_table('service_icecast')
    op.drop_table('service_features')
    op.drop_table('service_limits')
    op.drop_table('services')

