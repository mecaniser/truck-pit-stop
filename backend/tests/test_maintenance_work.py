from decimal import Decimal
from uuid import UUID, uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor
from app.db.models.service import ServicePart
from app.db.models.service_checklist import RepairOrderChecklistItem as Task
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.maintenance import MaintenanceWorkLink as Link, MaintenanceOperationLink as Mapping
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas import maintenance as wire
from app.services import maintenance as service
from test_service_checklists import seed
from test_maintenance_programs import create, config


@pytest.fixture
def db_session(db_session):
    db_session.autoflush = False
    return db_session


async def setup(db, *, channel='shop', existing=False):
    a = await seed(db)
    a.order.status = RepairOrderStatus.DRAFT
    if channel == 'fleet':
        db.add(FleetMembership(tenant_id=a.tenant.id, vehicle_id=a.vehicle.id, fleet_customer_id=a.customer.id))
    item = Inventory(id=uuid4(), tenant_id=a.tenant.id, sku='M1-' + uuid4().hex, name='Actual part', cost=Decimal(5), selling_price=Decimal(10), stock_quantity=10)
    db.add(item)
    await db.flush()
    db.add(ServicePart(id=uuid4(), tenant_id=a.tenant.id, service_id=a.service.id, inventory_id=item.id, quantity=2))
    await db.commit()
    refs = []
    for name in ['Oil', 'Inspection']:
        result, _ = await create(db, a, cfg=config(a, name=name), channel=channel)
        refs.append({'program_id': result['program']['id'], 'expected_version': result['program']['version']})
    target = {'kind': 'existing', 'repair_order_id': str(a.order.id)} if existing else {'kind': 'new', 'bill_to_customer_id': str(a.customer.id), 'description': 'Shared maintenance'}
    body = wire.WorkRequest.model_validate({'channel': channel, 'programs': refs, 'target': target,
        'coverage': [{'key': 'shared', 'program_ids': [r['program_id'] for r in refs], 'service_id': str(a.service.id), 'operation': {'kind': 'new'}}]})
    return a, item, body


@pytest.mark.asyncio
async def test_shared_work_once_and_receipt_preserves_identity(db_session):
    a, item, body = await setup(db_session)
    preview = await service.work_preview(db_session, a.owner, a.vehicle.id, body)
    assert preview['totals']['repair_total'] == '120.00'
    assert len(preview['coverage']) == 1 and preview['coverage'][0]['checklist_items'] == 3
    request = wire.WorkCommit.model_validate({**body.model_dump(mode='json'), 'expected_work_fingerprint': preview['expected_work_fingerprint']})
    key = str(uuid4())
    result = await service.work_command(db_session, a.owner, a.vehicle.id, request, key)
    repeat = await service.work_command(db_session, a.owner, a.vehicle.id, request, key)
    assert result['created'] and repeat['replayed'] and repeat['repair_order_id'] == result['repair_order_id']
    identity = UUID(result['repair_order_id'])
    assert len(result['links']) == 2
    assert await db_session.scalar(select(func.count(Labor.id)).where(Labor.repair_order_id == identity)) == 1
    assert await db_session.scalar(select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id == identity)) == 1
    assert await db_session.scalar(select(func.count(Task.id)).where(Task.repair_order_id == identity)) == 3
    assert await db_session.scalar(select(func.count(Mapping.id))) == 2
    await db_session.refresh(item)
    assert item.stock_quantity == 8
    order = await db_session.get(RepairOrder, identity)
    assert order.total_cost == Decimal(120) and not order.is_pm and not order.is_fleet_work
    assert order.pricing_policy_snapshot['customer_id'] == str(a.customer.id)


@pytest.mark.asyncio
async def test_changed_work_preview_rolls_back_without_order_or_claim(db_session):
    a, item, body = await setup(db_session)
    preview = await service.work_preview(db_session, a.owner, a.vehicle.id, body)
    a.service.duration_minutes = 90
    await db_session.commit()
    request = wire.WorkCommit.model_validate({**body.model_dump(mode='json'), 'expected_work_fingerprint': preview['expected_work_fingerprint']})
    with pytest.raises(HTTPException) as error:
        await service.work_command(db_session, a.owner, a.vehicle.id, request, str(uuid4()))
    assert error.value.detail['code'] == 'maintenance_preview_changed'
    assert error.value.detail['preview']['totals']['repair_total'] == '170.00'
    await db_session.rollback()
    assert await db_session.scalar(select(func.count(RepairOrder.id))) == 1
    assert await db_session.scalar(select(func.count(Link.id))) == 0
    assert await db_session.scalar(select(func.count(PartsUsage.id))) == 0


@pytest.mark.asyncio
async def test_fleet_add_is_nonreserved_and_safe(db_session):
    a, item, body = await setup(db_session, channel='fleet')
    preview = await service.work_preview(db_session, a.owner, a.vehicle.id, body)
    assert preview['projection'] == 'fleet' and set(preview['totals']) == {'kind', 'repair_total'}
    assert 'account_policy' not in preview and 'pricing' not in preview['lines'][0]
    request = wire.WorkCommit.model_validate({**body.model_dump(mode='json'), 'expected_work_fingerprint': preview['expected_work_fingerprint']})
    result = await service.work_command(db_session, a.owner, a.vehicle.id, request, str(uuid4()))
    row = await db_session.scalar(select(PartsUsage).where(PartsUsage.repair_order_id == UUID(result['repair_order_id'])))
    assert row.stock_reserved_packages == 0
    await db_session.refresh(item)
    assert item.stock_quantity == 10


