from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID
import stripe

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.logging import get_logger
from app.core.metrics import record_payment, record_payment_error
from app.db.models.tenant import Tenant
from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import (
    InvoicePaymentAttempt,
    PaymentRefund,
    TenantPaymentProviderConfiguration,
)
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.error_log import ErrorCategory, ErrorSeverity
from app.services import error_service
from app.services.stripe_payment_finalization import (
    finalize_stripe_invoice_payment,
    validate_db048_stripe_payment_intent,
    validate_legacy_stripe_payment_identity,
)
from app.services.db048_accounting_reconciliation import (
    DB048ReconciliationError,
    PAYOUT_RECONCILIATION_EVENT,
    close_stripe_dispute,
    finalize_provider_refund,
    record_stripe_dispute,
)
from app.services.invoice_settlement_service import (
    fail_attempt,
    locked_accessible_invoice_for_attempt,
)

WEBHOOK_PAYMENT_NOTE = "Payment confirmed by Stripe webhook."

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = get_logger(__name__)

router = APIRouter()


def _verified_stripe_event(*, payload: bytes, signature: str | None, secret: str | None):
    """Return a signature-verified Stripe event or fail closed.

    Provider webhooks are a financial mutation boundary. Development mode is
    not an exception: an absent secret must never turn an unsigned JSON body
    into trusted tenant/payment metadata.
    """
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhook verification is not configured",
        )
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )
    try:
        return stripe.Webhook.construct_event(payload, signature, secret)
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
        ) from exc


async def _record_webhook_delivery(db: AsyncSession, event, event_type: str, data_object):
    """Store minimal delivery health without retaining Stripe event payloads."""
    account_id = event.get("account")
    if event_type == "account.updated":
        account_id = data_object.get("id")

    tenant = None
    if account_id:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.stripe_account_id == account_id))
        ).scalar_one_or_none()
        if tenant is None:
            historical_config = await db.scalar(
                select(TenantPaymentProviderConfiguration).where(
                    TenantPaymentProviderConfiguration.selected_provider == "stripe_connect",
                    TenantPaymentProviderConfiguration.provider_account_snapshot == account_id,
                ).order_by(
                    TenantPaymentProviderConfiguration.effective_at.desc(),
                    TenantPaymentProviderConfiguration.version.desc(),
                ).limit(1)
            )
            if historical_config:
                tenant = await db.get(Tenant, historical_config.tenant_id)
    if not tenant and not account_id:
        tenant_id = data_object.get("metadata", {}).get("tenant_id")
        if tenant_id:
            try:
                tenant = (
                    await db.execute(select(Tenant).where(Tenant.id == UUID(tenant_id)))
                ).scalar_one_or_none()
            except ValueError:
                pass
    if tenant:
        tenant.stripe_last_webhook_at = datetime.now(timezone.utc)
        tenant.stripe_last_webhook_event = event_type
        tenant.stripe_last_webhook_error = None
    return tenant


@router.post("/connect")
async def stripe_connect_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe Connect webhooks for account updates"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    # Use Connect-specific webhook secret if available, otherwise fall back to main secret
    webhook_secret = settings.STRIPE_CONNECT_WEBHOOK_SECRET or settings.STRIPE_WEBHOOK_SECRET
    event = _verified_stripe_event(
        payload=payload, signature=sig_header, secret=webhook_secret,
    )
    
    event_type = event["type"]
    data_object = event["data"]["object"]
    delivery_tenant = await _record_webhook_delivery(db, event, event_type, data_object)

    if event_type == "account.updated":
        account = data_object
        account_id = account["id"]
        
        # Find tenant by stripe_account_id
        result = await db.execute(
            select(Tenant).where(Tenant.stripe_account_id == account_id)
        )
        tenant = result.scalar_one_or_none()
        
        if tenant:
            # Update onboarding status based on account capabilities
            charges_enabled = account.get("charges_enabled", False)
            payouts_enabled = account.get("payouts_enabled", False)
            onboarding_complete = charges_enabled and payouts_enabled
            
            tenant.stripe_onboarding_complete = onboarding_complete
    
    elif event_type == "account.application.deauthorized":
        # Tenant disconnected their Stripe account
        account_id = event.get("account")
        
        if account_id:
            result = await db.execute(
                select(Tenant).where(Tenant.stripe_account_id == account_id)
            )
            tenant = result.scalar_one_or_none()
            
            if tenant:
                tenant.stripe_account_id = None
                tenant.stripe_onboarding_complete = False
                logger.info("stripe_account_disconnected", tenant_id=str(tenant.id), account_id=account_id)

    elif event_type == "payment_intent.payment_failed":
        await _handle_payment_failed(db, data_object, event=event)
    elif event_type == "charge.failed":
        await _handle_charge_failed(db, data_object)
    elif event_type == "charge.dispute.created":
        await _handle_dispute_created(db, data_object, event=event)
    elif event_type == "charge.dispute.closed":
        await _handle_dispute_closed(db, data_object, event=event)
    elif event_type in {"refund.updated", "refund.failed"}:
        await _handle_db048_refund_event(db, data_object, event=event)
    elif event_type == "payout.paid":
        await _enqueue_db048_payout_reconciliation(db, data_object, event=event, tenant=delivery_tenant)
    elif event_type == "payment_intent.succeeded":
        await _handle_payment_succeeded(db, data_object, event=event)

    if delivery_tenant:
        if event_type == "payment_intent.payment_failed":
            delivery_tenant.stripe_last_webhook_error = data_object.get("last_payment_error", {}).get("message") or "Payment failed"
        elif event_type == "charge.failed":
            delivery_tenant.stripe_last_webhook_error = data_object.get("failure_message") or "Charge failed"
    await db.commit()
    
    return {"status": "success"}


