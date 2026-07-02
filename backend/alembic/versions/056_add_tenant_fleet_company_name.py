"""add fleet_company_name to tenants

The garage services its own internal fleet, which is operated by a named
company (e.g. "77 Cargo"). This is distinct from the garage's own name
(tenant.name). Storing it here lets internal fleet repair orders display the
fleet operator as the customer on the owner's board without inventing a fake
customer record.

Revision ID: 056
Revises: 055
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa


revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("fleet_company_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "fleet_company_name")
