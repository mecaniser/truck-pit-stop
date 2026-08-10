"""Signed, idempotent WorkOS reconciliation authority."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.redis import increment_token_version
from app.db.models.identity import (
    ExternalIdentity,
    IdentityPrincipal,
    TenantInvitation,
    TenantInvitationAuditEvent,
    TenantMembership,
    WorkOSEventReceipt,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User


SIGNATURE_TOLERANCE_SECONDS = 300


def verify_signature(raw_body: bytes, signature_header: Optional[str], *, now: Optional[float] = None) -> Dict[str, Any]:
    if not settings.WORKOS_WEBHOOK_SECRET or not signature_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WorkOS webhook signature")
    values = {}
    for part in signature_header.split(","):
        key, separator, value = part.strip().partition("=")
        if separator:
            values[key] = value
    try:
        issued_ms = int(values["t"])
        supplied = values["v1"]
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WorkOS webhook signature")
    current = time.time() if now is None else now
    if abs(current - issued_ms / 1000) > SIGNATURE_TOLERANCE_SECONDS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired WorkOS webhook signature")
    signed = str(issued_ms).encode() + b"." + raw_body
    expected = hmac.new(settings.WORKOS_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WorkOS webhook signature")
    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WorkOS webhook payload")
    if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not isinstance(event.get("event"), str) or not isinstance(event.get("data"), dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WorkOS webhook payload")
    return event


async def _revoke_principal(principal_id, db: AsyncSession) -> None:
    principal = await db.get(IdentityPrincipal, principal_id)
    if principal and principal.user_id:
        await increment_token_version(str(principal.user_id))


async def _sync_membership(event_type: str, data: Dict[str, Any], db: AsyncSession) -> None:
    provider_id = data.get("id")
    workos_user_id = data.get("user_id")
    workos_org_id = data.get("organization_id")
    external = (await db.execute(select(ExternalIdentity).where(
        ExternalIdentity.provider == "workos", ExternalIdentity.provider_subject == workos_user_id
    ))).scalar_one_or_none()
    tenant = (await db.execute(select(Tenant).where(Tenant.workos_organization_id == workos_org_id))).scalar_one_or_none()
    if not external or not tenant:
        return
    membership = (await db.execute(select(TenantMembership).where(
        TenantMembership.principal_id == external.principal_id,
        TenantMembership.tenant_id == tenant.id,
    ))).scalar_one_or_none()
    if not membership:
        return
    if provider_id:
        membership.provider_membership_id = provider_id
    role = data.get("role")
    role_slug = role.get("slug") if isinstance(role, dict) else data.get("role_slug")
    if isinstance(role_slug, str):
        membership.role_slug = role_slug
    provider_status = data.get("status")
    if event_type.endswith(".deleted") or provider_status in {"inactive", "pending", "deleted"}:
        membership.status = "inactive"
    elif provider_status == "active":
        membership.status = "active"
    membership.provider_updated_at = datetime.now(timezone.utc)
    # Any membership mutation revokes the existing local projection. The next
    # server-side refresh rebuilds permissions from a newly verified token.
    await _revoke_principal(external.principal_id, db)


async def _sync_invitation(event_id: str, event_type: str, data: Dict[str, Any], db: AsyncSession) -> None:
    invitation = (await db.execute(select(TenantInvitation).where(
        TenantInvitation.provider_invitation_id == data.get("id")
    ))).scalar_one_or_none()
    if not invitation:
        return
    previous = invitation.status
    state = data.get("state")
    invitation.status = state if state in {"pending", "accepted", "revoked", "expired"} else invitation.status
    if state == "accepted":
        invitation.accepted_at = datetime.now(timezone.utc)
    if state == "revoked":
        invitation.revoked_at = datetime.now(timezone.utc)
    if invitation.status != previous:
        db.add(TenantInvitationAuditEvent(
            tenant_id=invitation.tenant_id,
            invitation_id=invitation.id,
            driver_profile_id=invitation.driver_profile_id,
            actor_user_id=None,
            action="provider_reconciled",
            status_from=previous,
            status_to=invitation.status,
            provider_event_id=event_id,
            metadata_json={"event_type": event_type},
        ))


async def _sync_user(event_type: str, data: Dict[str, Any], db: AsyncSession) -> None:
    external = (await db.execute(select(ExternalIdentity).where(
        ExternalIdentity.provider == "workos", ExternalIdentity.provider_subject == data.get("id")
    ))).scalar_one_or_none()
    if not external:
        return
    external.email_snapshot = data.get("email") or external.email_snapshot
    if event_type.endswith(".deleted"):
        external.status = "deleted"
        principal = await db.get(IdentityPrincipal, external.principal_id)
        if principal:
            principal.status = "inactive"
            # WorkOS-only projections have no alternate local credential.
            if principal.user_id:
                user = await db.get(User, principal.user_id)
                if user and user.hashed_password is None:
                    user.is_active = False
                if user:
                    user.workos_identity_status = "deleted"
    await _revoke_principal(external.principal_id, db)


async def _revoke_org(data: Dict[str, Any], db: AsyncSession) -> None:
    org_id = data.get("organization_id")
    if not org_id and isinstance(data.get("organization"), dict):
        org_id = data["organization"].get("id")
    if not org_id:
        return
    tenant = (await db.execute(select(Tenant).where(Tenant.workos_organization_id == org_id))).scalar_one_or_none()
    if not tenant:
        memberships = (await db.execute(select(TenantMembership))).scalars().all()
    else:
        memberships = (await db.execute(select(TenantMembership).where(TenantMembership.tenant_id == tenant.id))).scalars().all()
    for membership in memberships:
        await _revoke_principal(membership.principal_id, db)


async def process_event(event: Dict[str, Any], raw_body: bytes, db: AsyncSession) -> str:
    event_id, event_type, data = event["id"], event["event"], event["data"]
    if (await db.execute(select(WorkOSEventReceipt.id).where(WorkOSEventReceipt.event_id == event_id))).scalar_one_or_none():
        return "duplicate"
    receipt = WorkOSEventReceipt(
        event_id=event_id,
        event_type=event_type,
        payload_sha256=hashlib.sha256(raw_body).hexdigest(),
        status="received",
    )
    db.add(receipt)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return "duplicate"
    if event_type.startswith("organization_membership."):
        await _sync_membership(event_type, data, db)
    elif event_type.startswith("invitation."):
        await _sync_invitation(event_id, event_type, data, db)
    elif event_type.startswith("user."):
        await _sync_user(event_type, data, db)
    elif event_type.startswith(("organization_role.", "permission.")):
        await _revoke_org(data, db)
    receipt.status = "processed"
    receipt.processed_at = datetime.now(timezone.utc)
    await db.commit()
    return "processed"
