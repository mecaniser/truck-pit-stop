"""DB132 real locking and durable evidence, only on an explicit disposable DB.

Append-only evidence is deliberately retained; no per-row cleanup weakens its
triggers. The owning local runner may dispose of the entire synthetic database.
"""
import asyncio
import os
from decimal import Decimal as D
from types import SimpleNamespace as NS
from uuid import uuid4, UUID

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.parts_pricing import PartsPricingEvent as Event, PartsPriceMatrixRevision as Revision
from app.api.v1.endpoints import parts_pricing as api, repair_orders as ro
from app.schemas import parts_pricing as s
from app.schemas.repair_order import PartsUsageCreate, PartsUsageUpdate
from app.services.parts_pricing_planner import build_plan
from app.services import parts_pricing as p
from app.services.parts_operations_service import apply_inventory_movement
from test_parts_pricing import BANDS

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def pg():
    raw = os.environ.get('DB132_POSTGRES_TEST_URL')
    if not raw:
        pytest.skip('DB132 isolated PostgreSQL not configured')
    url = make_url(raw)
    if url.host not in {'localhost', '127.0.0.1'} or not (url.database or '').startswith('db132_test'):
        raise RuntimeError('Only a disposable local db132_test database is permitted')
    engine = create_async_engine(raw)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db:
        tenant = Tenant(name='DB132 synthetic', slug='db132-' + uuid4().hex, is_active=True)
        db.add(tenant); await db.flush()
        actor = User(tenant_id=tenant.id, email=uuid4().hex+'@example.invalid', hashed_password='x', first_name='Test', last_name='Owner', role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True)
        customer = Customer(tenant_id=tenant.id, first_name='Test', last_name='Customer', email=uuid4().hex+'@example.invalid')
        db.add_all([actor, customer]); await db.flush()
        vehicle = Vehicle(tenant_id=tenant.id, customer_id=customer.id, make='Test', model='Truck')
        db.add(vehicle); await db.flush()
        order = RepairOrder(tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id, order_number='DB132-'+uuid4().hex[:10], status=RepairOrderStatus.DRAFT, total_parts_cost=0, total_labor_cost=0, total_cost=0)
        part = Inventory(tenant_id=tenant.id, sku='PG-'+uuid4().hex, name='Synthetic filter', cost=D('20'), selling_price=D('45'), stock_quantity=20)
        db.add_all([order,part]); await db.commit()
        a=NS(tenant=tenant,actor=actor,order=order,part=part)
    yield factory, a
    await engine.dispose()


async def make_matrix(db,a):
    return (await api.create_matrix(s.MatrixCreate(name='Rules '+uuid4().hex,bands=BANDS),str(uuid4()),db,a.actor))['matrix']


async def test_immutable_revision_audit_and_physical_usage_deletion(pg):
    factory,a=pg
    async with factory() as db:
        m=await make_matrix(db,a)
        await api.set_default(s.DefaultUpdate(matrix_id=UUID(m['id']),expected_generation=0),str(uuid4()),db,a.actor)
        req=s.ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':a.order.id},'plan':{'kind':'parts_add','lines':[{'client_key':'part','inventory_id':a.part.id,'quantity':'1'}]}})
        plan=await build_plan(db,a.actor,req)
        row=await ro.add_parts_to_repair_order(a.order.id,PartsUsageCreate(inventory_id=a.part.id,quantity=D(1),pricing_preview_fingerprint=plan.response['pricing_preview_fingerprint']),str(uuid4()),db,a.actor)
        event=await db.scalar(select(Event).where(Event.entity_id==row.id))
        original=event.identity_snapshot.copy();event_id=event.id
        for statement,params in [
            ('UPDATE parts_price_matrix_revisions SET name_snapshot=:name WHERE id=:id',{'name':'tamper','id':m['current_revision_id']}),
            ('DELETE FROM parts_price_matrix_revisions WHERE id=:id',{'id':m['current_revision_id']}),
            ('UPDATE parts_pricing_events SET reason=:name WHERE id=:id',{'name':'tamper','id':event_id}),
            ('DELETE FROM parts_pricing_events WHERE id=:id',{'id':event_id}),
            ("UPDATE parts_usage SET pricing_snapshot='{}'::jsonb WHERE id=:id",{'id':row.id}),
        ]:
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(text(statement),params)
        await ro.remove_parts_from_repair_order(a.order.id,row.id,db,a.actor)
        assert await db.get(PartsUsage,row.id) is None
        saved=await db.get(Event,event_id)
        assert saved.identity_snapshot==original
        assert await db.scalar(select(func.count(Event.id)).where(Event.entity_id==row.id,Event.event_type=='part.removed'))==1


