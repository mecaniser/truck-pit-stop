"""add explicit existing-user invitation target

Revision ID: 115_invitation_target_user
Revises: 114_invitation_audit
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "115_invitation_target_user"
down_revision = "114_invitation_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_invitations",
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tenant_invitations_target_user_id_users",
        "tenant_invitations",
        "users",
        ["target_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_tenant_invitations_target_user_id",
        "tenant_invitations",
        ["target_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_invitations_target_user_id", table_name="tenant_invitations")
    op.drop_constraint(
        "fk_tenant_invitations_target_user_id_users",
        "tenant_invitations",
        type_="foreignkey",
    )
    op.drop_column("tenant_invitations", "target_user_id")