@router.post("/payments")
async def stripe_payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Stripe payment webhooks for payment events.
    
    Handles:
    - payment_intent.payment_failed: Log failure, update invoice status
    - charge.failed: Log charge failure details
    - charge.dispute.created: Log and alert on disputes (critical)
    - payment_intent.succeeded: Backup confirmation (in case frontend fails)
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    event = _verified_stripe_event(
        payload=payload, signature=sig_header, secret=webhook_secret,
    )
    
    event_type = event["type"]
    data_object = event["data"]["object"]
    delivery_tenant = await _record_webhook_delivery(db, event, event_type, data_object)
    
    logger.info("stripe_webhook_received", event_type=event_type, event_id=event.get("id"))
    
    # Handle payment_intent.payment_failed
    if event_type == "payment_intent.payment_failed":
        await _handle_payment_failed(db, data_object, event=event)
    
    # Handle charge.failed
    elif event_type == "charge.failed":
        await _handle_charge_failed(db, data_object)
    
    # Handle charge.dispute.created (critical - money at risk)
    elif event_type == "charge.dispute.created":
        await _handle_dispute_created(db, data_object, event=event)
    elif event_type == "charge.dispute.closed":
        await _handle_dispute_closed(db, data_object, event=event)
    elif event_type in {"refund.updated", "refund.failed"}:
        await _handle_db048_refund_event(db, data_object, event=event)
    elif event_type == "payout.paid":
        await _enqueue_db048_payout_reconciliation(db, data_object, event=event, tenant=delivery_tenant)
    
    # Handle payment_intent.succeeded (backup confirmation)
    elif event_type == "payment_intent.succeeded":
        await _handle_payment_succeeded(db, data_object, event=event)

    if delivery_tenant:
        if event_type == "payment_intent.payment_failed":
            delivery_tenant.stripe_last_webhook_error = data_object.get("last_payment_error", {}).get("message") or "Payment failed"
        elif event_type == "charge.failed":
            delivery_tenant.stripe_last_webhook_error = data_object.get("failure_message") or "Charge failed"
    await db.commit()
    
    return {"status": "success"}


