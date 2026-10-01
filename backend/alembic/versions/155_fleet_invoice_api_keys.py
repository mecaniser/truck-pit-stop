"""DB-094: separate read-only credentials bound to one bill-to customer."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "155_fleet_invoice_api_keys"
down_revision = "154_fleet_telemetry_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("billed_customer_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_invoices_billed_customer_id", "invoices", ["billed_customer_id"])
    # Historical invoices remain NULL. Customer merges may already have
    # rewritten RO.customer_id, so it cannot authorize a historical export.
    op.create_table(
        "fleet_invoice_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key_hash", name="uq_fleet_invoice_api_keys_key_hash"),
    )
    op.create_index("ix_fleet_invoice_api_keys_tenant_id", "fleet_invoice_api_keys", ["tenant_id"])
    op.create_index("ix_fleet_invoice_api_keys_customer_id", "fleet_invoice_api_keys", ["customer_id"])
    op.create_index("ux_fleet_invoice_active_scope", "fleet_invoice_api_keys",
                    ["tenant_id", "customer_id"], unique=True,
                    postgresql_where=sa.text("revoked_at IS NULL"))


def downgrade():
    op.drop_index("ux_fleet_invoice_active_scope", table_name="fleet_invoice_api_keys")
    op.drop_index("ix_fleet_invoice_api_keys_customer_id", table_name="fleet_invoice_api_keys")
    op.drop_index("ix_fleet_invoice_api_keys_tenant_id", table_name="fleet_invoice_api_keys")
    op.drop_table("fleet_invoice_api_keys")
    op.drop_index("ix_invoices_billed_customer_id", table_name="invoices")
    op.drop_column("invoices", "billed_customer_id")
