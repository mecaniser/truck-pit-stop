"""DB133 real PostgreSQL locks, tenant FKs and immutable evidence. Disposable only."""
import asyncio
import os
from decimal import Decimal as D
from uuid import uuid4
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select,text,func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.exc import DBAPIError
from app.db.models.customer_pricing import AccountPricingEvent
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder,RepairOrderStatus
from app.services import customer_pricing as account
from app.services.customer_merge_guard import require_removable_pricing_identity
from app.api.v1.endpoints import customer_pricing as api
from app.schemas.customer_pricing import CustomerPricingWrite
from test_customer_pricing import setup,configure,create_order

pytestmark=pytest.mark.asyncio

@pytest_asyncio.fixture
async def pg():
    raw=os.environ.get('DB133_POSTGRES_TEST_URL')
    if not raw:pytest.skip('DB133 disposable PostgreSQL not configured')
    url=make_url(raw)
    if url.host not in {'localhost','127.0.0.1'} or not (url.database or '').startswith('db133_test'):raise RuntimeError('Only disposable local DB133 databases are permitted')
    engine=create_async_engine(raw)
    factory=async_sessionmaker(engine,expire_on_commit=False,autoflush=False)
    from types import SimpleNamespace
    from app.db.models.tenant import Tenant
    from app.db.models.user import User,UserRole
    from app.db.models.vehicle import Vehicle
    async with factory() as db:
        tenant=Tenant(name='DB133 PG synthetic',slug='db133-'+uuid4().hex,labor_rate=D('145'),is_active=True);db.add(tenant);await db.flush()
        actor=User(tenant_id=tenant.id,email=uuid4().hex+'@example.invalid',hashed_password='x',first_name='Synthetic',last_name='Owner',role=UserRole.GARAGE_OWNER,is_active=True,is_verified=True)
        customer=Customer(tenant_id=tenant.id,first_name='Synthetic',last_name='Account',email=uuid4().hex+'@example.invalid');db.add_all([actor,customer]);await db.flush()
        vehicle=Vehicle(tenant_id=tenant.id,customer_id=customer.id,make='Test',model='Truck');db.add(vehicle);await db.flush()
        order=RepairOrder(tenant_id=tenant.id,customer_id=customer.id,vehicle_id=vehicle.id,order_number='DB133-'+uuid4().hex,status=RepairOrderStatus.DRAFT,total_labor_cost=0,total_parts_cost=0,total_cost=0);db.add(order);await db.commit()
        a=SimpleNamespace(tenant=tenant,actor=actor,customer=customer,order=order)
    yield factory,a
    await engine.dispose()

async def test_two_configuration_saves_have_one_winner_and_append_only_evidence(pg):
    factory,a=pg
    async def write(rate):
        async with factory() as db:
            try:return await configure(db,a,rate=rate)
            except HTTPException as exc:await db.rollback();return exc
    results=await asyncio.gather(write('125'),write('135'))
    assert sum(isinstance(r,dict) for r in results)==1
    assert next(r for r in results if isinstance(r,HTTPException)).status_code==409
    async with factory() as db:
        event=await db.scalar(select(AccountPricingEvent).where(AccountPricingEvent.tenant_id==a.tenant.id))
        assert event.new_version==1
        for sql in ['UPDATE account_pricing_events SET reason=\'tamper\' WHERE id=:id','DELETE FROM account_pricing_events WHERE id=:id']:
            with pytest.raises(DBAPIError):
                async with db.begin_nested():await db.execute(text(sql),{'id':event.id})
        assert await db.scalar(select(func.count(AccountPricingEvent.id)).where(AccountPricingEvent.tenant_id==a.tenant.id))==1

