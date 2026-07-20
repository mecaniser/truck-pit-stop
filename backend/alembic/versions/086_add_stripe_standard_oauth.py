"""add Stripe Standard OAuth tenant authorization state

Revision ID: 086
Revises: 085
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("stripe_connection_type", sa.String(length=32), nullable=True))
    op.execute("UPDATE tenants SET stripe_connection_type = 'express_legacy' WHERE stripe_account_id IS NOT NULL")
    op.create_table(
        "stripe_oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["initiated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index(op.f("ix_stripe_oauth_states_state_hash"), "stripe_oauth_states", ["state_hash"], unique=True)
    op.create_index(op.f("ix_stripe_oauth_states_tenant_id"), "stripe_oauth_states", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_stripe_oauth_states_initiated_by_user_id"), "stripe_oauth_states", ["initiated_by_user_id"], unique=False)
    op.create_index(op.f("ix_stripe_oauth_states_expires_at"), "stripe_oauth_states", ["expires_at"], unique=False)
    op.create_index(op.f("ix_stripe_oauth_states_consumed_at"), "stripe_oauth_states", ["consumed_at"], unique=False)


def downgrade() -> None:
    op.drop_table("stripe_oauth_states")
    op.drop_column("tenants", "stripe_connection_type")
