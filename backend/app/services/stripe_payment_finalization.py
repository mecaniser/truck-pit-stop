from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Collection, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import record_payment
from app.core.websocket import broadcast_payment_received, broadcast_repair_order_update
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    InvoicePaymentAttempt,
    TenantPaymentProviderConfiguration,
)
from app.db.models.payment import Payment, PaymentMethod as PaymentMethodEnum, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.invoice_notification_service import send_invoice_payment_confirmation_email
from app.services.payment_number_service import allocate_next_payment_number
from app.services.paid_invoice_webhook_service import enqueue_paid_invoice_webhook
from app.services.invoice_settlement_service import (
    SettlementDomainError,
    confirm_attempt,
    money,
)

logger = get_logger(__name__)


@dataclass
class StripePaymentFinalizationResult:
    invoice: Invoice
    order: RepairOrder
    payment: Payment
    created: bool


@dataclass(frozen=True)
class ValidatedDB048StripePaymentIntent:
    """Exact, server-bound identity for one DB-048 Stripe attempt."""

    attempt: InvoicePaymentAttempt
    configuration: TenantPaymentProviderConfiguration
    payment_intent_id: str
    status: str
    latest_charge_id: Optional[str]


def _payment_intent_get(payment_intent: Any, key: str, default: Any = None) -> Any:
    if payment_intent is None:
        return default
    if isinstance(payment_intent, dict):
        return payment_intent.get(key, default)
    getter = getattr(payment_intent, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(payment_intent, key, default)


def _payment_intent_metadata(payment_intent: Any) -> dict:
    metadata = _payment_intent_get(payment_intent, "metadata", {}) or {}
    return dict(metadata)


def _latest_charge_id(payment_intent: Any) -> Optional[str]:
    latest_charge = _payment_intent_get(payment_intent, "latest_charge")
    if isinstance(latest_charge, str):
        return latest_charge
    if isinstance(latest_charge, dict):
        charge_id = latest_charge.get("id")
        return charge_id if isinstance(charge_id, str) else None
    charge_id = getattr(latest_charge, "id", None)
    return charge_id if isinstance(charge_id, str) else None


def _metadata_decimal(metadata: dict, key: str, scale: str) -> Optional[Decimal]:
    value = metadata.get(key)
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal(scale))
    except (InvalidOperation, ValueError):
        return None


def _provider_payment_mismatch() -> SettlementDomainError:
    return SettlementDomainError(
        "provider_payment_mismatch",
        "The provider payment does not match this invoice.",
    )


def _exact_integer(value: Any) -> Optional[int]:
    """Return an integer only when the provider value is exactly integral."""
    if value is None or isinstance(value, bool):
        return None
    try:
        candidate = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not candidate.is_finite() or candidate != candidate.to_integral_value():
        return None
    return int(candidate)


