"""One-time staff-attested tax adjustment, before any payment or remote export."""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, or_
from app.core.config import settings
from app.core.dependencies import user_has_permission
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoiceSettlement, InvoicePaymentAttempt, InvoicePaymentLedgerEvent, PaymentAccountingLink, PaymentRefund
from app.db.models.payment import Payment
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.user import UserRole
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.services.invoice_accounting_policy import locked_policy
from app.services.invoice_cash_service import valid_sandbox_cash_review, local_void_ancestor_snapshot, CASH_REVIEW_KEY
from app.services.invoice_settlement_service import SettlementDomainError, money, invoice_money_snapshot, _canonical_hash, _actor_snapshot
from app.schemas.invoice_settlement import InvoiceTaxExemptionRead

ZERO = Decimal("0.00")
MONEY_FIELDS = ("subtotal", "shop_supplies_amount", "service_fee_amount", "tax_amount", "discount_amount", "total_amount")


def authorized(actor):
    return bool(actor and actor.role in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN}
                and user_has_permission(actor, "payments"))


def snapshot(invoice):
    return {name: str(money(getattr(invoice, name))) for name in MONEY_FIELDS}


async def eligibility(db, invoice, settlement, *, lock=False):
    if invoice.tax_exemption:
        return "Tax exemption has already been applied."
    if (invoice.deleted_at or invoice.voided_at or invoice.is_internal
            or invoice.status not in {InvoiceStatus.SENT, InvoiceStatus.OVERDUE}):
        return "Only an active unpaid customer invoice can be made tax exempt."
    live_customer = await db.scalar(select(Customer.id).join(RepairOrder, RepairOrder.customer_id == Customer.id).where(
        RepairOrder.id == invoice.repair_order_id, RepairOrder.tenant_id == invoice.tenant_id,
        RepairOrder.deleted_at.is_(None), RepairOrder.status != RepairOrderStatus.CANCELLED,
        Customer.id == settlement.customer_id, Customer.tenant_id == invoice.tenant_id, Customer.deleted_at.is_(None)))
    if not live_customer or settlement.tenant_id != invoice.tenant_id or settlement.invoice_id != invoice.id:
        return "Invoice customer or repair order is unavailable."
    if money(invoice.tax_amount) <= ZERO:
        return "This invoice has no sales tax to exempt."
    values = {name: money(getattr(invoice, name)) for name in MONEY_FIELDS}
    if (any(value < ZERO for value in values.values())
            or values["total_amount"] != values["subtotal"] + values["shop_supplies_amount"]
                + values["service_fee_amount"] + values["tax_amount"] - values["discount_amount"]
            or values["total_amount"] - values["tax_amount"] - values["service_fee_amount"] <= ZERO):
        return "Invoice amounts require review before changing tax."
    if invoice.zelle_pending_submitted_at is not None:
        return "Resolve the pending Zelle payment before changing tax."
    if (settlement.state != "unpaid" or settlement.last_event_sequence
            or any(money(getattr(settlement, name)) != ZERO for name in
                   ("confirmed_principal", "active_pending_principal", "unapplied_credit", "refund_pending"))):
        return "Resolve existing payment activity before changing tax."
    principal, fee, fee_tax, _, _ = invoice_money_snapshot(invoice)
    if (money(settlement.principal_total), money(settlement.max_card_fee), money(settlement.max_card_fee_tax)) != (principal, fee, fee_tax):
        return "Invoice and settlement amounts require review before changing tax."
    for model in (InvoicePaymentAttempt, Payment, InvoicePaymentLedgerEvent, PaymentAccountingLink, PaymentRefund):
        if await db.scalar(select(model.id).where(model.tenant_id == invoice.tenant_id,
                                                  model.invoice_id == invoice.id).limit(1)):
            return "Tax cannot change after payment activity has started."
    if invoice.quickbooks_invoice_id or invoice.quickbooks_synced_at:
        return "This invoice has QuickBooks accounting history. Review it before changing tax."
    query = select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id == invoice.tenant_id,
                                             ProviderOutboxEvent.aggregate_id == invoice.id)
    if lock:
        query = query.with_for_update(nowait=True)
    events = list((await db.scalars(query.execution_options(populate_existing=True))).all())
    from app.services.provider_outbox_service import EMAIL_NOTIFICATION_EVENT
    for event in events:
        if event.event_type == EMAIL_NOTIFICATION_EVENT:
            continue
        if (event.event_type != "quickbooks.invoice.sync.v1" or event.status == "processing"
                or event.lock_token or event.locked_until or event.provider_message_id
                or event.status == "succeeded"):
            return "Invoice export activity must be resolved before changing tax."
        if (event.status not in {"pending", "dead", "suppressed", "deferred"}
                or ((event.payload or {}).get("cash_export_ambiguous")
                    or event.attempt_count and not (event.payload or {}).get("cash_no_dispatch"))
                and not valid_sandbox_cash_review(event, invoice)):
            return "Previous invoice export attempts require review before changing tax."
    if not events and invoice.quickbooks_sync_status not in {None, "pending", "not_synced", "not_required", "awaiting_payment"}:
        return "Previous invoice export history requires review before changing tax."
    seen, parent_id = {invoice.id}, invoice.supersedes_invoice_id
    while parent_id:
        if parent_id in seen:
            return "Invoice replacement history requires review."
        seen.add(parent_id)
        parent = await db.scalar(select(Invoice).where(Invoice.id == parent_id, Invoice.tenant_id == invoice.tenant_id))
        if not parent:
            return "Invoice replacement history requires review."
        if lock:
            await locked_policy(db, parent)
            await db.refresh(parent, attribute_names=[column.name for column in Invoice.__table__.columns])
        if parent.zelle_pending_submitted_at is not None or parent.quickbooks_invoice_id:
            return "A previous invoice has pending payment or QuickBooks history requiring review."
        parent_query = select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id == invoice.tenant_id,
            ProviderOutboxEvent.aggregate_id == parent.id, ProviderOutboxEvent.event_type != EMAIL_NOTIFICATION_EVENT)
        if lock:
            parent_query = parent_query.with_for_update(nowait=True)
        parent_events = list((await db.scalars(parent_query.execution_options(populate_existing=True))).all())
        reviews = [event.payload[CASH_REVIEW_KEY] for event in events if valid_sandbox_cash_review(event, invoice)]
        local_snapshot = await local_void_ancestor_snapshot(db, parent, lock=lock) if parent.quickbooks_synced_at else None
        local_reviewed = bool(local_snapshot and reviews and all(any(
            proof.get("schema") == "db048-local-void-ancestor-review-v1"
            and proof.get("invoice_id") == str(parent.id) and proof.get("snapshot") == local_snapshot
            and proof.get("confirmation_realm_id") == review.get("confirmation_realm_id")
            and proof.get("evidence_manifest_sha256") == review.get("evidence_manifest_sha256")
            for proof in review.get("ancestor_reviews", [])) for review in reviews))
        if parent.quickbooks_synced_at and not local_reviewed:
            return "A previous invoice has QuickBooks history requiring review."
        if not local_reviewed:
            for event in parent_events:
                if (event.event_type != "quickbooks.invoice.sync.v1" or event.status not in {"pending", "dead", "suppressed", "deferred"}
                        or event.lock_token or event.locked_until or event.provider_message_id
                        or ((event.payload or {}).get("cash_export_ambiguous")
                            or event.attempt_count and not (event.payload or {}).get("cash_no_dispatch"))
                        and not valid_sandbox_cash_review(event, parent)):
                    return "A previous invoice has unresolved export activity."
        attempt = await db.scalar(select(InvoicePaymentAttempt.id).where(
            InvoicePaymentAttempt.tenant_id == invoice.tenant_id, InvoicePaymentAttempt.invoice_id == parent.id,
            or_(InvoicePaymentAttempt.state == "pending", InvoicePaymentAttempt.received_amount.is_not(None),
                InvoicePaymentAttempt.provider_charge_id.is_not(None), InvoicePaymentAttempt.provider_intent_id.is_not(None),
                InvoicePaymentAttempt.provider_event_id.is_not(None), InvoicePaymentAttempt.provider_reference.is_not(None))).limit(1))
        prior = await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id == parent.id,
                                                               InvoiceSettlement.tenant_id == invoice.tenant_id))
        if attempt or prior and any(money(getattr(prior, name)) != ZERO for name in
                                   ("confirmed_principal", "active_pending_principal", "unapplied_credit", "refund_pending")):
            return "A previous invoice has unresolved payment activity. Resolve it before changing tax."
        for model in (Payment, PaymentAccountingLink, PaymentRefund):
            if await db.scalar(select(model.id).where(model.tenant_id == invoice.tenant_id, model.invoice_id == parent.id).limit(1)):
                return "A previous invoice has financial activity requiring review."
        parent_id = parent.supersedes_invoice_id
    return None


