from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.config import settings
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import (
    InvoicePaymentAttempt,
    InvoicePaymentLedgerEvent,
    PaymentAccountingLink,
    TenantPaymentProviderConfiguration,
)
from app.db.models.payment import Payment
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.user import UserRole
from app.services import invoice_cash_service as cash
from app.services.invoice_settlement_service import (
    append_ledger_event,
    create_attempt,
    fail_attempt,
    get_or_create_settlement,
    load_active_configuration,
)
from app.services.invoice_test_attempt_review import reviewed_test_ancestor
from sqlalchemy import select, update
from tests.test_db048_cash import pay
from tests.test_db048_invoice_settlements import _financial_context

MARKER = {
    'schema': 'owner-attested-test-reservation-release-v1',
    'failure_code': 'owner_attested_test_attempt',
    'classification': 'owner_attested_test_attempt',
    'operation': 'release_exact_internal_test_reservation',
    'provider_contacted': False, 'provider_verified': False,
    'attestation': 'Owner confirms this was an abandoned test with no provider activity.',
    'evidence_source': 'Synthetic explicit owner instruction',
}


async def reviewed(db, monkeypatch):
    tenant, owner, customer, parent = await _financial_context(db, monkeypatch)
    monkeypatch.setattr(settings, 'QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED', True)
    connection = await db.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id == tenant.id))
    connection.scopes = 'com.intuit.quickbooks.accounting com.intuit.quickbooks.payment'
    previous = await load_active_configuration(db, tenant.id)
    values = {c.name: getattr(previous, c.name) for c in previous.__table__.columns
              if c.name not in {'id', 'created_at', 'updated_at'}}
    previous.is_active = False
    previous.deactivated_at = datetime.now(UTC)
    values.update(version=2, selected_provider='quickbooks_payments', provider_account_snapshot=connection.realm_id,
                  is_active=True, deactivated_at=None, idempotency_key='test-qbo-config', request_hash='q' * 64)
    db.add(TenantPaymentProviderConfiguration(**values))
    await db.flush()
    old_settlement = await get_or_create_settlement(db, invoice=parent, tenant=tenant, customer_id=customer.id)
    creation = await create_attempt(db, invoice=parent, tenant=tenant, customer_id=customer.id, actor=owner,
        amount=Decimal(100), rail='card', expected_settlement_version=old_settlement.version,
        idempotency_key='test-parent-attempt', source='customer_portal', subject_type='customer', subject_id=customer.id)
    attempt = creation.attempt
    await append_ledger_event(db, settlement=old_settlement, attempt=attempt,
        event_type='provider_reconciliation_failed', idempotency_key='test-maintenance', actor=None,
        prior_state=old_settlement.state, new_state=old_settlement.state,
        evidence={'failure_code': 'quickbooks_payment_outcome_unknown', 'provider': 'quickbooks_payments',
                  'provider_account': attempt.provider_account_id, 'provider_intent_id': None})
    await fail_attempt(db, attempt_id=attempt.id, tenant_id=tenant.id, actor=owner,
        expected_attempt_version=attempt.version, failure_code='owner_attested_test_attempt', idempotency_key='test-release')
    terminal = next(row for row in db.new if isinstance(row, InvoicePaymentLedgerEvent))
    terminal.evidence_snapshot = dict(MARKER)
    parent.status = InvoiceStatus.CANCELLED
    parent.voided_at = datetime.now(UTC)
    await db.flush()
    invoice = Invoice(tenant_id=tenant.id, repair_order_id=parent.repair_order_id,
        billed_customer_id=customer.id, invoice_number=f'REPLACEMENT-{uuid4().hex}', status=InvoiceStatus.SENT,
        supersedes_invoice_id=parent.id, subtotal=parent.subtotal, shop_supplies_amount=parent.shop_supplies_amount,
        service_fee_amount=parent.service_fee_amount, tax_amount=parent.tax_amount,
        discount_amount=parent.discount_amount, total_amount=parent.total_amount)
    invoice.repair_order = parent.repair_order
    db.add(invoice)
    await db.flush()
    settlement = await get_or_create_settlement(db, invoice=invoice, tenant=tenant, customer_id=customer.id)
    await db.flush()
    return (tenant, owner, customer, invoice, settlement), parent, attempt, old_settlement, terminal


