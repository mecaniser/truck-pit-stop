"""add invitation identity review state

Revision ID: 116_invitation_identity_review
Revises: 115_invitation_target_user
"""
from alembic import op
import sqlalchemy as sa


revision = "116_invitation_identity_review"
down_revision = "115_invitation_target_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenant_invitations", sa.Column("provider_user_id", sa.String(255), nullable=True))
    op.add_column("tenant_invitations", sa.Column("provider_membership_id", sa.String(255), nullable=True))
    op.add_column("tenant_invitations", sa.Column("review_reason", sa.String(64), nullable=True))
    op.create_index(
        "ix_tenant_invitations_provider_user_id",
        "tenant_invitations",
        ["provider_user_id"],
    )
    op.create_index(
        "ix_tenant_invitations_provider_membership_id",
        "tenant_invitations",
        ["provider_membership_id"],
    )
    op.create_index(
        "ix_tenant_invitations_review_reason",
        "tenant_invitations",
        ["review_reason"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_invitations_review_reason", table_name="tenant_invitations")
    op.drop_index("ix_tenant_invitations_provider_membership_id", table_name="tenant_invitations")
    op.drop_index("ix_tenant_invitations_provider_user_id", table_name="tenant_invitations")
    op.drop_column("tenant_invitations", "review_reason")
    op.drop_column("tenant_invitations", "provider_membership_id")
    op.drop_column("tenant_invitations", "provider_user_id")