@pytest.mark.parametrize('change',['account','shop','matrix'])
async def test_intake_waiting_for_policy_update_cannot_commit_stale_terms(pg,change):
    from app.db.models.tenant import Tenant
    from app.api.v1.endpoints import parts_pricing as parts
    from app.schemas.parts_pricing import MatrixCreate,DefaultUpdate
    from test_parts_pricing import BANDS
    factory,a=pg
    async with factory() as db:preview=await api.intake_preview(a.customer.id,a.order.vehicle_id,None,db,a.actor)
    async with factory() as first:
        await account.pricing.lock_tenant_financials(first,a.tenant.id)
        if change=='account':await account.write_config(first,a.actor,CustomerPricingWrite(expected_version=0,labor_rate='125',parts_matrix_id=None,reason='Concurrent terms'),a.customer.id)
        elif change=='shop':
            tenant=await first.get(Tenant,a.tenant.id);tenant.labor_rate=D('160');await first.flush()
        else:
            from app.services.parts_pricing import write_matrix,set_default
            matrix=await write_matrix(first,a.actor,MatrixCreate(name='Concurrent matrix',bands=BANDS))
            await set_default(first,a.actor,DefaultUpdate(matrix_id=matrix['matrix']['id'],expected_generation=0))
        async with factory() as second:
            with pytest.raises(HTTPException) as exc:await create_order(second,a,expected_pricing_policy=preview['expected_pricing_policy'])
            assert exc.value.status_code==409
            await second.rollback()
        await first.commit()
    async with factory() as db:
        with pytest.raises(HTTPException) as exc:await create_order(db,a,expected_pricing_policy=preview['expected_pricing_policy'])
        assert exc.value.detail['code']=='account_pricing_changed'
        await db.rollback()
        assert await db.scalar(select(func.count(RepairOrder.id)).where(RepairOrder.tenant_id==a.tenant.id))==1

@pytest.mark.parametrize('reference',['policy','order','counter'])
async def test_merge_waits_for_first_account_reference_and_cannot_delete_identity(pg,reference):
    from app.db.models.inventory_lifecycle import CounterSale
    factory,a=pg
    async with factory() as first:
        await account.pricing.lock_tenant_financials(first,a.tenant.id)
        customer=await account.live_customer(first,a.tenant.id,a.customer.id,lock=True)
        if reference=='policy':await account.write_config(first,a.actor,CustomerPricingWrite(expected_version=0,labor_rate='125',parts_matrix_id=None,reason='First agreement'),customer.id)
        else:
            tenant=await first.get(__import__('app.db.models.tenant',fromlist=['Tenant']).Tenant,a.tenant.id)
            snapshot=await account.candidate(first,tenant,customer,counter=reference=='counter')
            if reference=='order':
                row=RepairOrder(tenant_id=a.tenant.id,customer_id=customer.id,vehicle_id=a.order.vehicle_id,order_number='DB133-'+uuid4().hex,status=RepairOrderStatus.DRAFT)
            else:row=CounterSale(tenant_id=a.tenant.id,customer_id=customer.id,sale_number='DB133-'+uuid4().hex,status='draft',created_by_user_id=a.actor.id,updated_by_user_id=a.actor.id)
            account.assign(row,snapshot);first.add(row);await first.flush()
        async def merge_guard():
            async with factory() as second:
                saved=await account.live_customer(second,a.tenant.id,a.customer.id,lock=True)
                try:await require_removable_pricing_identity(second,saved)
                except HTTPException as exc:return exc
                raise AssertionError('Guard allowed deleting referenced customer')
        task=asyncio.create_task(merge_guard());await asyncio.sleep(.03)
        assert not task.done()
        await first.commit()
        exc=await asyncio.wait_for(task,5)
        assert exc.detail['code']=='customer_pricing_merge_locked'

