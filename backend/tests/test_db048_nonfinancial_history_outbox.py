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
