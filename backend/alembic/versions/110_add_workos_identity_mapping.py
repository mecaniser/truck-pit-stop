"""add WorkOS organization and user identity mappings

Revision ID: 110_workos_identity_mapping
Revises: 109_ets_last_synced_at
"""
from alembic import op
import sqlalchemy as sa


revision = "110_workos_identity_mapping"
down_revision = "109_ets_last_synced_at"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenants", sa.Column("workos_organization_id", sa.String(255), nullable=True))
    op.create_index("ix_tenants_workos_organization_id", "tenants", ["workos_organization_id"], unique=True)
    op.add_column("users", sa.Column("workos_user_id", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("workos_identity_status", sa.String(32), nullable=False, server_default="legacy"),
    )
    op.add_column("users", sa.Column("workos_identity_linked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_workos_user_id", "users", ["workos_user_id"], unique=True)


def downgrade():
    op.drop_index("ix_users_workos_user_id", table_name="users")
    op.drop_column("users", "workos_identity_linked_at")
    op.drop_column("users", "workos_identity_status")
    op.drop_column("users", "workos_user_id")
    op.drop_index("ix_tenants_workos_organization_id", table_name="tenants")
    op.drop_column("tenants", "workos_organization_id")
