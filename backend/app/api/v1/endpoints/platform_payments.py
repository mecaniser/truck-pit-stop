"""Super-admin payment operations controls for Stripe and QuickBooks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_db
from app.db.models.error_log import ErrorCategory, ErrorLog
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.quickbooks_service import disconnect as disconnect_quickbooks_connection
from app.services.stripe_platform_fee import MAX_PLATFORM_FEE_PERCENT

router = APIRouter()
stripe.api_key = settings.STRIPE_SECRET_KEY


def _require_super_admin(current_user: User) -> None:
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")


def _stripe_value(value, key: str, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _fee_display(value: Optional[Decimal]) -> Optional[str]:
    return str(value.quantize(Decimal("0.001"))) if value is not None else None


def _connected_account_payments_url(account_id: Optional[str]) -> Optional[str]:
    if not account_id:
        return None
    mode_prefix = "/test" if settings.STRIPE_SECRET_KEY.startswith("sk_test_") else ""
    return f"https://dashboard.stripe.com{mode_prefix}/connect/accounts/{account_id}/payments"


def _merchant_status(tenant: Tenant) -> dict:
    base = {
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name,
        "owner_email": None,
        "account_id": tenant.stripe_account_id,
        "platform_fee_percent": _fee_display(tenant.stripe_platform_fee_percent),
        "uses_default_fee": tenant.stripe_platform_fee_percent is None,
        "last_webhook_at": tenant.stripe_last_webhook_at,
        "last_webhook_event": tenant.stripe_last_webhook_event,
        "last_webhook_error": tenant.stripe_last_webhook_error,
    }
    if not tenant.stripe_account_id:
        return {**base, "status": "not_started", "charges_enabled": False, "payouts_enabled": False, "requirements": []}

    try:
        account = stripe.Account.retrieve(tenant.stripe_account_id)
        charges_enabled = bool(_stripe_value(account, "charges_enabled"))
        payouts_enabled = bool(_stripe_value(account, "payouts_enabled"))
        requirements = _stripe_value(account, "requirements", {}) or {}
        currently_due = list(_stripe_value(requirements, "currently_due", []) or [])
        past_due = list(_stripe_value(requirements, "past_due", []) or [])
        disabled_reason = _stripe_value(requirements, "disabled_reason")
        if charges_enabled and payouts_enabled:
            merchant_state = "active"
        elif past_due or disabled_reason:
            merchant_state = "restricted"
        elif currently_due:
            merchant_state = "incomplete"
        else:
            merchant_state = "under_review"
        return {
            **base,
            "status": merchant_state,
            "charges_enabled": charges_enabled,
            "payouts_enabled": payouts_enabled,
            "requirements": past_due or currently_due,
            "disabled_reason": disabled_reason,
        }
    except stripe.error.StripeError:
        return {**base, "status": "unreachable", "charges_enabled": False, "payouts_enabled": False, "requirements": []}


def _quickbooks_configuration() -> dict:
    accounting_environment = settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT.strip().lower()
    payments_environment = settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT.strip().lower()
    return {
        "client_id_configured": bool(settings.QUICKBOOKS_CLIENT_ID),
        "client_secret_configured": bool(settings.QUICKBOOKS_CLIENT_SECRET),
        "redirect_uri_configured": bool(settings.QUICKBOOKS_REDIRECT_URI),
        "token_encryption_configured": bool(settings.QUICKBOOKS_TOKEN_ENCRYPTION_KEY),
        "webhook_verifier_configured": bool(settings.QUICKBOOKS_WEBHOOK_VERIFIER_TOKEN),
        "accounting_environment": accounting_environment,
        "payments_environment": payments_environment,
        "accounting_environment_valid": accounting_environment in {"sandbox", "production"},
        "payments_environment_valid": payments_environment in {"sandbox", "production"},
        "webhook_url": f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}/api/v1/quickbooks/webhook",
    }


def _quickbooks_token_health(connection: Optional[QuickBooksConnection]) -> str:
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


def _quickbooks_merchant_status(
    tenant: Tenant,
    connection: Optional[QuickBooksConnection],
    configuration: dict,
) -> dict:
    token_health = _quickbooks_token_health(connection)
    scopes = set((connection.scopes if connection else "").split())
    accounting_enabled = "com.intuit.quickbooks.accounting" in scopes
    payments_scope_enabled = "com.intuit.quickbooks.payment" in scopes
    requirements: list[str] = []

    if not connection or token_health == "not_connected":
        merchant_state = "not_connected"
    elif token_health == "reconnect_required":
        merchant_state = "reconnect_required"
        requirements.append("Reconnect QuickBooks authorization")
    elif not payments_scope_enabled:
        merchant_state = "accounting_only"
        requirements.append("Grant the QuickBooks Payments scope")
    elif token_health == "refresh_required":
        merchant_state = "refresh_required"
        requirements.append("Access token refresh is required")
    elif connection.last_token_refresh_error:
        merchant_state = "attention"
        requirements.append("Resolve the latest token refresh error")
    else:
        merchant_state = "active"

    if connection and connection.last_webhook_error:
        requirements.append("Resolve the latest webhook error")
    if connection and connection.last_cdc_error:
        requirements.append("Resolve the latest accounting sync error")
    if not configuration["payments_environment_valid"]:
        requirements.append("Configure a valid QuickBooks Payments environment")

    payments_enabled = (
        merchant_state in {"active", "refresh_required"}
        and payments_scope_enabled
        and configuration["payments_environment_valid"]
    )
    realm_suffix = connection.realm_id[-4:] if connection and connection.realm_id else None
    return {
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name,
        "owner_email": tenant.owner.email if tenant.owner else None,
        "connection_id": str(connection.id) if connection else None,
        "company_id_label": f"••••{realm_suffix}" if realm_suffix else None,
        "status": merchant_state,
        "is_connected": bool(connection and connection.status == "connected" and connection.realm_id),
        "accounting_enabled": accounting_enabled,
        "payments_scope_enabled": payments_scope_enabled,
        "payments_enabled": payments_enabled,
        "token_health": token_health,
        "requirements": requirements,
        "connected_at": connection.connected_at if connection else None,
        "access_token_expires_at": connection.access_token_expires_at if connection else None,
        "refresh_token_expires_at": connection.refresh_token_expires_at if connection else None,
        "last_token_refresh_at": connection.last_token_refresh_at if connection else None,
        "last_token_refresh_error": connection.last_token_refresh_error if connection else None,
        "last_webhook_at": connection.last_webhook_at if connection else None,
        "last_webhook_event": connection.last_webhook_event if connection else None,
        "last_webhook_error": connection.last_webhook_error if connection else None,
        "last_cdc_at": connection.last_cdc_at if connection else None,
        "last_cdc_error": connection.last_cdc_error if connection else None,
    }


class FeeOverrideRequest(BaseModel):
    percent: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=MAX_PLATFORM_FEE_PERCENT)


@router.get("/overview")
async def payment_operations_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_super_admin(current_user)
    tenants = (await db.execute(select(Tenant).options(selectinload(Tenant.owner)).order_by(Tenant.name))).scalars().all()
    merchants = []
    for tenant in tenants:
        merchant = _merchant_status(tenant)
        merchant["owner_email"] = tenant.owner.email if tenant.owner else None
        merchants.append(merchant)

    unresolved_errors = (
        await db.execute(
            select(ErrorLog)
            .where(ErrorLog.deleted_at.is_(None), ErrorLog.resolved.is_(False), ErrorLog.error_category == ErrorCategory.PAYMENT.value)
            .order_by(ErrorLog.created_at.desc())
            .limit(12)
        )
    ).scalars().all()
    alerts = [
        {
            "kind": "merchant",
            "severity": "critical" if merchant["status"] == "restricted" else "warning",
            "tenant_id": merchant["tenant_id"],
            "tenant_name": merchant["tenant_name"],
            "message": f"Stripe merchant is {merchant['status'].replace('_', ' ')}",
        }
        for merchant in merchants
        if merchant["status"] in {"incomplete", "restricted", "unreachable"}
    ]
    alerts.extend(
        {
            "kind": "payment_error",
            "severity": error.severity or "error",
            "tenant_id": str(error.tenant_id) if error.tenant_id else None,
            "tenant_name": None,
            "message": error.message,
            "created_at": error.created_at,
        }
        for error in unresolved_errors
    )

    return {
        "platform_fee_default_percent": _fee_display(Decimal(str(settings.PLATFORM_FEE_PERCENT))),
        "configuration": {
            "secret_key_configured": bool(settings.STRIPE_SECRET_KEY),
            "publishable_key_configured": bool(settings.STRIPE_PUBLISHABLE_KEY),
            "platform_webhook_configured": bool(settings.STRIPE_WEBHOOK_SECRET),
            "connect_webhook_configured": bool(settings.STRIPE_CONNECT_WEBHOOK_SECRET),
            "mode": "live" if settings.STRIPE_SECRET_KEY.startswith("sk_live_") else "test" if settings.STRIPE_SECRET_KEY.startswith("sk_test_") else "unknown",
            "connect_webhook_url": f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}/api/v1/webhooks/stripe/connect",
            "platform_webhook_url": f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}/api/v1/webhooks/stripe/payments",
        },
        "webhook_health": {
            "merchants_with_recent_delivery": sum(1 for merchant in merchants if merchant["last_webhook_at"] is not None),
            "merchants_with_delivery_error": sum(1 for merchant in merchants if merchant["last_webhook_error"]),
            "last_payment_error_at": unresolved_errors[0].created_at if unresolved_errors else None,
        },
        "merchant_summary": {state: sum(1 for merchant in merchants if merchant["status"] == state) for state in ("active", "not_started", "incomplete", "under_review", "restricted", "unreachable")},
        "merchants": merchants,
        "alerts": alerts,
    }


@router.get("/quickbooks/overview")
async def quickbooks_operations_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_super_admin(current_user)
    rows = (
        await db.execute(
            select(Tenant, QuickBooksConnection)
            .outerjoin(QuickBooksConnection, QuickBooksConnection.tenant_id == Tenant.id)
            .options(selectinload(Tenant.owner))
            .order_by(Tenant.name)
        )
    ).all()
    configuration = _quickbooks_configuration()
    merchants = [
        _quickbooks_merchant_status(tenant, connection, configuration)
        for tenant, connection in rows
    ]
    summary_states = (
        "active",
        "not_connected",
        "accounting_only",
        "refresh_required",
        "reconnect_required",
        "attention",
    )
    alerts = [
        {
            "kind": "quickbooks_connection",
            "severity": "critical" if merchant["status"] in {"reconnect_required", "attention"} else "warning",
            "tenant_id": merchant["tenant_id"],
            "tenant_name": merchant["tenant_name"],
            "message": f"QuickBooks connection is {merchant['status'].replace('_', ' ')}",
        }
        for merchant in merchants
        if merchant["status"] not in {"active", "not_connected"}
    ]
    return {
        "configuration": configuration,
        "merchant_summary": {
            state: sum(1 for merchant in merchants if merchant["status"] == state)
            for state in summary_states
        },
        "webhook_health": {
            "merchants_with_recent_delivery": sum(1 for merchant in merchants if merchant["last_webhook_at"]),
            "merchants_with_delivery_error": sum(1 for merchant in merchants if merchant["last_webhook_error"]),
            "merchants_with_cdc_error": sum(1 for merchant in merchants if merchant["last_cdc_error"]),
        },
        "merchants": merchants,
        "alerts": alerts,
    }


@router.get("/ledger")
async def payment_operations_ledger(
    tenant_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_super_admin(current_user)
    query = (
        select(Payment, Tenant, Invoice)
        .join(Tenant, Tenant.id == Payment.tenant_id)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .where(Payment.method == PaymentMethod.STRIPE)
        .order_by(Payment.created_at.desc())
        .limit(limit)
    )
    if tenant_id:
        query = query.where(Payment.tenant_id == tenant_id)
    rows = (await db.execute(query)).all()
    return {
        "entries": [
            {
                "payment_id": str(payment.id),
                "created_at": payment.created_at,
                "tenant_id": str(tenant.id),
                "tenant_name": tenant.name,
                "invoice_number": invoice.invoice_number,
                "amount": str(payment.amount),
                "status": payment.status.value if isinstance(payment.status, PaymentStatus) else str(payment.status),
                "payment_intent_id": payment.stripe_payment_intent_id,
                "connected_account_id": payment.stripe_connected_account_id,
                "stripe_dashboard_url": _connected_account_payments_url(payment.stripe_connected_account_id),
                "platform_fee_amount": str(payment.stripe_platform_fee_amount) if payment.stripe_platform_fee_amount is not None else None,
                "platform_fee_percent": _fee_display(payment.stripe_platform_fee_percent),
            }
            for payment, tenant, invoice in rows
        ],
        "totals": {
            "volume": str(sum((payment.amount for payment, _, _ in rows), Decimal("0"))),
            "platform_fees": str(sum((payment.stripe_platform_fee_amount or Decimal("0") for payment, _, _ in rows), Decimal("0"))),
        },
    }


@router.get("/quickbooks/ledger")
async def quickbooks_operations_ledger(
    tenant_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_super_admin(current_user)
    query = (
        select(Payment, Tenant, Invoice)
        .join(Tenant, Tenant.id == Payment.tenant_id)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .where(Payment.method == PaymentMethod.QUICKBOOKS)
        .order_by(Payment.created_at.desc())
        .limit(limit)
    )
    if tenant_id:
        query = query.where(Payment.tenant_id == tenant_id)
    rows = (await db.execute(query)).all()
    return {
        "entries": [
            {
                "payment_id": str(payment.id),
                "created_at": payment.created_at,
                "tenant_id": str(tenant.id),
                "tenant_name": tenant.name,
                "invoice_number": invoice.invoice_number,
                "amount": str(payment.amount),
                "status": payment.status.value if isinstance(payment.status, PaymentStatus) else str(payment.status),
                "charge_id": payment.quickbooks_charge_id,
                "charge_status": payment.quickbooks_charge_status,
                "quickbooks_payment_id": payment.quickbooks_payment_id,
                "refunded_amount": str(payment.quickbooks_refunded_amount) if payment.quickbooks_refunded_amount is not None else None,
                "reconciled_at": payment.quickbooks_reconciled_at,
                "sync_error": payment.quickbooks_sync_error,
            }
            for payment, tenant, invoice in rows
        ],
        "totals": {
            "volume": str(sum((payment.amount for payment, _, _ in rows), Decimal("0"))),
            "refunded": str(sum((payment.quickbooks_refunded_amount or Decimal("0") for payment, _, _ in rows), Decimal("0"))),
            "unreconciled": sum(1 for payment, _, _ in rows if payment.quickbooks_reconciled_at is None),
        },
    }


@router.patch("/tenants/{tenant_id}/fee")
async def update_tenant_platform_fee(
    tenant_id: UUID,
    body: FeeOverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_super_admin(current_user)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant.stripe_platform_fee_percent = body.percent.quantize(Decimal("0.001")) if body.percent is not None else None
    tenant.stripe_platform_fee_updated_at = datetime.now(timezone.utc)
    tenant.stripe_platform_fee_updated_by_id = current_user.id
    await db.commit()
    return {
        "tenant_id": str(tenant.id),
        "platform_fee_percent": _fee_display(tenant.stripe_platform_fee_percent),
        "uses_default_fee": tenant.stripe_platform_fee_percent is None,
        "effective_for": "new PaymentIntents only",
    }


@router.post("/tenants/{tenant_id}/reset-stripe-connection")
async def reset_tenant_stripe_connection(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Clear a stale local Stripe link so a merchant can start onboarding again."""
    _require_super_admin(current_user)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if not tenant.stripe_account_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant has no Stripe connection to reset")

    tenant.stripe_account_id = None
    tenant.stripe_connection_type = None
    tenant.stripe_onboarding_complete = False
    tenant.stripe_last_webhook_at = None
    tenant.stripe_last_webhook_event = None
    tenant.stripe_last_webhook_error = None
    await db.commit()
    return {
        "tenant_id": str(tenant.id),
        "status": "not_started",
        "message": "The local Stripe connection was reset. The merchant can begin Stripe setup again.",
    }


@router.post("/tenants/{tenant_id}/reset-quickbooks-connection")
async def reset_tenant_quickbooks_connection(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Forget tenant QuickBooks authorization without deleting local history."""
    _require_super_admin(current_user)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    connection = (
        await db.execute(
            select(QuickBooksConnection).where(QuickBooksConnection.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if not connection or connection.status != "connected":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant has no active QuickBooks connection to reset")

    disconnect_quickbooks_connection(connection)
    await db.commit()
    return {
        "tenant_id": str(tenant.id),
        "status": "not_connected",
        "message": "QuickBooks authorization was reset. Accounting and payment history were preserved.",
    }