async def summary(db, invoice, settlement, tenant, actor, *, audience):
    staff = audience == "staff" and authorized(actor) and actor.tenant_id == tenant.id
    enabled = settings.INVOICE_SPLIT_PAYMENTS_ENABLED and tenant.invoice_split_payments_enabled
    reason = await eligibility(db, invoice, settlement) if staff and enabled else "Only an authorized shop owner or administrator can change invoice tax."
    audit = invoice.tax_exemption or {}
    return InvoiceTaxExemptionRead(applied=bool(audit), can_apply=staff and enabled and reason is None,
        unavailable_reason=reason if staff else None, current_tax_amount=money(invoice.tax_amount),
        removed_tax_amount=money(audit.get("before", {}).get("tax_amount", ZERO)),
        exempt_principal_total=max(ZERO, money(invoice.total_amount) - money(invoice.tax_amount) - money(invoice.service_fee_amount)),
        reason=audit.get("reason") if staff else None, support_reference=audit.get("support_reference") if staff else None)


async def apply_exemption(db, *, invoice, tenant, actor, body, idempotency_key):
    if (not authorized(actor) or actor.tenant_id != tenant.id or invoice.tenant_id != tenant.id
            or not tenant.is_active or tenant.deleted_at):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if not settings.INVOICE_SPLIT_PAYMENTS_ENABLED or not tenant.invoice_split_payments_enabled:
        raise SettlementDomainError("split_payments_disabled", "Invoice settlement is not enabled for this shop.")
    await locked_policy(db, invoice)
    await db.refresh(invoice, attribute_names=[column.name for column in Invoice.__table__.columns])
    await db.refresh(tenant)
    if not tenant.is_active or tenant.deleted_at:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    settlement = await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id == invoice.id,
        InvoiceSettlement.tenant_id == tenant.id).execution_options(populate_existing=True))
    if not settlement:
        raise SettlementDomainError("tax_exemption_unavailable", "Refresh the invoice before changing tax.")
    request_hash = _canonical_hash({"invoice_id": str(invoice.id), "actor_id": str(actor.id), **body.model_dump()})
    if invoice.tax_exemption and invoice.tax_exemption.get("idempotency_key") == idempotency_key:
        if invoice.tax_exemption.get("request_hash") != request_hash:
            raise SettlementDomainError("idempotency_conflict", "This key was used for a different tax adjustment.")
        return settlement
    if settlement.version != body.expected_settlement_version:
        raise SettlementDomainError("stale_settlement_version", "The invoice changed. Refresh before changing tax.", current_version=settlement.version)
    reason = await eligibility(db, invoice, settlement, lock=True)
    if reason:
        raise SettlementDomainError("tax_exemption_unavailable", reason)
    before, version = snapshot(invoice), settlement.version
    invoice.total_amount = money(invoice.total_amount) - money(invoice.tax_amount)
    invoice.tax_amount = ZERO
    principal, fee, fee_tax, rate, fee_rate = invoice_money_snapshot(invoice)
    settlement.principal_total, settlement.max_card_fee, settlement.max_card_fee_tax = principal, fee, fee_tax
    settlement.sales_tax_rate_snapshot, settlement.card_fee_rate_snapshot = rate, fee_rate
    settlement.version += 1
    actor_id, actor_name, actor_role = _actor_snapshot(actor)
    invoice.tax_exemption = {"schema": "invoice-tax-exemption-v1", "tenant_id": str(tenant.id), "invoice_id": str(invoice.id),
        "applied_at": datetime.now(timezone.utc).isoformat(), "actor_id": str(actor_id), "actor_name": actor_name,
        "actor_role": actor_role, "reason": body.reason, "support_reference": body.support_reference,
        "idempotency_key": idempotency_key, "request_hash": request_hash, "before": before, "after": snapshot(invoice),
        "before_settlement_version": version, "after_settlement_version": settlement.version}
    await db.flush()
    return settlement
