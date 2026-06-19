"""add fleet_manager role + internal fleet house account

Adds:
- 'fleet_manager' to the userrole enum (garage-side staff managing the owned fleet)
- customers.is_internal_fleet — flags the garage's house-account customer
- repair_orders.is_internal — flags an internal-cost (no-markup, no-invoice) repair
- tenants.internal_labor_rate — hourly labor cost rate for internal fleet repairs

Backfills exactly one internal-fleet customer per tenant.

Revision ID: 047
Revises: 046
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa


revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. New staff role
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'fleet_manager'")

    # 2. Columns
    op.add_column(
        "customers",
        sa.Column("is_internal_fleet", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_customers_is_internal_fleet", "customers", ["is_internal_fleet"], unique=False
    )
    op.add_column(
        "repair_orders",
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_repair_orders_is_internal", "repair_orders", ["is_internal"], unique=False)
    op.add_column(
        "tenants",
        sa.Column(
            "internal_labor_rate",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0.00",
        ),
    )

    # 3. Backfill: one internal-fleet house-account customer per tenant.
    # Email is unique-indexed (non-unique index) but the column itself is not a
    # unique constraint, so a deterministic per-tenant address is safe.
    op.execute(
        """
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, company_name, email,
            is_internal_fleet, sms_opt_out, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), t.id, 'Internal', 'Fleet', 'House Account',
            'fleet+' || t.id || '@internal.local',
            TRUE, FALSE, NOW(), NOW()
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM customers c
            WHERE c.tenant_id = t.id AND c.is_internal_fleet = TRUE
        )
        """
    )

    # Drop server defaults now that existing rows are populated; the ORM owns the
    # default for new rows.
    op.alter_column("customers", "is_internal_fleet", server_default=None)
    op.alter_column("repair_orders", "is_internal", server_default=None)
    op.alter_column("tenants", "internal_labor_rate", server_default=None)


def downgrade() -> None:
    op.execute("DELETE FROM customers WHERE is_internal_fleet = TRUE")
    op.drop_column("tenants", "internal_labor_rate")
    op.drop_index("ix_repair_orders_is_internal", table_name="repair_orders")
    op.drop_column("repair_orders", "is_internal")
    op.drop_index("ix_customers_is_internal_fleet", table_name="customers")
    op.drop_column("customers", "is_internal_fleet")
    # Note: PostgreSQL cannot drop an enum value; 'fleet_manager' is left in place.
