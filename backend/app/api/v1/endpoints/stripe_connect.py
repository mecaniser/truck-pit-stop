from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Optional
from urllib.parse import urlencode

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_db, user_has_permission
from app.core.logging import get_logger
from app.db.models.stripe_oauth import StripeOAuthState
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = get_logger(__name__)
router = APIRouter()
STRIPE_AUTHORIZE_URL = "https://connect.stripe.com/oauth/authorize"


class OAuthLinkResponse(BaseModel):
    url: str


class ConnectStatusResponse(BaseModel):
    configured: bool
    is_connected: bool
    onboarding_complete: bool
    charges_enabled: bool
    payouts_enabled: bool
    account_id: Optional[str]
    connection_type: Optional[str]


class DisconnectResponse(BaseModel):
    is_connected: bool = False


def _require_garage_admin(current_user: User) -> None:
    if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN) or not user_has_permission(current_user, "payments"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to Stripe settings.")


def _oauth_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_CONNECT_CLIENT_ID and settings.STRIPE_CONNECT_REDIRECT_URI)


async def _tenant_for(current_user: User, db: AsyncSession) -> Tenant:
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.post("/connect", response_model=OAuthLinkResponse)
async def start_standard_oauth(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Redirect a garage owner to Stripe to authorize an existing Standard account."""
    _require_garage_admin(current_user)
    if not _oauth_configured():
        raise HTTPException(status_code=503, detail="Stripe Connect is not available yet")
    tenant = await _tenant_for(current_user, db)
    state = token_urlsafe(32)
    db.add(StripeOAuthState(
        state_hash=sha256(state.encode()).hexdigest(), tenant_id=tenant.id,
        initiated_by_user_id=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.STRIPE_CONNECT_OAUTH_STATE_TTL_SECONDS),
    ))
    await db.commit()
    return OAuthLinkResponse(url=f"{STRIPE_AUTHORIZE_URL}?{urlencode({'response_type': 'code', 'client_id': settings.STRIPE_CONNECT_CLIENT_ID, 'scope': 'read_write', 'redirect_uri': settings.STRIPE_CONNECT_REDIRECT_URI, 'state': state})}")


@router.post("/onboard", response_model=OAuthLinkResponse, deprecated=True)
async def start_standard_oauth_compat(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return await start_standard_oauth(db, current_user)


@router.get("/oauth/callback", include_in_schema=False)
async def stripe_oauth_callback(state: str = Query(..., min_length=20, max_length=512), code: Optional[str] = Query(None), error: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    state_record = (await db.execute(select(StripeOAuthState).where(StripeOAuthState.state_hash == sha256(state.encode()).hexdigest()))).scalar_one_or_none()
    frontend = settings.FRONTEND_URL.rstrip("/")
    expires_at = state_record.expires_at if state_record else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not state_record or state_record.consumed_at or expires_at < datetime.now(timezone.utc):
        return RedirectResponse(f"{frontend}/dashboard/settings?stripe=error", status_code=303)
    state_record.consumed_at = datetime.now(timezone.utc)
    await db.commit()
    if error or not code:
        return RedirectResponse(f"{frontend}/dashboard/settings?stripe=not-connected", status_code=303)
    try:
        authorization = stripe.OAuth.token(api_key=settings.STRIPE_SECRET_KEY, grant_type="authorization_code", code=code)
        account_id = authorization.get("stripe_user_id")
        if not account_id:
            raise ValueError("Stripe did not return an account")
        account = stripe.Account.retrieve(account_id)
    except Exception:
        logger.exception("stripe_standard_oauth_exchange_failed", tenant_id=str(state_record.tenant_id))
        return RedirectResponse(f"{frontend}/dashboard/settings?stripe=error", status_code=303)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == state_record.tenant_id))).scalar_one_or_none()
    if not tenant:
        return RedirectResponse(f"{frontend}/dashboard/settings?stripe=error", status_code=303)
    if tenant.stripe_account_id and tenant.stripe_connection_type not in (None, "standard_oauth"):
        return RedirectResponse(f"{frontend}/dashboard/settings?stripe=legacy-account", status_code=303)
    owner = (await db.execute(select(Tenant).where(Tenant.stripe_account_id == account_id, Tenant.id != tenant.id))).scalar_one_or_none()
    if owner:
        return RedirectResponse(f"{frontend}/dashboard/settings?stripe=account-in-use", status_code=303)
    tenant.stripe_account_id = account_id
    tenant.stripe_connection_type = "standard_oauth"
    tenant.stripe_onboarding_complete = bool(account.get("charges_enabled") and account.get("payouts_enabled"))
    await db.commit()
    logger.info("stripe_standard_oauth_connected", tenant_id=str(tenant.id), account_id=account_id)
    return RedirectResponse(f"{frontend}/dashboard/settings?stripe=connected", status_code=303)


@router.get("/status", response_model=ConnectStatusResponse)
async def get_connect_status(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _require_garage_admin(current_user)
    tenant = await _tenant_for(current_user, db)
    if not tenant.stripe_account_id:
        return ConnectStatusResponse(configured=_oauth_configured(), is_connected=False, onboarding_complete=False, charges_enabled=False, payouts_enabled=False, account_id=None, connection_type=None)
    try:
        account = stripe.Account.retrieve(tenant.stripe_account_id)
        charges_enabled, payouts_enabled = bool(account.get("charges_enabled")), bool(account.get("payouts_enabled"))
        complete = charges_enabled and payouts_enabled
        if tenant.stripe_onboarding_complete != complete:
            tenant.stripe_onboarding_complete = complete
            await db.commit()
        return ConnectStatusResponse(configured=_oauth_configured(), is_connected=True, onboarding_complete=complete, charges_enabled=charges_enabled, payouts_enabled=payouts_enabled, account_id=tenant.stripe_account_id, connection_type=tenant.stripe_connection_type or "express_legacy")
    except stripe.error.StripeError:
        raise HTTPException(status_code=502, detail="Unable to retrieve Stripe account status")


@router.post("/disconnect", response_model=DisconnectResponse)
async def disconnect_stripe_account(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Remove this garage's Stripe relationship without deleting its Stripe account."""
    _require_garage_admin(current_user)
    tenant = await _tenant_for(current_user, db)
    if tenant.stripe_account_id and tenant.stripe_connection_type == "standard_oauth":
        try:
            stripe.OAuth.deauthorize(api_key=settings.STRIPE_SECRET_KEY, client_id=settings.STRIPE_CONNECT_CLIENT_ID, stripe_user_id=tenant.stripe_account_id)
        except stripe.error.StripeError:
            raise HTTPException(status_code=502, detail="Unable to disconnect Stripe account")
    tenant.stripe_account_id = None
    tenant.stripe_connection_type = None
    tenant.stripe_onboarding_complete = False
    await db.commit()
    return DisconnectResponse()


@router.post("/dashboard", response_model=OAuthLinkResponse)
async def create_dashboard_link(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _require_garage_admin(current_user)
    tenant = await _tenant_for(current_user, db)
    if tenant.stripe_connection_type == "standard_oauth":
        raise HTTPException(status_code=400, detail="Manage this account directly in Stripe Dashboard")
    if not tenant.stripe_account_id:
        raise HTTPException(status_code=400, detail="Stripe account not connected")
    return OAuthLinkResponse(url=stripe.Account.create_login_link(tenant.stripe_account_id).url)
