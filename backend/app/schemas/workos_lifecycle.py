from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class WorkOSInvitationCreate(BaseModel):
    email: EmailStr
    role_slug: str = Field(min_length=1, max_length=64)
    driver_profile_id: Optional[UUID] = None
    resource_scope: Dict[str, Any] = Field(default_factory=dict)


class WorkOSInvitationResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    provider_invitation_id: Optional[str]
    email: str
    role_slug: str
    driver_profile_id: Optional[UUID]
    status: str
    expires_at: Optional[datetime]


PortalAccessStatus = Literal[
    "not_invited",
    "pending",
    "active",
    "expired",
    "revoked",
    "suspended",
    "needs_review",
]


class DriverPortalAccessResponse(BaseModel):
    """Provider-neutral portal projection consumed by fleet manager UI."""

    driver_profile_id: UUID
    profile_status: Literal["active", "inactive"]
    portal_access_status: PortalAccessStatus
    local_user_id: Optional[UUID] = None
    invitation_id: Optional[UUID] = None
    email: Optional[str] = None
    invited_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    last_sign_in_at: Optional[datetime] = None
    can_invite: bool
    can_resend: bool
    can_revoke: bool


class DriverInvitationCapability(BaseModel):
    available: bool
    reason: Literal[
        "available",
        "workos_auth_disabled",
        "organization_not_provisioned",
        "manager_not_provisioned",
        "workos_reauthentication_required",
        "missing_permission",
    ]
    required_permission: Literal["members:manage"] = "members:manage"
    reauth_path: Optional[str] = None


class WorkOSCapabilitiesResponse(BaseModel):
    session_provider: Literal["legacy", "workos"]
    workos_auth_enabled: bool
    organization_provisioned: bool
    driver_invitation_management: DriverInvitationCapability


class WorkOSSessionResponse(BaseModel):
    message: str
    expires_in: int


class WorkOSWebhookResponse(BaseModel):
    status: str


class WorkOSOrganizationProvision(BaseModel):
    tenant_id: UUID
    owner_email: EmailStr


class WorkOSOrganizationResponse(BaseModel):
    tenant_id: UUID
    workos_organization_id: str
    owner_invitation: WorkOSInvitationResponse