async def test_composite_tenant_identity_rejects_foreign_policy_revision(pg):
    factory,a=pg
    async with factory() as db:
        m=await make_matrix(db,a)
        foreign=Tenant(name='Other',slug='db132-'+uuid4().hex,is_active=True)
        db.add(foreign);await db.flush();await db.commit()
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text('INSERT INTO parts_pricing_policies (tenant_id,default_matrix_id,generation) VALUES (:tenant,:matrix,1)'),{'tenant':foreign.id,'matrix':m['id']})
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text('INSERT INTO parts_price_matrix_revisions (id,tenant_id,matrix_id,revision,name_snapshot,bands,created_by) VALUES (:id,:tenant,:matrix,99,\'x\',\'[]\',:actor)'),{'id':uuid4(),'tenant':foreign.id,'matrix':m['id'],'actor':a.actor.id})
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                p.add_event(db,NS(tenant_id=foreign.id,id=a.actor.id),'inventory',a.part.id,'test',inventory_id=a.part.id)
                await db.flush()


async def test_concurrent_matrix_edits_have_one_cas_winner(pg):
    factory,a=pg
    async with factory() as db: m=await make_matrix(db,a)
    async def edit(name):
        async with factory() as db:
            try:
                return await api.update_matrix(UUID(m['id']),s.MatrixUpdate(expected_version=1,name=name,bands=BANDS),str(uuid4()),db,a.actor)
            except HTTPException as exc:
                await db.rollback();return exc
    results=await asyncio.gather(edit('First'),edit('Second'))
    assert sum(isinstance(r,dict) for r in results)==1
    loser=next(r for r in results if isinstance(r,HTTPException))
    assert loser.status_code == 409
    # NOWAIT tenant serialization may reject the loser before it can read CAS.
    # Once the winner commits, the same stale version must still be rejected.
    retry = await edit('Stale retry')
    assert retry.status_code == 409 and retry.detail['code'] == 'matrix_version_conflict'
    async with factory() as db:
        assert await db.scalar(select(func.count(Revision.id)).where(Revision.matrix_id==UUID(m['id'])))==2


async def test_receipt_inventory_lock_changes_wac_then_stale_attach_rolls_back(pg):
    factory,a=pg
    async with factory() as db:
        m=await make_matrix(db,a)
        await api.set_default(s.DefaultUpdate(matrix_id=UUID(m['id']),expected_generation=0),str(uuid4()),db,a.actor)
        req=s.ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':a.order.id},'plan':{'kind':'parts_add','lines':[{'client_key':'part','inventory_id':a.part.id,'quantity':'1'}]}})
        token=(await build_plan(db,a.actor,req)).response['pricing_preview_fingerprint']
    async with factory() as receipt:
        item=await receipt.scalar(select(Inventory).where(Inventory.id==a.part.id).with_for_update())
        old_version = item.pricing_version
        await apply_inventory_movement(receipt, item=item, quantity_delta=1, movement_type='po_receipt', actor=a.actor, wac_after=D('30'), source_type='purchase_order', source_id=uuid4())
        assert item.pricing_version == old_version + 1
        async def attach():
            async with factory() as db:
                try:
                    await ro.add_parts_to_repair_order(a.order.id,PartsUsageCreate(inventory_id=a.part.id,quantity=D(1),pricing_preview_fingerprint=token),str(uuid4()),db,a.actor)
                except HTTPException as exc:
                    await db.rollback();return exc
        task=asyncio.create_task(attach())
        await asyncio.sleep(.1)
        assert not task.done()
        await receipt.commit()
        result=await asyncio.wait_for(task,5)
        assert result.status_code==409 and result.detail['code']=='pricing_preview_changed'
    async with factory() as db:
        assert await db.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id==a.order.id))==0
        item=await db.get(Inventory,a.part.id)
        assert item.stock_quantity==21 and item.cost==30


