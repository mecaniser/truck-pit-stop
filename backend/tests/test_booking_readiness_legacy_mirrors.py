"""DB149R: read-only cohort proof; historical mirrors never become checkout."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from hashlib import sha256
import json
from uuid import uuid4
from unittest.mock import AsyncMock,Mock
import pytest
from sqlalchemy import select,func,event
from app.core.config import settings
from app.db.models.invoice import Invoice,InvoiceStatus
from app.db.models.repair_order import RepairOrder,RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.tenant import Tenant
from app.db.models.invoice_settlement import InvoiceSettlement,TenantPaymentProviderConfiguration,InvoicePaymentAttempt,InvoiceSettlementBackfillRun
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.payment import Payment,PaymentStatus,PaymentMethod
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.booking_payment import BookingReceipt,BookingPaymentAttempt
from app.services import booking_payment_provider as provider,invoice_settlement_service as settlement
import test_db048_invoice_settlements as base

ETS='easy_truck_shop_import'

async def context(db,monkeypatch,*,snapshot='not_ready',rail='quickbooks_payments',config_overrides=None):
    def configuration(**kwargs):
        kwargs['readiness_state']=snapshot
        kwargs['selected_provider']=rail
        if rail=='quickbooks_payments':kwargs['provider_account_snapshot']=kwargs['qbo_realm_snapshot']
        kwargs.update(config_overrides or {})
        return TenantPaymentProviderConfiguration(**kwargs)
    monkeypatch.setattr(base,'TenantPaymentProviderConfiguration',configuration)
    tenant,owner,customer,invoice=await base._financial_context(db,monkeypatch)
    await settlement.get_or_create_settlement(db,invoice=invoice,customer_id=customer.id,tenant=tenant)
    connection=await db.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id==tenant.id))
    connection.scopes='com.intuit.quickbooks.accounting com.intuit.quickbooks.payment'
    connection.encrypted_refresh_token='synthetic-no-network'
    connection.access_token_expires_at=datetime.now(timezone.utc)+timedelta(hours=1)
    connection.refresh_token_expires_at=datetime.now(timezone.utc)+timedelta(days=30)
    monkeypatch.setattr(settings,'BOOKING_PAYMENTS_ENABLED',True)
    monkeypatch.setattr(settings,'BOOKING_PAYMENTS_APPROVED_TENANT_IDS','')
    monkeypatch.setattr(settings,'ENVIRONMENT','test')
    monkeypatch.setattr(settings,'QUICKBOOKS_PAYMENTS_ENVIRONMENT','sandbox')
    monkeypatch.setattr(settings,'STRIPE_SECRET_KEY','sk_test_fixture')
    monkeypatch.setattr(settings,'STRIPE_CONNECT_WEBHOOK_SECRET','synthetic-no-network')
    monkeypatch.setattr(provider,'quickbooks_payments_enabled_for_tenant',lambda identity:identity==tenant.id)
    monkeypatch.setattr(settlement,'quickbooks_payments_enabled_for_tenant',lambda identity:identity==tenant.id)
    await db.commit()
    config=await db.scalar(select(TenantPaymentProviderConfiguration).where(TenantPaymentProviderConfiguration.tenant_id==tenant.id))
    return tenant,owner,customer,invoice,config,connection

async def clone_invoice(db,ctx,*,invoice_source=ETS,order_source=ETS,foreign_order=False,status=InvoiceStatus.SENT):
    tenant,_,customer,original,*_=ctx
    order_tenant=tenant
    if foreign_order:
        order_tenant=Tenant(name='Other isolated shop',slug=f'foreign-{uuid4()}');db.add(order_tenant);await db.flush()
        customer=Customer(tenant_id=order_tenant.id,first_name='Other',last_name='Customer',email=f'{uuid4()}@example.test');db.add(customer);await db.flush()
        vehicle=Vehicle(tenant_id=order_tenant.id,customer_id=customer.id,make='Synthetic',model='Other');db.add(vehicle);await db.flush()
        vehicle_id=vehicle.id
    else:vehicle_id=original.repair_order.vehicle_id
    order=RepairOrder(tenant_id=order_tenant.id,customer_id=customer.id,vehicle_id=vehicle_id,source=order_source,order_number=f'COHORT-{uuid4()}',status=RepairOrderStatus.INVOICED,total_parts_cost=0,total_labor_cost=100,total_cost=100)
    db.add(order);await db.flush()
    invoice=Invoice(tenant_id=tenant.id,repair_order_id=order.id,source=invoice_source,invoice_number=f'MIRROR-{uuid4()}',status=status,subtotal=100,total_amount=100,accounting_policy='standard')
    db.add(invoice);await db.commit()
    return invoice,order

async def fingerprint(db):
    connection=await db.connection();proof={}
    for model in (Invoice,RepairOrder,InvoiceSettlement,InvoicePaymentAttempt,Payment,ProviderOutboxEvent,TenantPaymentProviderConfiguration,InvoiceSettlementBackfillRun,BookingReceipt,BookingPaymentAttempt):
        rows=(await connection.execute(select(model.__table__).order_by(model.__table__.c.id))).all()
        proof[model.__tablename__]=sha256(json.dumps([tuple(row) for row in rows],default=str,sort_keys=True).encode()).hexdigest()
    return proof

@pytest.mark.asyncio
@pytest.mark.parametrize('sources,excluded',[((None,None),False),((ETS,None),False),((None,ETS),False),(('native',ETS),False),((ETS,'native'),False),((ETS,ETS),True)])
async def test_only_exact_sql_cohort_excludes_tenant_wide_missing_settlement(db_session,monkeypatch,sources,excluded):
    ctx=await context(db_session,monkeypatch)
    invoice,_=await clone_invoice(db_session,ctx,invoice_source=sources[0],order_source=sources[1])
    before=await fingerprint(db_session)
    readiness=await settlement.provider_readiness(db_session,ctx[0])
    assert ('invoice_settlement_backfill_stale_invoice' not in readiness.reasons)==excluded
    assert readiness.status==('ready' if excluded else 'not_ready')
    assert await fingerprint(db_session)==before
    assert not db_session.new and not db_session.dirty and not db_session.deleted

@pytest.mark.asyncio
async def test_foreign_order_is_not_a_same_tenant_mirror(db_session,monkeypatch):
    ctx=await context(db_session,monkeypatch)
    await clone_invoice(db_session,ctx,foreign_order=True)
    assert 'invoice_settlement_backfill_stale_invoice' in (await settlement.provider_readiness(db_session,ctx[0])).reasons

@pytest.mark.asyncio
@pytest.mark.parametrize('stray_settlement',[False,True])
async def test_direct_raw_mirror_is_explicitly_read_only_even_with_settlement(db_session,monkeypatch,stray_settlement):
    ctx=await context(db_session,monkeypatch);invoice,order=await clone_invoice(db_session,ctx)
    if stray_settlement:
        db_session.add(InvoiceSettlement(tenant_id=ctx[0].id,invoice_id=invoice.id,customer_id=ctx[2].id,principal_total=100));await db_session.commit()
    before=await fingerprint(db_session)
    readiness=await settlement.provider_readiness(db_session,ctx[0],invoice_id=invoice.id)
    assert readiness.status=='not_ready' and 'raw_imported_invoice_read_only' in readiness.reasons
    assert await fingerprint(db_session)==before

@pytest.mark.asyncio
@pytest.mark.parametrize('snapshot,fresh_failure',[('not_ready',False),('ready',True)])
async def test_both_booking_entrypoints_use_current_read_only_proof_not_historical_string(db_session,monkeypatch,snapshot,fresh_failure):
    ctx=await context(db_session,monkeypatch,snapshot=snapshot);tenant,_,_,_,config,_=ctx
    for status in [InvoiceStatus.SENT,InvoiceStatus.PAID,InvoiceStatus.SENT]:await clone_invoice(db_session,ctx,status=status)
    if fresh_failure:await clone_invoice(db_session,ctx,invoice_source=None,order_source=None)
    before=await fingerprint(db_session)
    capability=await provider.booking_provider_capability(db_session,tenant)
    assert capability.available is not fresh_failure
    binding=provider.BookingProviderBinding(config.selected_provider,config.provider_account_snapshot,config.version,'sandbox',tenant.id)
    if fresh_failure:
        with pytest.raises(provider.BookingProviderError):await provider._bound_configuration(db_session,binding,new_charge=True)
    else:assert await provider._bound_configuration(db_session,binding,new_charge=True) is config
    assert config.readiness_state==snapshot
    assert await fingerprint(db_session)==before
    assert not db_session.new and not db_session.dirty and not db_session.deleted

@pytest.mark.asyncio
async def test_pending_unrelated_financial_object_is_never_autoflushed_by_readiness(db_session,monkeypatch):
    ctx=await context(db_session,monkeypatch);tenant,_,_,invoice,config,_=ctx
    pending=Payment(tenant_id=tenant.id,invoice_id=invoice.id,payment_number='UNFLUSHED-SYNTHETIC',amount=1,method=PaymentMethod.CHECK,status=PaymentStatus.COMPLETED)
    db_session.add(pending);db_session.autoflush=True
    calls=[]
    def sql(_connection,_cursor,statement,*args):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):calls.append(statement)
    engine=db_session.bind.sync_engine;event.listen(engine,'before_cursor_execute',sql)
    try:
        assert (await provider.booking_provider_capability(db_session,tenant)).available
        binding=provider.BookingProviderBinding(config.selected_provider,config.provider_account_snapshot,config.version,'sandbox',tenant.id)
        await provider._bound_configuration(db_session,binding,new_charge=True)
        assert not calls and pending in db_session.new
    finally:event.remove(engine,'before_cursor_execute',sql);db_session.autoflush=False

@pytest.mark.asyncio
@pytest.mark.parametrize('defect',['mapping','writer','realm','account','access_expired','refresh_expired','scope','booking_gate','tenant_gate','provider_gate','environment','backfill','unreconciled_payment','zelle'])
async def test_every_current_negative_remains_independently_effective_without_io_or_writes(db_session,monkeypatch,defect):
    overrides={'checking_account':None} if defect=='mapping' else {'writer_strategy':'intuit_native'} if defect=='writer' else {'qbo_realm_snapshot':'wrong-realm'} if defect=='realm' else {'provider_account_snapshot':'wrong-account'} if defect=='account' else {}
    ctx=await context(db_session,monkeypatch,snapshot='ready',config_overrides=overrides)
    tenant,_,_,invoice,config,connection=ctx
    await clone_invoice(db_session,ctx)
    if defect=='access_expired':connection.access_token_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    if defect=='refresh_expired':connection.refresh_token_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    if defect=='scope':connection.scopes='com.intuit.quickbooks.accounting'
    if defect=='booking_gate':monkeypatch.setattr(settings,'BOOKING_PAYMENTS_ENABLED',False)
    if defect=='tenant_gate':tenant.invoice_split_payments_enabled=False
    if defect=='provider_gate':monkeypatch.setattr(provider,'quickbooks_payments_enabled_for_tenant',lambda identity:False)
    if defect=='environment':monkeypatch.setattr(settings,'QUICKBOOKS_PAYMENTS_ENVIRONMENT','production')
    if defect=='backfill':
        run=await db_session.scalar(select(InvoiceSettlementBackfillRun));run.state='failed'
    if defect=='unreconciled_payment':db_session.add(Payment(tenant_id=tenant.id,invoice_id=invoice.id,payment_number=f'UNRECONCILED-{uuid4()}',amount=1,method=PaymentMethod.CHECK,status=PaymentStatus.COMPLETED))
    if defect=='zelle':invoice.zelle_pending_submitted_at=datetime.now(timezone.utc)
    await db_session.commit()
    before=await fingerprint(db_session)
    calls=[]
    for name in ('create_charge','get_charge','refund_charge'):
        spy=AsyncMock(side_effect=AssertionError('No provider IO for readiness'))
        monkeypatch.setattr(provider.qbp,name,spy);calls.append(spy)
    assert not (await provider.booking_provider_capability(db_session,tenant)).available
    binding=provider.BookingProviderBinding(config.selected_provider,config.provider_account_snapshot,config.version,'sandbox',tenant.id)
    with pytest.raises(provider.BookingProviderError):await provider._bound_configuration(db_session,binding,new_charge=True)
    assert await fingerprint(db_session)==before
    assert config.readiness_state=='ready' and not db_session.new and not db_session.dirty and not db_session.deleted
    for spy in calls:spy.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize('defect',['active','deleted','tenant','version','provider','account','environment','connection'])
async def test_stale_cached_authority_or_wrong_bound_identity_never_rebinds(db_session,monkeypatch,defect):
    from dataclasses import replace
    from sqlalchemy import update
    ctx=await context(db_session,monkeypatch);tenant,_,_,_,config,connection=ctx
    binding=provider.BookingProviderBinding(config.selected_provider,config.provider_account_snapshot,config.version,'sandbox',tenant.id)
    if defect=='active':
        await (await db_session.connection()).execute(update(TenantPaymentProviderConfiguration.__table__).where(TenantPaymentProviderConfiguration.id==config.id).values(is_active=False,deactivated_at=datetime.now(timezone.utc)))
        assert config.is_active is True
    elif defect=='deleted':
        await (await db_session.connection()).execute(update(TenantPaymentProviderConfiguration.__table__).where(TenantPaymentProviderConfiguration.id==config.id).values(deleted_at=datetime.now(timezone.utc)))
    elif defect=='connection':
        await (await db_session.connection()).execute(update(QuickBooksConnection.__table__).where(QuickBooksConnection.id==connection.id).values(status='disconnected'))
        assert connection.status=='connected'
    else:
        binding=replace(binding,**{'tenant':{'tenant_id':uuid4()},'version':{'configuration_version':999},'provider':{'provider':'stripe_connect'},'account':{'account_id':'foreign-account'},'environment':{'environment':'production'}}[defect])
    before=await fingerprint(db_session)
    if defect in {'active','deleted','connection'}:assert not (await provider.booking_provider_capability(db_session,tenant)).available
    with pytest.raises(provider.BookingProviderError):await provider._bound_configuration(db_session,binding,new_charge=True)
    assert await fingerprint(db_session)==before

@pytest.mark.asyncio
async def test_old_bound_configuration_recovery_remains_readable_when_admission_disabled(db_session,monkeypatch):
    ctx=await context(db_session,monkeypatch);tenant,_,_,_,config,_=ctx
    binding=provider.BookingProviderBinding(config.selected_provider,config.provider_account_snapshot,config.version,'sandbox',tenant.id)
    config.is_active=False;config.deactivated_at=datetime.now(timezone.utc);await db_session.commit()
    monkeypatch.setattr(settings,'BOOKING_PAYMENTS_ENABLED',False)
    before=await fingerprint(db_session)
    assert await provider._bound_configuration(db_session,binding,new_charge=False) is config
    with pytest.raises(provider.BookingProviderError):await provider._bound_configuration(db_session,binding,new_charge=True)
    assert await fingerprint(db_session)==before

@pytest.mark.asyncio
@pytest.mark.parametrize('defect',['tenant','customer','deleted'])
async def test_native_settlement_must_match_exact_live_tenant_and_payer(db_session,monkeypatch,defect):
    ctx=await context(db_session,monkeypatch);tenant,_,customer,*_=ctx
    invoice,_=await clone_invoice(db_session,ctx,invoice_source=None,order_source=None)
    other_tenant=Tenant(name='Other synthetic shop',slug=f'wrong-{uuid4()}');db_session.add(other_tenant);await db_session.flush()
    other_customer=Customer(tenant_id=tenant.id,first_name='Other',last_name='Payer',email=f'{uuid4()}@example.test');db_session.add(other_customer);await db_session.flush()
    db_session.add(InvoiceSettlement(tenant_id=other_tenant.id if defect=='tenant' else tenant.id,invoice_id=invoice.id,customer_id=other_customer.id if defect=='customer' else customer.id,principal_total=100,deleted_at=datetime.now(timezone.utc) if defect=='deleted' else None));await db_session.commit()
    before=await fingerprint(db_session)
    assert 'invoice_settlement_backfill_stale_invoice' in (await settlement.provider_readiness(db_session,tenant)).reasons
    assert await fingerprint(db_session)==before

@pytest.mark.asyncio
async def test_replaced_active_version_is_not_substituted_for_existing_binding(db_session,monkeypatch):
    ctx=await context(db_session,monkeypatch);tenant,_,_,_,config,_=ctx
    old_binding=provider.BookingProviderBinding(config.selected_provider,config.provider_account_snapshot,config.version,'sandbox',tenant.id)
    values={column.name:getattr(config,column.name) for column in config.__table__.columns if column.name not in {'id','created_at','updated_at','deleted_at'}}
    values.update(version=2,idempotency_key=f'replacement-{uuid4()}',request_hash='2'*64)
    config.is_active=False;config.deactivated_at=datetime.now(timezone.utc);await db_session.flush()
    replacement=TenantPaymentProviderConfiguration(**values);db_session.add(replacement);await db_session.commit()
    before=await fingerprint(db_session)
    current=await provider.booking_provider_capability(db_session,tenant)
    assert current.available and current.binding.configuration_version==2
    with pytest.raises(provider.BookingProviderError):await provider._bound_configuration(db_session,old_binding,new_charge=True)
    assert await provider._bound_configuration(db_session,old_binding,new_charge=False) is config
    assert await fingerprint(db_session)==before and not db_session.dirty
