from datetime import timedelta, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    create_shop_select_token,
    decode_token,
    get_token_expiry_seconds,
)
from app.core.dependencies import (
    get_db,
    get_current_active_user,
    get_token_from_request,
    identity_user,
)
from app.core.redis import (
    get_redis,
    get_token_version,
    increment_token_version,
    blacklist_token,
    is_token_blacklisted,
    store_password_reset_token,
    get_email_from_reset_token,
    delete_password_reset_token,
)
from app.core.config import settings
from app.core.correlation import normalize_correlation_id
from app.core.rate_limit import limiter
from app.core.metrics import record_login, record_logout
from app.core.phone import normalize_phone
from app.services.tenant_branding import extract_us_state
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.user_customer_link import UserCustomerLink
from app.schemas.auth import (
    UserLogin,
    UserRegister,
    UserResponse,
    TenantBrandingResponse,
    Token,
    ShopOption,
    SelectTenantRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from app.schemas.presentation import (
    AppearanceResetRequest,
    AppearanceUpdateRequest,
    PresentationResponse,
    TenantPresentationRolloutRequest,
)
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Union
from uuid import UUID
import json
import secrets
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from app.services import workos_provider, workos_session
from app.services.identity_lifecycle import IdentityReviewRequired, resolve_authenticated_identity
from app.services.presentation_service import (
    get_appearance,
    reset_appearance,
    set_own_tenant_presentation,
    resolve_presentation,
    update_appearance,
)
from app.services.workos_provider import WorkOSProviderError
from app.services.email_service import (
    send_password_reset_email,
    send_enrollment_received_email,
    send_new_enrollment_notification,
)
from app.services.website_logo_service import import_logo_from_website
from app.core.logging import get_logger
from app.core.password_policy import validate_password
from app.core.payment_step_up import (
    PaymentStepUpContext,
    PaymentStepUpScope,
    get_payment_step_up_context,
    issue_step_up_grant,
    payment_step_up_audit_event,
    validate_scope_authority,
)

router = APIRouter()
logger = get_logger(__name__)


def _workos_enabled() -> None:
    if not settings.WORKOS_AUTH_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WorkOS authentication is disabled")
    if not settings.WORKOS_API_KEY or not settings.WORKOS_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="WorkOS authentication is not configured")


def _safe_return_path(value: Optional[str]) -> str:
    return value if value and value.startswith("/") and not value.startswith("//") else "/"


def _workos_state_context(return_to: Optional[str], tenant_id: Optional[UUID]) -> str:
    """Serialize only server-validated OAuth continuation data."""
    return json.dumps(
        {
            "return_to": _safe_return_path(return_to),
            "tenant_id": str(tenant_id) if tenant_id else None,
        },
        separators=(",", ":"),
    )