async def test_concurrent_attachment_retry_has_single_usage_audit_and_stock_effect(pg):
    factory,a=pg
    key=str(uuid4())
    body=PartsUsageCreate(inventory_id=a.part.id,quantity=D(1))
    async def attach():
        async with factory() as db:
            try:
                return await ro.add_parts_to_repair_order(a.order.id,body,key,db,a.actor)
            except HTTPException as exc:
                await db.rollback();return exc
    results=await asyncio.gather(attach(),attach())
    successful=[r for r in results if not isinstance(r,HTTPException)]
    assert successful
    retry=await attach()
    assert not isinstance(retry,HTTPException)
    assert all(r.id==retry.id for r in successful)
    async with factory() as db:
        assert await db.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id==a.order.id))==1
        assert await db.scalar(select(func.count(Event.id)).where(Event.entity_id==retry.id,Event.event_type=='part.attached'))==1
        assert (await db.get(Inventory,a.part.id)).stock_quantity==19


async def test_template_edit_wins_and_stale_service_preview_cannot_attach(pg):
    from app.db.models.service import Service, ServicePart
    from app.services.price_build_service import PriceBuildService
    factory,a=pg
    async with factory() as db:
        svc=Service(tenant_id=a.tenant.id,name='Synthetic service',duration_minutes=60,base_price=0,is_active=True)
        db.add(svc);await db.flush()
        component=ServicePart(tenant_id=a.tenant.id,service_id=svc.id,inventory_id=a.part.id,quantity=D(1))
        db.add(component);await db.commit()
        request=s.ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':a.order.id},'plan':{'kind':'service_apply','service_id':svc.id,'quantity':1}})
        token=(await build_plan(db,a.actor,request)).response['pricing_preview_fingerprint']
    async with factory() as editor:
        await p.lock_tenant_financials(editor,a.tenant.id)
        await editor.scalar(select(Service).where(Service.id==svc.id).with_for_update())
        changed=await editor.get(ServicePart,component.id);changed.quantity=D(2)
        await editor.commit()
    async with factory() as attach:
        with pytest.raises(HTTPException) as conflict:
            await PriceBuildService().add_flat_service_line(attach,a.order,svc.id,actor=a.actor,pricing_preview_fingerprint=token)
        assert conflict.value.status_code==409 and conflict.value.detail['code']=='pricing_preview_changed'
        await attach.rollback()
        assert await attach.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id==a.order.id))==0
        assert (await attach.get(Inventory,a.part.id)).stock_quantity==20


@pytest.mark.parametrize('archive', [False, True], ids=['default-switch','clear-and-archive'])
async def test_policy_change_serializes_with_attachment_and_stale_quote_cannot_write(pg, archive):
    factory,a=pg
    async with factory() as db:
        first=await make_matrix(db,a)
        other=await make_matrix(db,a)
        await api.set_default(s.DefaultUpdate(matrix_id=first['id'],expected_generation=0),str(uuid4()),db,a.actor)
        request=s.ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':a.order.id},'plan':{'kind':'parts_add','lines':[{'client_key':'part','inventory_id':a.part.id,'quantity':'1'}]}})
        token=(await build_plan(db,a.actor,request)).response['pricing_preview_fingerprint']
    async def attach():
        async with factory() as db:
            try:
                return await ro.add_parts_to_repair_order(a.order.id,PartsUsageCreate(inventory_id=a.part.id,quantity=D(1),pricing_preview_fingerprint=token),str(uuid4()),db,a.actor)
            except HTTPException as exc:
                await db.rollback();return exc
    async with factory() as editor:
        await p.lock_tenant_financials(editor,a.tenant.id)
        await p.set_default(editor,a.actor,s.DefaultUpdate(matrix_id=None if archive else other['id'],expected_generation=1))
        if archive:
            await p.write_matrix(editor,a.actor,s.MatrixArchive(expected_version=1),UUID(first['id']),'archive')
        # A concurrent read may see the previous committed policy; the locked
        # mutation must not consume that quote while the switch is pending.
        async with factory() as reader:
            old=(await build_plan(reader,a.actor,request)).response
            assert old['pricing_preview_fingerprint']==token
        racing=await asyncio.wait_for(attach(),5)
        assert isinstance(racing,HTTPException) and racing.status_code==409
        await editor.commit()
    stale=await attach()
    assert isinstance(stale,HTTPException) and stale.status_code==409
    assert stale.detail['code']=='pricing_preview_changed'
    async with factory() as db:
        assert await db.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id==a.order.id))==0
        assert (await db.get(Inventory,a.part.id)).stock_quantity==20
        fresh=await build_plan(db,a.actor,request)
        line=fresh.response['lines'][0]
        assert line['pricing']['origin_source']==('catalog' if archive else 'matrix')


