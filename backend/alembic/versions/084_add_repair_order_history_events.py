"""add durable repair-order history events

Revision ID: 084
Revises: 083
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repair_order_history_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repair_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["repair_order_id"], ["repair_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_repair_order_history_events_tenant_id", "repair_order_history_events", ["tenant_id"])
    op.create_index("ix_repair_order_history_events_repair_order_id", "repair_order_history_events", ["repair_order_id"])
    op.create_index("ix_repair_order_history_events_event_type", "repair_order_history_events", ["event_type"])
    op.create_index("ix_repair_order_history_events_entity_id", "repair_order_history_events", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_repair_order_history_events_entity_id", table_name="repair_order_history_events")
    op.drop_index("ix_repair_order_history_events_event_type", table_name="repair_order_history_events")
    op.drop_index("ix_repair_order_history_events_repair_order_id", table_name="repair_order_history_events")
    op.drop_index("ix_repair_order_history_events_tenant_id", table_name="repair_order_history_events")
    op.drop_table("repair_order_history_events")
