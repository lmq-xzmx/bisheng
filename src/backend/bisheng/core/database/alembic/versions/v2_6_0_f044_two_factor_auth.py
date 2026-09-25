"""F044 add two-factor authentication fields to user table.

Revision ID: f044_two_factor_auth
Revises: f043_user_sync
Create Date: 2026-09-06

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f044_two_factor_auth'
down_revision: Union[str, Sequence[str], None] = 'f043_user_sync'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add two_factor_enabled column
    op.add_column(
        'user',
        sa.Column('two_factor_enabled', sa.Boolean(), nullable=False, server_default='0')
    )
    # Add totp_secret column (encrypted TOTP secret)
    op.add_column(
        'user',
        sa.Column('totp_secret', sa.String(length=255), nullable=True)
    )
    # Add backup_codes column (JSON array of hashed codes)
    op.add_column(
        'user',
        sa.Column('backup_codes', sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('user', 'backup_codes')
    op.drop_column('user', 'totp_secret')
    op.drop_column('user', 'two_factor_enabled')
