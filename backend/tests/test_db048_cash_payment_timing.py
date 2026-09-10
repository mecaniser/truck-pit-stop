from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.config import settings
from app.db.models.invoice_settlement import PaymentAccountingLink
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.services import quickbooks_sync_service as sync
from app.services.invoice_cash_service import cash_eligibility
from app.services.invoice_accounting_policy import first_export_awaits_payment, require_exportable_invoice
from app.services.invoice_settlement_service import create_attempt, confirm_attempt, SettlementDomainError, append_ledger_event
from app.services.quickbooks_accounting_service import QuickBooksAccountingError
from tests.test_db048_cash import context, pay


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_status", ["error", "syncing", "synced"])
async def test_deferral_preserves_orphan_export_history(db_session, monkeypatch, prior_status):
    ctx = await context(db_session, monkeypatch)
    ctx[3].quickbooks_sync_status = prior_status
    db_session.add(event(ctx[3], kind="email.notification.v1", status="succeeded"))
    await db_session.flush()
    assert (await cash_eligibility(db_session, ctx[3], ctx[4]))[0]
    assert await sync.enqueue_quickbooks_invoice_sync(db_session, invoice=ctx[3]) is None
    assert ctx[3].cash_export_review_required is True
    with pytest.raises(SettlementDomainError):
        await pay(db_session, ctx)


@pytest.mark.asyncio
async def test_actual_invoice_issuance_and_email_then_cash(db_session, monkeypatch):
    from app.api.v1.endpoints import invoices
    from app.db.models.invoice import InvoiceStatus
    from app.db.models.invoice_settlement import InvoiceSettlement
    from sqlalchemy.orm import selectinload
    from app.db.models.repair_order import RepairOrder
    ctx = await context(db_session, monkeypatch)
    tenant, owner, customer, old_invoice, _ = ctx
    old_invoice.status = InvoiceStatus.CANCELLED
    monkeypatch.setattr(settings, "PROVIDER_OUTBOX_ENABLED", True)
    # Suppress post-commit websocket/SMS delivery only; actual invoice creation
    # and transactional email producer remain real.
    monkeypatch.setattr(invoices, "notify_invoice_created", AsyncMock())
    order = await db_session.scalar(select(RepairOrder).where(RepairOrder.id == old_invoice.repair_order_id)
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle)))
    new_invoice = await invoices.auto_create_invoice_for_order(db_session, order, tenant,
        created_by_user_id=owner.id, notify=True)
    assert new_invoice.quickbooks_sync_status == "awaiting_payment"
    email = await db_session.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.aggregate_id == new_invoice.id,
        ProviderOutboxEvent.event_type == "email.notification.v1"))
    assert email is not None
    snapshot = {column.name: getattr(email, column.name) for column in email.__table__.columns}
    settlement = await db_session.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id == new_invoice.id))
    new_invoice.repair_order = order
    await pay(db_session, (tenant, owner, customer, new_invoice, settlement), version=settlement.version)
    await db_session.flush()
    await db_session.refresh(email)
    assert {column.name: getattr(email, column.name) for column in email.__table__.columns} == snapshot


def event(invoice, *, kind="quickbooks.invoice.sync.v1", attempts=0, status="pending", payload=None):
    return ProviderOutboxEvent(tenant_id=invoice.tenant_id, aggregate_id=invoice.id,
        aggregate_type="invoice", event_type=kind, status=status, attempt_count=attempts,
        available_at=datetime.now(timezone.utc)-timedelta(seconds=1),
        idempotency_key=f"test:{uuid4()}", payload=payload or {})


@pytest.mark.asyncio
@pytest.mark.parametrize("baseline", ["native", "reconciled"])
@pytest.mark.parametrize("email_state", ["pending", "processing", "succeeded"])
async def test_unpaid_issuance_and_email_preserve_full_cash_choice(db_session, monkeypatch, baseline, email_state):
    ctx = await context(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    settlement.legacy_reconciliation_status = baseline
    email = event(invoice, kind="email.notification.v1", status=email_state)
    email.provider_message_id = "email-provider-id"
    db_session.add(email)
    await db_session.flush()
    assert await sync.enqueue_quickbooks_invoice_sync(db_session, invoice=invoice) is None
    assert invoice.quickbooks_sync_status == "awaiting_payment"
    reason, financial_events = await cash_eligibility(db_session, invoice, settlement)
    assert reason is None and financial_events == []
    await pay(db_session, ctx)
    assert email.status == email_state and email.provider_message_id == "email-provider-id"
    assert "suppression_reason" not in email.payload


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["unknown.payment", "unknown.notification", "repair_order.paid"])
async def test_unknown_events_still_block_cash(db_session, monkeypatch, kind):
    ctx = await context(db_session, monkeypatch)
    db_session.add(event(ctx[3], kind=kind))
    await db_session.flush()
    with pytest.raises(SettlementDomainError): await pay(db_session, ctx)


