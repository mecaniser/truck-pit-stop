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
from app.db.models.customer import Customer
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
from pydantic import BaseModel, Field, EmailStr
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
    
    # Check if there's an existing Customer record with this email
    # This links the new User account to the Customer created by staff
    result = await db.execute(select(Customer).where(Customer.email == user_data.email))
    existing_customer = result.scalar_one_or_none()
    
    customer_id = None
    tenant_id = None
    
    if existing_customer:
        # Link to existing customer - inherit their tenant
        customer_id = existing_customer.id
        tenant_id = existing_customer.tenant_id
    elif user_data.tenant_slug:
        # No existing customer, but tenant slug provided
        result = await db.execute(select(Tenant).where(Tenant.slug == user_data.tenant_slug))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        tenant_id = tenant.id
    
    # Create user linked to existing customer (if any)
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        role=UserRole.CUSTOMER,
        tenant_id=tenant_id,
        customer_id=customer_id,
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
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, description="Required when changing email")


class ProfileUpdateResponse(BaseModel):
    """Response for profile updates - can include verification status"""
    user: Optional[UserResponse] = None
    message: Optional[str] = None
    email_verification_pending: bool = False


@router.put("/me", response_model=ProfileUpdateResponse)
async def update_current_user(
    update_data: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update current user's profile (name, phone, email)"""
    from app.core.redis import get_redis
    from app.services.email_service import send_email_verification, send_email_change_notification
    import secrets
    
    data = update_data.model_dump(exclude_unset=True)
    
    # Remove email if explicitly set to null (invalid value)
    if 'email' in data and data['email'] is None:
        data.pop('email')
    
    # If email is being changed, require password and send verification
    if 'email' in data and data['email'] != current_user.email:
        # Password is required for email changes
        if not update_data.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password confirmation required to change email",
            )
        
        # Verify password
        if not verify_password(update_data.password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password",
            )
        
        # Check if new email is already taken
        result = await db.execute(
            select(User).where(User.email == data['email'])
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use by another account",
            )
        
        # Generate verification token
        verification_token = secrets.token_urlsafe(32)
        old_email = current_user.email
        new_email = data['email']
        
        # Store pending email change in Redis (expires in 1 hour)
        # Use user-specific key to ensure only one pending verification per user
        # This invalidates any previous pending email change requests
        redis = await get_redis()
        user_key = f"email_change:user:{current_user.id}"
        
        # Delete any existing pending verification for this user
        existing_token = await redis.get(user_key)
        if existing_token:
            # Clean up the old token-based key if it exists
            await redis.delete(f"email_change:token:{existing_token}")
        
        # Store the new token in user-specific key
        await redis.setex(user_key, 3600, verification_token)
        
        # Store the verification data in token-based key for lookup during verification
        await redis.setex(
            f"email_change:token:{verification_token}",
            3600,  # 1 hour
            f"{current_user.id}:{new_email}"
        )
        
        # Send verification email to NEW address
        try:
            await send_email_verification(new_email, verification_token)
        except Exception as e:
            print(f"Error sending verification email: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email",
            )
        
        # Send notification to OLD address
        try:
            await send_email_change_notification(
                old_email, 
                new_email, 
                f"{current_user.first_name} {current_user.last_name}"
            )
        except Exception as e:
            print(f"Error sending notification email: {e}")
            # Don't fail if notification fails
        
        # Remove email from update data - will be updated after verification
        data.pop('email')
        email_verification_pending = True
    else:
        email_verification_pending = False
    
    # Remove password from update data
    data.pop('password', None)
    
    # If only email was being changed (no other fields to update), return early
    if email_verification_pending and not any(k in data for k in ['first_name', 'last_name', 'phone']):
        return ProfileUpdateResponse(
            user=UserResponse.model_validate(current_user),
            message="Verification email sent. Please check your new email address to confirm the change.",
            email_verification_pending=True
        )
    
    # Update User fields
    for field, value in data.items():
        setattr(current_user, field, value)
    
    # If user is a customer, also update their Customer record
    if current_user.customer_id and data:
        from app.db.models.customer import Customer
        result = await db.execute(
            select(Customer).where(Customer.id == current_user.customer_id)
        )
        customer = result.scalar_one_or_none()
        if customer:
            # Update matching fields in Customer table
            customer_fields = {'first_name', 'last_name', 'email', 'phone'}
            for field, value in data.items():
                if field in customer_fields:
                    setattr(customer, field, value)
    
    await db.commit()
    await db.refresh(current_user)
    
    # Build appropriate message based on what was updated
    message = None
    if email_verification_pending:
        message = "Profile updated. A verification email has been sent to your new email address."
    
    return ProfileUpdateResponse(
        user=UserResponse.model_validate(current_user),
        message=message,
        email_verification_pending=email_verification_pending
    )


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


class EmailVerificationRequest(BaseModel):
    token: str


class EmailVerificationResponse(BaseModel):
    message: str
    email: str


@router.post("/verify-email", response_model=EmailVerificationResponse)
async def verify_email_change(
    verify_data: EmailVerificationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify email change using token from email"""
    from app.core.redis import get_redis
    
    # Get pending email change from Redis using token-based key
    redis = await get_redis()
    token_key = f"email_change:token:{verify_data.token}"
    change_data = await redis.get(token_key)
    
    if not change_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link",
        )
    
    # Parse data: "user_id:new_email"
    try:
        user_id, new_email = change_data.split(':', 1)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token",
        )
    
    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Verify this token is still the active one for this user
    # This prevents old tokens from being used after a new verification was requested
    user_key = f"email_change:user:{user_id}"
    active_token = await redis.get(user_key)
    if active_token != verify_data.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is no longer valid. A newer email change request has been made.",
        )
    
    # Re-check if new email is still available (prevent race conditions)
    # Someone could have registered with this email while verification was pending
    if new_email != user.email:  # Only check if email actually different
        result = await db.execute(
            select(User).where(User.email == new_email)
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            # Delete the now-invalid tokens
            await redis.delete(token_key)
            await redis.delete(user_key)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email address is no longer available. It may have been taken by another user.",
            )
    
    # Update email in User record
    old_email = user.email
    user.email = new_email
    
    # If user is a customer, also update their Customer record email
    if user.customer_id:
        from app.db.models.customer import Customer
        result = await db.execute(
            select(Customer).where(Customer.id == user.customer_id)
        )
        customer = result.scalar_one_or_none()
        if customer:
            customer.email = new_email
    
    # Commit to database FIRST - only delete tokens if commit succeeds
    await db.commit()
    
    # Delete verification tokens only after successful commit
    # This ensures tokens remain valid if commit fails
    await redis.delete(token_key)
    await redis.delete(user_key)
    
    return EmailVerificationResponse(
        message=f"Email successfully changed from {old_email} to {new_email}",
        email=new_email
    )