@pytest.mark.asyncio
async def test_audited_test_ancestry_offers_cash_and_confirmation_preserves_history(db_session, monkeypatch):
    ctx, parent, attempt, old, terminal = await reviewed(db_session, monkeypatch)
    assert await reviewed_test_ancestor(db_session, ctx[3], parent)
    before = [cash.event_history_digest(row) for row in (parent, attempt, old, terminal)]
    provider = AsyncMock(side_effect=AssertionError('No provider call allowed'))
    monkeypatch.setattr('app.services.quickbooks_accounting_service._request', provider)
    reason, _ = await cash.cash_eligibility(db_session, ctx[3], ctx[4])
    assert reason is None
    receipt, _ = await pay(db_session, ctx)
    assert receipt and ctx[3].status == InvoiceStatus.PAID
    assert [cash.event_history_digest(row) for row in (parent, attempt, old, terminal)] == before
    assert parent.status == InvoiceStatus.CANCELLED
    assert len(list((await db_session.scalars(select(Payment))).all())) == 1
    assert not await db_session.scalar(select(PaymentAccountingLink.id))
    provider.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('key,value', [
    ('schema', 'arbitrary'), ('classification', 'ordinary_failure'), ('operation', 'other'),
    ('provider_contacted', 'false'), ('provider_verified', 0), ('attestation', ''), ('evidence_source', None),
])
async def test_untrusted_or_incomplete_marker_does_not_bypass_cash(db_session, monkeypatch, key, value):
    ctx, parent, _, _, terminal = await reviewed(db_session, monkeypatch)
    marker = {**MARKER, key: value}
    await db_session.execute(update(InvoicePaymentLedgerEvent).where(InvoicePaymentLedgerEvent.id == terminal.id)
                             .values(evidence_snapshot=marker).execution_options(synchronize_session=False))
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)
    assert (await cash.cash_eligibility(db_session, ctx[3], ctx[4]))[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [
    ('evidence_snapshot', {'failure_code': 'owner_attested_test_attempt'}),
    ('actor_user_id', None), ('actor_role_snapshot', 'customer'),
    ('attempt_id', None), ('money_snapshot', {'active_pending_principal': '0.00'}),
    ('event_type', 'provider_outcome_unknown'),
])
async def test_failure_code_or_partial_ledger_alone_is_insufficient(db_session, monkeypatch, field, value):
    ctx, parent, _, _, terminal = await reviewed(db_session, monkeypatch)
    await db_session.execute(update(InvoicePaymentLedgerEvent).where(InvoicePaymentLedgerEvent.id == terminal.id)
                             .values(**{field: value}).execution_options(synchronize_session=False))
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [
    ('provider_charge_id', 'unverified-charge'), ('provider_intent_id', 'intent'),
    ('provider_event_id', 'event'), ('provider_reference', 'reference'),
    ('source', 'staff'), ('provider', 'stripe_connect'), ('rail', 'check'), ('state', 'expired'),
    ('deleted_at', datetime.now(UTC)), ('manual_evidence', {'provider_charge_id': 'hidden'}),
])
async def test_attempt_drift_rejects_qualification(db_session, monkeypatch, field, value):
    ctx, parent, attempt, _, _ = await reviewed(db_session, monkeypatch)
    await db_session.execute(update(InvoicePaymentAttempt).where(InvoicePaymentAttempt.id == attempt.id)
                             .values(**{field: value}).execution_options(synchronize_session=False))
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)


