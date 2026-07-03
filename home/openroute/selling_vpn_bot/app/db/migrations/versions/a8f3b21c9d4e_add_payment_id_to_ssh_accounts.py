"""add payment_id to ssh_accounts

Revision ID: a8f3b21c9d4e
Revises: c5d2e7e0a1c2
Create Date: 2026-06-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8f3b21c9d4e'
down_revision: Union[str, Sequence[str], None] = 'c5d2e7e0a1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add payment_id FK column to ssh_accounts for traceability."""
    op.add_column(
        'ssh_accounts',
        sa.Column('payment_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_ssh_accounts_payment_id',
        'ssh_accounts', 'payments',
        ['payment_id'], ['id']
    )
    op.create_index(
        'ix_ssh_accounts_payment_id',
        'ssh_accounts',
        ['payment_id']
    )


def downgrade() -> None:
    """Remove payment_id FK column from ssh_accounts."""
    op.drop_index('ix_ssh_accounts_payment_id', table_name='ssh_accounts')
    op.drop_constraint('fk_ssh_accounts_payment_id', 'ssh_accounts', type_='foreignkey')
    op.drop_column('ssh_accounts', 'payment_id')
