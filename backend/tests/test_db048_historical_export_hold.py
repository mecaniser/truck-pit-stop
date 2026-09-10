from datetime import datetime, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest

from app.services.historical_export_hold import make_manifest, apply_manifest, digest
from app.services.invoice_accounting_policy import require_exportable_invoice, require_standard_payment, HISTORICAL_HOLD
from app.services.quickbooks_accounting_service import QuickBooksAccountingError
from app.services.invoice_settlement_service import SettlementDomainError, create_attempt
from app.services.quickbooks_sync_service import enqueue_quickbooks_invoice_sync
from tests.test_db048_cash import context, pay
from tests.test_db048_cash_payment_timing import event


async def manifest(db, ctx):
    return await make_manifest(db, tenant_id=ctx[0].id, invoice_ids=[ctx[3].id],
        cutoff=datetime.now(timezone.utc)+timedelta(seconds=1), reason="Historical records pending individual review")


@pytest.mark.asyncio
async def test_hold_is_metadata_only_and_does_not_launder_history(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    invoice = ctx[3]
    dead = event(invoice, status="dead", attempts=5, payload={"cash_export_ambiguous": True})
    waiting = event(invoice, status="deferred")
    email = event(invoice, kind="email.notification.v1", status="succeeded")
    email.lock_token = "retained-nonfinancial-email-token"
    db_session.add_all([dead, waiting, email])
    await db_session.flush()
    original = {c.name: getattr(invoice, c.name) for c in invoice.__table__.columns if c.name not in {"accounting_policy", "updated_at"}}
    reviewed = await manifest(db_session, ctx)
    assert not reviewed["invoices"][0]["blocked"]
    result = await apply_manifest(db_session, reviewed, expected_sha256=digest(reviewed))
    assert result["held_count"] == 1 and result["provider_calls"] == 0
    assert invoice.accounting_policy == HISTORICAL_HOLD
    assert original == {c: getattr(invoice, c) for c in original}
    assert dead.status == "dead" and dead.attempt_count == 5 and dead.payload == {"cash_export_ambiguous": True}
    assert waiting.status == "suppressed" and waiting.payload["suppression_reason"] == HISTORICAL_HOLD
    assert email.status == "succeeded" and email.lock_token == "retained-nonfinancial-email-token"
    with pytest.raises(SettlementDomainError):
        await pay(db_session, ctx)


@pytest.mark.asyncio
async def test_clean_held_invoice_can_still_pass_original_cash_checks(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    reviewed = await manifest(db_session, ctx)
    await apply_manifest(db_session, reviewed, expected_sha256=digest(reviewed))
    await pay(db_session, ctx)
    assert ctx[3].accounting_policy == "local_cash_only"


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["tenant", "digest", "changed", "linked", "lease", "pending", "cutoff"])
async def test_hold_negative_cases(db_session, monkeypatch, defect):
    ctx = await context(db_session, monkeypatch)
    if defect == "linked": ctx[3].quickbooks_invoice_id = "123"
    if defect == "lease":
        row = event(ctx[3], status="pending"); row.lock_token = "active"
        db_session.add(row)
    if defect == "pending":
        await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
            actor=ctx[1], amount=Decimal("10"), rail="zelle", expected_settlement_version=1,
            idempotency_key="pending", source="staff", subject_type="staff", subject_id=ctx[1].id)
    await db_session.flush()
    reviewed = await manifest(db_session, ctx)
    if defect == "tenant": reviewed["tenant_id"] = str(uuid4())
    if defect == "changed": ctx[3].invoice_number = "changed"; await db_session.flush()
    if defect == "cutoff": reviewed["cutoff"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        await apply_manifest(db_session, reviewed, expected_sha256="wrong" if defect == "digest" else digest(reviewed))
    assert ctx[3].accounting_policy == "standard"


@pytest.mark.asyncio
async def test_hold_blocks_enqueue_provider_boundary_and_new_money(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    ctx[3].accounting_policy = HISTORICAL_HOLD
    await db_session.flush()
    original_status = ctx[3].quickbooks_sync_status
    assert await enqueue_quickbooks_invoice_sync(db_session, invoice=ctx[3]) is None
    assert ctx[3].quickbooks_sync_status == original_status
    with pytest.raises(QuickBooksAccountingError, match="held"):
        await require_exportable_invoice(ctx[3])
    with pytest.raises(SettlementDomainError) as exc:
        await require_standard_payment(db_session, ctx[3])
    assert exc.value.code == HISTORICAL_HOLD
    with pytest.raises(SettlementDomainError):
        await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
            actor=ctx[1], amount=Decimal("10"), rail="card", expected_settlement_version=1,
            idempotency_key="held", source="staff", subject_type="staff", subject_id=ctx[1].id)


@pytest.mark.asyncio
async def test_accounting_dispatch_held_before_any_serializer(db_session, monkeypatch):
    from app.services.db048_accounting_reconciliation import deliver_accounting_envelope
    ctx = await context(db_session, monkeypatch)
    ctx[3].accounting_policy = HISTORICAL_HOLD
    await db_session.flush()
    dispatch = AsyncMock()
    with pytest.raises(QuickBooksAccountingError):
        await deliver_accounting_envelope(db_session, SimpleNamespace(invoice=ctx[3], config=SimpleNamespace(writer_strategy="dieselbridge")), sync_payment_func=dispatch)
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_verified_late_stripe_success_preserved_locally_export_suppressed(db_session, monkeypatch):
    from sqlalchemy import select
    from app.services.invoice_settlement_service import fail_attempt, money
    from app.services.stripe_payment_finalization import finalize_stripe_invoice_payment
    from app.db.models.provider_outbox import ProviderOutboxEvent
    ctx = await context(db_session, monkeypatch)
    tenant, owner, customer, invoice, settlement = ctx
    creation = await create_attempt(db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("40"), rail="card", expected_settlement_version=1,
        idempotency_key="late", source="staff", subject_type="staff", subject_id=owner.id)
    attempt = creation.attempt
    attempt.provider_intent_id = "pi_late_held"
    await fail_attempt(db_session, attempt_id=attempt.id, tenant_id=tenant.id, actor=None,
        expected_attempt_version=attempt.version, failure_code="outcome_unknown",
        idempotency_key="expired", expired=True)
    reviewed = await manifest(db_session, ctx)
    await apply_manifest(db_session, reviewed, expected_sha256=digest(reviewed))
    metadata = {"tenant_id": str(tenant.id), "invoice_id": str(invoice.id), "customer_id": str(customer.id),
        "invoice_payment_attempt_id": str(attempt.id), "provider_configuration_version": str(attempt.provider_configuration_version),
        "stripe_connected_account_id": attempt.provider_account_id,
        "principal_amount": str(money(attempt.principal_amount)), "card_fee_amount": str(money(attempt.card_fee_amount)),
        "card_fee_tax_amount": str(money(attempt.card_fee_tax_amount))}
    await finalize_stripe_invoice_payment(db=db_session, invoice=invoice, order=invoice.repair_order,
        customer=customer, tenant=tenant, vehicle=None, payment_note="verified late provider receipt",
        provider_account_id=attempt.provider_account_id, provider_event_id="evt_late",
        payment_intent={"id": attempt.provider_intent_id, "status": "succeeded", "currency": "usd",
            "amount": int(attempt.provider_charge_amount*100), "amount_received": int(attempt.provider_charge_amount*100),
            "latest_charge": "ch_late", "metadata": metadata})
    assert attempt.state == "confirmed" and settlement.confirmed_principal == Decimal("40")
    assert invoice.accounting_policy == HISTORICAL_HOLD
    accounting = await db_session.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.aggregate_id == attempt.id, ProviderOutboxEvent.event_type == "invoice_payment.accounting_sync"))
    assert accounting.status == "suppressed"
    assert accounting.payload["suppression_reason"] == HISTORICAL_HOLD


