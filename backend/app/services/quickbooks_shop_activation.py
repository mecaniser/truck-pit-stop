"""Creation-only shop admission and task-local, realm-bound accounting dispatch."""
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from uuid import UUID
from sqlalchemy import select, exists, and_, or_, inspect, cast, String, func
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import async_object_session
from app.db.models.quickbooks_shop_activation import QuickBooksShopActivation
from app.db.models.invoice import Invoice, InvoiceStatus

_dispatch = ContextVar("qbo_shop_dispatch", default=None)


def accounting_operation(function):
    """No ambient provider environment survives return, error or cancellation."""
    @wraps(function)
    async def wrapped(*args, **kwargs):
        token = _dispatch.set({})
        try:
            return await function(*args, **kwargs)
        finally:
            _dispatch.reset(token)
    return wrapped


def _deny(code, message):
    from app.services.invoice_settlement_service import SettlementDomainError
    raise SettlementDomainError(code, message)


async def load_shop_activation(db, tenant_id, *, lock=False):
    query = select(QuickBooksShopActivation).where(QuickBooksShopActivation.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update(read=True)
    return await db.scalar(query.execution_options(populate_existing=True))


def unmanaged_tenant(tenant_column):
    return ~exists(select(QuickBooksShopActivation.id).where(QuickBooksShopActivation.tenant_id == tenant_column))


def admitted_invoice_predicate(tenant_column, invoice_column):
    """Read-only preselection. The provider boundary repeats full admission."""
    candidate = aliased(Invoice)
    return or_(unmanaged_tenant(tenant_column), exists(select(candidate.id).join(
        QuickBooksShopActivation, and_(QuickBooksShopActivation.id == candidate.qbo_shop_activation_id,
        QuickBooksShopActivation.tenant_id == candidate.tenant_id)).where(
            candidate.id == invoice_column, candidate.tenant_id == tenant_column,
            QuickBooksShopActivation.enabled.is_(True), QuickBooksShopActivation.activated_at.is_not(None),
            candidate.created_at > QuickBooksShopActivation.activated_at,
            candidate.accounting_policy == "standard", candidate.source.is_(None),
            candidate.supersedes_invoice_id.is_(None), candidate.deleted_at.is_(None),
            candidate.voided_at.is_(None), candidate.status != InvoiceStatus.CANCELLED,
        )))


def event_selection_predicate(event):
    from app.db.models.invoice_settlement import InvoicePaymentAttempt, PaymentRefund
    candidate = aliased(Invoice)
    def normalized(value): return func.replace(cast(value, String), "-", "")
    matched = or_(candidate.id == event.aggregate_id,
        normalized(candidate.id) == normalized(event.payload["invoice_id"].as_string()),
        candidate.id.in_(select(InvoicePaymentAttempt.invoice_id).where(
            InvoicePaymentAttempt.tenant_id == event.tenant_id,
            or_(InvoicePaymentAttempt.id == event.aggregate_id,
                normalized(InvoicePaymentAttempt.id) == normalized(event.payload["attempt_id"].as_string())))),
        candidate.id.in_(select(PaymentRefund.invoice_id).where(
            PaymentRefund.tenant_id == event.tenant_id, PaymentRefund.id == event.aggregate_id)))
    return or_(unmanaged_tenant(event.tenant_id), and_(
        event.event_type != "stripe_payout.reconcile",
        exists(select(candidate.id).where(candidate.tenant_id == event.tenant_id, matched,
            admitted_invoice_predicate(candidate.tenant_id, candidate.id)))))


async def require_shop_invoice_admission(db, invoice, *, connection=None, payment=False, payment_provider=None):
    activation = await load_shop_activation(db, invoice.tenant_id)
    if activation is None:
        if getattr(invoice, "qbo_shop_activation_id", None) is not None:
            _deny("quickbooks_activation_missing", "Invoice enrollment has no matching activation.")
        return None
    from app.services.invoice_accounting_policy import locked_policy
    await locked_policy(db, invoice)
    activation = await load_shop_activation(db, invoice.tenant_id, lock=True)
    # Scalar column reload does not expire eagerly-loaded UI relationships.
    await db.refresh(invoice, attribute_names=[c.name for c in Invoice.__table__.columns])
    if not activation.enabled or activation.activated_at is None:
        _deny("quickbooks_shop_disabled", "QuickBooks processing for new invoices has not been activated for this shop.")
    if invoice.qbo_shop_activation_id != activation.id:
        _deny("quickbooks_invoice_not_enrolled", "This invoice was not enrolled when the shop was activated.")
    cutoff = activation.activated_at
    created = invoice.created_at
    if cutoff.tzinfo is None: cutoff = cutoff.replace(tzinfo=timezone.utc)
    if created.tzinfo is None: created = created.replace(tzinfo=timezone.utc)
    if (created <= cutoff or invoice.source is not None or invoice.supersedes_invoice_id is not None
            or invoice.accounting_policy != "standard" or invoice.deleted_at or invoice.voided_at
            or invoice.status == InvoiceStatus.CANCELLED):
        _deny("quickbooks_invoice_lineage_excluded", "Historical, imported or revised invoice lineage requires individual review.")
    from app.db.models.quickbooks_connection import QuickBooksConnection
    from app.db.models.invoice_settlement import InvoiceSettlement, TenantPaymentProviderConfiguration
    current = connection or await db.scalar(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == invoice.tenant_id, QuickBooksConnection.status == "connected",
        QuickBooksConnection.deleted_at.is_(None)))
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == invoice.tenant_id,
        TenantPaymentProviderConfiguration.is_active.is_(True)))
    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == invoice.tenant_id, InvoiceSettlement.invoice_id == invoice.id))
    if (not current or current.tenant_id != activation.tenant_id or current.realm_id != activation.realm_id
            or activation.writer != "dieselbridge" or activation.environment not in {"sandbox", "production"}
            or not config or config.writer_strategy != activation.writer or config.qbo_realm_snapshot != activation.realm_id
            or settlement and settlement.qbo_realm_snapshot and settlement.qbo_realm_snapshot != activation.realm_id):
        _deny("quickbooks_activation_identity_mismatch", "The connected company or accounting writer does not match this activation.")
    if payment and (payment_provider or config.selected_provider) == "quickbooks_payments":
        from app.core.config import settings
        if settings.QUICKBOOKS_PAYMENTS_ENVIRONMENT.strip().lower() != activation.environment:
            _deny("quickbooks_activation_environment_mismatch", "Payment processing environment does not match this shop activation.")
    scope = _dispatch.get()
    if scope is not None:
        scope[(str(activation.tenant_id), activation.realm_id)] = (activation.id, invoice.id, activation.environment)
    return activation


