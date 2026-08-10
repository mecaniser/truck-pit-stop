"""add invitation audit events

Revision ID: 114_invitation_audit
Revises: 113_merge_identity_balance
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "114_invitation_audit"
down_revision = "113_merge_identity_balance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_invitation_audit_events",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invitation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("status_from", sa.String(24), nullable=True),
        sa.Column("status_to", sa.String(24), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["invitation_id"], ["tenant_invitations.id"]),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_event_id"),
    )
    for name, columns, unique in (
        ("ix_tenant_invitation_audit_events_tenant_id", ["tenant_id"], False),
        ("ix_tenant_invitation_audit_events_invitation_id", ["invitation_id"], False),
        ("ix_tenant_invitation_audit_events_driver_profile_id", ["driver_profile_id"], False),
        ("ix_tenant_invitation_audit_events_actor_user_id", ["actor_user_id"], False),
        ("ix_tenant_invitation_audit_events_action", ["action"], False),
        ("ix_tenant_invitation_audit_events_provider_event_id", ["provider_event_id"], True),
    ):
        op.create_index(name, "tenant_invitation_audit_events", columns, unique=unique)


def downgrade() -> None:
    op.drop_table("tenant_invitation_audit_events")