async def test_bundle_component_recreation_retains_then_actual_remove_and_readd_is_new(pg):
    from app.db.models.service import Service, ServicePart
    from app.services.price_build_service import PriceBuildService
    factory,a=pg
    async with factory() as db:
        service=Service(tenant_id=a.tenant.id,name='Identity package',duration_minutes=30,base_price=0,is_active=True)
        db.add(service);await db.flush()
        component=ServicePart(tenant_id=a.tenant.id,service_id=service.id,inventory_id=a.part.id,quantity=D(1))
        db.add(component);await db.commit()
        svc=PriceBuildService()
        result=await svc.add_flat_service_line(db,a.order,service.id,actor=a.actor)
        old=result.order.parts_usage[0]
        identity,snapshot,parent,old_component=old.id,old.pricing_snapshot.copy(),old.source_line_id,component.id
        await db.delete(component);await db.flush()
        replacement=ServicePart(tenant_id=a.tenant.id,service_id=service.id,inventory_id=a.part.id,quantity=D(1))
        db.add(replacement);await db.commit()
        result=await svc.add_flat_service_line(db,a.order,service.id,actor=a.actor)
        retained=result.order.parts_usage[0]
        assert (retained.id,retained.pricing_snapshot,retained.source_line_id,retained.source_component_id)==(identity,snapshot,parent,old_component)
        await db.delete(replacement);await db.commit()
        await svc.add_flat_service_line(db,a.order,service.id,actor=a.actor)
        assert await db.get(PartsUsage,identity) is None
        assert (await db.get(Inventory,a.part.id)).stock_quantity==20
        part=await db.get(Inventory,a.part.id);part.cost=D(30);part.selling_price=D(60);part.pricing_version+=1
        db.add(ServicePart(tenant_id=a.tenant.id,service_id=service.id,inventory_id=a.part.id,quantity=D(1)));await db.commit()
        result=await svc.add_flat_service_line(db,a.order,service.id,actor=a.actor)
        new=result.order.parts_usage[0]
        assert new.id!=identity and new.pricing_snapshot['snapshot_id']!=snapshot['snapshot_id']
        assert new.unit_cost==30 and new.unit_price==60 and new.source_line_id==parent
        assert await db.scalar(select(func.count(Event.id)).where(Event.entity_id==identity,Event.event_type=='part.removed'))==1


async def test_ambiguous_legacy_component_mapping_rejects_without_changes(pg):
    from app.db.models.service import Service, ServicePart
    from app.db.models.labor import Labor, LaborLineType
    factory,a=pg
    async with factory() as db:
        service=Service(tenant_id=a.tenant.id,name='Ambiguous package',duration_minutes=30,base_price=0,is_active=True)
        db.add(service);await db.flush()
        parent=Labor(tenant_id=a.tenant.id,repair_order_id=a.order.id,description='Legacy package',hours=D('.5'),hourly_rate=D(100),total_cost=D(50),line_type=LaborLineType.MANUAL,source_service_id=service.id)
        db.add(parent);await db.flush()
        db.add(ServicePart(tenant_id=a.tenant.id,service_id=service.id,inventory_id=a.part.id,quantity=D(1)))
        for price in (D(40),D(50)):
            db.add(PartsUsage(tenant_id=a.tenant.id,repair_order_id=a.order.id,inventory_id=a.part.id,source_service_id=service.id,source_line_id=parent.id,quantity=D(1),unit_cost=D(20),unit_price=price,list_price=price,total_price=price,stock_reserved_packages=0,stock_shortage_override=False))
        await db.commit()
        req=s.ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':a.order.id},'plan':{'kind':'service_apply','service_id':service.id,'quantity':2}})
        with pytest.raises(HTTPException) as conflict: await build_plan(db,a.actor,req,lock=True)
        assert conflict.value.detail['code']=='bundle_identity_ambiguous'
        await db.rollback()
        assert await db.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id==a.order.id))==2
        assert (await db.get(Inventory,a.part.id)).stock_quantity==20


