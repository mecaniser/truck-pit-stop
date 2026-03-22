from typing import Optional
from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.db.session import get_db
from app.core.security import decode_token
from app.core.redis import is_token_blacklisted, get_token_version
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink

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

    # Check if token is blacklisted
    if jti and await is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Check token version (invalidated on password change)
    current_version = await get_token_version(user_id)
    if token_version < current_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

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

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
