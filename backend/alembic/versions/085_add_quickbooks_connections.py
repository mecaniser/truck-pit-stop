"""add tenant-scoped QuickBooks OAuth connections

Revision ID: 085
Revises: 084
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quickbooks_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("realm_id", sa.String(length=64), nullable=True),
        sa.Column("scopes", sa.String(length=500), server_default="", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="disconnected", nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
        sa.UniqueConstraint("realm_id"),
    )
    op.create_index(op.f("ix_quickbooks_connections_status"), "quickbooks_connections", ["status"], unique=False)

    op.create_table(
        "quickbooks_oauth_states",
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
    op.create_index(op.f("ix_quickbooks_oauth_states_consumed_at"), "quickbooks_oauth_states", ["consumed_at"], unique=False)
    op.create_index(op.f("ix_quickbooks_oauth_states_expires_at"), "quickbooks_oauth_states", ["expires_at"], unique=False)
    op.create_index(op.f("ix_quickbooks_oauth_states_initiated_by_user_id"), "quickbooks_oauth_states", ["initiated_by_user_id"], unique=False)
    op.create_index(op.f("ix_quickbooks_oauth_states_tenant_id"), "quickbooks_oauth_states", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_table("quickbooks_oauth_states")
    op.drop_table("quickbooks_connections")
