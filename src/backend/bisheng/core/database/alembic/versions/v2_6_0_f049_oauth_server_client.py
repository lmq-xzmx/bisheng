"""F049 OAuth Server Client table.

BiSheng acting as OAuth Authorization Server - client registration.

Revision ID: f049_oauth_server_client
Revises: v2_6_0_f048_merge_f046_f047_heads
Create Date: 2026-09-07

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f049_oauth_server_client'
down_revision: Union[str, None] = 'v2_6_0_f048_merge_f046_f047_heads'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'oauth_server_client',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('client_id', sa.String(length=64), nullable=False, unique=True),
        sa.Column('client_id_issued_at', sa.Integer(), nullable=False),
        sa.Column('client_secret', sa.String(length=256), nullable=True),  # NULL means public client
        sa.Column('client_secret_expires_at', sa.Integer(), nullable=True),  # 0 means never expires
        sa.Column('redirect_uris', sa.JSON(), nullable=False),
        sa.Column('grant_types', sa.JSON(), nullable=False),  # authorization_code, refresh_token
        sa.Column('response_types', sa.JSON(), nullable=False),  # code
        sa.Column('token_endpoint_auth_method', sa.String(length=32), nullable=False, server_default='client_secret_basic'),
        sa.Column('allowed_scopes', sa.JSON(), nullable=False, server_default='["openid", "profile", "email"]'),
        sa.Column('client_name', sa.String(length=128), nullable=True),
        sa.Column('client_uri', sa.String(length=512), nullable=True),
        sa.Column('logo_uri', sa.String(length=512), nullable=True),
        sa.Column('tos_uri', sa.String(length=512), nullable=True),
        sa.Column('policy_uri', sa.String(length=512), nullable=True),
        sa.Column('jwks_uri', sa.String(length=512), nullable=True),
        sa.Column('jwks', sa.JSON(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id'),
    )
    op.create_index('ix_oauth_server_client_enabled', 'oauth_server_client', ['enabled'])


def downgrade() -> None:
    op.drop_index('ix_oauth_server_client_enabled', table_name='oauth_server_client')
    op.drop_table('oauth_server_client')
