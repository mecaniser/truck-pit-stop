"""WorkOS organization lifecycle, invitation, session, and webhook endpoints."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.dependencies import get_current_active_user, get_token_from_request
from app.core.redis import get_token_version
from app.core.security import create_access_token, decode_token
from app.core.workos_auth import CurrentPrincipal, get_current_principal, require_permission
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
    DriverInvitationCapability,
    WorkOSCapabilitiesResponse,
    WorkOSSessionResponse,
    WorkOSWebhookResponse,
    WorkOSOrganizationProvision,
    WorkOSProductionRebind,
    WorkOSOrganizationResponse,
)
from app.schemas.auth import UserResponse
from app.services.identity_lifecycle import (
    IDENTITY_REVIEW_EMAIL_COLLISION,
    INVITABLE_ROLES,
    resolve_authenticated_identity,
)
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


def _safe_return_path(value: Optional[str]) -> str:
    return value if value and value.startswith("/") and not value.startswith("//") else "/"


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
        target_user_id=invitation.target_user_id,
        status=invitation.status,
        review_reason=invitation.review_reason,
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
        elif invitation.status in {"accepted", "creating", "needs_review"}:
            access_status = "needs_review"
        else:
            access_status = "needs_review"

    terminal_invitation = invitation and access_status in {"expired", "revoked"}
    collision_review = bool(invitation and invitation.review_reason == IDENTITY_REVIEW_EMAIL_COLLISION)
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
        review_reason=invitation.review_reason if invitation else None,
        last_sign_in_at=None,
        can_invite=not driver.user_id and (not invitation or bool(terminal_invitation)),
        can_resend=(
            not driver.user_id
            and access_status in {"pending", "expired"}
            and not collision_review
        ),
        can_revoke=not driver.user_id and access_status == "pending",
        can_cancel_review=(
            not driver.user_id
            and access_status == "needs_review"
            and collision_review
        ),
    )


@router.get("/capabilities", response_model=WorkOSCapabilitiesResponse)
async def get_workos_capabilities(
    return_to: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
    token: str = Depends(get_token_from_request),
    db: AsyncSession = Depends(get_db),
):
    """Describe whether this session may manage driver invitations.

    This endpoint is intentionally descriptive. Only ``require_permission``
    authorizes invitation actions; legacy roles never become WorkOS grants.
    """
    claims = decode_token(token) or {}
    session_provider = "workos" if claims.get("auth_provider") == "workos" else "legacy"
    tenant_id = claims.get("tid") or current_user.tenant_id
    tenant = await db.get(Tenant, tenant_id) if tenant_id else None
    organization_provisioned = bool(tenant and tenant.is_active and tenant.workos_organization_id)

    def response(reason: str, *, available: bool = False, reauth: bool = False):
        reauth_path = None
        if reauth:
            reauth_query = urlencode({
                'return_to': _safe_return_path(return_to),
                'tenant_id': str(tenant.id),
            })
            reauth_path = f"/auth/workos/login?{reauth_query}"
        return WorkOSCapabilitiesResponse(
            session_provider=session_provider,
            workos_auth_enabled=settings.WORKOS_AUTH_ENABLED,
            organization_provisioned=organization_provisioned,
            driver_invitation_management=DriverInvitationCapability(
                available=available,
                reason=reason,
                reauth_path=reauth_path,
            ),
        )

    if not settings.WORKOS_AUTH_ENABLED:
        return response("workos_auth_disabled")
    if not organization_provisioned:
        return response("organization_not_provisioned")

    if session_provider == "workos":
        try:
            principal = await get_current_principal(token=token, db=db)
        except HTTPException:
            return response("manager_not_provisioned")
        if "members:manage" not in principal.permissions:
            return response("missing_permission")
        return response("available", available=True)

    manager_roles = {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.FLEET_MANAGER}
    if current_user.role not in manager_roles:
        return response("manager_not_provisioned")
    projected_membership = (await db.execute(
        select(TenantMembership.id)
        .join(IdentityPrincipal, IdentityPrincipal.id == TenantMembership.principal_id)
        .where(
            IdentityPrincipal.user_id == current_user.id,
            IdentityPrincipal.status == "active",
            IdentityPrincipal.deleted_at.is_(None),
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.status == "active",
            TenantMembership.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not current_user.workos_user_id and not projected_membership:
        return response("manager_not_provisioned")
    return response("workos_reauthentication_required", reauth=True)


@router.get("/me", response_model=UserResponse)
async def get_workos_session_user(
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Bootstrap SPA state only from a validated WorkOS cookie session."""
    user = await db.get(User, principal.local_user_id)
    tenant = await db.get(Tenant, principal.tenant_id)
    if not user or not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS session is unavailable")
    result = UserResponse.model_validate(user)
    result.tenant_name = tenant.name
    result.tenant_slug = tenant.slug
    result.tenant_logo_url = tenant.logo_url
    result.messaging_enabled = tenant.messaging_enabled
    return result


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
    owner = await db.get(User, body.owner_user_id)
    if (
        not owner
        or owner.deleted_at
        or not owner.is_active
        or owner.tenant_id != tenant.id
        or owner.role != UserRole.GARAGE_OWNER
        or owner.email.casefold() != str(body.owner_email).casefold()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected owner account does not exactly match this tenant",
        )
    existing = (await db.execute(select(TenantInvitation).where(
        TenantInvitation.tenant_id == tenant.id,
        TenantInvitation.email_snapshot == str(body.owner_email),
        TenantInvitation.intended_role_slug == "garage_owner",
        TenantInvitation.target_user_id == owner.id,
        TenantInvitation.status.in_(("creating", "pending", "accepted")),
        TenantInvitation.deleted_at.is_(None),
    ))).scalar_one_or_none()
    identity = (await db.execute(select(IdentityPrincipal).where(
        IdentityPrincipal.user_id == owner.id,
        IdentityPrincipal.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if identity and not existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected owner already has an identity principal",
        )
    try:
        organization = await workos_provider.get_or_create_organization(tenant_id=str(tenant.id), name=tenant.name)
    except WorkOSProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if tenant.workos_organization_id and tenant.workos_organization_id != organization["id"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant is linked to a different WorkOS organization")
    tenant.workos_organization_id = organization["id"]
    if existing:
        await db.commit()
        return WorkOSOrganizationResponse(
            tenant_id=tenant.id,
            workos_organization_id=tenant.workos_organization_id,
            owner_invitation=_invitation_response(existing),
        )
    identity = IdentityPrincipal(user_id=owner.id, status="pending")
    db.add(identity)
    await db.flush()
    invitation = TenantInvitation(
        tenant_id=tenant.id,
        principal_id=identity.id,
        email_snapshot=str(body.owner_email),
        intended_role_slug="garage_owner",
        resource_scope={},
        target_user_id=owner.id,
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


@router.post("/organizations/rebind-production", response_model=WorkOSOrganizationResponse)
async def rebind_production_organization(
    body: WorkOSProductionRebind,
    platform_admin: User = Depends(_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Replace one exact Staging pilot projection with Production identities.

    This is intentionally narrower than ordinary provisioning. The caller must
    name every existing provider anchor, and the accepted Staging invitation is
    retained as superseded audit history. Domain records and the local User ID
    never change.
    """
    if (
        settings.ENVIRONMENT.strip().lower() != "production"
        or settings.WORKOS_ENVIRONMENT.strip().lower() != "production"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Production WorkOS rebinding is unavailable in this environment",
        )

    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == body.tenant_id).with_for_update()
    )).scalar_one_or_none()
    owner = (await db.execute(
        select(User).where(User.id == body.owner_user_id).with_for_update()
    )).scalar_one_or_none()
    if (
        not tenant
        or tenant.deleted_at
        or not tenant.is_active
        or tenant.enrollment_status != "approved"
        or not owner
        or owner.deleted_at
        or not owner.is_active
        or owner.tenant_id != tenant.id
        or owner.role != UserRole.GARAGE_OWNER
        or owner.email.casefold() != str(body.owner_email).casefold()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected owner account does not exactly match this tenant",
        )

    principal = (await db.execute(select(IdentityPrincipal).where(
        IdentityPrincipal.user_id == owner.id,
        IdentityPrincipal.deleted_at.is_(None),
    ).with_for_update())).scalar_one_or_none()
    old_invitation = (await db.execute(select(TenantInvitation).where(
        TenantInvitation.provider_invitation_id == body.expected_staging_invitation_id,
        TenantInvitation.tenant_id == tenant.id,
        TenantInvitation.target_user_id == owner.id,
        TenantInvitation.intended_role_slug == "garage_owner",
        TenantInvitation.deleted_at.is_(None),
    ).with_for_update())).scalar_one_or_none()
    if not principal or not old_invitation or old_invitation.principal_id != principal.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Staging identity projection does not match")

    external = (await db.execute(select(ExternalIdentity).where(
        ExternalIdentity.principal_id == principal.id,
        ExternalIdentity.provider == "workos",
        ExternalIdentity.provider_subject == body.expected_staging_user_id,
        ExternalIdentity.deleted_at.is_(None),
    ).with_for_update())).scalar_one_or_none()
    membership = (await db.execute(select(TenantMembership).where(
        TenantMembership.principal_id == principal.id,
        TenantMembership.tenant_id == tenant.id,
        TenantMembership.deleted_at.is_(None),
    ).with_for_update())).scalar_one_or_none()

    # A completed first attempt is returned rather than generating another
    # organization or invitation.
    replacement = (await db.execute(select(TenantInvitation).where(
        TenantInvitation.tenant_id == tenant.id,
        TenantInvitation.principal_id == principal.id,
        TenantInvitation.target_user_id == owner.id,
        TenantInvitation.intended_role_slug == "garage_owner",
        TenantInvitation.id != old_invitation.id,
        TenantInvitation.status.in_(("creating", "pending", "accepted")),
        TenantInvitation.deleted_at.is_(None),
    ).order_by(TenantInvitation.created_at.desc()))).scalars().first()
    if (
        old_invitation.status == "superseded"
        and replacement
        and tenant.workos_organization_id
        and tenant.workos_organization_id != body.expected_staging_organization_id
        and external
        and external.status == "superseded"
        and membership
        and membership.status in {"pending", "active"}
    ):
        return WorkOSOrganizationResponse(
            tenant_id=tenant.id,
            workos_organization_id=tenant.workos_organization_id,
            owner_invitation=_invitation_response(replacement),
        )

    if (
        tenant.workos_organization_id != body.expected_staging_organization_id
        or owner.workos_user_id != body.expected_staging_user_id
        or principal.status != "active"
        or not external
        or external.status != "active"
        or not membership
        or membership.status != "active"
        or membership.role_slug != "garage_owner"
        or old_invitation.status != "accepted"
        or old_invitation.provider_invitation_id != body.expected_staging_invitation_id
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Staging identity projection does not match")

    try:
        organization = await workos_provider.get_or_create_organization(
            tenant_id=str(tenant.id),
            name=tenant.name,
        )
    except WorkOSProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if organization.get("id") == body.expected_staging_organization_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="WorkOS Production organization is not isolated")

    old_status = old_invitation.status
    old_invitation.status = "superseded"
    external.status = "superseded"
    membership.status = "pending"
    old_provider_membership_id = membership.provider_membership_id
    membership.provider_membership_id = None
    membership.permissions = []
    membership.provider_updated_at = datetime.now(timezone.utc)
    principal.status = "pending"
    owner.workos_user_id = None
    owner.workos_identity_status = "pending"
    tenant.workos_organization_id = organization["id"]

    invitation = TenantInvitation(
        tenant_id=tenant.id,
        principal_id=principal.id,
        email_snapshot=str(body.owner_email),
        intended_role_slug="garage_owner",
        resource_scope={},
        target_user_id=owner.id,
        status="creating",
        invited_by_user_id=platform_admin.id,
    )
    db.add(invitation)
    await db.flush()
    db.add(TenantInvitationAuditEvent(
        tenant_id=tenant.id,
        invitation_id=old_invitation.id,
        driver_profile_id=None,
        actor_user_id=platform_admin.id,
        action="environment_rebind_started",
        status_from=old_status,
        status_to="superseded",
        metadata_json={
            "from_environment": "staging",
            "to_environment": "production",
            "old_organization_id": body.expected_staging_organization_id,
            "old_user_id": body.expected_staging_user_id,
            "old_membership_id": old_provider_membership_id,
        },
    ))
    try:
        provider = await workos_provider.send_invitation(
            email=str(body.owner_email),
            organization_id=tenant.workos_organization_id,
            role_slug="garage_owner",
            inviter_user_id=None,
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
        metadata={"environment": "production"},
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


async def _observe_terminal_provider_invitation(
    db: AsyncSession,
    invitation: TenantInvitation,
    tenant: Tenant,
    actor_user_id,
) -> bool:
    """Reconcile an accepted/revoked provider invitation after an action fails.

    Local development has no public webhook receiver, so WorkOS can advance an
    invitation while the local projection still says pending. The provider
    record is accepted only after all immutable invitation fields match.
    """
    provider = await workos_provider.get_invitation(invitation.provider_invitation_id)
    if (
        provider.get("id") != invitation.provider_invitation_id
        or provider.get("organization_id") != tenant.workos_organization_id
        or provider.get("role_slug") != "driver"
        or not isinstance(provider.get("email"), str)
        or provider["email"].casefold() != invitation.email_snapshot.casefold()
    ):
        raise WorkOSProviderError("WorkOS invitation state could not be verified")

    provider_state = provider.get("state")
    previous = invitation.status
    if provider_state == "accepted":
        invitation.status = "accepted"
        invitation.accepted_at = _provider_datetime(provider.get("accepted_at")) or datetime.now(timezone.utc)
        invitation.provider_user_id = provider.get("accepted_user_id") or invitation.provider_user_id
        action = "accepted_observed"
    elif provider_state == "revoked":
        invitation.status = "revoked"
        invitation.revoked_at = _provider_datetime(provider.get("revoked_at")) or datetime.now(timezone.utc)
        action = "revoked_observed"
    else:
        return False

    _audit_invitation(
        db,
        invitation,
        action=action,
        status_from=previous,
        status_to=invitation.status,
        actor_user_id=actor_user_id,
    )
    await db.commit()
    return True


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
        try:
            if await _observe_terminal_provider_invitation(
                db, invitation, tenant, principal.local_user_id
            ):
                return await _driver_portal_projection(db, driver)
        except WorkOSProviderError:
            pass
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
    tenant = await db.get(Tenant, principal.tenant_id)
    if not tenant or not tenant.workos_organization_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant has no WorkOS organization")
    try:
        provider = await workos_provider.revoke_invitation(invitation.provider_invitation_id)
    except WorkOSProviderError as exc:
        try:
            if await _observe_terminal_provider_invitation(
                db, invitation, tenant, principal.local_user_id
            ):
                return await _driver_portal_projection(db, driver)
        except WorkOSProviderError:
            pass
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


@router.post(
    "/invitations/{invitation_id}/identity-review/cancel",
    response_model=DriverPortalAccessResponse,
)
async def cancel_driver_identity_review(
    invitation_id: str,
    principal: CurrentPrincipal = Depends(require_permission("members:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate the exact accepted membership, then close local review.

    This endpoint never resolves a collision by email and never mutates a
    local User or DriverProfile. A retry after success is a no-op.
    """
    invitation, driver = await _driver_invitation_for_manager(db, invitation_id, principal.tenant_id)
    if (
        invitation.status == "revoked"
        and invitation.review_reason == IDENTITY_REVIEW_EMAIL_COLLISION
    ):
        return await _driver_portal_projection(db, driver)
    if (
        invitation.status != "needs_review"
        or invitation.review_reason != IDENTITY_REVIEW_EMAIL_COLLISION
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation is not awaiting identity review")
    if driver.user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Driver portal identity is already linked")
    identity = (await db.execute(select(IdentityPrincipal).where(
        IdentityPrincipal.id == invitation.principal_id,
        IdentityPrincipal.deleted_at.is_(None),
    ).with_for_update())).scalar_one_or_none()
    if not identity or identity.user_id is not None or identity.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation identity requires administrator review")
    tenant = await db.get(Tenant, principal.tenant_id)
    if not tenant or not tenant.workos_organization_id or not invitation.provider_invitation_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant invitation is not provisioned")

    try:
        provider_invitation = await workos_provider.get_invitation(invitation.provider_invitation_id)
        provider_user_id = provider_invitation.get("accepted_user_id")
        if (
            provider_invitation.get("state") != "accepted"
            or not isinstance(provider_user_id, str)
            or provider_invitation.get("organization_id") != tenant.workos_organization_id
            or provider_invitation.get("role_slug") != "driver"
            or not isinstance(provider_invitation.get("email"), str)
            or provider_invitation["email"].casefold() != invitation.email_snapshot.casefold()
            or (invitation.provider_user_id and invitation.provider_user_id != provider_user_id)
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Accepted WorkOS invitation requires review")
        membership = await workos_provider.find_organization_membership(
            user_id=provider_user_id,
            organization_id=tenant.workos_organization_id,
        )
        membership_outcome = "already_absent"
        if membership:
            role = membership.get("role")
            role_slug = role.get("slug") if isinstance(role, dict) else None
            if (
                role_slug != "driver"
                or membership.get("status") not in {"active", "inactive"}
                or (
                    invitation.provider_membership_id
                    and invitation.provider_membership_id != membership.get("id")
                )
            ):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="WorkOS membership requires review")
            invitation.provider_membership_id = membership["id"]
            if membership.get("status") == "active":
                await workos_provider.deactivate_organization_membership(membership["id"])
                membership_outcome = "deactivated"
            else:
                membership_outcome = "already_inactive"
    except WorkOSProviderError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    previous_status = invitation.status
    invitation.provider_user_id = provider_user_id
    invitation.status = "revoked"
    invitation.revoked_at = invitation.revoked_at or datetime.now(timezone.utc)
    identity.status = "inactive"
    _audit_invitation(
        db,
        invitation,
        action="identity_review_cancelled",
        status_from=previous_status,
        status_to="revoked",
        actor_user_id=principal.local_user_id,
        metadata={
            "reason": IDENTITY_REVIEW_EMAIL_COLLISION,
            "membership_outcome": membership_outcome,
        },
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