async def test_late_bundle_failure_rolls_back_labor_usage_audit_stock_and_receipt(pg,monkeypatch):
    from app.db.models.service import Service, ServicePart
    from app.db.models.labor import Labor
    from app.schemas.repair_order import PriceBuildFlatServiceRequest
    from app.services import parts_operations_service
    factory,a=pg
    async with factory() as db:
        service=Service(tenant_id=a.tenant.id,name='Atomic package',duration_minutes=30,base_price=0,is_active=True)
        second=Inventory(tenant_id=a.tenant.id,sku='PG-'+uuid4().hex,name='Second part',cost=D(10),selling_price=D(15),stock_quantity=20)
        db.add_all([service,second]);await db.flush()
        for inventory_id in (a.part.id,second.id): db.add(ServicePart(tenant_id=a.tenant.id,service_id=service.id,inventory_id=inventory_id,quantity=D(1)))
        await db.commit(); service_id,second_id=service.id,second.id
    original=parts_operations_service.apply_inventory_movement
    calls=0
    async def fail_second(*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==2: raise HTTPException(409,'Synthetic second-line failure')
        return await original(*args,**kwargs)
    key=str(uuid4());body=PriceBuildFlatServiceRequest(service_id=service_id)
    monkeypatch.setattr(parts_operations_service,'apply_inventory_movement',fail_second)
    async with factory() as db:
        with pytest.raises(HTTPException) as failed:
            await ro.add_price_build_flat_service(a.order.id,body,key,db,a.actor)
        assert failed.value.status_code==409 and calls==2
        await db.rollback()
    async with factory() as db:
        assert await db.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id==a.order.id))==0
        assert await db.scalar(select(func.count(Labor.id)).where(Labor.repair_order_id==a.order.id))==0
        assert await db.scalar(select(func.count(Event.id)).where(Event.tenant_id==a.tenant.id))==0
        assert (await db.get(Inventory,a.part.id)).stock_quantity==(await db.get(Inventory,second_id)).stock_quantity==20
        monkeypatch.setattr(parts_operations_service,'apply_inventory_movement',original)
        retry=await ro.add_price_build_flat_service(a.order.id,body,key,db,a.actor)
        assert len(retry.parts)==2
        assert (await db.get(Inventory,a.part.id)).stock_quantity==(await db.get(Inventory,second_id)).stock_quantity==19


async def test_service_total_survives_production_no_autoflush_session(pg):
    from app.db.models.service import Service, ServicePart
    from app.schemas.repair_order import PriceBuildFlatServiceRequest
    factory,a=pg
    async with factory() as db:
        tenant=await db.get(Tenant,a.tenant.id);tenant.labor_rate=D('145')
        a.actor.tenant_id=tenant.id
        await db.commit()
        await ro.add_parts_to_repair_order(a.order.id,PartsUsageCreate(inventory_id=a.part.id,quantity=D(3)),None,db,a.actor)
        service=Service(tenant_id=a.tenant.id,name='Quarter hour package',duration_minutes=15,base_price=None,is_active=True)
        second=Inventory(tenant_id=a.tenant.id,sku='PG-'+uuid4().hex,name='Fixed package part',cost=D(20),selling_price=D(59),stock_quantity=20,fixed_sales_price=True)
        db.add_all([service,second]);await db.flush()
        db.add(ServicePart(tenant_id=a.tenant.id,service_id=service.id,inventory_id=second.id,quantity=D(1)));await db.commit()
        req=s.ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':a.order.id},'plan':{'kind':'service_apply','service_id':service.id,'quantity':1}})
        preview=await build_plan(db,a.actor,req)
        expected=D('135')+D('59')+D('36.25')
        assert D(preview.response['totals']['repair_total'])==expected
        result=await ro.add_price_build_flat_service(a.order.id,PriceBuildFlatServiceRequest(service_id=service.id,pricing_preview_fingerprint=preview.response['pricing_preview_fingerprint']),str(uuid4()),db,a.actor)
        assert result.total_cost==expected
        fresh=await db.get(RepairOrder,a.order.id,populate_existing=True)
        assert fresh.total_cost==expected and fresh.total_labor_cost==D('36.25')
