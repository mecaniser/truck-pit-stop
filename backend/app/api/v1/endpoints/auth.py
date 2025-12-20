from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_token_expiry_seconds,
)
from app.core.dependencies import get_db, get_current_active_user
from app.core.redis import (
    get_token_version,
    increment_token_version,
    blacklist_token,
    is_token_blacklisted,
    store_password_reset_token,
    get_email_from_reset_token,
    delete_password_reset_token,
)
from app.core.config import settings
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.schemas.auth import (
    UserLogin,
    UserRegister,
    UserResponse,
    Token,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from pydantic import BaseModel
from typing import Optional
import secrets
from app.services.email_service import send_password_reset_email

router = APIRouter()

# Rate limiter - uses IP address as key
limiter = Limiter(key_func=get_remote_address)


def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Set httpOnly cookies for tokens."""
    # Access token cookie (shorter lived)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    # Refresh token cookie (longer lived)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/v1/auth",  # Only sent to auth endpoints
    )


def clear_auth_cookies(response: Response):
    """Clear auth cookies on logout."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # 10 registrations per minute per IP
async def register(
    request: Request,
    response: Response,
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    # Check if user exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Get tenant if provided
    tenant_id = None
    if user_data.tenant_slug:
        result = await db.execute(select(Tenant).where(Tenant.slug == user_data.tenant_slug))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        tenant_id = tenant.id
    
    # Create user
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        role=UserRole.CUSTOMER,
        tenant_id=tenant_id,
        is_active=True,
        is_verified=False,
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Generate tokens with version 0 for new users
    access_token = create_access_token(data={"sub": str(user.id)}, token_version=0)
    refresh_token = create_refresh_token(data={"sub": str(user.id)}, token_version=0)
    
    # Set httpOnly cookies
    set_auth_cookies(response, access_token, refresh_token)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")  # 5 login attempts per minute per IP
async def login(
    request: Request,
    response: Response,
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    
    # Get current token version for this user
    token_version = await get_token_version(str(user.id))
    
    access_token = create_access_token(data={"sub": str(user.id)}, token_version=token_version)
    refresh_token = create_refresh_token(data={"sub": str(user.id)}, token_version=token_version)
    
    # Set httpOnly cookies
    set_auth_cookies(response, access_token, refresh_token)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


class RefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=Token)
@limiter.limit("20/minute")  # 20 refresh requests per minute per IP
async def refresh_token_endpoint(
    request: Request,
    response: Response,
    token_request: Optional[RefreshTokenRequest] = None,
    refresh_token_cookie: Optional[str] = Cookie(None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db),
):
    # Get refresh token from body or cookie
    token_str = token_request.refresh_token if token_request else refresh_token_cookie
    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
        )
    
    payload = decode_token(token_str)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    
    user_id = payload.get("sub")
    jti = payload.get("jti")
    token_version = payload.get("ver", 0)
    
    # Check if token is blacklisted
    if jti and await is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )
    
    # Check token version
    current_version = await get_token_version(user_id)
    if token_version < current_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated",
        )
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    
    # Blacklist the old refresh token
    if jti:
        expiry = get_token_expiry_seconds(token_str)
        if expiry > 0:
            await blacklist_token(jti, expiry)
    
    access_token = create_access_token(data={"sub": str(user.id)}, token_version=current_version)
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)}, token_version=current_version)
    
    # Set httpOnly cookies
    set_auth_cookies(response, access_token, new_refresh_token)
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


class LogoutResponse(BaseModel):
    message: str


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_active_user),
):
    """Logout by blacklisting the current access token and clearing cookies."""
    # Get the token from header or cookie
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("access_token")
    
    if token:
        payload = decode_token(token)
        if payload and payload.get("jti"):
            expiry = get_token_expiry_seconds(token)
            if expiry > 0:
                await blacklist_token(payload["jti"], expiry)
    
    # Also blacklist refresh token if present
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        payload = decode_token(refresh_token)
        if payload and payload.get("jti"):
            expiry = get_token_expiry_seconds(refresh_token)
            if expiry > 0:
                await blacklist_token(payload["jti"], expiry)
    
    # Clear cookies
    clear_auth_cookies(response)
    
    return LogoutResponse(message="Successfully logged out")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
):
    return UserResponse.model_validate(current_user)


class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    update_data: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update current user's profile (name, phone)"""
    data = update_data.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(current_user, field, value)
    
    await db.commit()
    await db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class PasswordChangeResponse(BaseModel):
    message: str
    tokens_invalidated: bool = True


@router.post("/change-password", response_model=PasswordChangeResponse)
async def change_password(
    password_data: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Change current user's password and invalidate all existing tokens."""
    # Verify current password
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    
    # Update password
    current_user.hashed_password = get_password_hash(password_data.new_password)
    await db.commit()
    
    # Increment token version to invalidate ALL existing tokens for this user
    await increment_token_version(str(current_user.id))
    
    return PasswordChangeResponse(
        message="Password changed successfully. Please log in again.",
        tokens_invalidated=True,
    )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("3/hour")  # Rate limit: 3 requests per hour per IP
async def forgot_password(
    request: Request,
    forgot_request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send password reset email if user exists."""
    # Always return success to prevent email enumeration
    # Even if user doesn't exist, we return the same message
    
    result = await db.execute(select(User).where(User.email == forgot_request.email))
    user = result.scalar_one_or_none()
    
    if user and user.is_active:
        # Generate secure random token
        reset_token = secrets.token_urlsafe(32)
        
        # Store token in Redis (expires in 1 hour)
        await store_password_reset_token(forgot_request.email, reset_token, expires_in=3600)
        
        # Send email
        try:
            await send_password_reset_email(forgot_request.email, reset_token)
        except Exception:
            # Log error but don't reveal to user
            pass
    
    # Always return same message for security
    return ForgotPasswordResponse(
        message="If an account exists with that email, you will receive a password reset link shortly."
    )


@router.post("/reset-password", response_model=ResetPasswordResponse)
@limiter.limit("5/hour")  # Rate limit: 5 requests per hour per IP
async def reset_password(
    request: Request,
    reset_request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset password using token from email."""
    # Get email from token
    email = await get_email_from_reset_token(reset_request.token)
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    
    # Find user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    
    # Update password
    user.hashed_password = get_password_hash(reset_request.new_password)
    await db.commit()
    
    # Delete the used token
    await delete_password_reset_token(reset_request.token)
    
    # Invalidate all existing tokens for this user
    await increment_token_version(str(user.id))
    
    return ResetPasswordResponse(
        message="Password reset successfully. You can now log in with your new password."
    )
