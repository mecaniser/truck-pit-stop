"""Add tax and fee settings to tenants and invoices

Revision ID: 020
Revises: 019
Create Date: 2026-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tax/fee rate columns to tenants
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS sales_tax_rate NUMERIC(5,3) DEFAULT 0.000 NOT NULL
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS shop_supplies_rate NUMERIC(5,3) DEFAULT 0.000 NOT NULL
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS service_fee_rate NUMERIC(5,3) DEFAULT 0.000 NOT NULL
    """)
    
    # Add fee breakdown columns to invoices
    op.execute("""
        ALTER TABLE invoices 
        ADD COLUMN IF NOT EXISTS shop_supplies_amount NUMERIC(10,2) DEFAULT 0.00 NOT NULL
    """)
    op.execute("""
        ALTER TABLE invoices 
        ADD COLUMN IF NOT EXISTS service_fee_amount NUMERIC(10,2) DEFAULT 0.00 NOT NULL
    """)


def downgrade() -> None:
    op.drop_column('invoices', 'service_fee_amount')
    op.drop_column('invoices', 'shop_supplies_amount')
    op.drop_column('tenants', 'service_fee_rate')
    op.drop_column('tenants', 'shop_supplies_rate')
    op.drop_column('tenants', 'sales_tax_rate')
