"""New receipt admission does not release historical invoices or old export jobs."""
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from uuid import UUID
from sqlalchemy import select, or_
from app.core.config import settings
from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import InvoicePaymentAttempt, InvoiceSettlement, TenantPaymentProviderConfiguration, PaymentAccountingLink
from app.db.models.payment import Payment, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.quickbooks_connection import QuickBooksConnection

_receipt_scope = ContextVar("new_receipt_accounting_scope", default=None)
LIVE_SOURCES = {"staff", "customer_portal", "customer_portal_compatibility", "guest_token", "guest_invoice_access", "compatibility_adapter"}


def deny(code, message):
    from app.services.invoice_settlement_service import SettlementDomainError
    raise SettlementDomainError(code, message)


def authorization_matches(attempt, config):
    proof = getattr(attempt, "new_receipt_accounting_authorization", None)
    if not isinstance(proof, dict) or not config:
        return False
    try:
        issued = datetime.fromisoformat(proof["issued_at"])
        return (proof["version"] == "new_receipt_v1" and issued.tzinfo is not None
            and proof["tenant_id"] == str(attempt.tenant_id) == str(config.tenant_id)
            and proof["invoice_id"] == str(attempt.invoice_id)
            and proof["attempt_id"] == str(attempt.id)
            and proof["configuration_version"] == attempt.provider_configuration_version == config.version
            and proof["realm_id"] == config.qbo_realm_snapshot and bool(proof["realm_id"])
            and proof["writer"] == config.writer_strategy == "dieselbridge"
            and proof["environment"] in {"production", "sandbox"}
            and proof["effective_composition"] == "gross_invoice_v1"
            and attempt.source in LIVE_SOURCES and attempt.rail in {"card", "zelle", "check", "ach", "fleet_payment"})
    except (KeyError, TypeError, ValueError):
        return False


async def valid_attempt_authorization(db, attempt, *, check_connection=False):
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == attempt.tenant_id,
        TenantPaymentProviderConfiguration.version == attempt.provider_configuration_version))
    if not authorization_matches(attempt, config):
        return False
    if check_connection:
        connection = await db.scalar(select(QuickBooksConnection).where(
            QuickBooksConnection.tenant_id == attempt.tenant_id, QuickBooksConnection.status == "connected",
            QuickBooksConnection.deleted_at.is_(None)))
        if not connection or connection.realm_id != config.qbo_realm_snapshot:
            return False
        if attempt.provider == "quickbooks_payments" and settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT.strip().lower() != attempt.new_receipt_accounting_authorization["environment"]:
            return False
    return True


