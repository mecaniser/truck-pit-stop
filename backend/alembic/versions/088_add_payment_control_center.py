"""add platform payment control center fields

Revision ID: 088
Revises: 087
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("stripe_platform_fee_percent", sa.Numeric(5, 3), nullable=True))
    op.add_column("tenants", sa.Column("stripe_platform_fee_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("stripe_platform_fee_updated_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_tenants_stripe_platform_fee_updated_by_id_users",
        "tenants",
        "users",
        ["stripe_platform_fee_updated_by_id"],
        ["id"],
    )
    op.add_column("tenants", sa.Column("stripe_last_webhook_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("stripe_last_webhook_event", sa.String(100), nullable=True))
    op.add_column("tenants", sa.Column("stripe_last_webhook_error", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("stripe_connected_account_id", sa.String(255), nullable=True))
    op.create_index("ix_payments_stripe_connected_account_id", "payments", ["stripe_connected_account_id"], unique=False)
    op.add_column("payments", sa.Column("stripe_platform_fee_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("payments", sa.Column("stripe_platform_fee_percent", sa.Numeric(5, 3), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "stripe_platform_fee_percent")
    op.drop_column("payments", "stripe_platform_fee_amount")
    op.drop_index("ix_payments_stripe_connected_account_id", table_name="payments")
    op.drop_column("payments", "stripe_connected_account_id")
    op.drop_column("tenants", "stripe_last_webhook_error")
    op.drop_column("tenants", "stripe_last_webhook_event")
    op.drop_column("tenants", "stripe_last_webhook_at")
    op.drop_constraint("fk_tenants_stripe_platform_fee_updated_by_id_users", "tenants", type_="foreignkey")
    op.drop_column("tenants", "stripe_platform_fee_updated_by_id")
    op.drop_column("tenants", "stripe_platform_fee_updated_at")
    op.drop_column("tenants", "stripe_platform_fee_percent")