async def _handle_payment_failed(db: AsyncSession, payment_intent: dict, *, event=None):
    """Handle payment_intent.payment_failed event."""
    payment_intent_id = payment_intent.get("id")
    invoice_id = payment_intent.get("metadata", {}).get("invoice_id")
    tenant_id = payment_intent.get("metadata", {}).get("tenant_id")
    
    # Get failure details
    last_error = payment_intent.get("last_payment_error", {})
    error_code = last_error.get("code", "unknown")
    error_message = last_error.get("message", "Payment failed")
    decline_code = last_error.get("decline_code")
    
    # DB-048 failure releases its exact reservation immediately. The signed
    # Connect account and complete PI envelope are validated before lifecycle,
    # reservation, ledger, error-row, or payment state can change. Metadata
    # alone can never select a tenant or payment row.
    attempt_id = payment_intent.get("metadata", {}).get("invoice_payment_attempt_id")
    provider_account_id = event.get("account") if event else None
    provider_event_id = event.get("id") if event else None
    bound_db048_attempt = None
    if not attempt_id and provider_account_id and payment_intent_id:
        # Removing the attempt metadata from a known durable intent must not
        # downgrade it into the legacy observability-only path. Bind only by
        # signed account plus immutable provider intent; the strict validator
        # will then reject the incomplete metadata envelope.
        bound_db048_attempt = await db.scalar(
            select(InvoicePaymentAttempt).where(
                InvoicePaymentAttempt.provider == "stripe_connect",
                InvoicePaymentAttempt.provider_account_id == provider_account_id,
                InvoicePaymentAttempt.provider_intent_id == str(payment_intent_id),
                InvoicePaymentAttempt.deleted_at.is_(None),
            ).limit(1)
        )
        if bound_db048_attempt is not None:
            attempt_id = str(bound_db048_attempt.id)
    if attempt_id:
        if not provider_event_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provider payment identity mismatch",
            )
        validated = await validate_db048_stripe_payment_intent(
            db=db,
            payment_intent=payment_intent,
            trusted_provider_account_id=provider_account_id,
            attempt=bound_db048_attempt,
            allowed_statuses=("requires_payment_method", "canceled"),
        )
        attempt = validated.attempt
        # Unlike success, failure does not enter confirm_attempt, so enforce the
        # exact same tenant/customer/invoice/order lifecycle boundary here
        # before releasing the reservation.
        await locked_accessible_invoice_for_attempt(db, attempt)
        await fail_attempt(
            db,
            attempt_id=attempt.id,
            tenant_id=attempt.tenant_id,
            actor=None,
            expected_attempt_version=attempt.version,
            failure_code=str(error_code or "stripe_payment_failed")[:100],
            idempotency_key=f"stripe:{provider_account_id}:{provider_event_id}:failed",
        )

    logger.error(
        "payment_intent_failed",
        payment_intent_id=payment_intent_id,
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        error_code=error_code,
        error_message=error_message,
        decline_code=decline_code,
    )

    # Record metrics only after a DB-048 envelope/lifecycle passed. Legacy
    # failures retain their existing best-effort observability behavior.
    record_payment(status="failure", payment_method="stripe", tenant_id=tenant_id or "unknown")
    record_payment_error(error_type=f"PaymentFailed_{error_code}", provider="stripe")
    
    # Persist to error log
    await error_service.log_error(
        error_type=f"PaymentFailed_{error_code}",
        message=f"Payment failed: {error_message}" + (f" (decline: {decline_code})" if decline_code else ""),
        category=ErrorCategory.PAYMENT,
        severity=ErrorSeverity.ERROR,
        endpoint="/webhooks/stripe/payments",
        method="POST",
        status_code=None,  # Webhook, not a user request
        request_context={
            "payment_intent_id": payment_intent_id,
            "invoice_id": invoice_id,
            "tenant_id": tenant_id,
            "error_code": error_code,
            "decline_code": decline_code,
        },
    )


async def _handle_charge_failed(db: AsyncSession, charge: dict):
    """Handle charge.failed event."""
    charge_id = charge.get("id")
    payment_intent_id = charge.get("payment_intent")
    
    # Get failure details
    failure_code = charge.get("failure_code", "unknown")
    failure_message = charge.get("failure_message", "Charge failed")
    
    logger.error(
        "charge_failed",
        charge_id=charge_id,
        payment_intent_id=payment_intent_id,
        failure_code=failure_code,
        failure_message=failure_message,
    )
    
    # Record metrics
    record_payment_error(error_type=f"ChargeFailed_{failure_code}", provider="stripe")
    
    # Persist to error log
    await error_service.log_error(
        error_type=f"ChargeFailed_{failure_code}",
        message=f"Charge failed: {failure_message}",
        category=ErrorCategory.PAYMENT,
        severity=ErrorSeverity.ERROR,
        endpoint="/webhooks/stripe/payments",
        method="POST",
        request_context={
            "charge_id": charge_id,
            "payment_intent_id": payment_intent_id,
            "failure_code": failure_code,
        },
    )


