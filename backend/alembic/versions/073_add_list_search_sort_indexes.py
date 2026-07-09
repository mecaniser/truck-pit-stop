"""add pg_trgm + indexes to speed up customer / repair-order list search & sort

Backs the new server-side search/sort on GET /customers and GET /repair-orders:
- pg_trgm extension so ILIKE '%term%' can use a GIN trigram index.
- Trigram GIN indexes on the searchable text columns.
- A (tenant_id, created_at DESC) composite on repair_orders for the default list
  ordering.

All indexes are IF NOT EXISTS / created concurrently-safe (plain CREATE INDEX here;
tables are small enough that a blocking build is fine, and CONCURRENTLY can't run
inside Alembic's transaction).

Revision ID: 073
Revises: 072
Create Date: 2026-07-09
"""
from alembic import op


revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Customers — trigram indexes for ILIKE substring search.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_first_name_trgm "
        "ON customers USING gin (first_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_last_name_trgm "
        "ON customers USING gin (last_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_company_name_trgm "
        "ON customers USING gin (company_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_email_trgm "
        "ON customers USING gin (email gin_trgm_ops)"
    )

    # Repair orders — trigram search on order number + description.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_repair_orders_order_number_trgm "
        "ON repair_orders USING gin (order_number gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_repair_orders_description_trgm "
        "ON repair_orders USING gin (description gin_trgm_ops)"
    )
    # Default list ordering: newest-first within a tenant.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_repair_orders_tenant_created_at "
        "ON repair_orders (tenant_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_repair_orders_tenant_created_at")
    op.execute("DROP INDEX IF EXISTS ix_repair_orders_description_trgm")
    op.execute("DROP INDEX IF EXISTS ix_repair_orders_order_number_trgm")
    op.execute("DROP INDEX IF EXISTS ix_customers_email_trgm")
    op.execute("DROP INDEX IF EXISTS ix_customers_company_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_customers_last_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_customers_first_name_trgm")
    # Leave the pg_trgm extension in place — other objects may depend on it.