def _read_workos_state_context(
    raw: Optional[Union[str, bytes]],
    *,
    fallback_return_to: Optional[str] = None,
    fallback_tenant_id: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Read trusted state context, with safe fallback for rolling deploys."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        parsed = None

    if isinstance(parsed, dict):
        return_to = _safe_return_path(parsed.get("return_to"))
        raw_tenant_id = parsed.get("tenant_id")
    else:
        # Older deployments stored the literal "1". Browser cookies remain a
        # safe compatibility fallback until those ten-minute states expire.
        return_to = _safe_return_path(fallback_return_to)
        raw_tenant_id = fallback_tenant_id

    try:
        tenant_id = str(UUID(raw_tenant_id)) if raw_tenant_id else None
    except (TypeError, ValueError):
        tenant_id = None
    return return_to, tenant_id


async def _consume_workos_state(state: str) -> Optional[Union[str, bytes]]:
    """Atomically consume a one-time state where Redis supports GETDEL."""
    redis = await get_redis()
    getdel = getattr(redis, "getdel", None)
    if callable(getdel):
        return await getdel(f"workos:oauth-state:{state}")

    # Test/legacy Redis compatibility. Production Redis uses GETDEL above.
    key = f"workos:oauth-state:{state}"
    raw = await redis.get(key)
    if raw is None or not await redis.delete(key):
        return None
    return raw


def _return_path_with_reason(value: Optional[str], reason: str) -> str:
    """Append one fixed, non-sensitive reason to a validated SPA path."""
    safe = _safe_return_path(value)
    parts = urlsplit(safe)
    query = [(key, item) for key, item in parse_qsl(parts.query, keep_blank_values=True) if key != "reason"]
    query.append(("reason", reason))
    return urlunsplit(("", "", parts.path or "/", urlencode(query), ""))


def _workos_cookie_values(request: Request, name: str) -> list[str]:
    """Return every value for a cookie, including legacy duplicate scopes."""
    values: list[str] = []
    for raw_name, raw_value in request.scope.get("headers", []):
        if raw_name.lower() != b"cookie":
            continue
        for item in raw_value.decode("latin-1").split(";"):
            cookie_name, separator, cookie_value = item.strip().partition("=")
            if separator and cookie_name == name:
                values.append(cookie_value)
    return values


def _set_workos_flow_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(
        name,
        value,
        httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE,
        samesite="lax",
        max_age=600,
        path="/api/v1/auth/workos",
        domain=_cookie_domain(),
    )


def _delete_workos_flow_cookie(response: Response, name: str) -> None:
    """Clear shared cookies and host-only cookies from rolling deployments."""
    domain = _cookie_domain()
    if domain:
        response.delete_cookie(name, path="/api/v1/auth/workos", domain=domain)
    response.delete_cookie(name, path="/api/v1/auth/workos")


def _clear_failed_workos_login(response: Response, *, clear_recovery: bool = True) -> None:
    response.delete_cookie("access_token", path="/", domain=_cookie_domain())
    response.delete_cookie("workos_session", path="/api/v1/auth/workos", domain=_cookie_domain())
    response.delete_cookie("refresh_token", path="/api/v1/auth", domain=_cookie_domain())
    _delete_workos_flow_cookie(response, "workos_oauth_state")
    _delete_workos_flow_cookie(response, "workos_return_to")
    _delete_workos_flow_cookie(response, "workos_tenant_id")
    if clear_recovery:
        _delete_workos_flow_cookie(response, "workos_recovery_attempted")


async def _workos_state_failure_response(
    request: Request,
    state_context: Optional[Union[str, bytes]] = None,
) -> RedirectResponse:
    """Recover a stale callback without weakening browser-bound OAuth state.

    A callback can be revisited after the original one already succeeded, or
    an email client can open it outside the browser that started AuthKit. An
    existing opaque WorkOS session is safe to resume because the refresh
    endpoint independently revalidates its user, organization, membership,
    and permissions. Without a session, restart AuthKit once with a new state;
    a second failure stops at the login surface instead of looping.
    """
    return_to, tenant_id = _read_workos_state_context(
        state_context,
        fallback_return_to=request.cookies.get("workos_return_to"),
        fallback_tenant_id=request.cookies.get("workos_tenant_id"),
    )
    session_id = request.cookies.get("workos_session")
    if session_id and await workos_session.get_session(session_id):
        response = RedirectResponse(settings.WORKOS_POST_LOGIN_URL.rstrip("/") + return_to)
        _delete_workos_flow_cookie(response, "workos_oauth_state")
        _delete_workos_flow_cookie(response, "workos_return_to")
        _delete_workos_flow_cookie(response, "workos_tenant_id")
        _delete_workos_flow_cookie(response, "workos_recovery_attempted")
        return response

    login_path = "/driver/login" if return_to.startswith("/driver") else "/login"
    if request.cookies.get("workos_recovery_attempted") != "1":
        retry_params = {"return_to": return_to, "recovery": "1"}
        if tenant_id:
            retry_params["tenant_id"] = tenant_id
        response = RedirectResponse(f"/api/v1/auth/workos/login?{urlencode(retry_params)}")
        _set_workos_flow_cookie(response, "workos_recovery_attempted", "1")
        _clear_failed_workos_login(response, clear_recovery=False)
        return response

    parts = urlsplit(_return_path_with_reason(login_path, "workos_state_expired"))
    query = list(parse_qsl(parts.query, keep_blank_values=True))
    if tenant_id:
        query.append(("tenant_id", tenant_id))
    safe_path = urlunsplit(("", "", parts.path, urlencode(query), ""))
    response = RedirectResponse(settings.WORKOS_POST_LOGIN_URL.rstrip("/") + safe_path)
    _clear_failed_workos_login(response)
    return response


@router.get("/workos/login", include_in_schema=False)
async def workos_login(
    return_to: Optional[str] = None,
    tenant_id: Optional[UUID] = None,
    recovery: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Start AuthKit without changing any legacy login behavior."""
    _workos_enabled()
    state = secrets.token_urlsafe(32)
    # State is browser-bound and one-time: callback deletes it regardless of outcome.
    authorize_params = {
        "client_id": settings.WORKOS_CLIENT_ID,
        "redirect_uri": settings.WORKOS_REDIRECT_URI,
        "response_type": "code", "provider": "authkit", "state": state,
        # A shared browser may be used by managers and drivers. Never let an
        # existing AuthKit session silently choose the wrong local identity.
        "prompt": "login",
    }
    tenant = None
    if tenant_id is not None:
        tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
        if not tenant or not tenant.is_active or not tenant.workos_organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="WorkOS organization is not available",
            )
        # An exact workspace link bypasses organization selection. Generic
        # entry relies on authoritative WorkOS memberships and callback mapping.
        authorize_params["organization_id"] = tenant.workos_organization_id
    query = urlencode(authorize_params)
    response = RedirectResponse(f"https://api.workos.com/user_management/authorize?{query}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    _set_workos_flow_cookie(response, "workos_oauth_state", state)
    _set_workos_flow_cookie(response, "workos_return_to", _safe_return_path(return_to))
    if tenant:
        _set_workos_flow_cookie(response, "workos_tenant_id", str(tenant.id))
    if not recovery:
        _delete_workos_flow_cookie(response, "workos_recovery_attempted")
    await (await get_redis()).setex(
        f"workos:oauth-state:{state}",
        600,
        _workos_state_context(return_to, tenant.id if tenant else None),
    )
    return response


@router.get("/workos/callback", include_in_schema=False)
async def workos_callback(request: Request, code: str, state: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Exchange a WorkOS code, map its organization to a tenant, issue the
    existing local cookie/JWT session, then return to the configured SPA.
    """
    _workos_enabled()
    expected_states = _workos_cookie_values(request, "workos_oauth_state")
    if not state or not any(secrets.compare_digest(state, candidate) for candidate in expected_states):
        state_context = await _consume_workos_state(state) if state else None
        return await _workos_state_failure_response(request, state_context)
    # Consume only after confirming this browser owns the presented state.
    state_context = await _consume_workos_state(state)
    if state_context is None:
        return await _workos_state_failure_response(request)
    return_to, _ = _read_workos_state_context(
        state_context,
        fallback_return_to=request.cookies.get("workos_return_to"),
        fallback_tenant_id=request.cookies.get("workos_tenant_id"),
    )
    try:
        payload = await workos_provider.authenticate({
            "grant_type": "authorization_code",
            "code": code,
            "ip_address": request.client.host if request and request.client else None,
            "user_agent": request.headers.get("user-agent") if request else None,
        })
        claims = await workos_provider.verify_access_token(payload.get("access_token"))
    except WorkOSProviderError as exc:
        logger.warning("workos_code_exchange_failed", reason=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS authentication failed")
    workos_user = payload.get("user") or {}
    if workos_user.get("id") != claims["sub"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS authentication identity mismatch")
    try:
        user, tenant, _ = await resolve_authenticated_identity(db, claims=claims, workos_user=workos_user)
    except IdentityReviewRequired as exc:
        # Persist only the fail-closed review marker/audit written by the
        # resolver. No local identity, DriverProfile, or session is activated.
        await db.commit()
        correlation_id = normalize_correlation_id(
            getattr(request.state, "correlation_id", None)
        )
        logger.warning(
            "workos_identity_review_required",
            invitation_id=str(exc.invitation_id),
            reason=exc.reason,
            correlation_id=correlation_id,
        )
        review_return_to = _return_path_with_reason(return_to, "identity_review_required")
        response = RedirectResponse(settings.WORKOS_POST_LOGIN_URL.rstrip("/") + review_return_to)
        _clear_failed_workos_login(response)
        return response
    user.workos_identity_status = "active"
    user.workos_identity_linked_at = user.workos_identity_linked_at or datetime.now(timezone.utc)
    refresh_token = payload.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS session credential is unavailable")
    await db.commit()
    response = RedirectResponse(settings.WORKOS_POST_LOGIN_URL.rstrip("/") + return_to)
    token_version = await get_token_version(str(user.id))
    access_token = create_access_token(data={"sub": str(user.id), "auth_provider": "workos", "workos_user_id": claims["sub"], "workos_org_id": claims["org_id"], "permissions": claims["permissions"]}, expires_delta=timedelta(minutes=settings.WORKOS_ACCESS_TOKEN_MINUTES), tenant_id=str(tenant.id), token_version=token_version)
    set_access_cookie(response, access_token, max_age_seconds=settings.WORKOS_ACCESS_TOKEN_MINUTES * 60)
    session_id = await workos_session.create_session(
        refresh_token=refresh_token,
        local_user_id=str(user.id),
        workos_user_id=claims["sub"],
        workos_org_id=claims["org_id"],
    )
    response.set_cookie(
        "workos_session", session_id, httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE, samesite=settings.COOKIE_SAMESITE,
        max_age=workos_session.session_ttl_seconds(), domain=_cookie_domain(),
        path="/api/v1/auth/workos",
    )
    # Do not let an existing legacy refresh cookie convert this short-lived
    # WorkOS session into a multi-day legacy session.
    response.delete_cookie("refresh_token", path="/api/v1/auth", domain=_cookie_domain())
    _delete_workos_flow_cookie(response, "workos_oauth_state")
    _delete_workos_flow_cookie(response, "workos_return_to")
    _delete_workos_flow_cookie(response, "workos_tenant_id")
    _delete_workos_flow_cookie(response, "workos_recovery_attempted")
    return response


async def _build_user_response(user: User, db: AsyncSession) -> UserResponse:
    response = UserResponse.model_validate(user)

    if user.tenant_id:
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        if tenant:
            response.tenant_name = tenant.name
            response.tenant_slug = tenant.slug
            response.tenant_logo_url = tenant.logo_url
            response.messaging_enabled = tenant.messaging_enabled

    if user.role not in (UserRole.CUSTOMER, UserRole.DRIVER):
        try:
            response.presentation = await resolve_presentation(db, user)
        except HTTPException:
            response.presentation = None

    return response


def _cookie_domain() -> Optional[str]:
    domain = settings.COOKIE_DOMAIN.strip()
    return domain or None


def set_auth_cookies(response: Response, access_token: str, refresh_token: str, remember_me: bool = False):
    """Set httpOnly cookies for tokens."""
    # Access token cookie (shorter lived)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        domain=_cookie_domain(),
        path="/",
    )
    # Refresh token cookie (longer lived)
    refresh_days = settings.REFRESH_TOKEN_EXPIRE_DAYS_REMEMBER if remember_me else settings.REFRESH_TOKEN_EXPIRE_DAYS
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=refresh_days * 24 * 60 * 60,
        domain=_cookie_domain(),
        path="/api/v1/auth",  # Only sent to auth endpoints
    )


def set_access_cookie(response: Response, access_token: str, max_age_seconds: int):
    response.set_cookie(
        key="access_token", value=access_token, httponly=True,
        secure=settings.COOKIE_SECURE_EFFECTIVE, samesite=settings.COOKIE_SAMESITE,
        max_age=max_age_seconds, domain=_cookie_domain(), path="/",
    )


def clear_auth_cookies(response: Response):
    """Clear auth cookies on logout."""
    domain = _cookie_domain()
    response.delete_cookie(key="access_token", path="/", domain=domain)
    response.delete_cookie(key="refresh_token", path="/api/v1/auth", domain=domain)


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # 10 registrations per minute per IP
async def register(
    request: Request,
    response: Response,
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    # Validate password complexity
    validate_password(user_data.password)

    normalized_phone = normalize_phone(user_data.phone)

    # Resolve tenant from explicit slug first, then optional garage name fallback.
    target_tenant_id = None
    if user_data.tenant_slug:
        result = await db.execute(select(Tenant).where(Tenant.slug == user_data.tenant_slug))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        target_tenant_id = tenant.id
    elif user_data.garage_name and user_data.garage_name.strip():
        normalized_name = user_data.garage_name.strip().lower()
        result = await db.execute(
            select(Tenant).where(func.lower(Tenant.name) == normalized_name)
        )
        matching_tenants = result.scalars().all()
        if not matching_tenants:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found. Please check the name or use your shop code.",
            )
        if len(matching_tenants) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Multiple shops match this name. Please use your shop code.",
            )
        target_tenant_id = matching_tenants[0].id

    # Check if a global user identity already exists for this email
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        # --- Cross-tenant registration: link existing identity to a new shop ---
        # Security: require password verification before linking to prevent account takeover
        if not existing_user.hashed_password or not verify_password(user_data.password, existing_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )
        if not existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user",
            )
        if not target_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A shop is required to link your existing account to a new shop.",
            )

        # Reject if already linked to this shop
        link_result = await db.execute(
            select(UserCustomerLink).where(
                and_(
                    UserCustomerLink.user_id == existing_user.id,
                    UserCustomerLink.tenant_id == target_tenant_id,
                    UserCustomerLink.deleted_at.is_(None),
                )
            )
        )
        if link_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already registered at this shop. Please log in.",
            )

        # Find or match an existing Customer record in the target tenant
        customer_id = await _resolve_or_create_customer(
            db, user_data, normalized_phone, target_tenant_id
        )

        link = UserCustomerLink(
            user_id=existing_user.id,
            customer_id=customer_id,
            tenant_id=target_tenant_id,
        )
        db.add(link)
        await db.commit()

        token_version = await get_token_version(str(existing_user.id))
        access_token = create_access_token(
            data={"sub": str(existing_user.id)},
            tenant_id=str(target_tenant_id),
            token_version=token_version,
        )
        refresh_token = create_refresh_token(
            data={"sub": str(existing_user.id)},
            tenant_id=str(target_tenant_id),
            token_version=token_version,
        )
        set_auth_cookies(response, access_token, refresh_token)
        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

    # --- New user: create global identity + customer profile + link ---
    customer_id = None
    tenant_id = None

    if target_tenant_id:
        customer_id = await _resolve_or_create_customer(
            db, user_data, normalized_phone, target_tenant_id
        )
        tenant_id = target_tenant_id
    else:
        # No tenant specified — check for an existing Customer by email across all tenants
        result = await db.execute(select(Customer).where(Customer.email == user_data.email))
        existing_customer = result.scalar_one_or_none()
        if existing_customer:
            customer_id = existing_customer.id
            tenant_id = existing_customer.tenant_id
            target_tenant_id = tenant_id

    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=normalized_phone,
        role=UserRole.CUSTOMER,
        tenant_id=tenant_id,
        customer_id=customer_id,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.flush()

    if customer_id and target_tenant_id:
        db.add(UserCustomerLink(
            user_id=user.id,
            customer_id=customer_id,
            tenant_id=target_tenant_id,
        ))

    await db.commit()
    await db.refresh(user)

    tid = str(target_tenant_id) if target_tenant_id else None
    access_token = create_access_token(data={"sub": str(user.id)}, tenant_id=tid, token_version=0)
    refresh_token = create_refresh_token(data={"sub": str(user.id)}, tenant_id=tid, token_version=0)
    set_auth_cookies(response, access_token, refresh_token)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