@pytest.mark.asyncio
async def test_reissue_cannot_escape_hold(db_session, monkeypatch):
    from fastapi import HTTPException
    from app.api.v1.endpoints.invoices import auto_create_invoice_for_order
    from app.db.models.invoice import InvoiceStatus
    ctx = await context(db_session, monkeypatch)
    ctx[3].accounting_policy = HISTORICAL_HOLD
    ctx[3].status = InvoiceStatus.CANCELLED
    await db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await auto_create_invoice_for_order(db_session, ctx[3].repair_order, ctx[0])
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_worker_suppresses_held_event_without_dispatch(db_session, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import quickbooks_sync_service as sync
    ctx = await context(db_session, monkeypatch)
    ctx[3].accounting_policy = HISTORICAL_HOLD
    row = event(ctx[3])
    db_session.add(row)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    provider = AsyncMock(side_effect=AssertionError("provider call"))
    monkeypatch.setattr(sync, "sync_invoice", provider)
    await sync.process_quickbooks_invoice_sync_events(session_factory=sessions)
    await db_session.refresh(row)
    assert row.status == "suppressed"
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_held_refund_dispatch_is_blocked(db_session, monkeypatch):
    from app.db.models.invoice_settlement import PaymentRefund
    from app.services.db048_accounting_reconciliation import _submit_stripe_refund
    ctx = await context(db_session, monkeypatch)
    creation = await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=Decimal("10"), rail="card", expected_settlement_version=1,
        idempotency_key="refund-source", source="staff", subject_type="staff", subject_id=ctx[1].id)
    creation.attempt.provider_charge_id = "ch_source"
    refund = PaymentRefund(tenant_id=ctx[0].id, invoice_id=ctx[3].id, source_attempt_id=creation.attempt.id,
        amount=Decimal("1"), reason="test", destination_rail="card", mode="automatic", state="pending",
        actor_name_snapshot="Owner", idempotency_key="refund", request_hash="0"*64)
    db_session.add(refund)
    ctx[3].accounting_policy = HISTORICAL_HOLD
    await db_session.flush()
    dispatch = AsyncMock(side_effect=AssertionError("provider call"))
    monkeypatch.setattr("app.services.db048_accounting_reconciliation.stripe.Refund.create", dispatch)
    with pytest.raises(SettlementDomainError) as exc:
        await _submit_stripe_refund(db_session, SimpleNamespace(tenant_id=ctx[0].id,
            payload={"refund_id": str(refund.id), "attempt_id": str(creation.attempt.id)}))
    assert exc.value.code == HISTORICAL_HOLD
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_held_payout_source_blocks_journal_before_provider_io(db_session, monkeypatch):
    from app.services.invoice_settlement_service import confirm_attempt
    from app.services.db048_accounting_reconciliation import reconcile_stripe_payout, _book_stripe_payout_batch
    ctx = await context(db_session, monkeypatch)
    creation = await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=Decimal("10"), rail="card", expected_settlement_version=1,
        idempotency_key="payout-source", source="staff", subject_type="staff", subject_id=ctx[1].id)
    await confirm_attempt(db_session, attempt_id=creation.attempt.id, tenant=ctx[0], actor=None,
        expected_attempt_version=creation.attempt.version, idempotency_key="payout-confirm", provider_charge_id="ch_payout")
    gross = creation.attempt.provider_charge_amount
    batch = await reconcile_stripe_payout(db_session, tenant_id=ctx[0].id,
        provider_account_id=creation.attempt.provider_account_id, payout_id="po_held", net_payout=gross,
        entries=[{"id": "ch_payout", "type": "charge", "amount": str(gross),
            "attempt_id": str(creation.attempt.id), "occurred_at": datetime.now(timezone.utc)}])
    ctx[3].accounting_policy = HISTORICAL_HOLD
    await db_session.flush()
    dispatch = AsyncMock(side_effect=AssertionError("provider call"))
    monkeypatch.setattr("app.services.db048_accounting_reconciliation._request", dispatch)
    with pytest.raises(QuickBooksAccountingError, match="held"):
        await _book_stripe_payout_batch(db_session, batch=batch)
    dispatch.assert_not_awaited()