async def require_clean_historical_balance(db, invoice):
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == invoice.tenant_id,
        TenantPaymentProviderConfiguration.is_active.is_(True)))
    if not config or not config.qbo_card_fee_item_id or not config.qbo_card_fee_tax_code_id:
        deny("new_receipt_accounting_mappings", "Complete the card-fee accounting mappings before collecting a new payment.")
    attempts = list((await db.scalars(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.tenant_id == invoice.tenant_id, InvoicePaymentAttempt.invoice_id == invoice.id,
        or_(InvoicePaymentAttempt.confirmed_at.is_not(None),
            InvoicePaymentAttempt.state.in_(["confirmed", "refunded", "reversed"]))))).all())
    for attempt in attempts:
        if not await valid_attempt_authorization(db, attempt):
            deny("historical_payment_balance_review", "Existing historical payments need balance review before a new payment can be collected.")
    payments = list((await db.scalars(select(Payment).where(Payment.tenant_id == invoice.tenant_id,
        Payment.invoice_id == invoice.id, Payment.status == PaymentStatus.COMPLETED))).all())
    authorized = {attempt.id for attempt in attempts}
    links = list((await db.scalars(select(PaymentAccountingLink).where(
        PaymentAccountingLink.tenant_id == invoice.tenant_id,
        PaymentAccountingLink.invoice_id == invoice.id))).all())
    # A clean first receipt cannot adopt an unknown remote balance. Subsequent
    # receipts may use only the accounting lineage authorized by this flow.
    if (not authorized and (invoice.quickbooks_invoice_id or invoice.quickbooks_synced_at
            or invoice.quickbooks_sync_status == "synced")) or any(
            link.attempt_id not in authorized for link in links):
        deny("historical_accounting_balance_review", "Existing QuickBooks accounting history needs balance review before a new payment can be collected.")
    if any(payment.invoice_payment_attempt_id not in authorized for payment in payments):
        deny("historical_payment_balance_review", "Existing historical payments need balance review before a new payment can be collected.")
    settlement = await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id == invoice.id,
        InvoiceSettlement.tenant_id == invoice.tenant_id))
    if settlement:
        from app.services.invoice_settlement_service import invoice_money_snapshot, money
        principal, fee, fee_tax, _, _ = invoice_money_snapshot(invoice)
        if (principal != money(settlement.principal_total)
                or fee != money(settlement.max_card_fee)
                or fee_tax != money(settlement.max_card_fee_tax)
                or settlement.currency != "USD"):
            deny("historical_invoice_snapshot_review", "Invoice amounts differ from the payment snapshot. Review the balance before collecting a new payment.")
    if settlement and settlement.confirmed_principal > sum((attempt.applied_principal_amount for attempt in attempts), 0):
        deny("historical_payment_balance_review", "Existing historical balance needs review before a new payment can be collected.")
    seen, parent_id = {invoice.id}, invoice.supersedes_invoice_id
    while parent_id:
        if parent_id in seen:
            deny("historical_payment_balance_review", "Invoice replacement history requires review.")
        seen.add(parent_id)
        parent = await db.scalar(select(Invoice).where(Invoice.id == parent_id, Invoice.tenant_id == invoice.tenant_id))
        if parent is None:
            deny("historical_payment_balance_review", "Invoice replacement history requires review.")
        from app.services.invoice_accounting_policy import locked_policy
        await locked_policy(db, parent)
        active = await db.scalar(select(InvoicePaymentAttempt.id).where(InvoicePaymentAttempt.invoice_id == parent.id,
            InvoicePaymentAttempt.tenant_id == invoice.tenant_id,
            or_(InvoicePaymentAttempt.state == "pending", InvoicePaymentAttempt.received_amount > 0)).limit(1))
        parent_settlement = await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id == parent.id,
            InvoiceSettlement.tenant_id == invoice.tenant_id))
        pending = await db.scalar(select(InvoicePaymentAttempt.id).where(InvoicePaymentAttempt.invoice_id == parent.id,
            InvoicePaymentAttempt.tenant_id == invoice.tenant_id, InvoicePaymentAttempt.state == "pending").limit(1))
        if pending or parent_settlement and parent_settlement.active_pending_principal > 0:
            deny("previous_invoice_payment_pending", "A previous version of this invoice has a pending payment. Resolve it before collecting another payment.")
        received = await db.scalar(select(Payment.id).where(Payment.invoice_id == parent.id,
            Payment.tenant_id == invoice.tenant_id, Payment.status == PaymentStatus.COMPLETED).limit(1))
        if active or received or parent_settlement and any(getattr(parent_settlement, field) > 0
                for field in ("confirmed_principal", "active_pending_principal", "unapplied_credit", "refund_pending")):
            deny("historical_payment_balance_review", "A replaced invoice has payment activity. Resolve it before collecting a new payment.")
        parent_id = parent.supersedes_invoice_id


def issue_authorization(attempt, config):
    environment = settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT.strip().lower()
    if attempt.source not in LIVE_SOURCES or config.writer_strategy != "dieselbridge" or environment not in {"sandbox", "production"}:
        deny("new_receipt_accounting_unavailable", "Accounting is not ready for a new payment on this invoice.")
    if attempt.provider == "quickbooks_payments" and settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT.strip().lower() != environment:
        deny("new_receipt_environment_mismatch", "Payment and accounting environments do not match.")
    return dict(version="new_receipt_v1", tenant_id=str(attempt.tenant_id), invoice_id=str(attempt.invoice_id),
        attempt_id=str(attempt.id), issued_at=datetime.now(timezone.utc).isoformat(),
        configuration_version=config.version, realm_id=config.qbo_realm_snapshot,
        environment=environment, writer=config.writer_strategy, effective_composition="gross_invoice_v1")