async def _resolve_or_create_customer(
    db: AsyncSession,
    user_data,
    normalized_phone: Optional[str],
    tenant_id,
) -> "UUID":
    """Find an existing Customer in this tenant by email or phone, or create one."""
    # Try email match first
    result = await db.execute(
        select(Customer).where(
            and_(Customer.email == user_data.email, Customer.tenant_id == tenant_id)
        )
    )
    customer = result.scalar_one_or_none()

    # Try phone match for walk-ins with placeholder emails
    if not customer and normalized_phone:
        result = await db.execute(
            select(Customer).where(
                and_(Customer.phone == normalized_phone, Customer.tenant_id == tenant_id)
            )
        )
        customer = result.scalar_one_or_none()
        if customer and "@placeholder" in (customer.email or ""):
            customer.email = user_data.email
            customer.first_name = user_data.first_name
            customer.last_name = user_data.last_name

    if customer:
        return customer.id

    # No existing record — create a fresh Customer profile for this tenant
    new_customer = Customer(
        tenant_id=tenant_id,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        email=user_data.email,
        phone=normalized_phone,
        source="portal",
    )
    db.add(new_customer)
    await db.flush()
    return new_customer.id


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
    tenant_id_str = str(user.tenant_id) if user and user.tenant_id else "unknown"

    if not user or not user.hashed_password or not verify_password(credentials.password, user.hashed_password):
        record_login(success=False, tenant_id=tenant_id_str)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        record_login(success=False, tenant_id=tenant_id_str)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    token_version = await get_token_version(str(user.id))

    # For customers: check how many shops they belong to
    if user.role == UserRole.CUSTOMER:
        links_result = await db.execute(
            select(UserCustomerLink, Tenant)
            .join(Tenant, Tenant.id == UserCustomerLink.tenant_id)
            .where(
                and_(
                    UserCustomerLink.user_id == user.id,
                    UserCustomerLink.deleted_at.is_(None),
                )
            )
        )
        rows = links_result.all()

        if len(rows) > 1:
            # Multiple shops: return shop list and a short-lived selection token.
            # No cookies are set yet — the customer must pick a shop first.
            shops = [
                ShopOption(
                    id=str(tenant.id),
                    name=tenant.name,
                    slug=tenant.slug,
                    logo_url=tenant.logo_url,
                )
                for _, tenant in rows
            ]
            selection_token = create_shop_select_token(
                data={"sub": str(user.id)}, token_version=token_version
            )
            record_login(success=True, tenant_id="multi")
            return Token(
                access_token=selection_token,
                refresh_token="",
                requires_shop_selection=True,
                shops=shops,
            )

        # Single shop (or legacy user with no link yet): auto-select
        tid = str(rows[0][0].tenant_id) if rows else (str(user.tenant_id) if user.tenant_id else None)
    else:
        # Staff: no shop selection needed
        tid = None

    access_token = create_access_token(
        data={"sub": str(user.id)}, tenant_id=tid, token_version=token_version
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)},
        tenant_id=tid,
        token_version=token_version,
        remember_me=credentials.remember_me,
    )
    set_auth_cookies(response, access_token, refresh_token, remember_me=credentials.remember_me)
    record_login(success=True, tenant_id=tid or tenant_id_str)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.post("/select-tenant", response_model=Token)