async def test_reverse_pair_customer_locks_are_ordered_without_deadlock(pg):
    factory,a=pg
    async with factory() as db:
        b=Customer(tenant_id=a.tenant.id,first_name='Other',last_name='Synthetic',email=uuid4().hex+'@example.invalid');db.add(b);await db.commit();bid=b.id
    entered=asyncio.Event()
    async def first():
        async with factory() as db:
            await account.lock_customers(db,a.tenant.id,[a.customer.id,bid]);entered.set();await asyncio.sleep(.05);await db.commit()
    async def second():
        await entered.wait()
        async with factory() as db:
            rows=await account.lock_customers(db,a.tenant.id,[bid,a.customer.id]);await db.commit();return rows
    results=await asyncio.wait_for(asyncio.gather(first(),second()),5)
    assert set(results[1])=={a.customer.id,bid}

async def test_concurrent_manual_rate_then_service_reapply_keeps_saved_rate(pg):
    from app.db.models.service import Service
    from app.db.models.labor import Labor
    from app.services.price_build_service import PriceBuildService
    factory,a=pg
    async with factory() as db:
        await configure(db,a);created=await create_order(db,a)
        service=Service(tenant_id=a.tenant.id,name='Rate race',duration_minutes=60,is_active=True);db.add(service);await db.commit();sid=service.id
        svc=PriceBuildService();order=await svc.load_order(db,created.id)
        result=await svc.add_flat_service_line(db,order,sid,actor=a.actor);lid=result.order.labor_items[0].id
    async with factory() as first:
        order=await first.scalar(select(RepairOrder).where(RepairOrder.id==created.id).with_for_update())
        line=await first.get(Labor,lid);before=line.hourly_rate
        line.hourly_rate=D('111');line.total_cost=D('111');line.auto_recalc_enabled=True
        account.observe_rate_change(first,a.actor,order,line,before,line.pricing_source);await first.flush()
        async def reapply():
            async with factory() as db:
                svc=PriceBuildService();saved=await svc.load_order(db,created.id)
                return await svc.add_flat_service_line(db,saved,sid,quantity=2,actor=a.actor)
        task=asyncio.create_task(reapply());await asyncio.sleep(.03);await first.commit()
        result=await asyncio.wait_for(task,5)
        assert result.order.labor_items[0].hourly_rate==111 and result.order.total_labor_cost==222

async def test_saved_policy_and_labor_origin_immutable_and_no_null_replacement(pg):
    from app.api.v1.endpoints import repair_orders as ro
    from app.schemas.repair_order import LaborCreate
    factory,a=pg
    async with factory() as db:
        await configure(db,a);created=await create_order(db,a)
        line=await ro.add_labor_to_repair_order(created.id,LaborCreate(description='Snapshot proof',hours=1),db,a.actor)
        for sql,identity in [("UPDATE repair_orders SET pricing_policy_snapshot=NULL WHERE id=:id",created.id),("UPDATE labor SET pricing_snapshot=NULL WHERE id=:id",line.id)]:
            with pytest.raises(DBAPIError):
                async with db.begin_nested():await db.execute(text(sql),{'id':identity})

async def test_concurrent_known_call_reservation_uses_one_provider_result(pg,monkeypatch):
    from app.services import repair_intake_reference as intake
    from app.db.models.parts_operations import PartsOperationIdempotency
    factory,a=pg;calls=[];reserved=uuid4();opportunity=uuid4()
    async def provider(*args):
        calls.append(True);await asyncio.sleep(.05)
        return intake.IntakeReservation(repair_order_uuid=reserved,elis_opportunity_id=opportunity,callrail_call_id='synthetic-call')
    monkeypatch.setattr(intake,'reserve_originating_call',provider)
    async def attempt():
        async with factory() as db:return await account.reserve_call(db,a.actor,a.customer.id,a.order.vehicle_id,'same-opaque-token')
    results=await asyncio.gather(attempt(),attempt())
    assert len(calls)==1 and all(r.repair_order_uuid==reserved for r in results)
    async with factory() as db:
        receipt=await db.scalar(select(PartsOperationIdempotency).where(PartsOperationIdempotency.tenant_id==a.tenant.id,PartsOperationIdempotency.operation_family=='c1_call_reservation'))
        assert 'same-opaque-token' not in receipt.response_body and receipt.idempotency_key!='same-opaque-token'
