from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import (
    InvoicePaymentAttempt, InvoicePaymentLedgerEvent, InvoiceSettlement,
)
from app.db.models.payment import Payment
from app.db.models.source_debt_handoff import EtsReceiptUpdateTask
from app.schemas.source_debt_handoff import SourceVersionRequest
from app.services import financial_transaction_lock, source_debt_handoff as svc
from app.services.invoice_settlement_service import (
    SettlementDomainError, confirm_attempt, create_attempt, provider_readiness,
)
from test_db149_source_collection import context


async def active_collection(db, monkeypatch):
    tenant, actor, customer, original, proof, body = await context(db, monkeypatch)
    handoff = await svc.prepare(db, tenant.id, actor, body, 'prepare')
    proof['summary'].observed_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    await svc.activate(db, handoff, actor, SourceVersionRequest(
        expected_version=handoff.version,
        expected_source_capture_sha256=proof['digest'],
        expected_source_revision=proof['revision'],
    ), 'activate')
    invoice = await db.get(Invoice, handoff.native_invoice_id)
    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.invoice_id == invoice.id,
    ))
    return tenant, actor, customer, original, proof, handoff, invoice, settlement


async def attempt(db, tenant, actor, customer, invoice, settlement, key, rail='check'):
    # Attempt-only fixture: no provider request or real receipt is made.
    return await create_attempt(
        db, invoice=invoice, tenant=tenant, customer_id=customer.id, actor=actor,
        amount=Decimal('200'), rail=rail,
        expected_settlement_version=settlement.version, idempotency_key=key,
        source='staff_manual', subject_type='staff', subject_id=actor.id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('source_total', ['500.00', '1500.00'])
async def test_total_drift_disables_readiness_and_collection_summary(db_session, monkeypatch, source_total):
    tenant, actor, customer, original, proof, handoff, invoice, settlement = await active_collection(db_session, monkeypatch)
    assert (await provider_readiness(db_session, tenant, invoice_id=invoice.id)).status == 'ready'
    # Valid source arithmetic and unchanged allocation identities; only the
    # source-issued total changes after the handoff's opening snapshot froze.
    proof['summary'].total_amount = Decimal(source_total)
    proof['summary'].recorded_remaining_amount = Decimal(source_total) - Decimal('400')
    readiness = await provider_readiness(db_session, tenant, invoice_id=invoice.id)
    assert readiness.status == 'not_ready'
    assert 'source_invoice_total_changed' in readiness.reasons
    summary = await svc.summary(db_session, handoff)
    assert summary['collection_enabled'] is False
    assert 'source_invoice_total_changed' in summary['payment_hold_reasons']
    assert summary['balance_due'] == '600.00'
    assert original.total_amount == handoff.original_issued_total == Decimal('1000')
    assert invoice.total_amount == settlement.principal_total == Decimal('600')


@pytest.mark.asyncio
@pytest.mark.parametrize('source_total', ['500.00', '1500.00'])
async def test_attempt_rechecks_source_total_after_financial_lock_without_money_writes(db_session, monkeypatch, source_total):
    tenant, actor, customer, original, proof, handoff, invoice, settlement = await active_collection(db_session, monkeypatch)
    # An earlier ready result cannot authorize an attempt after source drift.
    assert (await provider_readiness(db_session, tenant, invoice_id=invoice.id)).status == 'ready'
    sequence = []
    real_lock = financial_transaction_lock.lock_tenant_financials

    async def locked(db, tenant_id):
        await real_lock(db, tenant_id)
        sequence.append('lock')

    async def changed_source(*args, **kwargs):
        assert sequence and sequence[0] == 'lock'
        sequence.append('source')
        proof['summary'].total_amount = Decimal(source_total)
        proof['summary'].recorded_remaining_amount = Decimal(source_total) - Decimal('400')
        return proof

    monkeypatch.setattr(financial_transaction_lock, 'lock_tenant_financials', locked)
    monkeypatch.setattr(svc, 'source_proof', AsyncMock(side_effect=changed_source))
    version = settlement.version
    with pytest.raises(SettlementDomainError) as exc:
        await attempt(db_session, tenant, actor, customer, invoice, settlement, 'drifted-attempt')
    assert exc.value.code == 'source_invoice_total_changed'
    assert sequence[:2] == ['lock', 'source']
    for model in (InvoicePaymentAttempt, Payment, InvoicePaymentLedgerEvent, EtsReceiptUpdateTask):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0
    assert settlement.version == version and settlement.confirmed_principal == 0
    assert original.total_amount == Decimal('1000') and invoice.total_amount == Decimal('600')


@pytest.mark.asyncio
async def test_unacknowledged_native_receipt_preserves_balance_and_attempt_idempotency(db_session, monkeypatch):
    tenant, actor, customer, original, proof, handoff, invoice, settlement = await active_collection(db_session, monkeypatch)
    first = await attempt(db_session, tenant, actor, customer, invoice, settlement, 'first')
    await confirm_attempt(
        db_session, attempt_id=first.attempt.id, tenant=tenant, actor=actor,
        expected_attempt_version=first.attempt.version, idempotency_key='confirm-first',
        received_principal=Decimal('200'), reference='FICTIONAL-200',
    )
    # ETS still says 600 due while DBN has confirmed 200 and its manual ETS
    # update is pending. Compare issued totals, never those unequal balances.
    assert proof['summary'].recorded_remaining_amount == Decimal('600')
    summary = await svc.summary(db_session, handoff)
    assert summary['balance_due'] == '400.00' and summary['collection_enabled'] is True
    assert summary['source_sync_state'] == 'ets_update_pending'
    second = await attempt(db_session, tenant, actor, customer, invoice, settlement, 'second')
    replay = await attempt(db_session, tenant, actor, customer, invoice, settlement, 'second')
    assert replay.attempt.id == second.attempt.id
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentAttempt)) == 2
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 1
    assert await db_session.scalar(select(func.count()).select_from(EtsReceiptUpdateTask)) == 1


@pytest.mark.asyncio
async def test_total_drift_blocks_new_collection_but_retains_verified_provider_receipt(db_session, monkeypatch):
    tenant, actor, customer, original, proof, handoff, invoice, settlement = await active_collection(db_session, monkeypatch)
    pending = await attempt(db_session, tenant, actor, customer, invoice, settlement, 'before-drift', rail='card')
    proof['summary'].total_amount = Decimal('500')
    proof['summary'].recorded_remaining_amount = Decimal('100')
    # Recording a verified outcome for an existing attempt must remain possible
    # even though new collection is now held. Never lose already-received money.
    confirmed = await confirm_attempt(
        db_session, attempt_id=pending.attempt.id, tenant=tenant, actor=None,
        expected_attempt_version=pending.attempt.version, idempotency_key='after-drift',
        provider_charge_id='ch_fictional_source_drift', verified_provider_fact=True,
    )
    assert confirmed.payment.amount == settlement.confirmed_principal == Decimal('200')
    summary = await svc.summary(db_session, handoff)
    assert summary['balance_due'] == '400.00' and summary['collection_enabled'] is False
    assert 'source_invoice_total_changed' in summary['payment_hold_reasons']
    with pytest.raises(SettlementDomainError) as exc:
        await attempt(db_session, tenant, actor, customer, invoice, settlement, 'after-drift-new')
    assert exc.value.code == 'source_invoice_total_changed'
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 1
    assert await db_session.scalar(select(func.count()).select_from(EtsReceiptUpdateTask)) == 1