@limiter.limit("10/minute")
async def select_tenant(
    request: Request,
    response: Response,
    body: SelectTenantRequest,
    token: str = Depends(get_token_from_request),
    db: AsyncSession = Depends(get_db),
):
    """Exchange a shop-select token + tenant choice for a full scoped JWT."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "shop_select":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired shop selection token",
        )

    user_id: Optional[str] = payload.get("sub")
    jti: Optional[str] = payload.get("jti")
    token_version: int = payload.get("ver", 0)

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if jti and await is_token_blacklisted(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    current_version = await get_token_version(user_id)
    if token_version < current_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been invalidated")

    # Validate that this user actually belongs to the requested tenant
    link_result = await db.execute(
        select(UserCustomerLink).where(
            and_(
                UserCustomerLink.user_id == user_id,
                UserCustomerLink.tenant_id == body.tenant_id,
                UserCustomerLink.deleted_at.is_(None),
            )
        )
    )
    if not link_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Blacklist the selection token — it's single-use
    if jti:
        expiry = get_token_expiry_seconds(token)
        if expiry > 0:
            await blacklist_token(jti, expiry)

    tid = str(body.tenant_id)
    access_token = create_access_token(
        data={"sub": user_id}, tenant_id=tid, token_version=current_version
    )
    new_refresh_token = create_refresh_token(
        data={"sub": user_id}, tenant_id=tid, token_version=current_version
    )
    set_auth_cookies(response, access_token, new_refresh_token)
    return {"access_token": access_token, "refresh_token": new_refresh_token, "token_type": "bearer"}


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
    
    # Preserve remember_me and tenant scope from original token
    remember_me = payload.get("rem", False)
    tid = payload.get("tid")

    access_token = create_access_token(
        data={"sub": str(user.id)}, token_version=current_version, tenant_id=tid
    )
    new_refresh_token = create_refresh_token(
        data={"sub": str(user.id)}, token_version=current_version, remember_me=remember_me, tenant_id=tid
    )
    
    # Set httpOnly cookies
    set_auth_cookies(response, access_token, new_refresh_token, remember_me=remember_me)
    
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
    record_logout(tenant_id=str(current_user.tenant_id) if current_user.tenant_id else "unknown")
    
    return LogoutResponse(message="Successfully logged out")


@router.post("/workos/logout", response_model=LogoutResponse)
async def workos_logout(request: Request, response: Response):
    """End only the short-lived repair-shop WorkOS session.

    This intentionally does not clear the legacy refresh cookie or any future
    platform-admin session; callers must present a WorkOS-marked access token.
    """
    token = request.cookies.get("access_token")
    payload = decode_token(token) if token else None
    session_id = request.cookies.get("workos_session")
    if (not payload or payload.get("auth_provider") != "workos") and not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="WorkOS session required")
    if payload and payload.get("auth_provider") == "workos" and payload.get("jti"):
        expiry = get_token_expiry_seconds(token)
        if expiry > 0:
            await blacklist_token(payload["jti"], expiry)
    if session_id:
        await workos_session.delete_session(session_id)
    response.delete_cookie("access_token", path="/", domain=_cookie_domain())
    response.delete_cookie("workos_session", path="/api/v1/auth/workos", domain=_cookie_domain())
    return LogoutResponse(message="Successfully logged out of repair-shop session")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _build_user_response(current_user, db)


@router.get("/me/appearance", response_model=PresentationResponse)
async def get_current_appearance(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_appearance(db, current_user)


@router.put("/me/appearance", response_model=PresentationResponse)
async def put_current_appearance(
    body: AppearanceUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_appearance(
        db,
        current_user,
        base_revision=body.base_revision,
        appearance=body.appearance,
        migration_source=body.migration_source,
    )


@router.delete("/me/appearance", response_model=PresentationResponse)
async def delete_current_appearance(
    body: AppearanceResetRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await reset_appearance(db, current_user, base_revision=body.base_revision)


@router.put("/me/tenant-presentation", response_model=PresentationResponse)
async def put_tenant_presentation(
    body: TenantPresentationRolloutRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Let a shop owner or admin switch their own tenant between workspaces.

    The rollout endpoint under /admin is super-admin only, which meant a shop
    could not move itself between the classic and modern workspace without
    platform help. This is the same operation scoped to the caller's tenant.
    """
    return await set_own_tenant_presentation(db, current_user, body.presentation)