@pytest.mark.asyncio
async def test_reconciled_flag_does_not_override_real_ledger_evidence(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    ctx[4].legacy_reconciliation_status = "reconciled"
    await append_ledger_event(db_session, settlement=ctx[4], event_type="legacy_payment_baseline",
        idempotency_key="ledger", actor=ctx[1])
    await db_session.flush()
    ctx[4].last_event_sequence = 0  # Even a stale/malformed zero counter is not proof.
    with pytest.raises(SettlementDomainError): await pay(db_session, ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("old_attempts", [0, 5])
async def test_worker_defers_before_provider_io_preserves_ambiguity(db_session, monkeypatch, old_attempts):
    ctx = await context(db_session, monkeypatch)
    queued = event(ctx[3], attempts=old_attempts,
                   payload={"cash_export_ambiguous": True} if old_attempts else {})
    db_session.add(queued)
    await db_session.commit()
    async def unexpected(*args, **kwargs): raise AssertionError("Unpaid invoice must not contact provider")
    monkeypatch.setattr(sync, "_refresh_if_needed", unexpected)
    monkeypatch.setattr(sync, "sync_invoice", unexpected)
    monkeypatch.setattr(sync, "sync_db048_principal_invoice", unexpected)
    result = await sync.process_quickbooks_invoice_sync_events(
        session_factory=async_sessionmaker(db_session.bind, expire_on_commit=False), batch_size=1)
    await db_session.refresh(queued)
    await db_session.refresh(ctx[3], ["quickbooks_sync_status"])
    assert result["skipped"] == 1 and queued.status == "deferred"
    assert ctx[3].quickbooks_sync_status == "awaiting_payment"
    if old_attempts:
        assert queued.payload["cash_export_ambiguous"] is True
        with pytest.raises(SettlementDomainError): await pay(db_session, ctx)
    else:
        assert queued.payload["cash_no_dispatch"] is True
        await pay(db_session, ctx)
        assert queued.status == "suppressed"


@pytest.mark.asyncio
async def test_expired_processing_lease_defers_but_never_becomes_cash_safe(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    queued = event(ctx[3], status="processing", attempts=1, payload={"cash_no_dispatch": True})
    queued.lock_token = str(uuid4())
    queued.locked_until = datetime.now(timezone.utc) - timedelta(minutes=30)
    db_session.add(queued)
    await db_session.commit()
    monkeypatch.setattr(sync, "_refresh_if_needed", AsyncMock(side_effect=AssertionError("provider IO")))
    result = await sync.process_quickbooks_invoice_sync_events(
        session_factory=async_sessionmaker(db_session.bind, expire_on_commit=False), batch_size=1)
    await db_session.refresh(queued)
    assert result["skipped"] == 1 and queued.status == "deferred"
    assert queued.payload["cash_export_ambiguous"] is True
    with pytest.raises(SettlementDomainError):
        await pay(db_session, ctx)


@pytest.mark.asyncio
async def test_direct_export_cannot_bypass_unpaid_guard(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    with pytest.raises(QuickBooksAccountingError, match="awaits"):
        await require_exportable_invoice(ctx[3])
    from app.services.quickbooks_accounting_service import sync_invoice
    from app.services.db048_accounting_reconciliation import _ensure_db048_qbo_invoice
    from app.services.db048_qbo_gross_accounting import ensure_gross_invoice
    # Each actual writer must reject before it even inspects the connection.
    with pytest.raises(QuickBooksAccountingError, match="awaits"):
        await sync_invoice(None, ctx[3], ctx[2])
    with pytest.raises(QuickBooksAccountingError, match="awaits"):
        await _ensure_db048_qbo_invoice(connection=None, invoice=ctx[3], customer=ctx[2], principal_total=Decimal("100"))
    with pytest.raises(QuickBooksAccountingError, match="awaits"):
        await ensure_gross_invoice(db_session, connection=None, invoice=ctx[3], customer=ctx[2], settlement=ctx[4])
    pending = await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=Decimal("20"), rail="zelle", expected_settlement_version=ctx[4].version,
        idempotency_key="pending", source="staff", subject_type="staff", subject_id=ctx[1].id)
    assert await first_export_awaits_payment(db_session, ctx[3])
    with pytest.raises(QuickBooksAccountingError, match="awaits"):
        await require_exportable_invoice(ctx[3])
    pending.attempt.state = "failed"
    await db_session.flush()
    assert await first_export_awaits_payment(db_session, ctx[3])


@pytest.mark.asyncio
@pytest.mark.parametrize("later_state", ["refunded", "reversed"])
async def test_later_reversal_does_not_erase_prior_confirmation(db_session, monkeypatch, later_state):
    ctx = await context(db_session, monkeypatch)
    created = await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=Decimal("20"), rail="zelle", expected_settlement_version=ctx[4].version,
        idempotency_key="prior-confirmed", source="staff", subject_type="staff", subject_id=ctx[1].id)
    result = await confirm_attempt(db_session, attempt_id=created.attempt.id, tenant=ctx[0], actor=ctx[1],
        expected_attempt_version=created.attempt.version, idempotency_key="confirm", reference="bank-ref")
    result.attempt.state = later_state
    result.payment.status = PaymentStatus.REFUNDED
    await db_session.flush()
    assert not await first_export_awaits_payment(db_session, ctx[3])
    await require_exportable_invoice(ctx[3])
    with pytest.raises(SettlementDomainError): await pay(db_session, ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("compatibility", ["nonpilot", "global_off", "linked"])
async def test_legacy_export_and_existing_links_remain_supported(db_session, monkeypatch, compatibility):
    ctx = await context(db_session, monkeypatch)
    if compatibility == "nonpilot": ctx[0].invoice_split_payments_enabled = False
    if compatibility == "global_off": monkeypatch.setattr(settings, "INVOICE_SPLIT_PAYMENTS_ENABLED", False)
    if compatibility == "linked": ctx[3].quickbooks_invoice_id = "existing"
    await db_session.flush()
    assert not await first_export_awaits_payment(db_session, ctx[3])
    assert await sync.enqueue_quickbooks_invoice_sync(db_session, invoice=ctx[3]) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("method,status,allowed", [(PaymentMethod.CHECK, PaymentStatus.COMPLETED, True),
    (PaymentMethod.CASH, PaymentStatus.COMPLETED, False), (PaymentMethod.ACH, PaymentStatus.PENDING, False)])
async def test_legacy_noncash_receipt_predicate(db_session, monkeypatch, method, status, allowed):
    ctx = await context(db_session, monkeypatch)
    db_session.add(Payment(tenant_id=ctx[0].id, invoice_id=ctx[3].id, payment_number=f"PAY-{uuid4()}",
        amount=Decimal("20"), method=method, status=status))
    await db_session.flush()
    assert await first_export_awaits_payment(db_session, ctx[3]) is not allowed


@pytest.mark.asyncio
@pytest.mark.parametrize("source,subject", [("staff", "staff"), ("customer_portal", "customer")])
async def test_first_confirmed_partial_exports_full_invoice_and_applied_receipt(db_session, monkeypatch, source, subject):
    from tests import test_db048_invoice_settlements as fixtures
    from tests.test_db048_gross_accounting import provider
    from app.services import db048_accounting_reconciliation as r, db048_qbo_gross_accounting as g
    original_config = fixtures.TenantPaymentProviderConfiguration
    monkeypatch.setattr(fixtures, "TenantPaymentProviderConfiguration", lambda **kwargs: original_config(
        **kwargs, qbo_card_fee_item_id="fee-item", qbo_card_fee_tax_code_id="tax-code"))
    monkeypatch.setattr(settings, "DB048_GROSS_QBO_ACCOUNTING_ENABLED", True)
    ctx = await context(db_session, monkeypatch)
    tenant, owner, customer, invoice, settlement = ctx
    assert await sync.enqueue_quickbooks_invoice_sync(db_session, invoice=invoice) is None
    created = await create_attempt(db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("20"), rail="zelle", expected_settlement_version=settlement.version,
        idempotency_key="partial", source=source, subject_type=subject,
        subject_id=owner.id if subject == "staff" else customer.id)
    assert await first_export_awaits_payment(db_session, invoice)
    result = await confirm_attempt(db_session, attempt_id=created.attempt.id, tenant=tenant, actor=owner,
        expected_attempt_version=created.attempt.version, idempotency_key="confirm-partial", reference="zelle-bank-ref")
    assert not await first_export_awaits_payment(db_session, invoice)
    link = await db_session.scalar(select(PaymentAccountingLink).where(PaymentAccountingLink.attempt_id == created.attempt.id))
    assert link is not None and link.principal_amount_snapshot == Decimal("20")
    queued = await db_session.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.tenant_id == tenant.id,
        ProviderOutboxEvent.aggregate_id == created.attempt.id,
        ProviderOutboxEvent.event_type == r.PAYMENT_ACCOUNTING_EVENT))
    assert queued is not None
    env = await r.load_accounting_envelope(db_session, queued)
    real_lock, real_projection = g._locked_settlement, g._projection
    _, state = provider(monkeypatch, env)
    monkeypatch.setattr(g, "_locked_settlement", real_lock)
    monkeypatch.setattr(g, "_projection", real_projection)
    await r.deliver_accounting_envelope(db_session, env)
    assert state["invoice"]["TotalAmt"] == 100
    assert state["payment"]["TotalAmt"] == 20
    assert state["payment"]["Line"][0]["Amount"] == 20
    assert state["payment"]["Line"][0]["LinkedTxn"][0]["TxnId"] == state["invoice"]["Id"]
