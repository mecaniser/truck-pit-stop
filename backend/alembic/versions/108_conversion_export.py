"""Supported paid repair-order conversion export.

Revision ID: 108_conversion_export
Revises: 107_merge_reviews_authorizations
"""
from alembic import op
import sqlalchemy as sa

revision = "108_conversion_export"
down_revision = "107_merge_reviews_authorizations"
branch_labels = None
depends_on = None


ATTRIBUTION_COLUMNS = (
    ("lead_source_channel", 64), ("external_lead_id", 255), ("callrail_call_id", 255),
    ("google_click_id", 255), ("gbraid", 255), ("wbraid", 255),
    ("landing_page_url", 2048), ("utm_source", 255), ("utm_medium", 255),
    ("utm_campaign", 255), ("utm_term", 255), ("utm_content", 255),
)


def upgrade() -> None:
    op.add_column("tenants", sa.Column("paid_invoice_webhook_url", sa.String(2048)))
    op.add_column("tenants", sa.Column("paid_invoice_webhook_secret_encrypted", sa.Text()))
    op.add_column("tenants", sa.Column("paid_invoice_webhook_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    for name, length in ATTRIBUTION_COLUMNS:
        op.add_column("repair_orders", sa.Column(name, sa.String(length)))
    for name in ("lead_source_channel", "external_lead_id", "callrail_call_id", "google_click_id"):
        op.create_index(f"ix_repair_orders_{name}", "repair_orders", [name])
    op.add_column("provider_outbox", sa.Column("last_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("provider_outbox", sa.Column("last_response_code", sa.Integer()))
    op.create_table(
        "conversion_api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    for name in ("tenant_id", "key_prefix", "revoked_at"):
        op.create_index(f"ix_conversion_api_keys_{name}", "conversion_api_keys", [name])


def downgrade() -> None:
    op.drop_table("conversion_api_keys")
    op.drop_column("provider_outbox", "last_response_code")
    op.drop_column("provider_outbox", "last_attempt_at")
    for name, _ in reversed(ATTRIBUTION_COLUMNS):
        if name in {"lead_source_channel", "external_lead_id", "callrail_call_id", "google_click_id"}:
            op.drop_index(f"ix_repair_orders_{name}", table_name="repair_orders")
        op.drop_column("repair_orders", name)
    op.drop_column("tenants", "paid_invoice_webhook_enabled")
    op.drop_column("tenants", "paid_invoice_webhook_secret_encrypted")
    op.drop_column("tenants", "paid_invoice_webhook_url")
