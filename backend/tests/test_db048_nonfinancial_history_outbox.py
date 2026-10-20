"""Job-history delivery must not masquerade as invoice accounting activity."""
import pytest

from app.services.invoice_accounting_policy import mark_awaiting_payment
from app.services.invoice_cash_service import ancestor_financial_events, cash_eligibility
from app.services import invoice_tax_exemption as tax
from app.services import invoice_charge_adjustments as charges
from tests.test_db048_cash import context, pay
from tests.test_db048_cash_payment_timing import event
from tests.test_db048_tax_exemption import setup


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["job.history_snapshot", "job.history_capture_failed"])
async def test_job_history_keeps_full_cash_available_without_touching_delivery(db_session, monkeypatch, kind):
    ctx = await context(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    invoice.quickbooks_sync_status = "awaiting_payment"
    history = event(invoice, kind=kind,
                    status="succeeded" if kind == "job.history_snapshot" else "dead")
    history.provider_message_id = "source-receipt" if kind == "job.history_snapshot" else None
    db_session.add(history)
    await db_session.flush()

    assert (await cash_eligibility(db_session, invoice, settlement)) == (None, [])
    assert await ancestor_financial_events(db_session, invoice) == []
    before = (history.status, history.provider_message_id, history.payload)
    await pay(db_session, ctx)
    assert (history.status, history.provider_message_id, history.payload) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["job.history_snapshot", "job.history_capture_failed"])
