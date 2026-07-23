from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_db, user_has_permission
from app.core.logging import get_logger
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = get_logger(__name__)
router = APIRouter()

HOSTED_CONNECTION_TYPE = "stripe_hosted"


class ConnectLinkResponse(BaseModel):
    url: str


class RecentStripePayment(BaseModel):
    invoice_number: str
    amount: str
    status: str
    payment_intent_id: Optional[str] = None
    created_at: datetime


class ConnectStatusResponse(BaseModel):
    configured: bool
    is_connected: bool
    onboarding_complete: bool
    charges_enabled: bool
    payouts_enabled: bool
    account_id: Optional[str]
    connection_type: Optional[str]
    verification_status: str
    requirements: list[str]
    mode: str
    account_dashboard_url: Optional[str] = None
    available_balance: Optional[str] = None
    pending_balance: Optional[str] = None
    last_payout_amount: Optional[str] = None
    last_payout_status: Optional[str] = None
    last_payout_at: Optional[datetime] = None
    recent_payments: list[RecentStripePayment] = Field(default_factory=list)


class DisconnectResponse(BaseModel):
    is_connected: bool = False


def _stripe_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _require_garage_admin(current_user: User) -> None:
    if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN) or not user_has_permission(current_user, "payments"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to Stripe settings.")


def _connect_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PUBLISHABLE_KEY)


def _stripe_mode() -> str:
    if settings.STRIPE_SECRET_KEY.startswith("sk_live_"):
        return "live"
    if settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
        return "test"
    return "unknown"


def _connected_account_payments_url(account_id: str) -> str:
    prefix = "/test" if _stripe_mode() == "test" else ""
    return f"https://dashboard.stripe.com{prefix}/connect/accounts/{account_id}/payments"


def _display_amount_from_cents(entries: Any) -> Optional[str]:
    for entry in entries or []:
        if _stripe_value(entry, "currency") == "usd":
            amount = Decimal(str(_stripe_value(entry, "amount", 0))) / Decimal("100")
            return str(amount.quantize(Decimal("0.01")))
    return None


def _payout_snapshot(
    account_id: str,
) -> tuple[Optional[str], Optional[str], Optional[datetime], Optional[str], Optional[str]]:
    """Fetch provider-owned balance data without making the tenant status unavailable on a Stripe error."""
    try:
        balance = stripe.Balance.retrieve(stripe_account=account_id)
        available = _display_amount_from_cents(_stripe_value(balance, "available", []))
        pending = _display_amount_from_cents(_stripe_value(balance, "pending", []))
        payouts = stripe.Payout.list(limit=1, stripe_account=account_id)
        payout = list(_stripe_value(payouts, "data", []) or [])
        if not payout:
            return available, pending, None, None, None
        latest = payout[0]
        created = _stripe_value(latest, "created")
        paid_at = datetime.fromtimestamp(created, timezone.utc) if created else None
        payout_amount = Decimal(str(_stripe_value(latest, "amount", 0))) / Decimal("100")
        return (
            available,
            pending,
            paid_at,
            str(payout_amount.quantize(Decimal("0.01"))),
            _stripe_value(latest, "status"),
        )
    except stripe.error.StripeError:
        return None, None, None, None, None


async def _tenant_for(current_user: User, db: AsyncSession) -> Tenant:
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _account_is_ready(account: Any) -> bool:
    return bool(_stripe_value(account, "charges_enabled") and _stripe_value(account, "payouts_enabled"))


def _verification_status(account: Any) -> tuple[str, list[str]]:
    """Translate Stripe requirements into a tenant-facing connection state."""
    if _account_is_ready(account):
        return "active", []

    requirements = _stripe_value(account, "requirements", {}) or {}
    currently_due = list(_stripe_value(requirements, "currently_due", []) or [])
    past_due = list(_stripe_value(requirements, "past_due", []) or [])
    pending_verification = list(_stripe_value(requirements, "pending_verification", []) or [])
    disabled_reason = _stripe_value(requirements, "disabled_reason")

    if past_due or disabled_reason:
        return "restricted", past_due or currently_due
    if currently_due:
        return "needs_information", currently_due
    if pending_verification or _stripe_value(account, "details_submitted"):
        return "under_review", pending_verification
    return "setup_incomplete", []