def scoped_invoice(invoice):
    scope = _receipt_scope.get()
    return bool(scope and scope["tenant_id"] == str(invoice.tenant_id)
        and scope["invoice_id"] == str(getattr(invoice, "invoice_id", invoice.id)))


def effective_gross(settlement):
    scope = _receipt_scope.get()
    return (getattr(settlement, "accounting_composition_version", None) == "gross_invoice_v1"
        or bool(scope and str(settlement.tenant_id) == scope["tenant_id"]
            and str(settlement.invoice_id) == scope["invoice_id"] and scope["effective_composition"] == "gross_invoice_v1"))


async def attempt_effective_gross(db, settlement, attempt):
    return effective_gross(settlement) or await valid_attempt_authorization(db, attempt)


def request_environment(connection):
    scope = _receipt_scope.get()
    if scope is None:
        return settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT
    if str(connection.tenant_id) != scope["tenant_id"] or connection.realm_id != scope["realm_id"]:
        from app.services.quickbooks_accounting_service import QuickBooksAccountingError
        raise QuickBooksAccountingError("New receipt accounting connection identity changed")
    return scope["environment"]


def receipt_accounting_operation(function):
    @wraps(function)
    async def wrapped(db, envelope, *args, **kwargs):
        token = _receipt_scope.set(None)
        try:
            from app.services.invoice_accounting_policy import locked_policy, HISTORICAL_HOLD
            if db is not None and getattr(envelope.invoice, "accounting_policy", None) == HISTORICAL_HOLD and await locked_policy(db, envelope.invoice) == HISTORICAL_HOLD:
                from app.services.quickbooks_accounting_service import QuickBooksAccountingError
                if not all(hasattr(envelope, name) for name in ("attempt", "event_id", "link", "connection", "config")):
                    raise QuickBooksAccountingError("Historical accounting remains held; no new receipt envelope")
                attempt = await db.scalar(select(InvoicePaymentAttempt).where(InvoicePaymentAttempt.id == envelope.attempt.id,
                    InvoicePaymentAttempt.tenant_id == envelope.invoice.tenant_id).execution_options(populate_existing=True))
                event = await db.scalar(select(ProviderOutboxEvent).where(ProviderOutboxEvent.id == envelope.event_id,
                    ProviderOutboxEvent.tenant_id == envelope.invoice.tenant_id))
                link = await db.scalar(select(PaymentAccountingLink).where(PaymentAccountingLink.id == envelope.link.id,
                    PaymentAccountingLink.tenant_id == envelope.invoice.tenant_id).execution_options(populate_existing=True))
                lease_end = event.locked_until if event else None
                if lease_end is not None and lease_end.tzinfo is None:
                    lease_end = lease_end.replace(tzinfo=timezone.utc)
                if (not attempt or not await valid_attempt_authorization(db, attempt)
                        or attempt.invoice_id != envelope.invoice.id or attempt.state not in {"confirmed", "refunded", "reversed"}
                        or not event or event.status != "processing" or not event.lock_token or not lease_end or lease_end <= datetime.now(timezone.utc)
                        or (event.payload or {}).get("accounting_link_id") != str(envelope.link.id)
                        or not link or link.attempt_id != attempt.id or link.invoice_id != envelope.invoice.id
                        or link.owning_writer != "dieselbridge"
                        or envelope.config.version != attempt.provider_configuration_version
                        or str(envelope.config.tenant_id) != str(attempt.tenant_id)
                        or link.qbo_realm_snapshot != attempt.new_receipt_accounting_authorization["realm_id"]):
                    raise QuickBooksAccountingError("Historical accounting remains held; this event has no new receipt authorization.")
                _receipt_scope.set(dict(attempt.new_receipt_accounting_authorization))
                request_environment(envelope.connection)
            return await function(db, envelope, *args, **kwargs)
        finally:
            _receipt_scope.reset(token)
    return wrapped