@pytest.mark.asyncio
async def test_foreign_parent_and_inactive_actor_cannot_qualify(db_session, monkeypatch):
    ctx, parent, _, _, _ = await reviewed(db_session, monkeypatch)
    from types import SimpleNamespace
    foreign = SimpleNamespace(tenant_id=uuid4(), repair_order_id=parent.repair_order_id)
    assert not await reviewed_test_ancestor(db_session, foreign, parent)
    ctx[1].is_active = False
    await db_session.flush()
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)


@pytest.mark.asyncio
async def test_new_history_after_display_blocks_final_cash_confirmation(db_session, monkeypatch):
    ctx, _parent, attempt, old, _ = await reviewed(db_session, monkeypatch)
    assert (await cash.cash_eligibility(db_session, ctx[3], ctx[4]))[0] is None
    await append_ledger_event(db_session, settlement=old, attempt=attempt, actor=ctx[1],
        event_type='new_audit_activity', idempotency_key='late-history')
    await db_session.flush()
    with pytest.raises(cash.SettlementDomainError, match='payment activity'):
        await pay(db_session, ctx)
    assert not await db_session.scalar(select(Payment.id))


@pytest.mark.asyncio
async def test_accounting_history_is_never_bypassed_by_test_attestation(db_session, monkeypatch):
    ctx, parent, _, _, _ = await reviewed(db_session, monkeypatch)
    parent.quickbooks_invoice_id = 'existing-invoice'
    await db_session.flush()
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)
    assert (await cash.cash_eligibility(db_session, ctx[3], ctx[4]))[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['confirmed_principal', 'active_pending_principal', 'unapplied_credit', 'refund_pending'])
async def test_any_parent_settlement_money_blocks_test_exception(db_session, monkeypatch, field):
    ctx, parent, _, old, _ = await reviewed(db_session, monkeypatch)
    from app.db.models.invoice_settlement import InvoiceSettlement
    await db_session.execute(update(InvoiceSettlement).where(InvoiceSettlement.id == old.id)
                             .values(**{field: Decimal(1)}).execution_options(synchronize_session=False))
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)


@pytest.mark.asyncio
async def test_even_an_unlinked_receipt_on_parent_denies_cash(db_session, monkeypatch):
    ctx, parent, _, _, _ = await reviewed(db_session, monkeypatch)
    from app.db.models.payment import PaymentMethod, PaymentStatus
    db_session.add(Payment(tenant_id=ctx[0].id, invoice_id=parent.id, payment_number='TEST-RECEIPT',
        amount=Decimal(1), method=PaymentMethod.CHECK, status=PaymentStatus.COMPLETED))
    await db_session.flush()
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)


@pytest.mark.asyncio
@pytest.mark.parametrize('defect', ['missing_snapshot', 'wrong_pending', 'hidden_charge', 'nonzero_maintenance', 'sequence_gap'])
async def test_complete_maintenance_ledger_is_checked(db_session, monkeypatch, defect):
    ctx, parent, attempt, _, _ = await reviewed(db_session, monkeypatch)
    middle = (await db_session.scalars(select(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.attempt_id == attempt.id,
        InvoicePaymentLedgerEvent.event_type == 'provider_reconciliation_failed'))).one()
    if defect == 'missing_snapshot':
        values = {'money_snapshot': {}}
    elif defect == 'wrong_pending':
        values = {'money_snapshot': {**middle.money_snapshot, 'active_pending_principal': '0'}}
    elif defect == 'hidden_charge':
        values = {'evidence_snapshot': {**middle.evidence_snapshot, 'provider_charge_id': 'unreviewed'}}
    elif defect == 'nonzero_maintenance':
        values = {'pending_delta': Decimal(1)}
    else:
        values = {'sequence': 7}
    await db_session.execute(update(InvoicePaymentLedgerEvent).where(InvoicePaymentLedgerEvent.id == middle.id)
                             .values(**values).execution_options(synchronize_session=False))
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)


