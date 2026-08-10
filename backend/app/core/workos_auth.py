"""WorkOS principal helpers used during the additive authentication cutover."""
from dataclasses import dataclass
from typing import FrozenSet
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, get_token_from_request
from app.core.security import decode_token
from app.db.models.tenant import Tenant
from app.db.models.user import User


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
    row = (await db.execute(
        select(User, Tenant).join(Tenant, Tenant.workos_organization_id == workos_org_id)
        .where(User.id == user_id, User.workos_user_id == workos_user_id, User.is_active.is_(True), Tenant.is_active.is_(True))
    )).one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WorkOS organization access is not provisioned")
    user, tenant = row
    return CurrentPrincipal(user.id, workos_user_id, workos_org_id, tenant.id, frozenset(claims.get("permissions") or ()))
