"""add_stripe_customer_id

Revision ID: 004
Revises: 003
Create Date: 2025-12-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
    op.create_unique_constraint('uq_customers_stripe_customer_id', 'customers', ['stripe_customer_id'])


def downgrade() -> None:
    op.drop_constraint('uq_customers_stripe_customer_id', 'customers', type_='unique')
    op.drop_column('customers', 'stripe_customer_id')