@router.get("/my-shops", response_model=List[ShopOption])
async def get_my_shops(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all shops the current customer belongs to."""
    if current_user.role != UserRole.CUSTOMER:
        return []

    links_result = await db.execute(
        select(UserCustomerLink, Tenant)
        .join(Tenant, Tenant.id == UserCustomerLink.tenant_id)
        .where(
            and_(
                UserCustomerLink.user_id == current_user.id,
                UserCustomerLink.deleted_at.is_(None),
            )
        )
    )
    return [
        ShopOption(id=str(tenant.id), name=tenant.name, slug=tenant.slug, logo_url=tenant.logo_url)
        for _, tenant in links_result.all()
    ]


@router.post("/switch-shop", response_model=Token)
async def switch_shop(
    response: Response,
    body: SelectTenantRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Switch the active shop context for a multi-tenant customer."""
    if current_user.role != UserRole.CUSTOMER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only customers can switch shops")

    link_result = await db.execute(
        select(UserCustomerLink).where(
            and_(
                UserCustomerLink.user_id == current_user.id,
                UserCustomerLink.tenant_id == body.tenant_id,
                UserCustomerLink.deleted_at.is_(None),
            )
        )
    )
    if not link_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    tid = str(body.tenant_id)
    token_version = await get_token_version(str(current_user.id))
    access_token = create_access_token(data={"sub": str(current_user.id)}, tenant_id=tid, token_version=token_version)
    new_refresh_token = create_refresh_token(data={"sub": str(current_user.id)}, tenant_id=tid, token_version=token_version)
    set_auth_cookies(response, access_token, new_refresh_token)
    return {"access_token": access_token, "refresh_token": new_refresh_token, "token_type": "bearer"}


@router.get("/tenant-branding", response_model=TenantBrandingResponse)
async def get_current_tenant_branding(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.tenant_id or current_user.role == UserRole.SUPER_ADMIN:
        return TenantBrandingResponse()

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        return TenantBrandingResponse()

    return TenantBrandingResponse(
        name=tenant.name,
        slug=tenant.slug,
        logo_url=tenant.logo_url,
        state=extract_us_state(tenant.address),
    )


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


class PlatformContactResponse(BaseModel):
    support_name: str
    support_email: Optional[str] = None
    support_phone: Optional[str] = None


class LandingPartnerResponse(BaseModel):
    id: str
    name: str
    slug: str
    address: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    partner_summary: Optional[str] = None
    partner_services: Optional[str] = None


@router.get("/platform-contact", response_model=PlatformContactResponse)
async def get_platform_contact(
    db: AsyncSession = Depends(get_db),
):
    """
    Public platform support contact details for customer-facing pages.
    Source of truth is the most recently updated active super admin profile.
    """
    active_super_admin_result = await db.execute(
        select(User)
        .where(
            User.role == UserRole.SUPER_ADMIN,
            User.is_active == True,
        )
        .order_by(User.updated_at.desc(), User.created_at.desc())
    )
    support_user = active_super_admin_result.scalars().first()

    if not support_user:
        fallback_super_admin_result = await db.execute(
            select(User)
            .where(User.role == UserRole.SUPER_ADMIN)
            .order_by(User.updated_at.desc(), User.created_at.desc())
        )
        support_user = fallback_super_admin_result.scalars().first()

    if not support_user:
        return PlatformContactResponse(
            support_name="Diesel Bridge Support",
            support_email=None,
            support_phone=None,
        )

    support_name = f"{support_user.first_name} {support_user.last_name}".strip() or "Diesel Bridge Support"
    return PlatformContactResponse(
        support_name=support_name,
        support_email=support_user.email,
        support_phone=support_user.phone,
    )


@router.get("/landing-partners", response_model=List[LandingPartnerResponse])
async def get_landing_partners(
    db: AsyncSession = Depends(get_db),
):
    """Public list of approved active businesses to showcase on the landing page."""
    result = await db.execute(
        select(Tenant)
        .where(
            Tenant.enrollment_status == "approved",
            Tenant.is_active == True,
        )
        .order_by(Tenant.name.asc())
    )
    tenants = result.scalars().all()

    return [
        LandingPartnerResponse(
            id=str(tenant.id),
            name=tenant.name,
            slug=tenant.slug,
            address=tenant.address,
            website=tenant.website,
            logo_url=tenant.logo_url,
            partner_summary=tenant.partner_summary,
            partner_services=tenant.partner_services,
        )
        for tenant in tenants
    ]


@router.put("/me", response_model=ProfileUpdateResponse)
async def update_current_user(
    update_data: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update current user's profile (name, phone, email)"""
    persisted_user = identity_user(current_user)
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
        if not current_user.hashed_password or not verify_password(update_data.password, current_user.hashed_password):
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
        
        # Resolve shop name for branding
        shop_name = None
        if current_user.tenant_id:
            from app.db.models.tenant import Tenant
            tenant_result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
            tenant = tenant_result.scalar_one_or_none()
            shop_name = tenant.name if tenant else None

        # Send verification email to NEW address
        try:
            await send_email_verification(new_email, verification_token, shop_name=shop_name)
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
                f"{current_user.first_name} {current_user.last_name}",
                shop_name=shop_name,
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
    if 'phone' in data:
        data['phone'] = normalize_phone(data['phone'])
    
    # If only email was being changed (no other fields to update), return early
    if email_verification_pending and not any(k in data for k in ['first_name', 'last_name', 'phone']):
        response_user = await _build_user_response(current_user, db)
        return ProfileUpdateResponse(
            user=response_user,
            message="Verification email sent. Please check your new email address to confirm the change.",
            email_verification_pending=True
        )
    
    # Update User fields
    for field, value in data.items():
        setattr(persisted_user, field, value)
    
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
    await db.refresh(persisted_user)
    
    # Build appropriate message based on what was updated
    message = None
    if email_verification_pending:
        message = "Profile updated. A verification email has been sent to your new email address."
    
    response_user = await _build_user_response(current_user, db)
    
    return ProfileUpdateResponse(
        user=response_user,
        message=message,
        email_verification_pending=email_verification_pending
    )


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class PasswordChangeResponse(BaseModel):
    message: str
    tokens_invalidated: bool = True


class VerifyPasswordRequest(BaseModel):
    password: str


class VerifyPasswordResponse(BaseModel):
    valid: bool


class PaymentStepUpGrantRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    scope: PaymentStepUpScope
    target_tenant_id: Optional[UUID] = None


class PaymentStepUpGrantResponse(BaseModel):
    grant_token: str
    scope: PaymentStepUpScope
    expires_at: datetime
    one_time: bool


@router.post("/step-up-grants", response_model=PaymentStepUpGrantResponse)
@limiter.limit("20/hour")
@limiter.limit("5/15 minutes")
async def create_payment_step_up_grant(
    request: Request,
    body: PaymentStepUpGrantRequest,
    db: AsyncSession = Depends(get_db),
    context: PaymentStepUpContext = Depends(get_payment_step_up_context),
):
    """Verify the current user and issue a server-stored payment-settings grant."""
    validate_scope_authority(context.current_user, body.scope, body.target_tenant_id)
    if not context.current_user.hashed_password:
        db.add(
            payment_step_up_audit_event(
                context=context,
                event_type="denied",
                scope=body.scope,
                target_tenant_id=body.target_tenant_id,
                metadata={"reason": "method_unavailable"},
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STEP_UP_METHOD_UNAVAILABLE",
                "message": "This account has no local password available for payment-settings verification.",
            },
        )
    if not verify_password(body.password, context.current_user.hashed_password):
        db.add(
            payment_step_up_audit_event(
                context=context,
                event_type="denied",
                scope=body.scope,
                target_tenant_id=body.target_tenant_id,
                metadata={"reason": "verification_failed"},
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "STEP_UP_VERIFICATION_FAILED",
                "message": "Password verification failed.",
            },
        )

    grant, raw_grant = issue_step_up_grant(
        context=context,
        scope=body.scope,
        target_tenant_id=body.target_tenant_id,
    )
    db.add(grant)
    await db.flush()
    db.add(
        payment_step_up_audit_event(
            context=context,
            event_type="issued",
            scope=body.scope,
            grant=grant,
            target_tenant_id=body.target_tenant_id,
        )
    )
    await db.commit()
    return PaymentStepUpGrantResponse(
        grant_token=raw_grant,
        scope=body.scope,
        expires_at=grant.expires_at,
        one_time=grant.one_time,
    )


@router.post("/verify-password", response_model=VerifyPasswordResponse)
@limiter.limit("20/hour")
@limiter.limit("5/15 minutes")
async def verify_user_password(
    request: Request,
    body: VerifyPasswordRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Verify current user's password without changing anything."""
    is_valid = bool(current_user.hashed_password) and verify_password(body.password, current_user.hashed_password)
    return VerifyPasswordResponse(valid=is_valid)


@router.post("/change-password", response_model=PasswordChangeResponse)
async def change_password(
    password_data: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Change current user's password and invalidate all existing tokens."""
    # Validate new password complexity
    validate_password(password_data.new_password)
    
    # Verify current password
    if not current_user.hashed_password or not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    
    # Update password
    persisted_user = identity_user(current_user)
    persisted_user.hashed_password = get_password_hash(password_data.new_password)
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
    
    if user and user.is_active and user.hashed_password:
        # Generate secure random token
        reset_token = secrets.token_urlsafe(32)

        # Store token in Redis (expires in 1 hour)
        await store_password_reset_token(forgot_request.email, reset_token, expires_in=3600)

        # Resolve shop name for tenant-specific branding
        shop_name = None
        if user.tenant_id:
            from app.db.models.tenant import Tenant
            tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
            tenant = tenant_result.scalar_one_or_none()
            shop_name = tenant.name if tenant else None

        # Send email
        try:
            await send_password_reset_email(forgot_request.email, reset_token, shop_name=shop_name)
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
    # Validate new password complexity
    validate_password(reset_request.new_password)
    
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
    
    if not user or not user.hashed_password:
        await delete_password_reset_token(reset_request.token)
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


# ============================================================================
# Garage Enrollment
# ============================================================================

class GarageEnrollmentRequest(BaseModel):
    # Garage info
    garage_name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r'^[a-z0-9-]+$')
    address: str = Field(..., min_length=5, max_length=500)
    phone: str = Field(..., min_length=10, max_length=20)
    email: EmailStr  # Garage contact email
    website: Optional[str] = Field(None, max_length=255)
    business_license: Optional[str] = Field(None, max_length=100)
    ein: Optional[str] = Field(None, max_length=20)  # XX-XXXXXXX format
    
    # Owner info
    owner_email: EmailStr
    owner_first_name: str = Field(..., min_length=1, max_length=100)
    owner_last_name: str = Field(..., min_length=1, max_length=100)
    owner_phone: str = Field(..., min_length=10, max_length=20)
    owner_password: str = Field(..., min_length=8)


class GarageEnrollmentResponse(BaseModel):
    message: str
    garage_name: str
    status: str = "pending"


@router.post("/enroll-garage", response_model=GarageEnrollmentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")  # Rate limit: 5 enrollments per hour per IP
async def enroll_garage(
    request: Request,
    enrollment_data: GarageEnrollmentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint for garage owners to apply for platform enrollment.
    Creates a tenant and owner user with pending status.
    """
    if enrollment_data.email.strip().lower() != enrollment_data.owner_email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business contact email and owner login email must match.",
        )

    # Validate password complexity
    validate_password(enrollment_data.owner_password)
    
    # Validate EIN format if provided (XX-XXXXXXX)
    if enrollment_data.ein:
        ein_pattern = r'^\d{2}-\d{7}$'
        if not re.match(ein_pattern, enrollment_data.ein):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="EIN must be in format XX-XXXXXXX (e.g., 12-3456789)",
            )
    
    # Check if slug is already taken
    result = await db.execute(select(Tenant).where(Tenant.slug == enrollment_data.slug))
    existing_tenant = result.scalar_one_or_none()
    if existing_tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This shop URL slug is already taken. Please choose another.",
        )
    
    # Check if owner email is already registered
    result = await db.execute(select(User).where(User.email == enrollment_data.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is already registered. Please log in or use a different email.",
        )
    
    # Create tenant with pending status
    tenant = Tenant(
        name=enrollment_data.garage_name,
        slug=enrollment_data.slug,
        address=enrollment_data.address,
        phone=enrollment_data.phone,
        email=enrollment_data.email,
        website=enrollment_data.website,
        business_license=enrollment_data.business_license,
        ein=enrollment_data.ein,
        is_active=False,  # Not active until approved
        enrollment_status="pending",
        applied_at=datetime.now(timezone.utc),
    )
    
    db.add(tenant)
    await db.flush()  # Get tenant ID

    if tenant.website:
        try:
            tenant.logo_url = await import_logo_from_website(tenant.website, tenant_id=str(tenant.id))
        except Exception as exc:
            logger.warning(
                "tenant_logo_import_failed_during_enrollment",
                tenant_id=str(tenant.id),
                website=tenant.website,
                error=str(exc),
            )
    
    # Create owner user with inactive status
    owner = User(
        email=enrollment_data.email,
        hashed_password=get_password_hash(enrollment_data.owner_password),
        first_name=enrollment_data.owner_first_name,
        last_name=enrollment_data.owner_last_name,
        phone=enrollment_data.owner_phone,
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=False,  # Not active until approved
        is_verified=False,
    )
    
    db.add(owner)
    await db.flush()

    # Every garage gets an internal-fleet house account for its own trucks.
    from app.services.internal_fleet import ensure_internal_fleet_customer
    await ensure_internal_fleet_customer(db, tenant.id)

    # Link owner to tenant
    tenant.owner_id = owner.id
    
    await db.commit()
    
    # Send confirmation email to applicant
    owner_name = f"{enrollment_data.owner_first_name} {enrollment_data.owner_last_name}"
    try:
        await send_enrollment_received_email(
            to=enrollment_data.email,
            garage_name=enrollment_data.garage_name,
            owner_name=owner_name,
        )
    except Exception as e:
        print(f"Error sending enrollment confirmation: {e}")
    
    # Notify super admins
    result = await db.execute(
        select(User.email).where(User.role == UserRole.SUPER_ADMIN, User.is_active == True)
    )
    admin_emails = [row[0] for row in result.all()]
    
    if admin_emails:
        try:
            await send_new_enrollment_notification(
                admin_emails=admin_emails,
                garage_name=enrollment_data.garage_name,
                owner_name=owner_name,
                owner_email=enrollment_data.email,
            )
        except Exception as e:
            print(f"Error sending admin notification: {e}")
    
    return GarageEnrollmentResponse(
        message="Your application has been submitted successfully. We'll review it and get back to you within 1-2 business days.",
        garage_name=enrollment_data.garage_name,
        status="pending",
    )
