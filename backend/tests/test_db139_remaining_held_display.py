"""Explicit source-confirmed display variants; no financial mutation or generic relaxation."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentStatus, PaymentMethod
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.services import imported_billing as billing
from app.services.ets_source_evidence import _digest
from test_db139_retired_invoice_display import retired_fixture


def refresh(envelope):
    envelope['observations'][0]['sha256'] = _digest(envelope['observations'][0]['evidence'])


async def variant(db, monkeypatch, kind):
    orders, inv, copy, payment, env = await retired_fixture(db, monkeypatch)
    facts = env['observations'][0]['evidence']
    extra = None
    if kind == 'unapplied':
        facts['payment_lines'][0]['payment']['total']['amount'] = '600.00'
        facts['payment_lines'][0]['payment']['unapplied_amount']['amount'] = '65.59'
        refresh(env)
    elif kind == 'source_total':
        inv.total_amount = copy.total_amount = Decimal('550.00')
    elif kind == 'same_owner':
        copy.repair_order_id = inv.repair_order_id
        copy.invoice_number = inv.invoice_number + '-' + orders[0].order_number
        inv.created_at = datetime.now(timezone.utc)
        copy.created_at = inv.created_at - timedelta(days=2)
        copy.deleted_at = copy.updated_at = inv.created_at - timedelta(days=1)
        payment.deleted_at = payment.updated_at = copy.deleted_at
    elif kind == 'fallback':
        copy.invoice_number = 'ETSINV-7001-' + orders[1].order_number
    elif kind == 'reconciled_payment':
        now = datetime.now(timezone.utc)
        extra = Payment(id=uuid4(), tenant_id=inv.tenant_id, invoice_id=inv.id,
            payment_number='ETSPAY-7001-0', source=billing.SOURCE, amount=Decimal('534.41'),
            method=PaymentMethod.OTHER, status=PaymentStatus.FAILED,
            notes=' [retired: no matching payment in Easy Truck Shop]', deleted_at=now, updated_at=now)
        db.add(extra)
    await db.flush()
    copy.updated_at = copy.deleted_at
    payment.updated_at = payment.deleted_at
    await db.flush()
    return orders, inv, copy, payment, env, extra


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['unapplied','source_total','same_owner','fallback','reconciled_payment'])
async def test_source_confirmed_display_variants(db_session, monkeypatch, kind):
    orders, inv, copy, payment, env, extra = await variant(db_session, monkeypatch, kind)
    before = (inv.total_amount, inv.status, copy.total_amount, copy.status, copy.deleted_at,
              payment.amount, payment.status, payment.deleted_at)
    statements=[]
    def record(_conn,_cursor,statement,*_): statements.append(statement)
    event.listen(db_session.bind.sync_engine,'before_cursor_execute',record)
    try:
        result = await billing.load_imported_billing(db_session, orders[2])
    finally:
        event.remove(db_session.bind.sync_engine,'before_cursor_execute',record)
    assert len(statements) <= 7 and all(sql.lstrip().startswith('SELECT') for sql in statements)
    assert before == (inv.total_amount, inv.status, copy.total_amount, copy.status, copy.deleted_at,
                      payment.amount, payment.status, payment.deleted_at)
    assert result.payment_status == 'paid'
    assert result.total_amount == Decimal('534.41') and result.recorded_remaining_amount == 0
    assert result.recorded_completed_amount == Decimal('534.41') and result.invoice_id == inv.id
    if kind == 'source_total': assert 'imported_financial_rows_differ' in result.review_reasons
    assert billing.supported_invoice([inv,copy])[1] == 'deleted_invoice_evidence'
    if kind == 'unapplied':
        strict = billing.summarize_imported_billing([inv], [], env, order=orders[0], shop_id='shop1')
        assert strict.payment_status == 'unverified' and 'unsupported_payment_state' in strict.review_reasons
    if extra:
        assert extra.status == PaymentStatus.FAILED and extra.deleted_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['unapplied_over_parent','unapplied_credit','unapplied_cancelled','unapplied_partial',
    'unapplied_negative','unapplied_stale','same_owner_no_chronology','same_owner_revision','fallback_conflict',
    'fallback_wrong_service','source_total_copy_diff','reconcile_wrong_marker','reconcile_live','reconcile_provider',
    'reconcile_negative','reconcile_amount_mismatch','reconcile_reference','reconcile_ledger_reference'])
async def test_variant_uncertainty_keeps_hold(db_session, monkeypatch, case):
    kind = ('unapplied' if case.startswith('unapplied') else 'same_owner' if case.startswith('same_owner')
            else 'fallback' if case.startswith('fallback') else 'source_total' if case.startswith('source_total')
            else 'reconciled_payment')
    orders, inv, copy, payment, env, extra = await variant(db_session, monkeypatch, kind)
    facts=env['observations'][0]['evidence'];parent=facts['payment_lines'][0]['payment']
    if case == 'unapplied_over_parent': parent['unapplied_amount']['amount']='100.00'
    elif case == 'unapplied_credit': parent['credit_total']['amount']='1.00'
    elif case == 'unapplied_cancelled': parent['canceled']=True
    elif case == 'unapplied_partial':
        facts['invoice_status']='5';facts['balance']['amount']='34.41';facts['payment_lines'][0]['amount']['amount']='500.00'
    elif case == 'unapplied_negative': parent['unapplied_amount']['amount']='-1.00'
    elif case == 'unapplied_stale': facts['observed_at_source']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    elif case == 'same_owner_no_chronology': inv.created_at=copy.created_at
    elif case == 'same_owner_revision': inv.supersedes_invoice_id=copy.id
    elif case == 'fallback_wrong_service': copy.invoice_number='ETSINV-7002-'+orders[1].order_number
    elif case == 'fallback_conflict':
        other = RepairOrder(id=uuid4(),tenant_id=inv.tenant_id,customer_id=orders[0].customer_id,
            vehicle_id=orders[0].vehicle_id,order_number='ETS-9999-8002',source=billing.SOURCE,
            status=RepairOrderStatus.COMPLETED)
        db_session.add_all([other,Invoice(id=uuid4(),tenant_id=inv.tenant_id,repair_order_id=other.id,
            invoice_number='ETSINV-7001',source=None,status=InvoiceStatus.PAID,subtotal=1,tax_amount=0,total_amount=1)])
    elif case == 'source_total_copy_diff': copy.total_amount+=1
    elif case == 'reconcile_wrong_marker': extra.notes='Customer refunded'
    elif case == 'reconcile_live': extra.deleted_at=None
    elif case == 'reconcile_provider': extra.quickbooks_refund_id='refund'
    elif case == 'reconcile_negative': extra.amount=Decimal('-534.41')
    elif case == 'reconcile_amount_mismatch':
        live=(await db_session.scalars(select(Payment).where(Payment.invoice_id==inv.id,Payment.deleted_at.is_(None)))).one()
        live.amount=Decimal('500.00')
    elif case == 'reconcile_reference':
        from app.db.models.invoice_settlement import PaymentAccountingLink
        db_session.add(PaymentAccountingLink(id=uuid4(),tenant_id=inv.tenant_id,invoice_id=None,
            financial_object_type='payment',financial_object_id=extra.id,owning_writer='dieselbridge'))
    elif case == 'reconcile_ledger_reference':
        from app.db.models.invoice_settlement import InvoiceSettlement, InvoicePaymentLedgerEvent
        settlement = InvoiceSettlement(id=uuid4(),tenant_id=inv.tenant_id,invoice_id=inv.id,
            customer_id=orders[0].customer_id,principal_total=inv.total_amount)
        db_session.add(settlement);await db_session.flush()
        db_session.add(InvoicePaymentLedgerEvent(id=uuid4(),tenant_id=inv.tenant_id,invoice_id=inv.id,
            settlement_id=settlement.id,customer_id=orders[0].customer_id,actor_name_snapshot='Fixture',
            sequence=1,idempotency_key='fixture-ledger',event_type='legacy_payment_baseline',
            evidence_snapshot={'legacy_payment_id':str(extra.id)}))
    refresh(env)
    await db_session.flush()
    result=await billing.load_imported_billing(db_session,orders[2])
    assert result.total_amount is None and result.payment_status=='unverified'


@pytest.mark.asyncio
async def test_fallback_foreign_root_cannot_block_or_supply_context(db_session, monkeypatch):
    orders, inv, copy, retired_payment, envelope, extra = await variant(db_session, monkeypatch, 'fallback')
    other = RepairOrder(id=uuid4(),tenant_id=uuid4(),customer_id=orders[0].customer_id,
        vehicle_id=orders[0].vehicle_id,order_number='ETS-9999-8002',source=billing.SOURCE,
        status=RepairOrderStatus.COMPLETED)
    db_session.add_all([other,Invoice(id=uuid4(),tenant_id=other.tenant_id,repair_order_id=other.id,
        invoice_number='ETSINV-7001',source=None,status=InvoiceStatus.PAID,subtotal=1,tax_amount=0,total_amount=1)])
    await db_session.flush()
    assert billing._retired_display_candidate([inv,copy],orders) is inv, (copy.deleted_at,copy.updated_at,copy.invoice_number)
    result=await billing.load_imported_billing(db_session,orders[2])
    assert result.payment_status=='paid' and result.invoice_id==inv.id, result.model_dump()
