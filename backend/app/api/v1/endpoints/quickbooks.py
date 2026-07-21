"""Tenant-owned QuickBooks Online OAuth endpoints.

These endpoints authorize both QBO Accounting and QBO Payments. They do not
accept card data and do not yet create QuickBooks invoices or charges.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import base64
import hashlib
import hmac
import json
from hashlib import sha256
from secrets import token_urlsafe
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_db, user_has_permission
from app.core.logging import get_logger
from app.db.models.quickbooks_connection import QuickBooksConnection, QuickBooksOAuthState
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.quickbooks_service import (
    QuickBooksConfigurationError,
    QuickBooksOAuthError,
    build_authorization_url,
    disconnect,
    ensure_quickbooks_configured,
    exchange_authorization_code,
    is_quickbooks_configured,
    refresh_access_token,
    save_token_set,
)
from app.services.quickbooks_payment_finalization import (
    finalize_quickbooks_invoice_payment,
    find_quickbooks_payment,
)
from app.services.quickbooks_payments_service import (
    QuickBooksPaymentError,
    create_charge,
    is_successful_charge,
    payments_base_url,
)
from app.services.payment_number_service import allocate_next_payment_number


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
    token_health: str = "not_connected"
    last_token_refresh_at: Optional[datetime] = None
    last_token_refresh_error: Optional[str] = None
    last_webhook_at: Optional[datetime] = None
    last_webhook_event: Optional[str] = None
    last_webhook_error: Optional[str] = None


class QuickBooksPaymentAvailabilityResponse(BaseModel):
    available: bool
    token_url: Optional[str] = None
    message: Optional[str] = None


class QuickBooksChargeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: UUID
    token: str = Field(min_length=8, max_length=2048)
    idempotency_key: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class QuickBooksChargeResponse(BaseModel):
    status: str
    charge_id: str
    payment_id: Optional[UUID] = None
    message: str


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


def _connection_token_health(connection: Optional[QuickBooksConnection]) -> str:
    if not connection or connection.status != "connected" or not connection.realm_id:
        return "not_connected"
    if not connection.encrypted_access_token or not connection.encrypted_refresh_token:
        return "reconnect_required"
    now = datetime.now(timezone.utc)
    if connection.refresh_token_expires_at and connection.refresh_token_expires_at <= now:
        return "reconnect_required"
    if connection.access_token_expires_at and connection.access_token_expires_at <= now + timedelta(minutes=5):
        return "refresh_required"
    return "healthy"


def _status_response(connection: Optional[QuickBooksConnection]) -> QuickBooksConnectionStatusResponse:
    is_connected = bool(connection and connection.status == "connected" and connection.realm_id)
    return QuickBooksConnectionStatusResponse(
        configured=is_quickbooks_configured(),
        is_connected=is_connected,
        realm_id=connection.realm_id if is_connected else None,
        scopes=connection.scopes.split() if is_connected and connection.scopes else [],
        connected_at=connection.connected_at if is_connected else None,
        token_health=_connection_token_health(connection),
        last_token_refresh_at=connection.last_token_refresh_at if connection else None,
        last_token_refresh_error=connection.last_token_refresh_error if connection else None,
        last_webhook_at=connection.last_webhook_at if connection else None,
        last_webhook_event=connection.last_webhook_event if connection else None,
        last_webhook_error=connection.last_webhook_error if connection else None,
    )


def _quickbooks_payments_token_url() -> str:
    return f"{payments_base_url()}/quickbooks/v4/payments/tokens"


async def _refresh_connection_if_needed(db: AsyncSession, connection: QuickBooksConnection) -> None:
    if _connection_token_health(connection) != "refresh_required":
        return
    try:
        token_set = await refresh_access_token(connection)
        save_token_set(connection, realm_id=connection.realm_id or "", token_set=token_set)
        connection.last_token_refresh_at = datetime.now(timezone.utc)
        connection.last_token_refresh_error = None
        await db.commit()
    except (QuickBooksConfigurationError, QuickBooksOAuthError) as exc:
        connection.last_token_refresh_error = str(exc)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="QuickBooks requires this shop to reconnect") from exc


@router.get("/status", response_model=QuickBooksConnectionStatusResponse)
async def quickbooks_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_quickbooks_admin(current_user)
    connection = await _get_connection(db, current_user.tenant_id)
    return _status_response(connection)


@router.post("/health/check", response_model=QuickBooksConnectionStatusResponse)
async def check_quickbooks_connection_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Refresh an expiring tenant token and return secret-free connection health."""
    _require_quickbooks_admin(current_user)
    connection = await _get_connection(db, current_user.tenant_id)
    if not connection:
        return _status_response(None)
    if _connection_token_health(connection) == "refresh_required":
        try:
            token_set = await refresh_access_token(connection)
            save_token_set(connection, realm_id=connection.realm_id or "", token_set=token_set)
            connection.last_token_refresh_at = datetime.now(timezone.utc)
            connection.last_token_refresh_error = None
        except (QuickBooksConfigurationError, QuickBooksOAuthError) as exc:
            connection.last_token_refresh_error = str(exc)
        await db.commit()
    return _status_response(connection)