async def enroll_new_invoice(db, invoice):
    """Only call before initial flush in native invoice constructors."""
    state = inspect(invoice)
    if not (state.transient or state.pending):
        _deny("quickbooks_enrollment_creation_only", "Existing invoices cannot be enrolled automatically.")
    activation = await load_shop_activation(db, invoice.tenant_id, lock=True)
    if not activation or not activation.enabled or not activation.activated_at:
        return
    if invoice.source is not None or invoice.supersedes_invoice_id or invoice.accounting_policy not in {None, "standard"}:
        return
    # Server-side creation time, never a client-provided or imported date.
    invoice.created_at = datetime.now(timezone.utc)
    invoice.qbo_shop_activation_id = activation.id


async def request_environment(connection, *, method, resource):
    from app.core.config import settings
    state = inspect(connection, raiseerr=False)
    db = async_object_session(connection) if state is not None else None
    if db is None:
        return settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT.strip().lower()
    activation = await load_shop_activation(db, connection.tenant_id)
    if activation is None:
        return settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT.strip().lower()
    if activation.realm_id != connection.realm_id:
        _deny("quickbooks_activation_identity_mismatch", "Company identity differs from the managed activation.")
    # Settings may still display the connected company's identity while disabled.
    if method.upper() == "GET" and resource == f"companyinfo/{connection.realm_id}":
        return activation.environment
    proof = (_dispatch.get() or {}).get((str(connection.tenant_id), connection.realm_id))
    if not proof or proof[0] != activation.id or not activation.enabled:
        _deny("quickbooks_dispatch_not_admitted", "Accounting operation is not admitted for this managed shop.")
    invoice = await db.scalar(select(Invoice).where(Invoice.id == proof[1], Invoice.tenant_id == connection.tenant_id))
    if invoice is None:
        _deny("quickbooks_dispatch_not_admitted", "Accounting source invoice is unavailable.")
    await require_shop_invoice_admission(db, invoice, connection=connection)
    return activation.environment


async def event_admitted(db, event):
    """Never claim managed legacy/payout/unresolved envelopes by guessing scope."""
    if await load_shop_activation(db, event.tenant_id) is None:
        return True
    from app.db.models.invoice_settlement import InvoicePaymentAttempt, PaymentRefund, PaymentAccountingLink
    ids = set()
    payload = event.payload or {}
    for key in ("invoice_id", "target_invoice_id", "source_invoice_id"):
        if payload.get(key):
            try: ids.add(UUID(str(payload[key])))
            except ValueError: return False
    if event.event_type == "quickbooks.invoice.sync.v1": ids.add(event.aggregate_id)
    for model, key in ((InvoicePaymentAttempt, "attempt_id"), (InvoicePaymentAttempt, "source_attempt_id"), (PaymentRefund, "refund_id"), (PaymentAccountingLink, "accounting_link_id")):
        if payload.get(key):
            try: source_id = UUID(str(payload[key]))
            except ValueError: return False
            source = await db.scalar(select(model).where(model.id == source_id, model.tenant_id == event.tenant_id))
            if not source: return False
            ids.add(source.invoice_id)
    if not ids or "payout" in event.event_type:
        return False
    from app.services.invoice_settlement_service import SettlementDomainError
    for invoice_id in sorted(ids, key=str):
        invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == event.tenant_id))
        if invoice is None: return False
        try:
            await require_shop_invoice_admission(db, invoice)
        except SettlementDomainError:
            return False
    return True
