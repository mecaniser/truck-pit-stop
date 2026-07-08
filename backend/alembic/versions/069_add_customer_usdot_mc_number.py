"""add usdot_number and mc_number to customers

Federal motor carrier identifiers (FMCSA). The Easy Truck Shop import captured
USDOT numbers for many customers but had nowhere to store them; MC (Motor
Carrier) number is scraped in a follow-up pass. Both are optional free-text
(not validated/normalized — formats vary and some customers have neither).

Revision ID: 069
Revises: 068
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa


revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("usdot_number", sa.String(20), nullable=True))
    op.create_index("ix_customers_usdot_number", "customers", ["usdot_number"])
    op.add_column("customers", sa.Column("mc_number", sa.String(20), nullable=True))
    op.create_index("ix_customers_mc_number", "customers", ["mc_number"])


def downgrade() -> None:
    op.drop_index("ix_customers_mc_number", table_name="customers")
    op.drop_column("customers", "mc_number")
    op.drop_index("ix_customers_usdot_number", table_name="customers")
    op.drop_column("customers", "usdot_number")