async def test_job_history_does_not_disable_invoice_charge_controls(db_session, monkeypatch, kind):
    ctx = await setup(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    invoice.quickbooks_sync_status = "awaiting_payment"
    history = event(invoice, kind=kind,
                    status="succeeded" if kind == "job.history_snapshot" else "dead")
    history.provider_message_id = "source-receipt" if kind == "job.history_snapshot" else None
    db_session.add(history)
    await db_session.flush()

    assert await tax.eligibility(db_session, invoice, settlement) is None
    controls = await charges.summary(db_session, invoice, settlement, ctx[0], ctx[1], audience="staff")
    assert controls.can_adjust and controls.unavailable_reason is None
    assert (await cash_eligibility(db_session, invoice, settlement)) == (None, [])


@pytest.mark.asyncio
async def test_same_event_type_with_wrong_aggregate_and_unknown_event_still_block(db_session, monkeypatch):
    ctx = await setup(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    for kind, aggregate_type in (("job.history_snapshot", "quickbooks_invoice"),
                                 ("unknown.delivery", "invoice")):
        history = event(invoice, kind=kind, status="succeeded")
        history.aggregate_type = aggregate_type
        db_session.add(history)
        await db_session.flush()
        assert (await cash_eligibility(db_session, invoice, settlement))[0] == (
            "Existing invoice delivery activity requires review before local cash.")
        assert await tax.eligibility(db_session, invoice, settlement) == (
            "Invoice export activity must be resolved before changing tax.")
        await db_session.delete(history)
        await db_session.flush()


@pytest.mark.asyncio
async def test_history_cannot_hide_orphan_quickbooks_status(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    invoice.quickbooks_sync_status = "error"
    db_session.add(event(invoice, kind="job.history_snapshot", status="succeeded"))
    await db_session.flush()

    await mark_awaiting_payment(db_session, invoice)
    assert invoice.cash_export_review_required is True
    assert (await cash_eligibility(db_session, invoice, settlement))[0] == (
        "Previous QuickBooks accounting activity requires review before local cash.")


@pytest.mark.asyncio
async def test_history_does_not_hide_quickbooks_event_on_invoice_or_ancestor(db_session, monkeypatch):
    ctx = await setup(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    history = event(invoice, kind="job.history_snapshot", status="succeeded")
    qbo = event(invoice, kind="quickbooks.invoice.sync.v1", status="succeeded")
    qbo.aggregate_type = "quickbooks_invoice"
    db_session.add_all([history, qbo])
    await db_session.flush()

    assert (await cash_eligibility(db_session, invoice, settlement))[0] == (
        "This invoice already has QuickBooks export history.")
    assert await tax.eligibility(db_session, invoice, settlement) == (
        "Invoice export activity must be resolved before changing tax.")
    assert [row.id for row in await ancestor_financial_events(db_session, invoice)] == [qbo.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["previous export failed", ""])
async def test_retained_orphan_error_blocks_cash_and_charges(db_session, monkeypatch, error):
    from app.services.invoice_settlement_service import SettlementDomainError
    ctx = await setup(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    invoice.quickbooks_sync_status = "awaiting_payment"
    invoice.quickbooks_sync_error = error
    db_session.add(event(invoice, kind="job.history_snapshot", status="succeeded"))
    await db_session.flush()
    assert (await cash_eligibility(db_session, invoice, settlement))[0]
    assert await tax.eligibility(db_session, invoice, settlement)
    assert not (await charges.summary(db_session, invoice, settlement, ctx[0], ctx[1], audience="staff")).can_adjust
    with pytest.raises(SettlementDomainError, match="accounting activity"):
        await pay(db_session, ctx)
    await mark_awaiting_payment(db_session, invoice)
    assert invoice.cash_export_review_required is True


@pytest.mark.asyncio
async def test_cash_confirmation_refreshes_retained_error_after_lock(db_session, monkeypatch):
    from sqlalchemy import update, select, func
    from app.db.models.invoice import Invoice
    from app.db.models.payment import Payment
    from app.services.invoice_settlement_service import SettlementDomainError
    ctx = await context(db_session, monkeypatch)
    invoice = ctx[3]
    invoice.quickbooks_sync_status = "awaiting_payment"
    db_session.add(event(invoice, kind="job.history_snapshot", status="succeeded"))
    await db_session.flush()
    await db_session.execute(update(Invoice).where(Invoice.id == invoice.id).values(
        quickbooks_sync_error="concurrent retained error").execution_options(synchronize_session=False))
    assert invoice.quickbooks_sync_error is None
    with pytest.raises(SettlementDomainError, match="accounting activity"):
        await pay(db_session, ctx)
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("evidence", ["qbo", "payment"])
async def test_history_only_successor_still_checks_ancestor(db_session, monkeypatch, evidence):
    from tests.test_db048_owner_attested_cash import reviewed_owner_cash
    from app.db.models.invoice import Invoice
    from app.services.invoice_settlement_service import SettlementDomainError
    ctx, parent, _, _, _ = await reviewed_owner_cash(db_session, monkeypatch)
    invoice, settlement = ctx[3:5]
    invoice.accounting_policy = "standard"
    invoice.quickbooks_sync_status = "awaiting_payment"
    # The fixture includes a predecessor with payment history. Remove the
    # current financial event so this exercises the new history-only path.
    for row in await ancestor_financial_events(db_session, invoice):
        await db_session.delete(row)
    parent = await db_session.get(Invoice, invoice.supersedes_invoice_id)
    if evidence == "qbo":
        parent.quickbooks_invoice_id = "prior-qbo-record"
    db_session.add(event(invoice, kind="job.history_snapshot", status="succeeded"))
    await db_session.flush()
    assert (await cash_eligibility(db_session, invoice, settlement))[0]
    with pytest.raises(SettlementDomainError):
        await pay(db_session, ctx[:5])


@pytest.mark.asyncio
@pytest.mark.parametrize("evidence", ["history_only", "qbo_link", "qbo_event", "unknown_event", "error", "empty_error", "status"])
async def test_history_only_successor_checks_isolated_parent_evidence(db_session, monkeypatch, evidence):
    from app.db.models.invoice import Invoice, InvoiceStatus
    from app.services.invoice_settlement_service import SettlementDomainError
    ctx = await setup(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    invoice.quickbooks_sync_status = "awaiting_payment"
    parent = Invoice(tenant_id=invoice.tenant_id, repair_order_id=invoice.repair_order_id,
        invoice_number="CANCELLED-PARENT", subtotal=invoice.subtotal,
        total_amount=invoice.total_amount, status=InvoiceStatus.CANCELLED,
        quickbooks_sync_status="awaiting_payment")
    db_session.add(parent)
    await db_session.flush()
    invoice.supersedes_invoice_id = parent.id
    db_session.add_all([event(invoice, kind="job.history_snapshot", status="succeeded"),
                       event(parent, kind="job.history_snapshot", status="succeeded")])
    if evidence == "qbo_link":
        parent.quickbooks_invoice_id = "prior-qbo-record"
    elif evidence in {"qbo_event", "unknown_event"}:
        db_session.add(event(parent, kind="quickbooks.invoice.sync.v1" if evidence == "qbo_event" else "unknown.delivery",
                             status="succeeded"))
    elif evidence in {"error", "empty_error"}:
        parent.quickbooks_sync_error = "retained prior failure" if evidence == "error" else ""
    elif evidence == "status":
        parent.quickbooks_sync_status = "error"
    await db_session.flush()
    cash_reason = (await cash_eligibility(db_session, invoice, settlement))[0]
    tax_reason = await tax.eligibility(db_session, invoice, settlement)
    if evidence == "history_only":
        assert cash_reason is None and tax_reason is None
        await pay(db_session, ctx)
    else:
        assert cash_reason and tax_reason
        with pytest.raises(SettlementDomainError):
            await pay(db_session, ctx)