@pytest.mark.asyncio
async def test_another_failed_attempt_requires_its_own_review(db_session, monkeypatch):
    ctx, parent, attempt, _, _ = await reviewed(db_session, monkeypatch)
    values = {c.name: getattr(attempt, c.name) for c in attempt.__table__.columns
              if c.name not in {'id', 'created_at', 'updated_at'}}
    values.update(idempotency_key='second-attempt', request_hash='s' * 64)
    db_session.add(InvoicePaymentAttempt(**values))
    await db_session.flush()
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)


@pytest.mark.asyncio
@pytest.mark.parametrize('defect', ['wrong_billed_customer', 'not_voided', 'deleted_parent', 'foreign_actor', 'unprivileged_actor'])
async def test_parent_and_actor_identity_are_revalidated(db_session, monkeypatch, defect):
    ctx, parent, _, _, terminal = await reviewed(db_session, monkeypatch)
    if defect == 'wrong_billed_customer':
        parent.billed_customer_id = uuid4()
    elif defect == 'not_voided':
        parent.voided_at = None
    elif defect == 'deleted_parent':
        parent.deleted_at = datetime.now(UTC)
    elif defect == 'unprivileged_actor':
        ctx[1].role = UserRole.GARAGE_ADMIN
        ctx[1].permissions = {}
    else:
        foreign = await _financial_context(db_session, monkeypatch)
        await db_session.execute(update(InvoicePaymentLedgerEvent).where(InvoicePaymentLedgerEvent.id == terminal.id)
                                 .values(actor_user_id=foreign[1].id).execution_options(synchronize_session=False))
    await db_session.flush()
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)


@pytest.mark.asyncio
@pytest.mark.parametrize('defect', ['future_failure', 'nested_account', 'terminal_charge', 'creation_charge', 'paid_creation'])
async def test_contradictory_time_or_provider_evidence_fails_closed(db_session, monkeypatch, defect):
    ctx, parent, attempt, _, _terminal = await reviewed(db_session, monkeypatch)
    if defect == 'future_failure':
        await db_session.execute(update(InvoicePaymentAttempt).where(InvoicePaymentAttempt.id == attempt.id)
            .values(failed_at=attempt.failed_at + timedelta(days=20)).execution_options(synchronize_session=False))
    else:
        kind = 'attempt_created' if defect in {'creation_charge', 'paid_creation'} else 'provider_reconciliation_failed' if defect == 'nested_account' else 'payment_failed'
        event = (await db_session.scalars(select(InvoicePaymentLedgerEvent).where(
            InvoicePaymentLedgerEvent.attempt_id == attempt.id, InvoicePaymentLedgerEvent.event_type == kind))).one()
        values = {'new_state': 'paid'} if defect == 'paid_creation' else {'evidence_snapshot': {
            **event.evidence_snapshot,
            **({'provider_account': {'provider_charge_id': 'real-charge'}} if defect == 'nested_account' else {'provider_charge_id': 'real-charge'}),
        }}
        await db_session.execute(update(InvoicePaymentLedgerEvent).where(InvoicePaymentLedgerEvent.id == event.id)
            .values(**values).execution_options(synchronize_session=False))
    assert not await reviewed_test_ancestor(db_session, ctx[3], parent)


@pytest.mark.asyncio
async def test_transaction_start_and_wall_clock_release_times_may_differ(db_session, monkeypatch):
    ctx, parent, attempt, _, terminal = await reviewed(db_session, monkeypatch)
    wall_clock = terminal.occurred_at.replace(tzinfo=UTC) + timedelta(minutes=2)
    await db_session.execute(update(InvoicePaymentAttempt).where(InvoicePaymentAttempt.id == attempt.id)
        .values(failed_at=wall_clock).execution_options(synchronize_session=False))
    assert await reviewed_test_ancestor(db_session, ctx[3], parent)
