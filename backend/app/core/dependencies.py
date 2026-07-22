from typing import Optional
from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.db.session import get_db
from app.core.security import decode_token
from app.core.redis import get_auth_token_state
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.tenant import Tenant

security = HTTPBearer(auto_error=False)


async def get_token_from_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(None),
) -> str:
    """Extract token from Authorization header or httpOnly cookie."""
    # Prefer Authorization header (for API clients)
    if credentials and credentials.credentials:
        return credentials.credentials

    # Fall back to httpOnly cookie (for browser)
    if access_token:
        return access_token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


async def get_current_user(
    token: str = Depends(get_token_from_request),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    # Reject refresh tokens and shop-select tokens — only plain access tokens allowed here
    if payload.get("type") is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    user_id: Optional[str] = payload.get("sub")
    jti: Optional[str] = payload.get("jti")
    token_version: int = payload.get("ver", 0)
    tenant_id_claim: Optional[str] = payload.get("tid")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    is_blacklisted, current_version = await get_auth_token_state(jti, user_id)
    if is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    if token_version < current_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated",
        )

    result = await db.execute(
        select(User, Tenant.is_active.label("tenant_is_active"))
        .outerjoin(Tenant, Tenant.id == User.tenant_id)
        .where(User.id == user_id)
    )
    user_row = result.one_or_none()
    user = user_row[0] if user_row else None

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    # For customers with a tenant claim in the JWT, resolve the active shop context
    # from the join table and override tenant_id/customer_id for this request.
    if user.role == UserRole.CUSTOMER and tenant_id_claim:
        link_result = await db.execute(
            select(UserCustomerLink).where(
                and_(
                    UserCustomerLink.user_id == user.id,
                    UserCustomerLink.tenant_id == tenant_id_claim,
                    UserCustomerLink.deleted_at.is_(None),
                )
            )
        )
        link = link_result.scalar_one_or_none()
        if not link:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Shop access denied",
            )
        # Set the active tenant context for this request (not persisted to DB)
        user.tenant_id = link.tenant_id
        user.customer_id = link.customer_id

    # A tenant can be offboarded without deleting its records. Honor that
    # platform-level switch for every tenant-scoped request while allowing
    # super admins to continue managing the platform.
    if user.role != UserRole.SUPER_ADMIN and user.tenant_id:
        tenant_is_active = user_row.tenant_is_active

        # Customer tokens can select a tenant that differs from the user's
        # legacy tenant_id, so only that less common path needs another lookup.
        if user.role == UserRole.CUSTOMER and tenant_id_claim:
            tenant_is_active = (
                await db.execute(select(Tenant.is_active).where(Tenant.id == user.tenant_id))
            ).scalar_one_or_none()

        if tenant_is_active is not True:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This shop is inactive. Please contact DieselBridge support.",
            )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


def user_has_permission(user: User, key: str) -> bool:
    """True if the user can access a gated settings surface (payments,
    taxes_fees, workforce). Owners and super admins always pass; garage
    admins need an explicit grant in user.permissions; everyone else fails.
    """
    if user.role in (UserRole.SUPER_ADMIN, UserRole.GARAGE_OWNER):
        return True
    if user.role == UserRole.GARAGE_ADMIN:
        return bool((user.permissions or {}).get(key, False))
    return False


def require_permission(key: str):
    """Dependency factory gating an endpoint on a specific settings grant."""
    async def checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if not user_has_permission(current_user, key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this setting. Ask the shop owner to grant access.",
            )
        return current_user
    return checker