@router.get("/payments/availability/{invoice_id}", response_model=QuickBooksPaymentAvailabilityResponse)
async def quickbooks_payment_availability(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return the direct-to-Intuit token endpoint only for an eligible invoice."""
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only customers can pay invoices")
    invoice = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not invoice or invoice.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    owner = (await db.execute(select(RepairOrder.customer_id).where(RepairOrder.id == invoice.repair_order_id))).scalar_one_or_none()
    if owner != current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if invoice.status == InvoiceStatus.PAID:
        return QuickBooksPaymentAvailabilityResponse(available=False, message="Invoice already paid")
    connection = await _get_connection(db, invoice.tenant_id)
    if not connection or _connection_token_health(connection) in {"not_connected", "reconnect_required"}:
        return QuickBooksPaymentAvailabilityResponse(available=False, message="This shop has not finished QuickBooks Payments setup")
    try:
        return QuickBooksPaymentAvailabilityResponse(available=True, token_url=_quickbooks_payments_token_url())
    except QuickBooksPaymentError:
        return QuickBooksPaymentAvailabilityResponse(available=False, message="QuickBooks Payments is not configured for this environment")


@router.post("/payments/charge", response_model=QuickBooksChargeResponse)
async def charge_quickbooks_invoice(
    body: QuickBooksChargeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Charge an invoice with an opaque browser token from Intuit.

    The request deliberately has no card, account, routing, or CVC fields.
    """
    if current_user.role != UserRole.CUSTOMER or not current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only customers can pay invoices")
    invoice = (await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.repair_order).selectinload(RepairOrder.customer),
            selectinload(Invoice.repair_order).selectinload(RepairOrder.vehicle),
        )
        .where(Invoice.id == body.invoice_id)
    )).scalar_one_or_none()
    if not invoice or not invoice.repair_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if invoice.repair_order.customer_id != current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    existing = await find_quickbooks_payment(db, body.idempotency_key)
    if existing:
        if existing.invoice_id != invoice.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment request belongs to a different invoice")
        return QuickBooksChargeResponse(
            status=existing.quickbooks_charge_status or existing.status.value,
            charge_id=existing.quickbooks_charge_id or "",
            payment_id=existing.id,
            message="Payment request already processed",
        )
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invoice already paid")
    if invoice.total_amount <= Decimal("0.00"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice amount must be positive")

    connection = await _get_connection(db, invoice.tenant_id)
    if not connection or _connection_token_health(connection) in {"not_connected", "reconnect_required"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This shop has not finished QuickBooks Payments setup")
    await _refresh_connection_if_needed(db, connection)
    try:
        charge = await create_charge(
            connection=connection,
            token=body.token,
            amount=invoice.total_amount,
            description=f"DieselBridge invoice {invoice.invoice_number}",
            request_id=body.idempotency_key,
        )
    except QuickBooksPaymentError as exc:
        logger.warning("quickbooks_payment_charge_failed", invoice_id=str(invoice.id), tenant_id=str(invoice.tenant_id))
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc

    if charge.amount != invoice.total_amount:
        logger.error("quickbooks_payment_amount_mismatch", invoice_id=str(invoice.id), charge_id=charge.id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="QuickBooks returned an unexpected payment amount")

    if is_successful_charge(charge):
        tenant = (await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))).scalar_one_or_none()
        payment = await finalize_quickbooks_invoice_payment(
            db=db,
            invoice=invoice,
            order=invoice.repair_order,
            customer=invoice.repair_order.customer,
            tenant=tenant,
            vehicle=invoice.repair_order.vehicle,
            charge=charge,
            idempotency_key=body.idempotency_key,
        )
        return QuickBooksChargeResponse(status=charge.status, charge_id=charge.id, payment_id=payment.id, message="Payment successful")

    payment = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        payment_number=await allocate_next_payment_number(db, invoice.tenant_id),
        amount=charge.amount,
        method=PaymentMethod.QUICKBOOKS,
        status=PaymentStatus.PENDING if charge.status in {"PENDING", "AUTHORIZED"} else PaymentStatus.FAILED,
        quickbooks_charge_id=charge.id,
        quickbooks_charge_status=charge.status,
        quickbooks_idempotency_key=body.idempotency_key,
        notes="QuickBooks Payments charge awaiting settlement.",
    )
    db.add(payment)
    await db.commit()
    return QuickBooksChargeResponse(status=charge.status, charge_id=charge.id, payment_id=payment.id, message="Payment is processing")


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
    return _status_response(connection)


@router.post("/webhook", include_in_schema=False)
async def quickbooks_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Verify Intuit webhook signatures and retain only delivery health metadata."""
    verifier = settings.QUICKBOOKS_WEBHOOK_VERIFIER_TOKEN.strip()
    if not verifier:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="QuickBooks webhooks are not configured")
    payload = await request.body()
    supplied_signature = request.headers.get("intuit-signature", "")
    expected_signature = base64.b64encode(
        hmac.new(verifier.encode("utf-8"), payload, hashlib.sha256).digest()
    ).decode("ascii")
    if not supplied_signature or not hmac.compare_digest(expected_signature, supplied_signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Intuit signature")
    try:
        events = json.loads(payload)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid QuickBooks webhook payload")
    if not isinstance(events, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid QuickBooks webhook payload")

    now = datetime.now(timezone.utc)
    for event in events:
        if not isinstance(event, dict):
            continue
        realm_id = str(event.get("intuitaccountid") or "")
        if not realm_id:
            continue
        connection = (await db.execute(
            select(QuickBooksConnection).where(QuickBooksConnection.realm_id == realm_id)
        )).scalar_one_or_none()
        if connection:
            connection.last_webhook_at = now
            connection.last_webhook_event = str(event.get("type") or "unknown")[:160]
            connection.last_webhook_error = None
    await db.commit()
    return {"status": "success"}
