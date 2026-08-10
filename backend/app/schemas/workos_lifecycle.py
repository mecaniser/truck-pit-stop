from datetime import datetime
from typing import Any, Dict, Optional
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
