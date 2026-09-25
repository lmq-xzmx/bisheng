"""F050 add embedding model migration fields to knowledge_base and tenant_config.

Revision ID: f050_embedding_migration
Revises: f049_oauth_server_client
Create Date: 2026-09-25

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f050_embedding_migration'
down_revision: Union[str, Sequence[str], None] = 'f049_oauth_server_client'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add migration fields to knowledge_base table
    op.add_column(
        'knowledge_base',
        sa.Column('target_model', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'knowledge_base',
        sa.Column('migration_status', sa.String(length=50), nullable=False, server_default='idle')
    )
    op.add_column(
        'knowledge_base',
        sa.Column('migration_progress', sa.Float(), nullable=False, server_default='0.0')
    )
    op.add_column(
        'knowledge_base',
        sa.Column('locked_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'knowledge_base',
        sa.Column('locked_by', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'knowledge_base',
        sa.Column('locked_model', sa.String(length=255), nullable=True)
    )

    # Add embedding query strategy to tenant_system_config
    # Note: tenant_system_config table already exists from previous migrations
    op.add_column(
        'tenant_system_config',
        sa.Column('embedding_query_strategy', sa.String(length=50), nullable=False, server_default='dual_rrf')
    )
    op.add_column(
        'tenant_system_config',
        sa.Column('show_embedding_details', sa.Boolean(), nullable=False, server_default='0')
    )


def downgrade() -> None:
    op.drop_column('tenant_system_config', 'show_embedding_details')
    op.drop_column('tenant_system_config', 'embedding_query_strategy')
    op.drop_column('knowledge_base', 'locked_model')
    op.drop_column('knowledge_base', 'locked_by')
    op.drop_column('knowledge_base', 'locked_at')
    op.drop_column('knowledge_base', 'migration_progress')
    op.drop_column('knowledge_base', 'migration_status')
    op.drop_column('knowledge_base', 'target_model')