@pytest.mark.asyncio
async def test_existing_operation_mapping_preserves_all_saved_work(db_session):
    a, item, body = await setup(db_session, existing=True)
    labor = Labor(id=uuid4(), tenant_id=a.tenant.id, repair_order_id=a.order.id, source_service_id=a.service.id,
        description='Saved scope', hours=Decimal('2.5'), hourly_rate=Decimal(123), total_cost=Decimal('307.50'), execution_status='pending', execution_version=7)
    db_session.add(labor)
    a.order.total_labor_cost = a.order.total_cost = labor.total_cost
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await service.work_preview(db_session, a.owner, a.vehicle.id, body)
    assert error.value.detail['code'] == 'maintenance_operation_exists'
    raw = body.model_dump(mode='json')
    raw['coverage'][0]['operation'] = {'kind': 'existing', 'labor_id': str(labor.id), 'expected_operation_version': 7}
    request_body = wire.WorkRequest.model_validate(raw)
    preview = await service.work_preview(db_session, a.owner, a.vehicle.id, request_body)
    a.service.duration_minutes = 190
    item.selling_price = Decimal(999)
    await db_session.commit()
    request = wire.WorkCommit.model_validate({**raw, 'expected_work_fingerprint': preview['expected_work_fingerprint']})
    result = await service.work_command(db_session, a.owner, a.vehicle.id, request, str(uuid4()))
    assert not result['created']
    await db_session.refresh(labor)
    assert (labor.hours, labor.hourly_rate, labor.total_cost, labor.execution_version) == (Decimal('2.5'), Decimal(123), Decimal('307.50'), 7)
    assert await db_session.scalar(select(func.count(PartsUsage.id))) == 0
    assert await db_session.scalar(select(func.count(Task.id))) == 0


@pytest.mark.asyncio
async def test_fleet_membership_append_preserves_existing_rows_and_replay(db_session):
    from app.db.models.fleet import RepairOrderPMService
    from app.db.models.service import Service
    a, _, body = await setup(db_session,channel='fleet',existing=True)
    a.order.is_pm = a.order.is_fleet_work = True
    old_service=Service(id=uuid4(),tenant_id=a.tenant.id,name='Saved unrelated package',duration_minutes=30,is_active=True)
    db_session.add(old_service)
    await db_session.flush()
    old=RepairOrderPMService(id=uuid4(),tenant_id=a.tenant.id,repair_order_id=a.order.id,service_id=old_service.id,sort_order=7)
    db_session.add(old)
    await db_session.commit()
    preview=await service.work_preview(db_session,a.owner,a.vehicle.id,body)
    command=wire.WorkCommit.model_validate({**body.model_dump(mode='json'),'expected_work_fingerprint':preview['expected_work_fingerprint']})
    key=str(uuid4())
    saved=await service.work_command(db_session,a.owner,a.vehicle.id,command,key)
    repeated=await service.work_command(db_session,a.owner,a.vehicle.id,command,key)
    rows=list((await db_session.scalars(select(RepairOrderPMService).where(RepairOrderPMService.repair_order_id==a.order.id).order_by(RepairOrderPMService.sort_order))).all())
    assert repeated['replayed'] and repeated['repair_order_id']==saved['repair_order_id']
    assert [(row.id,row.service_id,row.sort_order) for row in rows][0]==(old.id,old_service.id,7)
    assert [(row.service_id,row.sort_order) for row in rows][1:]==[(a.service.id,8)]


@pytest.mark.asyncio
async def test_existing_only_fleet_attachment_never_reseeds_membership(db_session):
    from app.db.models.fleet import RepairOrderPMService
    a, _, body = await setup(db_session,channel='fleet',existing=True)
    a.order.is_pm=a.order.is_fleet_work=True
    operation=Labor(id=uuid4(),tenant_id=a.tenant.id,repair_order_id=a.order.id,description='Saved operation',
        source_service_id=a.service.id,hours=1,hourly_rate=100,total_cost=100,execution_status='pending',execution_version=1)
    db_session.add(operation)
    await db_session.commit()
    raw=body.model_dump(mode='json')
    raw['coverage'][0]['operation']={'kind':'existing','labor_id':str(operation.id),'expected_operation_version':1}
    body=wire.WorkRequest.model_validate(raw)
    preview=await service.work_preview(db_session,a.owner,a.vehicle.id,body)
    await service.work_command(db_session,a.owner,a.vehicle.id,wire.WorkCommit.model_validate({**body.model_dump(mode='json'),'expected_work_fingerprint':preview['expected_work_fingerprint']}),str(uuid4()))
    assert await db_session.scalar(select(func.count(RepairOrderPMService.id)).where(RepairOrderPMService.repair_order_id==a.order.id))==0