def _onboarding_urls() -> tuple[str, str]:
    settings_url = f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/settings"
    return f"{settings_url}?stripe=refresh", f"{settings_url}?stripe=return"


def _create_hosted_account(tenant: Tenant) -> Any:
    account_params: dict[str, Any] = {
        "controller": {
            "fees": {"payer": "account"},
            "losses": {"payments": "stripe"},
            "requirement_collection": "stripe",
            "stripe_dashboard": {"type": "full"},
        },
        "metadata": {"tenant_id": str(tenant.id), "tenant_name": tenant.name},
        "business_profile": {"product_description": f"Truck repair services provided by {tenant.name}"},
    }
    if tenant.email:
        account_params["email"] = tenant.email
    return stripe.Account.create(**account_params)


@router.post("/connect", response_model=ConnectLinkResponse)
async def start_hosted_onboarding(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create or resume Stripe-hosted onboarding for a garage merchant account."""
    _require_garage_admin(current_user)
    if not _connect_configured():
        raise HTTPException(status_code=503, detail="Stripe Connect is not available yet")

    tenant = await _tenant_for(current_user, db)
    try:
        if tenant.stripe_account_id:
            account = stripe.Account.retrieve(tenant.stripe_account_id)
        else:
            account = _create_hosted_account(tenant)
            account_id = _stripe_value(account, "id")
            if not account_id:
                raise ValueError("Stripe did not return a connected account ID")
            tenant.stripe_account_id = account_id
            tenant.stripe_connection_type = HOSTED_CONNECTION_TYPE

        tenant.stripe_onboarding_complete = _account_is_ready(account)
        await db.commit()

        refresh_url, return_url = _onboarding_urls()
        account_link = stripe.AccountLink.create(
            account=tenant.stripe_account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
            collection_options={"fields": "eventually_due"},
        )
        link_url = _stripe_value(account_link, "url")
        if not link_url:
            raise ValueError("Stripe did not return an onboarding URL")
    except stripe.error.InvalidRequestError as exc:
        # Stripe rejects Connect account creation until the platform's own live
        # account has completed activation. That is a platform action, not a
        # tenant onboarding failure, so make it clear to the garage.
        if "must be activated in order to create accounts" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="DieselBridge must complete its Stripe platform activation before shops can connect. Please contact a platform administrator.",
            )
        logger.exception("stripe_hosted_onboarding_failed", tenant_id=str(tenant.id), error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to start Stripe onboarding")
    except stripe.error.StripeError as exc:
        logger.exception("stripe_hosted_onboarding_failed", tenant_id=str(tenant.id), error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to start Stripe onboarding")
    except ValueError as exc:
        logger.error("stripe_hosted_onboarding_invalid_response", tenant_id=str(tenant.id), error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to start Stripe onboarding")

    logger.info(
        "stripe_hosted_onboarding_started",
        tenant_id=str(tenant.id),
        account_id=tenant.stripe_account_id,
    )
    return ConnectLinkResponse(url=link_url)


@router.post("/onboard", response_model=ConnectLinkResponse, deprecated=True)
async def start_hosted_onboarding_compat(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await start_hosted_onboarding(db, current_user)


@router.get("/status", response_model=ConnectStatusResponse)
async def get_connect_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_garage_admin(current_user)
    tenant = await _tenant_for(current_user, db)
    mode = _stripe_mode()
    if not tenant.stripe_account_id:
        return ConnectStatusResponse(
            configured=_connect_configured(),
            is_connected=False,
            onboarding_complete=False,
            charges_enabled=False,
            payouts_enabled=False,
            account_id=None,
            connection_type=None,
            verification_status="not_connected",
            requirements=[],
            mode=mode,
        )
    try:
        account = stripe.Account.retrieve(tenant.stripe_account_id)
        charges_enabled = bool(_stripe_value(account, "charges_enabled"))
        payouts_enabled = bool(_stripe_value(account, "payouts_enabled"))
        complete = charges_enabled and payouts_enabled
        verification_status, requirements = _verification_status(account)
        if tenant.stripe_onboarding_complete != complete:
            tenant.stripe_onboarding_complete = complete
            await db.commit()
        payment_rows = (
            await db.execute(
                select(Payment, Invoice.invoice_number)
                .join(Invoice, Invoice.id == Payment.invoice_id)
                .where(Payment.tenant_id == tenant.id, Payment.method == PaymentMethod.STRIPE)
                .order_by(Payment.created_at.desc())
                .limit(5)
            )
        ).all()
        recent_payments = [
            RecentStripePayment(
                invoice_number=invoice_number,
                amount=str(payment.amount),
                status=payment.status.value if isinstance(payment.status, PaymentStatus) else str(payment.status),
                payment_intent_id=payment.stripe_payment_intent_id,
                created_at=payment.created_at,
            )
            for payment, invoice_number in payment_rows
        ]
        available, pending, last_payout_at, last_payout_amount, last_payout_status = _payout_snapshot(
            tenant.stripe_account_id
        )
        return ConnectStatusResponse(
            configured=_connect_configured(),
            is_connected=True,
            onboarding_complete=complete,
            charges_enabled=charges_enabled,
            payouts_enabled=payouts_enabled,
            account_id=tenant.stripe_account_id,
            connection_type=tenant.stripe_connection_type or "express_legacy",
            verification_status=verification_status,
            requirements=requirements,
            mode=mode,
            account_dashboard_url=_connected_account_payments_url(tenant.stripe_account_id),
            available_balance=available,
            pending_balance=pending,
            last_payout_amount=last_payout_amount,
            last_payout_status=last_payout_status,
            last_payout_at=last_payout_at,
            recent_payments=recent_payments,
        )
    except stripe.error.InvalidRequestError:
        # A deleted or otherwise invalid connected account must not trap the
        # shop behind a failing status request. Keep the local ID visible so
        # the settings UI can offer a deliberate local reset.
        if tenant.stripe_onboarding_complete:
            tenant.stripe_onboarding_complete = False
            await db.commit()
        return ConnectStatusResponse(
            configured=_connect_configured(),
            is_connected=True,
            onboarding_complete=False,
            charges_enabled=False,
            payouts_enabled=False,
            account_id=tenant.stripe_account_id,
            connection_type=tenant.stripe_connection_type or "express_legacy",
            verification_status="unreachable",
            requirements=[],
            mode=mode,
        )
    except stripe.error.StripeError:
        raise HTTPException(status_code=502, detail="Unable to retrieve Stripe account status")


@router.post("/disconnect", response_model=DisconnectResponse)
async def disconnect_stripe_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Unlink the garage locally without deleting its Stripe account."""
    _require_garage_admin(current_user)
    tenant = await _tenant_for(current_user, db)
    tenant.stripe_account_id = None
    tenant.stripe_connection_type = None
    tenant.stripe_onboarding_complete = False
    await db.commit()
    return DisconnectResponse()


@router.post("/dashboard", response_model=ConnectLinkResponse)
async def create_dashboard_link(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_garage_admin(current_user)
    tenant = await _tenant_for(current_user, db)
    if not tenant.stripe_account_id:
        raise HTTPException(status_code=400, detail="Stripe account not connected")
    if tenant.stripe_connection_type in (HOSTED_CONNECTION_TYPE, "standard_oauth"):
        return ConnectLinkResponse(url="https://dashboard.stripe.com/")
    try:
        login_link = stripe.Account.create_login_link(tenant.stripe_account_id)
        return ConnectLinkResponse(url=_stripe_value(login_link, "url"))
    except stripe.error.StripeError:
        raise HTTPException(status_code=502, detail="Unable to open Stripe Dashboard")
