"""WorkOS principal helpers used during the additive authentication cutover."""
from dataclasses import dataclass
from typing import FrozenSet
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, get_token_from_request
from app.core.redis import get_auth_token_state
from app.core.security import decode_token
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.db.models.identity import ExternalIdentity, IdentityPrincipal, TenantMembership


@dataclass(frozen=True)
class CurrentPrincipal:
    local_user_id: UUID
    workos_user_id: str
    workos_org_id: str
    tenant_id: UUID
    permissions: FrozenSet[str]


def require_permission(*required: str):
    """FastAPI dependency factory; callers still enforce record ownership."""
    required_set = frozenset(required)

    async def check(principal: CurrentPrincipal = Depends(get_current_principal)) -> CurrentPrincipal:
        if not required_set.issubset(principal.permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing required permission",
            )
        return principal

    return check


async def get_current_principal(
    token: str = Depends(get_token_from_request), db: AsyncSession = Depends(get_db)
) -> CurrentPrincipal:
    """Resolve only short-lived WorkOS-backed local sessions.

    The callback places the active organization and WorkOS-derived permissions
    into a five-minute local session; this bounded projection is intentionally
    distinct from the legacy JWT path.
    """
    claims = decode_token(token)
    if not claims or claims.get("auth_provider") != "workos":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS authentication required")
    user_id, workos_user_id, workos_org_id = claims.get("sub"), claims.get("workos_user_id"), claims.get("workos_org_id")
    if not user_id or not workos_user_id or not workos_org_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WorkOS session")
    permissions = claims.get("permissions")
    if not isinstance(permissions, list) or not all(isinstance(value, str) for value in permissions):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WorkOS permission claims")
    is_blacklisted, current_version = await get_auth_token_state(claims.get("jti"), user_id)
    if is_blacklisted or claims.get("ver", 0) < current_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS session has been revoked")
    row = (await db.execute(
        select(User, Tenant).join(Tenant, Tenant.workos_organization_id == workos_org_id)
        .where(User.id == user_id, User.workos_user_id == workos_user_id, User.is_active.is_(True), Tenant.is_active.is_(True))
    )).one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WorkOS organization access is not provisioned")
    user, tenant = row
    external = (await db.execute(select(ExternalIdentity).where(
        ExternalIdentity.provider == "workos",
        ExternalIdentity.provider_subject == workos_user_id,
        ExternalIdentity.status == "active",
        ExternalIdentity.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not external:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WorkOS membership is inactive")
    membership = (await db.execute(
        select(TenantMembership)
        .join(IdentityPrincipal, IdentityPrincipal.id == TenantMembership.principal_id)
        .where(
            TenantMembership.principal_id == external.principal_id,
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.provider == "workos",
            TenantMembership.status == "active",
            TenantMembership.deleted_at.is_(None),
            IdentityPrincipal.user_id == user.id,
            IdentityPrincipal.status == "active",
            IdentityPrincipal.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WorkOS membership is inactive")
    return CurrentPrincipal(user.id, workos_user_id, workos_org_id, tenant.id, frozenset(permissions))
