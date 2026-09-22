"""Opt-in ELIS outcome identity and delivery-only pause; preserve v1 defaults."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "148_elis_outcome_source"
down_revision = "147_credit_link_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenants", sa.Column("paid_invoice_webhook_delivery_paused", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("tenants", sa.Column("paid_invoice_webhook_payload_version", sa.Integer(), server_default="1", nullable=False))
    op.create_check_constraint("ck_tenant_webhook_payload_version", "tenants", "paid_invoice_webhook_payload_version IN (1, 2)")
    op.add_column("repair_orders", sa.Column("elis_opportunity_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_repair_orders_elis_opportunity_id", "repair_orders", ["elis_opportunity_id"])


def downgrade():
    op.drop_index("ix_repair_orders_elis_opportunity_id", table_name="repair_orders")
    op.drop_column("repair_orders", "elis_opportunity_id")
    op.drop_constraint("ck_tenant_webhook_payload_version", "tenants", type_="check")
    op.drop_column("tenants", "paid_invoice_webhook_payload_version")
    op.drop_column("tenants", "paid_invoice_webhook_delivery_paused")