async def validate_db048_stripe_payment_intent(
    *,
    db: AsyncSession,
    payment_intent: Any,
    trusted_provider_account_id: Optional[str],
    attempt: Optional[InvoicePaymentAttempt] = None,
    allowed_statuses: Collection[str] = ("succeeded",),
) -> ValidatedDB048StripePaymentIntent:
    """Validate the complete immutable Stripe envelope for a DB-048 attempt.

    ``trusted_provider_account_id`` is server-owned evidence: the signed
    ``event.account`` for a webhook, or the exact Connect account passed to
    ``PaymentIntent.retrieve`` for a browser/reconciliation read. Metadata is
    never allowed to select or replace that account.

    The historical provider configuration is resolved by the attempt's frozen
    version. It intentionally need not be current or active, because provider
    switches affect only new attempts and cannot orphan refunds/reconciliation
    for money created under an older configuration.
    """
    metadata = _payment_intent_metadata(payment_intent)
    payment_intent_id = _payment_intent_get(payment_intent, "id")
    raw_attempt_id = metadata.get("invoice_payment_attempt_id")
    trusted_account = (
        str(trusted_provider_account_id).strip()
        if trusted_provider_account_id is not None
        else ""
    )
    if not payment_intent_id or not raw_attempt_id or not trusted_account:
        raise _provider_payment_mismatch()

    try:
        metadata_attempt_id = UUID(str(raw_attempt_id))
    except (TypeError, ValueError) as exc:
        raise _provider_payment_mismatch() from exc

    if attempt is None:
        attempt = await db.scalar(
            select(InvoicePaymentAttempt).where(
                InvoicePaymentAttempt.id == metadata_attempt_id,
                InvoicePaymentAttempt.deleted_at.is_(None),
            )
        )
    if (
        attempt is None
        or attempt.deleted_at is not None
        or attempt.id != metadata_attempt_id
        or attempt.rail != "card"
        or attempt.provider != "stripe_connect"
        or not attempt.provider_account_id
        or attempt.provider_account_id != trusted_account
        or attempt.provider_intent_id != str(payment_intent_id)
    ):
        raise _provider_payment_mismatch()

    # Provider data must not revive a disabled tenant or a deleted/foreign
    # customer. Resolve immutable attempt ownership from local authority rather
    # than trusting request objects or PaymentIntent metadata.
    attempt_tenant = await db.scalar(
        select(Tenant).where(
            Tenant.id == attempt.tenant_id,
            Tenant.deleted_at.is_(None),
            Tenant.is_active.is_(True),
        )
    )
    attempt_customer = await db.scalar(
        select(Customer).where(
            Customer.id == attempt.customer_id,
            Customer.tenant_id == attempt.tenant_id,
            Customer.deleted_at.is_(None),
        )
    )
    if (
        attempt_tenant is None
        or attempt_tenant.id != attempt.tenant_id
        or attempt_tenant.deleted_at is not None
        or not bool(attempt_tenant.is_active)
        or attempt_customer is None
        or attempt_customer.id != attempt.customer_id
        or attempt_customer.tenant_id != attempt.tenant_id
        or attempt_customer.deleted_at is not None
    ):
        raise _provider_payment_mismatch()

    configuration = await db.scalar(
        select(TenantPaymentProviderConfiguration).where(
            TenantPaymentProviderConfiguration.tenant_id == attempt.tenant_id,
            TenantPaymentProviderConfiguration.version
            == attempt.provider_configuration_version,
            TenantPaymentProviderConfiguration.deleted_at.is_(None),
        )
    )
    if (
        configuration is None
        or configuration.selected_provider != "stripe_connect"
        or configuration.provider_account_snapshot != trusted_account
    ):
        raise _provider_payment_mismatch()

    payment_status = str(_payment_intent_get(payment_intent, "status", ""))
    normalized_allowed_statuses = {str(value) for value in allowed_statuses}
    currency = str(_payment_intent_get(payment_intent, "currency", "")).lower()
    expected_charge_cents = int(money(attempt.provider_charge_amount) * 100)
    amount_cents = _exact_integer(_payment_intent_get(payment_intent, "amount"))
    latest_charge_id = _latest_charge_id(payment_intent)
    if (
        not normalized_allowed_statuses
        or payment_status not in normalized_allowed_statuses
        or currency != "usd"
        or amount_cents != expected_charge_cents
        or (
            payment_status == "succeeded"
            and _exact_integer(_payment_intent_get(payment_intent, "amount_received"))
            != expected_charge_cents
        )
        or (payment_status == "succeeded" and not latest_charge_id)
    ):
        raise _provider_payment_mismatch()

    expected_metadata = {
        "tenant_id": str(attempt.tenant_id),
        "invoice_id": str(attempt.invoice_id),
        "customer_id": str(attempt.customer_id),
        "invoice_payment_attempt_id": str(attempt.id),
        "provider_configuration_version": str(
            attempt.provider_configuration_version
        ),
        "stripe_connected_account_id": trusted_account,
        "principal_amount": str(money(attempt.principal_amount)),
        "card_fee_amount": str(money(attempt.card_fee_amount)),
        "card_fee_tax_amount": str(money(attempt.card_fee_tax_amount)),
    }
    if any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise _provider_payment_mismatch()

    # Stripe webhook account identity is supplied separately as signed server
    # evidence. Some Stripe object serializers also include a top-level account;
    # when present it must agree rather than creating a second authority.
    object_account = _payment_intent_get(payment_intent, "account")
    if object_account not in (None, "") and str(object_account) != trusted_account:
        raise _provider_payment_mismatch()

    return ValidatedDB048StripePaymentIntent(
        attempt=attempt,
        configuration=configuration,
        payment_intent_id=str(payment_intent_id),
        status=payment_status,
        latest_charge_id=latest_charge_id,
    )


