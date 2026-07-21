"""Super-admin payment operations controls for Stripe Connect."""
from __future__ import annotations

from datetime import datetime, timezone
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
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
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
