"""Tenant-owned QuickBooks Online OAuth endpoints.

These endpoints authorize both QBO Accounting and QBO Payments. They do not
accept card data and do not yet create QuickBooks invoices or charges.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_db, user_has_permission
from app.core.logging import get_logger
from app.db.models.quickbooks_connection import QuickBooksConnection, QuickBooksOAuthState
from app.db.models.user import User, UserRole
from app.services.quickbooks_service import (
    QuickBooksConfigurationError,
    QuickBooksOAuthError,
    build_authorization_url,
    disconnect,
    ensure_quickbooks_configured,
    exchange_authorization_code,
    is_quickbooks_configured,
    save_token_set,
)


router = APIRouter()
logger = get_logger(__name__)


class QuickBooksAuthorizationResponse(BaseModel):
    url: str


class QuickBooksConnectionStatusResponse(BaseModel):
    configured: bool
    is_connected: bool
    realm_id: Optional[str] = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: Optional[datetime] = None


def _require_quickbooks_admin(current_user: User) -> None:
    if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only shop administrators can manage QuickBooks settings",
        )
    if not user_has_permission(current_user, "payments"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to QuickBooks settings. Ask the shop owner to grant access.",
        )
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")


def _state_hash(state_value: str) -> str:
    return sha256(state_value.encode("utf-8")).hexdigest()


def _callback_redirect(result: str) -> RedirectResponse:
    # The target is deployment configuration, never a browser-provided URL.
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/settings?quickbooks={result}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


async def _get_connection(db: AsyncSession, tenant_id) -> Optional[QuickBooksConnection]:
    result = await db.execute(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id == tenant_id))
    return result.scalar_one_or_none()


@router.get("/status", response_model=QuickBooksConnectionStatusResponse)
async def quickbooks_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_quickbooks_admin(current_user)
    connection = await _get_connection(db, current_user.tenant_id)
    is_connected = bool(connection and connection.status == "connected" and connection.realm_id)
    return QuickBooksConnectionStatusResponse(
        configured=is_quickbooks_configured(),
        is_connected=is_connected,
        realm_id=connection.realm_id if is_connected else None,
        scopes=connection.scopes.split() if is_connected and connection.scopes else [],
        connected_at=connection.connected_at if is_connected else None,
    )


@router.post("/connect", response_model=QuickBooksAuthorizationResponse)
async def begin_quickbooks_connection(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Start one-time OAuth consent for the signed-in tenant administrator."""
    _require_quickbooks_admin(current_user)
    try:
        ensure_quickbooks_configured()
    except QuickBooksConfigurationError:
        logger.warning("quickbooks_connection_requested_without_configuration", tenant_id=str(current_user.tenant_id))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="QuickBooks is not configured for this environment",
        )

    state_value = token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        QuickBooksOAuthState(
            state_hash=_state_hash(state_value),
            tenant_id=current_user.tenant_id,
            initiated_by_user_id=current_user.id,
            expires_at=now + timedelta(seconds=settings.QUICKBOOKS_OAUTH_STATE_TTL_SECONDS),
        )
    )
    await db.commit()
    return QuickBooksAuthorizationResponse(url=build_authorization_url(state_value))


@router.get("/oauth/callback", include_in_schema=False)
async def quickbooks_oauth_callback(
    state_value: str = Query(..., alias="state", min_length=20, max_length=512),
    code: Optional[str] = Query(None, min_length=1, max_length=4096),
    realm_id: Optional[str] = Query(None, alias="realmId", min_length=1, max_length=64),
    oauth_error: Optional[str] = Query(None, alias="error", max_length=100),
    db: AsyncSession = Depends(get_db),
):
    """Consume the one-time state and persist an encrypted Intuit token set."""
    now = datetime.now(timezone.utc)
    state_result = await db.execute(
        select(QuickBooksOAuthState)
        .where(
            QuickBooksOAuthState.state_hash == _state_hash(state_value),
            QuickBooksOAuthState.consumed_at.is_(None),
            QuickBooksOAuthState.expires_at >= now,
        )
        .with_for_update()
    )
    oauth_state = state_result.scalar_one_or_none()
    if not oauth_state:
        # A non-redirect error prevents an arbitrary site from using this
        # callback as an open redirect and makes state replay visible to Intuit.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired QuickBooks authorization state")

    # Commit before calling Intuit so a double callback cannot race this request.
    oauth_state.consumed_at = now
    await db.commit()

    if oauth_error or not code or not realm_id:
        logger.info("quickbooks_authorization_not_completed", tenant_id=str(oauth_state.tenant_id))
        return _callback_redirect("not-connected")

    try:
        token_set = await exchange_authorization_code(code)
    except (QuickBooksConfigurationError, QuickBooksOAuthError):
        logger.warning("quickbooks_authorization_exchange_failed", tenant_id=str(oauth_state.tenant_id))
        return _callback_redirect("error")

    other_realm_result = await db.execute(
        select(QuickBooksConnection).where(
            QuickBooksConnection.realm_id == realm_id,
            QuickBooksConnection.tenant_id != oauth_state.tenant_id,
            QuickBooksConnection.status == "connected",
        )
    )
    if other_realm_result.scalar_one_or_none():
        logger.warning("quickbooks_realm_already_connected", tenant_id=str(oauth_state.tenant_id))
        return _callback_redirect("realm-in-use")

    connection = await _get_connection(db, oauth_state.tenant_id)
    if not connection:
        connection = QuickBooksConnection(tenant_id=oauth_state.tenant_id)
        db.add(connection)
    try:
        save_token_set(
            connection,
            realm_id=realm_id,
            token_set=token_set,
            now=datetime.now(timezone.utc),
        )
        await db.commit()
    except (IntegrityError, QuickBooksOAuthError, RuntimeError):
        await db.rollback()
        logger.exception("quickbooks_connection_persist_failed", tenant_id=str(oauth_state.tenant_id))
        return _callback_redirect("error")

    logger.info("quickbooks_connection_established", tenant_id=str(oauth_state.tenant_id))
    return _callback_redirect("connected")


@router.post("/disconnect", response_model=QuickBooksConnectionStatusResponse)
async def disconnect_quickbooks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Forget local QuickBooks credentials for this tenant."""
    _require_quickbooks_admin(current_user)
    connection = await _get_connection(db, current_user.tenant_id)
    if connection:
        disconnect(connection)
        await db.commit()
        logger.info("quickbooks_connection_disconnected", tenant_id=str(current_user.tenant_id))
    return QuickBooksConnectionStatusResponse(configured=is_quickbooks_configured(), is_connected=False)
