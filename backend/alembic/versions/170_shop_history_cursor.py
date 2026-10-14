"""Durable bounded shop history capture cursor."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "170_shop_history_cursor"
down_revision = "169_external_service_history"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("shop_history_cursors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("last_invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("tenant_id", name="uq_shop_history_cursor_tenant"))
    op.create_index("ix_shop_history_cursors_id", "shop_history_cursors", ["id"])

    op.create_table("shop_history_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("source_revision", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "invoice_id", name="uq_shop_history_observation_invoice"),
        sa.CheckConstraint("sequence >= 1", name="ck_shop_history_observation_sequence"))
    op.create_index("ix_shop_history_observations_id", "shop_history_observations", ["id"])


def downgrade():
    op.drop_table("shop_history_observations")
    op.drop_table("shop_history_cursors")
