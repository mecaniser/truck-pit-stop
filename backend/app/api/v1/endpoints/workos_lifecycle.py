"""WorkOS organization lifecycle, invitation, session, and webhook endpoints."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.dependencies import get_current_active_user
from app.core.redis import get_token_version
from app.core.security import create_access_token
from app.core.workos_auth import CurrentPrincipal, require_permission
from app.db.models.driver_accountability import DriverProfile
from app.db.models.identity import (
    ExternalIdentity,
    IdentityPrincipal,
    TenantInvitation,
    TenantInvitationAuditEvent,
    TenantMembership,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.schemas.workos_lifecycle import (
    WorkOSInvitationCreate,
    WorkOSInvitationResponse,
    DriverPortalAccessResponse,
    WorkOSSessionResponse,
    WorkOSWebhookResponse,
    WorkOSOrganizationProvision,
    WorkOSOrganizationResponse,
)
from app.services.identity_lifecycle import INVITABLE_ROLES, resolve_authenticated_identity
from app.services import workos_provider, workos_session, workos_webhooks
from app.services.workos_provider import WorkOSProviderError


router = APIRouter()


async def _platform_admin(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform administrator required")
    return current_user


def _cookie_domain() -> Optional[str]:
    value = settings.COOKIE_DOMAIN.strip()
    return value or None


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.WORKOS_ACCESS_TOKEN_MINUTES * 60,
        domain=_cookie_domain(),
        path="/",
    )


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        "workos_session",
        session_id,
        httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=workos_session.session_ttl_seconds(),
        domain=_cookie_domain(),
        path="/api/v1/auth/workos",
    )


def _invitation_response(invitation: TenantInvitation) -> WorkOSInvitationResponse:
    return WorkOSInvitationResponse(
        id=invitation.id,
        tenant_id=invitation.tenant_id,
        provider_invitation_id=invitation.provider_invitation_id,
        email=invitation.email_snapshot,
        role_slug=invitation.intended_role_slug,
        driver_profile_id=invitation.driver_profile_id,
        status=invitation.status,
        expires_at=invitation.expires_at,
    )


def _provider_datetime(value) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_expired(invitation: TenantInvitation) -> bool:
    if not invitation.expires_at:
        return False
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def _audit_invitation(
    db: AsyncSession,
    invitation: TenantInvitation,
    *,
    action: str,
    status_from: Optional[str],
    status_to: str,
    actor_user_id=None,
    provider_event_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    db.add(TenantInvitationAuditEvent(
        tenant_id=invitation.tenant_id,
        invitation_id=invitation.id,
        driver_profile_id=invitation.driver_profile_id,
        actor_user_id=actor_user_id,
        action=action,
        status_from=status_from,
        status_to=status_to,
        provider_event_id=provider_event_id,
        metadata_json=metadata or {},
    ))


async def _driver_for_manager(db: AsyncSession, driver_profile_id, tenant_id) -> DriverProfile:
    driver = (await db.execute(select(DriverProfile).where(
        DriverProfile.id == driver_profile_id,
        DriverProfile.tenant_id == tenant_id,
        DriverProfile.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver profile not found")
    return driver


async def _latest_driver_invitation(db: AsyncSession, driver: DriverProfile) -> Optional[TenantInvitation]:
    invitations = (await db.execute(
        select(TenantInvitation)
        .where(
            TenantInvitation.driver_profile_id == driver.id,
            TenantInvitation.tenant_id == driver.tenant_id,
            TenantInvitation.intended_role_slug == "driver",
            TenantInvitation.deleted_at.is_(None),
        )
        .order_by(TenantInvitation.created_at.desc(), TenantInvitation.id.desc())
    )).scalars().all()
    # A fresh live invitation supersedes terminal history. This avoids relying
    # on timestamp precision when a replacement is created in the same flush.
    live = next((item for item in invitations if item.status == "pending" and not _is_expired(item)), None)
    return live or (invitations[0] if invitations else None)


async def _driver_portal_projection(db: AsyncSession, driver: DriverProfile) -> DriverPortalAccessResponse:
    invitation = await _latest_driver_invitation(db, driver)
    access_status = "not_invited"

    if driver.user_id:
        user = await db.get(User, driver.user_id)
        principal = (await db.execute(select(IdentityPrincipal).where(
            IdentityPrincipal.user_id == driver.user_id,
            IdentityPrincipal.deleted_at.is_(None),
        ))).scalar_one_or_none()
        external = None
        membership = None
        if principal:
            external = (await db.execute(select(ExternalIdentity).where(
                ExternalIdentity.principal_id == principal.id,
                ExternalIdentity.provider == "workos",
                ExternalIdentity.deleted_at.is_(None),
            ))).scalar_one_or_none()
            membership = (await db.execute(select(TenantMembership).where(
                TenantMembership.principal_id == principal.id,
                TenantMembership.tenant_id == driver.tenant_id,
                TenantMembership.role_slug == "driver",
                TenantMembership.deleted_at.is_(None),
            ))).scalar_one_or_none()
        if not user or not principal or not external or not membership:
            access_status = "needs_review"
        elif not user.is_active or principal.status != "active" or external.status != "active" or membership.status != "active":
            access_status = "suspended"
        else:
            access_status = "active"
    elif invitation:
        if invitation.status == "pending" and _is_expired(invitation):
            access_status = "expired"
        elif invitation.status in {"pending", "expired", "revoked"}:
            access_status = invitation.status
        elif invitation.status == "accepted" or invitation.status == "creating":
            access_status = "needs_review"
        else:
            access_status = "needs_review"

    terminal_invitation = invitation and access_status in {"expired", "revoked"}
    return DriverPortalAccessResponse(
        driver_profile_id=driver.id,
        profile_status=driver.employment_status,
        portal_access_status=access_status,
        local_user_id=driver.user_id,
        invitation_id=invitation.id if invitation else None,
        email=invitation.email_snapshot if invitation else driver.email,
        invited_at=invitation.created_at if invitation else None,
        expires_at=invitation.expires_at if invitation else None,
        accepted_at=invitation.accepted_at if invitation else None,
        revoked_at=invitation.revoked_at if invitation else None,
        last_sign_in_at=None,
        can_invite=not driver.user_id and (not invitation or bool(terminal_invitation)),
        can_resend=not driver.user_id and access_status in {"pending", "expired", "revoked"},
        can_revoke=not driver.user_id and access_status == "pending",
    )


@router.post("/organizations/provision", response_model=WorkOSOrganizationResponse)
async def provision_organization(
    body: WorkOSOrganizationProvision,
    platform_admin: User = Depends(_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Provision an approved garage and invite its first owner idempotently."""
    tenant = await db.get(Tenant, body.tenant_id)
    if not tenant or tenant.deleted_at or tenant.enrollment_status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only an approved tenant can be provisioned")
    try:
        organization = await workos_provider.get_or_create_organization(tenant_id=str(tenant.id), name=tenant.name)
    except WorkOSProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if tenant.workos_organization_id and tenant.workos_organization_id != organization["id"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant is linked to a different WorkOS organization")
    tenant.workos_organization_id = organization["id"]
    existing = (await db.execute(select(TenantInvitation).where(
        TenantInvitation.tenant_id == tenant.id,
        TenantInvitation.email_snapshot == str(body.owner_email),
        TenantInvitation.intended_role_slug == "garage_owner",
        TenantInvitation.status.in_(("creating", "pending", "accepted")),
        TenantInvitation.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if existing:
        await db.commit()
        return WorkOSOrganizationResponse(
            tenant_id=tenant.id,
            workos_organization_id=tenant.workos_organization_id,
            owner_invitation=_invitation_response(existing),
        )
    identity = IdentityPrincipal(status="pending")
    db.add(identity)
    await db.flush()
    invitation = TenantInvitation(
        tenant_id=tenant.id,
        principal_id=identity.id,
        email_snapshot=str(body.owner_email),
        intended_role_slug="garage_owner",
        resource_scope={},
        status="creating",
        invited_by_user_id=platform_admin.id,
    )
    db.add(invitation)
    await db.flush()
    try:
        provider = await workos_provider.send_invitation(
            email=str(body.owner_email),
            organization_id=tenant.workos_organization_id,
            role_slug="garage_owner",
            inviter_user_id=platform_admin.workos_user_id,
        )
    except WorkOSProviderError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    invitation.provider_invitation_id = provider["id"]
    invitation.status = provider.get("state") if provider.get("state") in {"pending", "accepted"} else "pending"
    if isinstance(provider.get("expires_at"), str):
        invitation.expires_at = datetime.fromisoformat(provider["expires_at"].replace("Z", "+00:00"))
    _audit_invitation(
        db,
        invitation,
        action="created",
        status_from="creating",
        status_to=invitation.status,
        actor_user_id=platform_admin.id,
    )
    await db.commit()
    return WorkOSOrganizationResponse(
        tenant_id=tenant.id,
        workos_organization_id=tenant.workos_organization_id,
        owner_invitation=_invitation_response(invitation),
    )


@router.post("/invitations", response_model=WorkOSInvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    body: WorkOSInvitationCreate,
    principal: CurrentPrincipal = Depends(require_permission("members:manage")),
    db: AsyncSession = Depends(get_db),
):
    if body.role_slug not in INVITABLE_ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported WorkOS role")
    if body.role_slug == "garage_owner" and "organization:manage" not in principal.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner invitations require organization management")
    tenant = await db.get(Tenant, principal.tenant_id)
    if not tenant or not tenant.workos_organization_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant has no WorkOS organization")
    if body.role_slug == "driver":
        if not body.driver_profile_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A driver profile is required")
        driver = (await db.execute(select(DriverProfile).where(
            DriverProfile.id == body.driver_profile_id,
        ).with_for_update())).scalar_one_or_none()
        if not driver or driver.tenant_id != principal.tenant_id or driver.deleted_at or driver.user_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Driver profile is not available for linking")
        existing = (await db.execute(select(TenantInvitation.id).where(
            TenantInvitation.driver_profile_id == driver.id,
            TenantInvitation.tenant_id == principal.tenant_id,
            TenantInvitation.status.in_(("creating", "pending", "accepted")),
            TenantInvitation.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Driver profile already has a live portal invitation")
    elif body.driver_profile_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Driver profile is valid only for driver invitations")

    identity = IdentityPrincipal(status="pending")
    db.add(identity)
    await db.flush()
    invitation = TenantInvitation(
        tenant_id=principal.tenant_id,
        principal_id=identity.id,
        email_snapshot=str(body.email),
        intended_role_slug=body.role_slug,
        resource_scope=body.resource_scope,
        driver_profile_id=body.driver_profile_id,
        status="creating",
        invited_by_user_id=principal.local_user_id,
    )
    db.add(invitation)
    await db.flush()
    try:
        provider = await workos_provider.send_invitation(
            email=str(body.email),
            organization_id=tenant.workos_organization_id,
            role_slug=body.role_slug,
            inviter_user_id=principal.workos_user_id,
        )
    except WorkOSProviderError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    invitation.provider_invitation_id = provider["id"]
    invitation.status = provider.get("state") if provider.get("state") in {"pending", "accepted"} else "pending"
    expires_at = provider.get("expires_at")
    if isinstance(expires_at, str):
        invitation.expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    _audit_invitation(
        db,
        invitation,
        action="created",
        status_from="creating",
        status_to=invitation.status,
        actor_user_id=principal.local_user_id,
    )
    await db.commit()
    return _invitation_response(invitation)


@router.get("/driver-profiles/{driver_profile_id}/portal-access", response_model=DriverPortalAccessResponse)
async def get_driver_portal_access(
    driver_profile_id: str,
    principal: CurrentPrincipal = Depends(require_permission("members:manage")),
    db: AsyncSession = Depends(get_db),
):
    driver = await _driver_for_manager(db, driver_profile_id, principal.tenant_id)
    return await _driver_portal_projection(db, driver)


async def _driver_invitation_for_manager(
    db: AsyncSession,
    invitation_id: str,
    tenant_id,
) -> tuple[TenantInvitation, DriverProfile]:
    invitation = (await db.execute(select(TenantInvitation).where(
        TenantInvitation.id == invitation_id,
        TenantInvitation.tenant_id == tenant_id,
        TenantInvitation.intended_role_slug == "driver",
        TenantInvitation.driver_profile_id.is_not(None),
        TenantInvitation.deleted_at.is_(None),
    ).with_for_update())).scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver portal invitation not found")
    driver = await _driver_for_manager(db, invitation.driver_profile_id, tenant_id)
    return invitation, driver


@router.post("/invitations/{invitation_id}/resend", response_model=DriverPortalAccessResponse)
async def resend_driver_invitation(
    invitation_id: str,
    principal: CurrentPrincipal = Depends(require_permission("members:manage")),
    db: AsyncSession = Depends(get_db),
):
    invitation, driver = await _driver_invitation_for_manager(db, invitation_id, principal.tenant_id)
    if driver.user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Driver portal identity is already linked")
    effective_status = "expired" if invitation.status == "pending" and _is_expired(invitation) else invitation.status
    tenant = await db.get(Tenant, principal.tenant_id)
    if not tenant or not tenant.workos_organization_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant has no WorkOS organization")
    try:
        if effective_status == "pending":
            provider = await workos_provider.resend_invitation(invitation.provider_invitation_id)
            previous = invitation.status
            invitation.status = "pending"
            invitation.expires_at = _provider_datetime(provider.get("expires_at")) or invitation.expires_at
            target = invitation
            action = "resent"
        elif effective_status in {"expired", "revoked"}:
            if invitation.status == "pending":
                invitation.status = "expired"
                _audit_invitation(
                    db,
                    invitation,
                    action="expired_observed",
                    status_from="pending",
                    status_to="expired",
                    actor_user_id=principal.local_user_id,
                )
            invitation.status = effective_status
            provider = await workos_provider.send_invitation(
                email=invitation.email_snapshot,
                organization_id=tenant.workos_organization_id,
                role_slug="driver",
                inviter_user_id=principal.workos_user_id,
            )
            target = TenantInvitation(
                tenant_id=invitation.tenant_id,
                principal_id=invitation.principal_id,
                provider_invitation_id=provider["id"],
                email_snapshot=invitation.email_snapshot,
                intended_role_slug="driver",
                resource_scope=invitation.resource_scope,
                driver_profile_id=invitation.driver_profile_id,
                status="pending",
                expires_at=_provider_datetime(provider.get("expires_at")),
                invited_by_user_id=principal.local_user_id,
            )
            db.add(target)
            await db.flush()
            previous = None
            action = "reissued"
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation cannot be resent in its current state")
    except WorkOSProviderError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    _audit_invitation(
        db,
        target,
        action=action,
        status_from=previous,
        status_to=target.status,
        actor_user_id=principal.local_user_id,
        metadata={"replaces_invitation_id": str(invitation.id)} if target.id != invitation.id else {},
    )
    await db.commit()
    return await _driver_portal_projection(db, driver)


@router.post("/invitations/{invitation_id}/revoke", response_model=DriverPortalAccessResponse)
async def revoke_driver_invitation(
    invitation_id: str,
    principal: CurrentPrincipal = Depends(require_permission("members:manage")),
    db: AsyncSession = Depends(get_db),
):
    invitation, driver = await _driver_invitation_for_manager(db, invitation_id, principal.tenant_id)
    if driver.user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active portal access must be suspended through membership management")
    effective_status = "expired" if invitation.status == "pending" and _is_expired(invitation) else invitation.status
    if effective_status in {"revoked", "expired"}:
        if invitation.status == "pending":
            invitation.status = "expired"
            _audit_invitation(
                db,
                invitation,
                action="expired_observed",
                status_from="pending",
                status_to="expired",
                actor_user_id=principal.local_user_id,
            )
        invitation.status = effective_status
        await db.commit()
        return await _driver_portal_projection(db, driver)
    if effective_status != "pending" or not invitation.provider_invitation_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation cannot be revoked in its current state")
    try:
        provider = await workos_provider.revoke_invitation(invitation.provider_invitation_id)
    except WorkOSProviderError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if provider.get("state") != "revoked":
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="WorkOS invitation revocation was not confirmed")
    invitation.status = "revoked"
    invitation.revoked_at = _provider_datetime(provider.get("revoked_at")) or datetime.now(timezone.utc)
    _audit_invitation(
        db,
        invitation,
        action="revoked",
        status_from="pending",
        status_to="revoked",
        actor_user_id=principal.local_user_id,
    )
    await db.commit()
    return await _driver_portal_projection(db, driver)


@router.get("/invitations/{invitation_id}", response_model=WorkOSInvitationResponse)
async def get_invitation_status(
    invitation_id: str,
    principal: CurrentPrincipal = Depends(require_permission("members:manage")),
    db: AsyncSession = Depends(get_db),
):
    invitation = (await db.execute(select(TenantInvitation).where(
        TenantInvitation.id == invitation_id,
        TenantInvitation.tenant_id == principal.tenant_id,
        TenantInvitation.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    return _invitation_response(invitation)


@router.post("/session/refresh", response_model=WorkOSSessionResponse)
async def refresh_session(
    request: Request,
    response: Response,
    workos_session_cookie: Optional[str] = Cookie(None, alias="workos_session"),
    db: AsyncSession = Depends(get_db),
):
    if not settings.WORKOS_AUTH_ENABLED or not workos_session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS session required")
    stored = await workos_session.get_session(workos_session_cookie)
    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS session expired")
    try:
        result = await workos_provider.authenticate({
            "grant_type": "refresh_token",
            "refresh_token": stored["refresh_token"],
            "organization_id": stored["workos_org_id"],
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        })
        claims = await workos_provider.verify_access_token(result.get("access_token"))
    except WorkOSProviderError:
        await workos_session.delete_session(workos_session_cookie)
        response.delete_cookie("workos_session", path="/api/v1/auth/workos", domain=_cookie_domain())
        response.delete_cookie("access_token", path="/", domain=_cookie_domain())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS session is no longer authorized")
    if claims["sub"] != stored["workos_user_id"] or claims["org_id"] != stored["workos_org_id"]:
        await workos_session.delete_session(workos_session_cookie)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS session identity changed")
    try:
        user, tenant, _ = await resolve_authenticated_identity(db, claims=claims, workos_user=result.get("user") or {})
    except HTTPException:
        await db.rollback()
        await workos_session.delete_session(workos_session_cookie)
        response.delete_cookie("workos_session", path="/api/v1/auth/workos", domain=_cookie_domain())
        response.delete_cookie("access_token", path="/", domain=_cookie_domain())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS membership is no longer authorized")
    if str(user.id) != stored["local_user_id"]:
        await workos_session.delete_session(workos_session_cookie)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS session identity changed")
    await db.commit()
    rotated = result.get("refresh_token")
    if not isinstance(rotated, str) or not await workos_session.rotate_session(workos_session_cookie, rotated):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS session could not be renewed")
    token_version = await get_token_version(str(user.id))
    local_token = create_access_token(
        data={
            "sub": str(user.id),
            "auth_provider": "workos",
            "workos_user_id": claims["sub"],
            "workos_org_id": claims["org_id"],
            "permissions": claims["permissions"],
        },
        tenant_id=str(tenant.id),
        token_version=token_version,
        expires_delta=timedelta(minutes=settings.WORKOS_ACCESS_TOKEN_MINUTES),
    )
    _set_access_cookie(response, local_token)
    return WorkOSSessionResponse(message="WorkOS session renewed", expires_in=settings.WORKOS_ACCESS_TOKEN_MINUTES * 60)


@router.post("/webhook", response_model=WorkOSWebhookResponse, include_in_schema=False)
async def workos_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    event = workos_webhooks.verify_signature(raw, request.headers.get("workos-signature"))
    result = await workos_webhooks.process_event(event, raw, db)
    return WorkOSWebhookResponse(status=result)
