"""add provider-neutral identity membership and invitation lifecycle

Revision ID: 112_identity_membership
Revises: 111_driver_accountability
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "112_identity_membership"
down_revision = "111_driver_accountability"
branch_labels = None
depends_on = None


def _base_columns():
    return (
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=True)
    op.create_table(
        "identity_principals",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        *_base_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_identity_principals_user_id", "identity_principals", ["user_id"], unique=True)
    op.create_index("ix_identity_principals_status", "identity_principals", ["status"])
    op.create_table(
        "external_identities",
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_subject", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("email_snapshot", sa.String(255), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["principal_id"], ["identity_principals.id"]),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_external_identity_subject"),
    )
    op.create_index("ix_external_identities_principal_id", "external_identities", ["principal_id"])
    op.create_index("ix_external_identities_status", "external_identities", ["status"])
    op.create_table(
        "tenant_memberships",
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="workos"),
        sa.Column("provider_membership_id", sa.String(255), nullable=True),
        sa.Column("role_slug", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("resource_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["principal_id"], ["identity_principals.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("principal_id", "tenant_id", name="uq_tenant_membership_principal_tenant"),
        sa.UniqueConstraint("provider_membership_id"),
    )
    for name, columns, unique in (
        ("ix_tenant_memberships_principal_id", ["principal_id"], False),
        ("ix_tenant_memberships_tenant_id", ["tenant_id"], False),
        ("ix_tenant_memberships_provider_membership_id", ["provider_membership_id"], True),
        ("ix_tenant_memberships_role_slug", ["role_slug"], False),
        ("ix_tenant_memberships_status", ["status"], False),
    ):
        op.create_index(name, "tenant_memberships", columns, unique=unique)
    op.create_table(
        "tenant_invitations",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="workos"),
        sa.Column("provider_invitation_id", sa.String(255), nullable=True),
        sa.Column("email_snapshot", sa.String(255), nullable=False),
        sa.Column("intended_role_slug", sa.String(64), nullable=False),
        sa.Column("resource_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="creating"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["identity_principals.id"]),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"]),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("provider_invitation_id"),
    )
    for name, columns, unique in (
        ("ix_tenant_invitations_tenant_id", ["tenant_id"], False),
        ("ix_tenant_invitations_principal_id", ["principal_id"], False),
        ("ix_tenant_invitations_provider_invitation_id", ["provider_invitation_id"], True),
        ("ix_tenant_invitations_email_snapshot", ["email_snapshot"], False),
        ("ix_tenant_invitations_driver_profile_id", ["driver_profile_id"], False),
        ("ix_tenant_invitations_status", ["status"], False),
        ("ix_tenant_invitations_invited_by_user_id", ["invited_by_user_id"], False),
    ):
        op.create_index(name, "tenant_invitations", columns, unique=unique)
    op.create_table(
        "workos_event_receipts",
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="received"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        *_base_columns(),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_workos_event_receipts_event_id", "workos_event_receipts", ["event_id"], unique=True)
    op.create_index("ix_workos_event_receipts_event_type", "workos_event_receipts", ["event_type"])
    op.create_index("ix_workos_event_receipts_status", "workos_event_receipts", ["status"])


def downgrade() -> None:
    op.drop_table("workos_event_receipts")
    op.drop_table("tenant_invitations")
    op.drop_table("tenant_memberships")
    op.drop_table("external_identities")
    op.drop_table("identity_principals")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM users WHERE hashed_password IS NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade while WorkOS-only users exist; deactivate and migrate them explicitly first';
            END IF;
        END $$
    """)
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=False)