async def _handle_dispute_created(db: AsyncSession, dispute: dict, *, event=None):
    """
    Handle charge.dispute.created event.
    
    This is CRITICAL - a dispute means potential chargeback and money at risk.
    """
    dispute_id = dispute.get("id")
    charge_id = dispute.get("charge")
    amount = dispute.get("amount", 0) / 100  # Convert cents to dollars
    reason = dispute.get("reason", "unknown")
    dispute_status = dispute.get("status")
    
    logger.critical(
        "dispute_created",
        dispute_id=dispute_id,
        charge_id=charge_id,
        amount=amount,
        reason=reason,
        status=dispute_status,
    )
    
    # Record metrics
    record_payment_error(error_type=f"Dispute_{reason}", provider="stripe")
    
    # Persist to error log with CRITICAL severity
    await error_service.log_error(
        error_type=f"Dispute_{reason}",
        message=f"DISPUTE CREATED: ${amount:.2f} - Reason: {reason}. Immediate action required!",
        category=ErrorCategory.PAYMENT,
        severity=ErrorSeverity.CRITICAL,
        endpoint="/webhooks/stripe/payments",
        method="POST",
        request_context={
            "dispute_id": dispute_id,
            "charge_id": charge_id,
            "amount": amount,
            "reason": reason,
            "status": dispute_status,
        },
    )
    provider_account_id = event.get("account") if event else None
    provider_event_id = event.get("id") if event else None
    if not charge_id or not dispute_id or not provider_event_id:
        return
    any_db048_attempt = await db.scalar(select(InvoicePaymentAttempt.id).where(
        InvoicePaymentAttempt.provider == "stripe_connect",
        InvoicePaymentAttempt.provider_charge_id == charge_id,
    ).limit(1))
    if any_db048_attempt and not provider_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider dispute account mismatch",
        )
    if provider_account_id:
        attempt = await db.scalar(select(InvoicePaymentAttempt).where(
            InvoicePaymentAttempt.provider == "stripe_connect",
            InvoicePaymentAttempt.provider_account_id == provider_account_id,
            InvoicePaymentAttempt.provider_charge_id == charge_id,
        ))
        if any_db048_attempt and not attempt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provider dispute account mismatch",
            )
        if attempt:
            await record_stripe_dispute(
                db,
                provider_account_id=provider_account_id,
                provider_charge_id=str(charge_id),
                provider_dispute_id=str(dispute_id),
                provider_event_id=str(provider_event_id),
                amount=Decimal(str(dispute.get("amount", 0))) / Decimal("100"),
                currency=str(dispute.get("currency") or "").upper(),
                reason=str(reason),
            )


async def _handle_dispute_closed(db: AsyncSession, dispute: dict, *, event=None):
    """Apply signed Stripe dispute finality; won restores the exact lost funds."""
    provider_account_id = event.get("account") if event else None
    provider_event_id = event.get("id") if event else None
    dispute_id = dispute.get("id")
    charge_id = dispute.get("charge")
    if not provider_account_id or not provider_event_id or not dispute_id or not charge_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider dispute identity mismatch",
        )
    outcome = str(dispute.get("status") or "").casefold()
    if outcome not in {"won", "lost"}:
        # Stripe may deliver a closed-type event before a supported terminal
        # projection; never guess or change money.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider dispute outcome is not terminal",
        )
    await close_stripe_dispute(
        db,
        provider_account_id=str(provider_account_id),
        provider_charge_id=str(charge_id),
        provider_dispute_id=str(dispute_id),
        provider_event_id=str(provider_event_id),
        amount=Decimal(str(dispute.get("amount", 0))) / Decimal("100"),
        currency=str(dispute.get("currency") or "").upper(),
        outcome=outcome,
    )


async def _handle_db048_refund_event(db: AsyncSession, refund: dict, *, event) -> None:
    metadata = refund.get("metadata") or {}
    refund_id = metadata.get("payment_refund_id")
    tenant_id = metadata.get("tenant_id")
    provider_account_id = event.get("account")
    if not refund_id or not tenant_id or not provider_account_id:
        return
    try:
        refund_uuid = UUID(str(refund_id))
        tenant_uuid = UUID(str(tenant_id))
    except ValueError:
        return
    provider_status = "failed" if event.get("type") == "refund.failed" else str(refund.get("status") or "pending")
    if provider_status in {"succeeded", "failed", "canceled", "cancelled"}:
        await finalize_provider_refund(
            db,
            refund_id=refund_uuid,
            tenant_id=tenant_uuid,
            provider_account_id=provider_account_id,
            provider_reference=str(refund.get("id") or ""),
            provider_event_id=str(event.get("id")),
            provider_status=provider_status,
        )