def _invoice_not_found() -> SettlementDomainError:
    """Return the same boundary error for every inaccessible invoice state."""
    return SettlementDomainError(
        "invoice_not_found",
        "Invoice not found.",
        status_code=status.HTTP_404_NOT_FOUND,
    )


async def validate_legacy_stripe_payment_identity(
    *,
    db: AsyncSession,
    invoice: Invoice,
    order: RepairOrder,
    tenant: Optional[Tenant],
    payment_intent: Any,
    provider_account_id: Optional[str],
) -> None:
    """Bind a legacy Stripe success to its exact tenant and Connect account.

    DB-048 attempts carry their own immutable provider/configuration snapshot
    and are validated in the durable-attempt branch below. Legacy intents do
    not, so both webhook and browser finalization must bind their metadata to
    the current tenant account before even an idempotent Payment lookup. That
    ordering prevents a known PaymentIntent id from masking forged tenant or
    Connect-account context.
    """
    # Lifecycle eligibility is deliberately checked before provider identity or
    # an idempotent Payment lookup.  A valid late provider event must not
    # resurrect a soft-deleted, voided, or cancelled financial document.
    if (
        invoice.deleted_at is not None
        or invoice.voided_at is not None
        or invoice.status == InvoiceStatus.CANCELLED
        or order.deleted_at is not None
        or order.status == RepairOrderStatus.CANCELLED
    ):
        raise _invoice_not_found()

    metadata = _payment_intent_metadata(payment_intent)
    metadata_tenant_id = metadata.get("tenant_id")
    metadata_account_id = metadata.get("stripe_connected_account_id")
    if (
        tenant is None
        or not bool(tenant.is_active)
        or not provider_account_id
        or not metadata_tenant_id
        or not metadata_account_id
        or invoice.tenant_id != tenant.id
        or order.tenant_id != tenant.id
        or invoice.repair_order_id != order.id
        or metadata_tenant_id != str(tenant.id)
        or metadata_account_id != provider_account_id
        or tenant.stripe_account_id != provider_account_id
        or not bool(tenant.stripe_onboarding_complete)
    ):
        raise _provider_payment_mismatch()

    active_config = await db.scalar(
        select(TenantPaymentProviderConfiguration).where(
            TenantPaymentProviderConfiguration.tenant_id == tenant.id,
            TenantPaymentProviderConfiguration.is_active.is_(True),
            TenantPaymentProviderConfiguration.deleted_at.is_(None),
        ).limit(1)
    )
    # Gate-off tenants may still complete a pre-DB-048 legacy intent without a
    # provider-configuration row. Once a configuration is relevant (present or
    # tenant-enabled), however, its immutable account snapshot is authoritative.
    if active_config is None:
        if bool(tenant.invoice_split_payments_enabled):
            raise _provider_payment_mismatch()
        return
    if (
        active_config.selected_provider != "stripe_connect"
        or active_config.provider_account_snapshot != provider_account_id
    ):
        raise _provider_payment_mismatch()


async def find_stripe_payment(
    db: AsyncSession,
    payment_intent_id: str,
) -> Optional[Payment]:
    result = await db.execute(
        select(Payment).where(Payment.stripe_payment_intent_id == payment_intent_id)
    )
    return result.scalar_one_or_none()


