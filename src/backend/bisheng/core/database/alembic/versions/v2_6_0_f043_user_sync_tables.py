"""F043 user_sync tables: oauth_provider_config, ldap_config, user_sync_config.

Revision ID: f043_user_sync
Revises: v2_5_1_f022_approval_request
Create Date: 2026-09-06

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f043_user_sync'
down_revision: Union[str, None] = 'v2_5_1_f022_approval_request'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create oauth_provider_config table
    op.create_table(
        'oauth_provider_config',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True, index=True),
        sa.Column('provider', sa.String(length=32), nullable=False, index=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('client_id', sa.String(length=256), nullable=False),
        sa.Column('client_secret_encrypted', sa.String(length=512), nullable=False),
        sa.Column('redirect_uri', sa.String(length=512), nullable=False),
        sa.Column('scopes', sa.String(length=256), nullable=False, server_default='openid email profile'),
        sa.Column('config_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'provider', name='uk_oauth_tenant_provider'),
    )

    # Create ldap_config table
    op.create_table(
        'ldap_config',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True, index=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('server_url', sa.String(length=512), nullable=False),
        sa.Column('base_dn', sa.String(length=256), nullable=False),
        sa.Column('bind_dn', sa.String(length=256), nullable=False),
        sa.Column('bind_password_encrypted', sa.String(length=512), nullable=False),
        sa.Column('user_filter', sa.String(length=512), nullable=False, server_default='(uid={username})'),
        sa.Column('use_ssl', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('timeout', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('auto_register', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('sync_strategies', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', name='uk_ldap_tenant'),
    )

    # Create user_sync_config table
    op.create_table(
        'user_sync_config',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False, index=True),
        sa.Column('source', sa.String(length=32), nullable=False, index=True),
        sa.Column('auto_register', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('sync_email', sa.String(length=32), nullable=False, server_default='first_only'),
        sa.Column('sync_phone', sa.String(length=32), nullable=False, server_default='first_only'),
        sa.Column('sync_name', sa.String(length=32), nullable=False, server_default='never'),
        sa.Column('sync_department', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('logout_redirect_oauth', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'source', name='uk_usersync_tenant_source'),
    )


def downgrade() -> None:
    op.drop_table('user_sync_config')
    op.drop_table('ldap_config')
    op.drop_table('oauth_provider_config')
