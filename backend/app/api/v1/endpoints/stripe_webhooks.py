from datetime import datetime, timezone

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
from app.db.models.repair_order import RepairOrder
from app.db.models.error_log import ErrorCategory, ErrorSeverity
from app.services import error_service
from app.services.stripe_payment_finalization import finalize_stripe_invoice_payment

WEBHOOK_PAYMENT_NOTE = "Payment confirmed by Stripe webhook."

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = get_logger(__name__)

router = APIRouter()


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
    if not tenant:
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
    
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )
    
    # Use Connect-specific webhook secret if available, otherwise fall back to main secret
    webhook_secret = settings.STRIPE_CONNECT_WEBHOOK_SECRET or settings.STRIPE_WEBHOOK_SECRET
    
    if not webhook_secret:
        # In development without webhook secret, just parse the event
        try:
            event = stripe.Event.construct_from(
                stripe.util.json.loads(payload), stripe.api_key
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payload",
            )
    else:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature",
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payload",
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
        await _handle_payment_failed(db, data_object)
    elif event_type == "charge.failed":
        await _handle_charge_failed(db, data_object)
    elif event_type == "charge.dispute.created":
        await _handle_dispute_created(db, data_object)
    elif event_type == "payment_intent.succeeded":
        await _handle_payment_succeeded(db, data_object)

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
    
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )
    
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    
    if not webhook_secret:
        # In development without webhook secret, just parse the event
        try:
            event = stripe.Event.construct_from(
                stripe.util.json.loads(payload), stripe.api_key
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payload",
            )
    else:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature",
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payload",
            )
    
    event_type = event["type"]
    data_object = event["data"]["object"]
    delivery_tenant = await _record_webhook_delivery(db, event, event_type, data_object)
    
    logger.info("stripe_webhook_received", event_type=event_type, event_id=event.get("id"))
    
    # Handle payment_intent.payment_failed
    if event_type == "payment_intent.payment_failed":
        await _handle_payment_failed(db, data_object)
    
    # Handle charge.failed
    elif event_type == "charge.failed":
        await _handle_charge_failed(db, data_object)
    
    # Handle charge.dispute.created (critical - money at risk)
    elif event_type == "charge.dispute.created":
        await _handle_dispute_created(db, data_object)
    
    # Handle payment_intent.succeeded (backup confirmation)
    elif event_type == "payment_intent.succeeded":
        await _handle_payment_succeeded(db, data_object)

    if delivery_tenant:
        if event_type == "payment_intent.payment_failed":
            delivery_tenant.stripe_last_webhook_error = data_object.get("last_payment_error", {}).get("message") or "Payment failed"
        elif event_type == "charge.failed":
            delivery_tenant.stripe_last_webhook_error = data_object.get("failure_message") or "Charge failed"
        await db.commit()
    
    return {"status": "success"}


async def _handle_payment_failed(db: AsyncSession, payment_intent: dict):
    """Handle payment_intent.payment_failed event."""
    payment_intent_id = payment_intent.get("id")
    invoice_id = payment_intent.get("metadata", {}).get("invoice_id")
    tenant_id = payment_intent.get("metadata", {}).get("tenant_id")
    
    # Get failure details
    last_error = payment_intent.get("last_payment_error", {})
    error_code = last_error.get("code", "unknown")
    error_message = last_error.get("message", "Payment failed")
    decline_code = last_error.get("decline_code")
    
    logger.error(
        "payment_intent_failed",
        payment_intent_id=payment_intent_id,
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        error_code=error_code,
        error_message=error_message,
        decline_code=decline_code,
    )
    
    # Record metrics
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


async def _handle_dispute_created(db: AsyncSession, dispute: dict):
    """
    Handle charge.dispute.created event.
    
    This is CRITICAL - a dispute means potential chargeback and money at risk.
    """
    dispute_id = dispute.get("id")
    charge_id = dispute.get("charge")
    amount = dispute.get("amount", 0) / 100  # Convert cents to dollars
    reason = dispute.get("reason", "unknown")
    status = dispute.get("status")
    
    logger.critical(
        "dispute_created",
        dispute_id=dispute_id,
        charge_id=charge_id,
        amount=amount,
        reason=reason,
        status=status,
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
            "status": status,
        },
    )


async def _handle_payment_succeeded(db: AsyncSession, payment_intent: dict):
    """
    Handle payment_intent.succeeded event.
    
    This is a backup confirmation in case the frontend fails to call /confirm-payment.
    """
    payment_intent_id = payment_intent.get("id")
    invoice_id = payment_intent.get("metadata", {}).get("invoice_id")
    
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
