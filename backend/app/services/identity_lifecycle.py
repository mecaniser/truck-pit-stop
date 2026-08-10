"""Local identity/membership projection and exact invitation binding."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.driver_accountability import DriverProfile
from app.db.models.identity import ExternalIdentity, IdentityPrincipal, TenantInvitation, TenantMembership
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services import workos_provider
from app.services.workos_provider import WorkOSProviderError


ROLE_TO_USER_ROLE = {
    "garage_owner": UserRole.GARAGE_OWNER,
    "garage_admin": UserRole.GARAGE_ADMIN,
    "fleet_manager": UserRole.FLEET_MANAGER,
    "mechanic": UserRole.MECHANIC,
    "receptionist": UserRole.RECEPTIONIST,
    "driver": UserRole.DRIVER,
}
INVITABLE_ROLES = frozenset(ROLE_TO_USER_ROLE)


async def resolve_authenticated_identity(
    db: AsyncSession,
    *,
    claims: Dict[str, Any],
    workos_user: Dict[str, Any],
) -> Tuple[User, Tenant, Optional[TenantMembership]]:
    """Resolve an existing member or bind one exact accepted invitation.

    Email is used only to populate a new local projection after WorkOS proves
    the invitation id, accepted user id, organization, and role.
    """
    workos_user_id = claims["sub"]
    workos_org_id = claims["org_id"]
    role_slug = claims.get("role")
    permissions = claims["permissions"]
    tenant = (await db.execute(select(Tenant).where(Tenant.workos_organization_id == workos_org_id))).scalar_one_or_none()
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WorkOS organization is not provisioned")

    external = (await db.execute(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == "workos",
            ExternalIdentity.provider_subject == workos_user_id,
            ExternalIdentity.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if external:
        principal = await db.get(IdentityPrincipal, external.principal_id)
        membership = (await db.execute(select(TenantMembership).where(
            TenantMembership.principal_id == principal.id,
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.deleted_at.is_(None),
        ))).scalar_one_or_none()
        user = await db.get(User, principal.user_id) if principal and principal.user_id else None
        if not principal or principal.status != "active" or external.status != "active" or not membership or membership.status != "active" or not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WorkOS membership is inactive")
        if role_slug not in INVITABLE_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WorkOS role is not supported")
        membership.role_slug = role_slug
        membership.permissions = permissions
        membership.provider_updated_at = datetime.now(timezone.utc)
        return user, tenant, membership

    # Compatibility canary: an administrator explicitly pre-linked the WorkOS
    # subject, so it is safe to build provider-neutral projections without email.
    user = (await db.execute(select(User).where(User.workos_user_id == workos_user_id))).scalar_one_or_none()
    if user:
        if not user.is_active or role_slug not in INVITABLE_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WorkOS access is not provisioned")
        principal = IdentityPrincipal(user_id=user.id, status="active")
        db.add(principal)
        await db.flush()
        db.add(ExternalIdentity(principal_id=principal.id, provider="workos", provider_subject=workos_user_id, status="active", email_snapshot=user.email))
        membership = TenantMembership(
            principal_id=principal.id,
            tenant_id=tenant.id,
            provider="workos",
            role_slug=role_slug,
            status="active",
            permissions=permissions,
            resource_scope={},
            provider_updated_at=datetime.now(timezone.utc),
        )
        db.add(membership)
        return user, tenant, membership

    invitations = (await db.execute(select(TenantInvitation).where(
        TenantInvitation.tenant_id == tenant.id,
        TenantInvitation.provider == "workos",
        TenantInvitation.status.in_(("pending", "accepted")),
        TenantInvitation.provider_invitation_id.is_not(None),
        TenantInvitation.deleted_at.is_(None),
    ))).scalars().all()
    matched = None
    for invitation in invitations:
        try:
            provider_invitation = await workos_provider.get_invitation(invitation.provider_invitation_id)
        except WorkOSProviderError:
            continue
        if (
            provider_invitation.get("state") == "accepted"
            and provider_invitation.get("accepted_user_id") == workos_user_id
            and provider_invitation.get("organization_id") == workos_org_id
            and provider_invitation.get("role_slug") == invitation.intended_role_slug
            and role_slug == invitation.intended_role_slug
        ):
            matched = invitation
            break
    if not matched:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A matching accepted invitation is required")

    email = workos_user.get("email")
    first_name = workos_user.get("first_name") or "Invited"
    last_name = workos_user.get("last_name") or "User"
    if not isinstance(email, str) or not email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WorkOS user email is unavailable")
    # A collision is intentionally not auto-linked. An administrator must
    # resolve it through an explicit identity-linking workflow.
    if (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An existing local identity requires explicit linking")
    principal = await db.get(IdentityPrincipal, matched.principal_id)
    if not principal or principal.user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invitation identity is already linked")
    user = User(
        email=email,
        hashed_password=None,
        first_name=first_name,
        last_name=last_name,
        role=ROLE_TO_USER_ROLE[matched.intended_role_slug],
        tenant_id=tenant.id,  # compatibility projection only
        workos_user_id=workos_user_id,
        workos_identity_status="active",
        workos_identity_linked_at=datetime.now(timezone.utc),
        is_active=True,
        is_verified=bool(workos_user.get("email_verified")),
    )
    db.add(user)
    await db.flush()
    principal.user_id = user.id
    principal.status = "active"
    db.add(ExternalIdentity(principal_id=principal.id, provider="workos", provider_subject=workos_user_id, status="active", email_snapshot=email))
    membership = TenantMembership(
        principal_id=principal.id,
        tenant_id=tenant.id,
        provider="workos",
        role_slug=matched.intended_role_slug,
        status="active",
        permissions=permissions,
        resource_scope=matched.resource_scope,
        provider_updated_at=datetime.now(timezone.utc),
    )
    db.add(membership)
    if matched.driver_profile_id:
        driver = await db.get(DriverProfile, matched.driver_profile_id)
        if not driver or driver.tenant_id != tenant.id or driver.user_id is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Driver profile is no longer available for linking")
        driver.user_id = user.id
    matched.status = "accepted"
    matched.accepted_at = datetime.now(timezone.utc)
    return user, tenant, membership
