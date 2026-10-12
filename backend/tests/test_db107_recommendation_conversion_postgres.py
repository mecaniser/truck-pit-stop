"""Run only against a separately provisioned disposable PostgreSQL database."""
import asyncio
import os
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models.tenant import Tenant
from app.db.models.repair_order import RepairOrderStatus
from app.db.models.user import User, UserRole
from app.db.models.labor import Labor
from app.db.models.recommendation_conversion import RecommendationConversion
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.schemas.recommendation_conversion import RecommendationConvertRequest
from app.services.recommendation_conversion import convert
from app.services.invoice_settlement_service import SettlementDomainError
from tests.test_db099_recommended_work import customer, vehicle, order, recommendation, actor


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get('DB107_POSTGRES_URL'),reason='requires dedicated migrated PostgreSQL DB107 database')
@pytest.mark.parametrize('scenario',['same_key','two_keys','two_targets'])
async def test_postgres_concurrent_conversion_once(scenario):
    engine=create_async_engine(os.environ['DB107_POSTGRES_URL'])
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with factory() as db:
        tenant=Tenant(name='DB107 Race Shop',slug=f'db107-race-{uuid4().hex}',labor_rate=Decimal('145'))
        db.add(tenant); await db.flush()
        payer=await customer(db,tenant)
        truck=await vehicle(db,tenant,payer)
        source=await order(db,tenant,payer,truck,status=RepairOrderStatus.COMPLETED)
        first=await order(db,tenant,payer,truck,status=RepairOrderStatus.IN_PROGRESS)
        second=await order(db,tenant,payer,truck,status=RepairOrderStatus.IN_PROGRESS)
        rec=await recommendation(db,tenant,source)
        user=await actor(db,tenant,UserRole.GARAGE_ADMIN)
        await db.commit()
        tenant_id,rec_id,user_id,first_id,second_id=tenant.id,rec.id,user.id,first.id,second.id
    request_id=uuid4()
    ready=asyncio.Event()
    async def attempt(index):
        body=RecommendationConvertRequest(request_id=request_id if scenario=='same_key' else uuid4(),hours='1.25',hourly_rate='145')
        target_id=second_id if scenario=='two_targets' and index else first_id
        await ready.wait()
        for _ in range(40):
            async with factory() as db:
                user=await db.get(User,user_id)
                try:
                    result,replayed=await convert(db,target_id=target_id,recommendation_id=rec_id,body=body,user=user)
                    await db.commit()
                    return ('replay' if replayed else 'created',result.id)
                except SettlementDomainError as error:
                    await db.rollback()
                    assert error.code=='invoice_busy'
                except HTTPException as error:
                    await db.rollback()
                    return error.detail['code'],None
            await asyncio.sleep(.025)
        raise AssertionError('financial lock did not become available')
    tasks=[asyncio.create_task(attempt(index)) for index in (0,1)]
    ready.set()
    try:
        results=await asyncio.gather(*tasks)
        assert sorted(r[0] for r in results)==(['already_converted','created'] if scenario=='two_targets' else ['created','replay'])
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(RecommendationConversion).where(RecommendationConversion.tenant_id==tenant_id))==1
            assert await db.scalar(select(func.count()).select_from(Labor).where(Labor.tenant_id==tenant_id))==1
            assert await db.scalar(select(func.count()).select_from(RepairOrderHistoryEvent).where(RepairOrderHistoryEvent.tenant_id==tenant_id,RepairOrderHistoryEvent.event_type=='recommendation_converted'))==1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get('DB107_POSTGRES_URL'),reason='requires dedicated migrated PostgreSQL DB107 database')
@pytest.mark.parametrize('internal',[False,True])
async def test_start_serializes_with_cancellation_and_replacement(internal):
    from app.api.v1.endpoints import fleet, repair_orders
    from app.db.models.repair_order import RepairOrder
    from app.services.financial_transaction_lock import lock_tenant_financials
    engine=create_async_engine(os.environ['DB107_POSTGRES_URL'])
    factory=async_sessionmaker(engine,expire_on_commit=False)
    try:
        async with factory() as db:
            tenant=Tenant(name='DB107 Lifecycle Shop',slug=f'db107-lifecycle-{uuid4().hex}',labor_rate=Decimal('145'))
            db.add(tenant);await db.flush()
            payer=await customer(db,tenant)
            truck=await vehicle(db,tenant,payer)
            if internal:
                from app.db.models.vehicle_relationship import FleetMembership
                db.add(FleetMembership(tenant_id=tenant.id,vehicle_id=truck.id,fleet_customer_id=payer.id))
                await db.flush()
            target=await order(db,tenant,payer,truck,is_internal=internal,is_fleet_work=internal,status=RepairOrderStatus.DRAFT)
            user=await actor(db,tenant,UserRole.GARAGE_ADMIN)
            await db.commit()
            tenant_id,target_id,user_id=tenant.id,target.id,user.id
        async with factory() as cancellation:
            await lock_tenant_financials(cancellation,tenant_id)
            target=await cancellation.get(RepairOrder,target_id)
            target.status=RepairOrderStatus.CANCELLED
            await cancellation.flush()
            async with factory() as start:
                user=await start.get(User,user_id)
                with pytest.raises(SettlementDomainError) as blocked:
                    if internal:
                        await fleet.start_work_order(target_id,db=start,current_user=user)
                    else:
                        await repair_orders.override_start_work_without_mechanic(target_id,db=start,current_user=user)
                assert blocked.value.code=='invoice_busy'
                await start.rollback()
            await cancellation.commit()
        async with factory() as start:
            user=await start.get(User,user_id)
            with pytest.raises(HTTPException) as refused:
                if internal:
                    await fleet.start_work_order(target_id,db=start,current_user=user)
                else:
                    await repair_orders.override_start_work_without_mechanic(target_id,db=start,current_user=user)
            assert refused.value.status_code==400
            await start.rollback()
        async with factory() as check:
            assert (await check.get(RepairOrder,target_id)).status==RepairOrderStatus.CANCELLED
    finally:
        await engine.dispose()
