"""add durable provider outbox

Revision ID: 082
Revises: 081
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_token", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "event_type",
            "idempotency_key",
            name="uq_provider_outbox_tenant_event_idempotency",
        ),
    )
    op.create_index("ix_provider_outbox_due", "provider_outbox", ["status", "available_at"], unique=False)
    op.create_index("ix_provider_outbox_tenant_created", "provider_outbox", ["tenant_id", "created_at"], unique=False)
    op.create_index(op.f("ix_provider_outbox_aggregate_id"), "provider_outbox", ["aggregate_id"], unique=False)
    op.create_index(op.f("ix_provider_outbox_event_type"), "provider_outbox", ["event_type"], unique=False)
    op.create_index(op.f("ix_provider_outbox_locked_until"), "provider_outbox", ["locked_until"], unique=False)
    op.create_index(op.f("ix_provider_outbox_lock_token"), "provider_outbox", ["lock_token"], unique=False)
    op.create_index(op.f("ix_provider_outbox_status"), "provider_outbox", ["status"], unique=False)
    op.create_index(op.f("ix_provider_outbox_tenant_id"), "provider_outbox", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_table("provider_outbox")