async def finalize_stripe_invoice_payment(
    *,
    db: AsyncSession,
    invoice: Invoice,
    order: RepairOrder,
    customer: Optional[Customer],
    tenant: Optional[Tenant],
    vehicle: Optional[Vehicle],
    payment_intent: Any,
    payment_note: str,
    allow_already_paid_without_payment: bool = False,
    provider_account_id: Optional[str] = None,
    provider_event_id: Optional[str] = None,
) -> StripePaymentFinalizationResult:
    """Persist the local side effects for a succeeded Stripe invoice payment.

    This function is intentionally shared by browser confirmation and Stripe
    webhooks so the webhook is a real backup path rather than a log-only path.
    """
    metadata = _payment_intent_metadata(payment_intent)
    payment_intent_id = _payment_intent_get(payment_intent, "id")
    if not payment_intent_id:
        if metadata.get("invoice_payment_attempt_id"):
            await validate_db048_stripe_payment_intent(
                db=db,
                payment_intent=payment_intent,
                trusted_provider_account_id=provider_account_id,
                allowed_statuses=("succeeded",),
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment intent")

    # DB-048 intents carry a durable attempt identity. They must be finalized
    # through the locked allocation service so a partial charge cannot mark the
    # whole invoice paid and webhooks/browser retries share one idempotent path.
    db048_attempt_id = metadata.get("invoice_payment_attempt_id")
    bound_db048_attempt = None
    if not db048_attempt_id and provider_account_id:
        # A stripped/forged attempt-id metadata field must not downgrade a
        # durable PI into the legacy full-balance path. Resolve only by the
        # trusted retrieval/webhook account plus immutable provider intent.
        bound_db048_attempt = await db.scalar(
            select(InvoicePaymentAttempt).where(
                InvoicePaymentAttempt.provider == "stripe_connect",
                InvoicePaymentAttempt.provider_account_id == provider_account_id,
                InvoicePaymentAttempt.provider_intent_id == str(payment_intent_id),
                InvoicePaymentAttempt.deleted_at.is_(None),
            ).limit(1)
        )
        if bound_db048_attempt is not None:
            db048_attempt_id = str(bound_db048_attempt.id)
    if db048_attempt_id:
        if tenant is None:
            raise _provider_payment_mismatch()
        validated = await validate_db048_stripe_payment_intent(
            db=db,
            payment_intent=payment_intent,
            trusted_provider_account_id=provider_account_id,
            attempt=bound_db048_attempt,
            allowed_statuses=("succeeded",),
        )
        attempt = validated.attempt
        if (
            tenant.id != attempt.tenant_id
            or invoice.id != attempt.invoice_id
            or invoice.tenant_id != attempt.tenant_id
            or order.id != invoice.repair_order_id
            or order.tenant_id != attempt.tenant_id
            or order.customer_id != attempt.customer_id
        ):
            raise _provider_payment_mismatch()
        result = await confirm_attempt(
            db,
            attempt_id=attempt.id,
            tenant=tenant,
            actor=None,
            expected_attempt_version=attempt.version,
            idempotency_key=(
                f"stripe:{attempt.provider_account_id}:"
                f"{provider_event_id or validated.payment_intent_id}:confirmed"
            ),
            received_principal=attempt.principal_amount,
            # Keep each provider identity in its own immutable field: the PI is
            # the provider reference, the charge is the charge, and only a
            # signature-verified webhook event id is provider_event_id.
            reference=validated.payment_intent_id,
            provider_charge_id=validated.latest_charge_id,
            provider_event_id=provider_event_id,
        )
        await db.commit()
        if result.payment is None:
            raise SettlementDomainError(
                "payment_finalization_failed",
                "The payment was accepted but its local receipt is unavailable.",
                status_code=503,
                retryable=True,
            )
        await broadcast_payment_received(
            tenant_id=str(invoice.tenant_id),
            customer_id=str(order.customer_id),
            invoice_id=str(invoice.id),
            order_id=str(order.id),
        )
        if result.paid_transition:
            await broadcast_repair_order_update(
                tenant_id=str(invoice.tenant_id),
                customer_id=str(order.customer_id),
                order_id=str(order.id),
                order_number=order.order_number,
                status=order.status.value,
                updated_at=order.updated_at.isoformat() if order.updated_at else None,
            )
        record_payment(status="success", payment_method="stripe", tenant_id=str(invoice.tenant_id))
        return StripePaymentFinalizationResult(
            invoice=invoice,
            order=order,
            payment=result.payment,
            created=not result.replayed,
        )

    if metadata.get("invoice_id") != str(invoice.id):
        logger.warning(
            "payment_intent_mismatch",
            invoice_id=str(invoice.id),
            payment_intent_invoice_id=metadata.get("invoice_id"),
            payment_intent_id=payment_intent_id,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment intent mismatch")

    # Validate every legacy success before the rollback guard, idempotent
    # Payment lookup, or any financial state mutation.
    await validate_legacy_stripe_payment_identity(
        db=db,
        invoice=invoice,
        order=order,
        tenant=tenant,
        payment_intent=payment_intent,
        provider_account_id=provider_account_id,
    )

    # Once any durable DB-048 attempt exists, an unbound/legacy PaymentIntent
    # must never run the old full-balance finalizer. This guard remains active
    # when rollout gates are disabled so rollback cannot double-charge or mark
    # a partially paid invoice as settled.
    protected_attempt_id = await db.scalar(select(InvoicePaymentAttempt.id).where(
        InvoicePaymentAttempt.tenant_id == invoice.tenant_id,
        InvoicePaymentAttempt.invoice_id == invoice.id,
    ).limit(1))
    if protected_attempt_id is not None:
        raise SettlementDomainError(
            "provider_payment_mismatch",
            "This invoice has protected payment activity and cannot use legacy checkout.",
        )

    existing_payment = await find_stripe_payment(db, payment_intent_id)
    if existing_payment:
        return StripePaymentFinalizationResult(
            invoice=invoice,
            order=order,
            payment=existing_payment,
            created=False,
        )

    if invoice.status == InvoiceStatus.PAID:
        if allow_already_paid_without_payment:
            logger.info(
                "stripe_payment_succeeded_invoice_already_paid_without_matching_payment",
                invoice_id=str(invoice.id),
                payment_intent_id=payment_intent_id,
            )
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invoice already paid")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice already paid")

    invoice.zelle_pending_submitted_at = None
    invoice.zelle_pending_sender_email = None
    invoice.zelle_pending_sender_phone = None
    invoice.zelle_pending_last_reminder_at = None
    invoice.zelle_pending_reminder_count = 0
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.now(timezone.utc)
    order.status = RepairOrderStatus.PAID

    payment_number = await allocate_next_payment_number(db, invoice.tenant_id)
    platform_fee_cents = _metadata_decimal(metadata, "platform_fee_amount_cents", "1")
    payment = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        payment_number=payment_number,
        amount=invoice.total_amount,
        method=PaymentMethodEnum.STRIPE,
        status=PaymentStatus.COMPLETED,
        stripe_payment_intent_id=payment_intent_id,
        stripe_charge_id=_latest_charge_id(payment_intent),
        stripe_connected_account_id=metadata.get("stripe_connected_account_id"),
        stripe_platform_fee_amount=(
            platform_fee_cents / Decimal("100")
            if platform_fee_cents is not None
            else None
        ),
        stripe_platform_fee_percent=_metadata_decimal(metadata, "platform_fee_percent", "0.001"),
        notes=payment_note,
    )
    db.add(payment)
    await enqueue_paid_invoice_webhook(
        db,
        tenant=tenant,
        invoice=invoice,
        order=order,
        customer=customer,
    )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing_payment = await find_stripe_payment(db, payment_intent_id)
        if existing_payment:
            return StripePaymentFinalizationResult(
                invoice=invoice,
                order=order,
                payment=existing_payment,
                created=False,
            )
        raise

    await db.refresh(invoice)
    await db.refresh(order)

    await broadcast_payment_received(
        tenant_id=str(invoice.tenant_id),
        customer_id=str(order.customer_id),
        invoice_id=str(invoice.id),
        order_id=str(order.id),
    )
    await broadcast_repair_order_update(
        tenant_id=str(invoice.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )

    record_payment(status="success", payment_method="stripe", tenant_id=str(invoice.tenant_id))

    try:
        await send_invoice_payment_confirmation_email(
            db=db,
            invoice=invoice,
            order=order,
            customer=customer,
            tenant=tenant,
            vehicle=vehicle,
        )
    except Exception as exc:
        logger.warning(
            "invoice_paid_confirmation_email_failed",
            invoice_id=str(invoice.id),
            error=str(exc),
        )

    logger.info(
        "stripe_invoice_payment_finalized",
        invoice_id=str(invoice.id),
        payment_intent_id=payment_intent_id,
        payment_id=str(payment.id) if getattr(payment, "id", None) else None,
        amount=float(invoice.total_amount),
    )

    return StripePaymentFinalizationResult(
        invoice=invoice,
        order=order,
        payment=payment,
        created=True,
    )
