"""Provider-neutral identity, tenant membership, and invitation projections."""
from sqlalchemy import Column, String, ForeignKey, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import BaseModel


class IdentityPrincipal(BaseModel):
    __tablename__ = "identity_principals"

    # A principal is a durable person/account anchor. A local User projection is
    # optional until an invitation is accepted and is never linked by email.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, unique=True, index=True)
    status = Column(String(24), nullable=False, default="pending", server_default="pending", index=True)


class ExternalIdentity(BaseModel):
    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_subject", name="uq_external_identity_subject"),)

    principal_id = Column(UUID(as_uuid=True), ForeignKey("identity_principals.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    provider_subject = Column(String(255), nullable=False)
    status = Column(String(24), nullable=False, default="active", server_default="active", index=True)
    email_snapshot = Column(String(255), nullable=True)


class TenantMembership(BaseModel):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("principal_id", "tenant_id", name="uq_tenant_membership_principal_tenant"),)

    principal_id = Column(UUID(as_uuid=True), ForeignKey("identity_principals.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="workos", server_default="workos")
    provider_membership_id = Column(String(255), nullable=True, unique=True, index=True)
    role_slug = Column(String(64), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="pending", server_default="pending", index=True)
    permissions = Column(JSONB, nullable=False, default=list, server_default="[]")
    resource_scope = Column(JSONB, nullable=False, default=dict, server_default="{}")
    provider_updated_at = Column(DateTime(timezone=True), nullable=True)


class TenantInvitation(BaseModel):
    __tablename__ = "tenant_invitations"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    principal_id = Column(UUID(as_uuid=True), ForeignKey("identity_principals.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="workos", server_default="workos")
    provider_invitation_id = Column(String(255), nullable=True, unique=True, index=True)
    email_snapshot = Column(String(255), nullable=False, index=True)
    intended_role_slug = Column(String(64), nullable=False)
    resource_scope = Column(JSONB, nullable=False, default=dict, server_default="{}")
    driver_profile_id = Column(UUID(as_uuid=True), ForeignKey("driver_profiles.id"), nullable=True, index=True)
    # Explicit local identity target for an already-existing staff account.
    # This is never inferred from email; exact provider invitation acceptance
    # is still required before the WorkOS identity is attached.
    target_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    # Provider identifiers captured only after exact invitation acceptance is
    # proven. They let an administrator deactivate the precise membership
    # during a reviewed collision cleanup without using email as identity.
    provider_user_id = Column(String(255), nullable=True, index=True)
    provider_membership_id = Column(String(255), nullable=True, index=True)
    review_reason = Column(String(64), nullable=True, index=True)
    status = Column(String(24), nullable=False, default="creating", server_default="creating", index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)


class TenantInvitationAuditEvent(BaseModel):
    """Append-only manager/provider actions affecting a tenant invitation."""

    __tablename__ = "tenant_invitation_audit_events"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invitation_id = Column(UUID(as_uuid=True), ForeignKey("tenant_invitations.id"), nullable=False, index=True)
    driver_profile_id = Column(UUID(as_uuid=True), ForeignKey("driver_profiles.id"), nullable=True, index=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(48), nullable=False, index=True)
    status_from = Column(String(24), nullable=True)
    status_to = Column(String(24), nullable=False)
    provider_event_id = Column(String(255), nullable=True, unique=True, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict, server_default="{}")


class WorkOSEventReceipt(BaseModel):
    __tablename__ = "workos_event_receipts"

    event_id = Column(String(255), nullable=False, unique=True, index=True)
    event_type = Column(String(120), nullable=False, index=True)
    payload_sha256 = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False, default="received", server_default="received", index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
