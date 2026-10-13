"""Durable recommendation conversion and replay identity.

Retain this additive table on application rollback after adoption.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "166_recommendation_conversion"
down_revision = "164_motive_driver_journal"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recommendation_conversions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("recommendation_id", UUID(as_uuid=True), sa.ForeignKey("recommended_services.id"), nullable=False),
        sa.Column("source_order_id", UUID(as_uuid=True), sa.ForeignKey("repair_orders.id"), nullable=False),
        sa.Column("source_order_number", sa.String(255), nullable=False),
        sa.Column("source_description", sa.Text(), nullable=False),
        sa.Column("source_priority", sa.String(20), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=True), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("target_order_id", UUID(as_uuid=True), sa.ForeignKey("repair_orders.id"), nullable=False),
        sa.Column("target_order_number", sa.String(255), nullable=False),
        sa.Column("target_labor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("hours", sa.Numeric(5,2), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(10,2), nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_by_conversion_id", UUID(as_uuid=True), sa.ForeignKey("recommendation_conversions.id")),
        sa.UniqueConstraint("tenant_id", "request_id", name="uq_rec_conversion_request"),
        sa.UniqueConstraint("tenant_id", "target_labor_id", name="uq_rec_conversion_labor"),
    )
    for column in ("tenant_id", "recommendation_id", "target_order_id"):
        op.create_index(f"ix_recommendation_conversions_{column}", "recommendation_conversions", [column])
    op.create_index("uq_rec_conversion_current", "recommendation_conversions", ["tenant_id", "recommendation_id"], unique=True, postgresql_where=sa.text("superseded_at IS NULL"))


def downgrade():
    op.drop_table("recommendation_conversions")