async def _enqueue_db048_payout_reconciliation(
    db: AsyncSession,
    payout: dict,
    *,
    event,
    tenant: Tenant | None,
) -> None:
    provider_account_id = event.get("account")
    payout_id = payout.get("id")
    event_id = event.get("id")
    if not provider_account_id or not payout_id or not event_id:
        return
    # A provider switch only affects new attempts. Historical payout events
    # remain bound to the immutable provider-account configuration snapshot.
    config = (await db.execute(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.selected_provider == "stripe_connect",
        TenantPaymentProviderConfiguration.provider_account_snapshot == provider_account_id,
    ).order_by(TenantPaymentProviderConfiguration.version.desc()).limit(1))).scalar_one_or_none()
    if not config:
        raise DB048ReconciliationError("Stripe payout account does not match a provider snapshot")
    tenant = await db.get(Tenant, config.tenant_id)
    if not tenant:
        raise DB048ReconciliationError("Stripe payout tenant identity is unavailable")
    idempotency_key = f"stripe-payout:{provider_account_id}:{payout_id}"
    existing = (await db.execute(select(ProviderOutboxEvent.id).where(
        ProviderOutboxEvent.tenant_id == tenant.id,
        ProviderOutboxEvent.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if existing:
        return
    db.add(ProviderOutboxEvent(
        tenant_id=tenant.id,
        event_type=PAYOUT_RECONCILIATION_EVENT,
        aggregate_type="stripe_payout",
        aggregate_id=tenant.id,
        payload={
            "payout_id": str(payout_id),
            "provider_account_id": str(provider_account_id),
            "provider_event_id": str(event_id),
            "net_payout": str(Decimal(str(payout.get("amount", 0))) / Decimal("100")),
        },
        idempotency_key=idempotency_key,
        status=ProviderOutboxStatus.PENDING.value,
        available_at=datetime.now(timezone.utc),
    ))


async def _handle_payment_succeeded(db: AsyncSession, payment_intent: dict, *, event=None):
    """
    Handle payment_intent.succeeded event.
    
    This is a backup confirmation in case the frontend fails to call /confirm-payment.
    """
    payment_intent_id = payment_intent.get("id")
    metadata = payment_intent.get("metadata", {}) or {}
    invoice_id = metadata.get("invoice_id")
    provider_account_id = event.get("account") if event else None
    provider_event_id = event.get("id") if event else None
    db048_attempt_id = metadata.get("invoice_payment_attempt_id")
    if not provider_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider payment identity mismatch",
        )
    if (
        not db048_attempt_id
        and (not metadata.get("tenant_id") or not metadata.get("stripe_connected_account_id"))
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider payment identity mismatch",
        )
    if db048_attempt_id and not provider_event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider payment identity mismatch",
        )
    
    if not invoice_id:
        logger.warning("payment_succeeded_no_invoice", payment_intent_id=payment_intent_id)
        return
    
    # Check if invoice is already paid (frontend already confirmed)
    try:
        from uuid import UUID
        invoice_uuid = UUID(invoice_id)
        result = await db.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.repair_order).selectinload(RepairOrder.customer),
                selectinload(Invoice.repair_order).selectinload(RepairOrder.vehicle),
            )
            .where(Invoice.id == invoice_uuid)
        )
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            logger.warning("payment_succeeded_invoice_not_found", payment_intent_id=payment_intent_id, invoice_id=invoice_id)
            return

        if not invoice.repair_order:
            logger.warning("payment_succeeded_invoice_missing_order", payment_intent_id=payment_intent_id, invoice_id=invoice_id)
            return

        tenant_result = await db.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
        tenant = tenant_result.scalar_one_or_none()

        if not db048_attempt_id:
            await validate_legacy_stripe_payment_identity(
                db=db,
                invoice=invoice,
                order=invoice.repair_order,
                tenant=tenant,
                payment_intent=payment_intent,
                provider_account_id=provider_account_id,
            )
        
        logger.info(
            "payment_succeeded_backup_confirmation",
            payment_intent_id=payment_intent_id,
            invoice_id=invoice_id,
        )

        finalization = await finalize_stripe_invoice_payment(
            db=db,
            invoice=invoice,
            order=invoice.repair_order,
            customer=invoice.repair_order.customer,
            tenant=tenant,
            vehicle=invoice.repair_order.vehicle,
            payment_intent=payment_intent,
            payment_note=WEBHOOK_PAYMENT_NOTE,
            allow_already_paid_without_payment=True,
            provider_account_id=provider_account_id,
            provider_event_id=provider_event_id,
        )
        if finalization.created:
            logger.info(
                "payment_succeeded_webhook_finalized_invoice",
                payment_intent_id=payment_intent_id,
                invoice_id=invoice_id,
            )
        else:
            logger.debug(
                "payment_succeeded_already_finalized",
                payment_intent_id=payment_intent_id,
                invoice_id=invoice_id,
            )
        
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            logger.info(
                "payment_succeeded_invoice_already_paid_elsewhere",
                payment_intent_id=payment_intent_id,
                invoice_id=invoice_id,
            )
            return
        raise
    except Exception as e:
        logger.error("payment_succeeded_handler_error", payment_intent_id=payment_intent_id, error=str(e))
        raise
