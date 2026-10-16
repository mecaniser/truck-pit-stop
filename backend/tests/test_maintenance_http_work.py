"""Actual HTTP boundary, current authorization and both finalization adapters."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from app.api.v1.endpoints.maintenance import router, work_router
from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.db.models.user import UserRole
from app.db.models.maintenance import MaintenanceCompletion as Completion, MaintenanceWorkLink as Link
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.labor import Labor
from app.db.models.service_checklist import RepairOrderChecklistItem as Task
from app.db.models.invoice import Invoice
from app.middleware.idempotency import IdempotencyMiddleware
from app.schemas import maintenance as wire
from app.services import maintenance as service
from test_maintenance_work import setup
from test_maintenance_evidence import actual


@pytest.fixture
def db_session(db_session):
    db_session.autoflush = False
    return db_session


def http_app(db, actor):
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.include_router(work_router, prefix='/api/v1')
    app.add_middleware(IdempotencyMiddleware)
    async def database():
        try:
            yield db
        except Exception:
            await db.rollback()
            raise
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_active_user] = lambda: actor
    return app


@pytest.mark.asyncio
async def test_http_shared_work_preview_receipt_and_current_role(db_session):
    a, _, request = await setup(db_session)
    actor = SimpleNamespace(id=a.owner.id, tenant_id=a.tenant.id, role=UserRole.GARAGE_OWNER, first_name='Synthetic', last_name='Manager')
    app = http_app(db_session, actor)
    path = f'/api/v1/vehicles/{a.vehicle.id}/maintenance-work'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        preview = await client.post(path+'-preview', json=request.model_dump(mode='json'))
        assert preview.status_code == 200, preview.text
        body = {**request.model_dump(mode='json'), 'expected_work_fingerprint': preview.json()['expected_work_fingerprint']}
        headers = {'Idempotency-Key':str(uuid4())}
        first = await client.post(path, json=body, headers=headers)
        assert first.status_code == 201, first.text
        replay = await client.post(path, json=body, headers=headers)
        assert replay.status_code == 200 and replay.json()['replayed']
        assert first.json()['repair_order_id'] == replay.json()['repair_order_id']
        actor.role = UserRole.MECHANIC
        denied = await client.post(path, json=body, headers=headers)
        assert denied.status_code == 403
        actor.role = UserRole.GARAGE_OWNER
        actor.tenant_id = uuid4()
        denied = await client.post(path, json=body, headers=headers)
        assert denied.status_code == 403
    assert await db_session.scalar(select(func.count(Link.id))) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('channel', ['shop','fleet'])
async def test_actual_manager_routes_advance_once_and_issue_with_missing_reading(db_session, monkeypatch, channel):
    from unittest.mock import AsyncMock
    from app.api.v1.endpoints import repair_orders, fleet, invoices
    from app.schemas.fleet import WorkOrderComplete
    a, _, request = await setup(db_session, channel=channel)
    preview = await service.work_preview(db_session, a.owner, a.vehicle.id, request)
    result = await service.work_command(db_session, a.owner, a.vehicle.id,
        wire.WorkCommit.model_validate({**request.model_dump(mode='json'), 'expected_work_fingerprint':preview['expected_work_fingerprint']}), str(uuid4()))
    order = await db_session.get(RepairOrder, UUID(result['repair_order_id']))
    order.status = RepairOrderStatus.PENDING_REVIEW
    order.work_completed_at = datetime.now(timezone.utc)
    for task in (await db_session.scalars(select(Task).where(Task.repair_order_id==order.id))).all():
        task.is_completed = True
        task.completed_at = datetime.now(timezone.utc)
        task.completed_by_user_id = a.owner.id
        task.completed_by_name = 'Synthetic Manager'
    for operation in (await db_session.scalars(select(Labor).where(Labor.repair_order_id==order.id))).all():
        operation.execution_status = 'completed'
        operation.execution_version += 1
        operation.completed_at = datetime.now(timezone.utc)
    a.customer.phone = None
    await db_session.commit()
    summary = await service.order_maintenance(db_session, a.owner, channel, order.id)
    programs = {row['id']:row for row in summary['programs']}
    entries = [{'work_link_id':row['work_link_id'], 'expected_link_version':row['version'],
        'program': {'program_id':str(link.program_id),'expected_version':programs[str(link.program_id)]['version']},
        'attestation':actual() if index==0 else actual(None)}
        for index,(row,link) in enumerate(zip(summary['links'],[await db_session.get(Link,UUID(row['work_link_id'])) for row in summary['links']]))]
    raw = {'purpose':'completion','channel':channel,'repair_order_id':str(order.id),
        'expected_review_fingerprint':summary['expected_review_fingerprint'],'entries':entries}
    app = http_app(db_session,a.owner)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        target = await client.post(f'/api/v1/vehicles/{a.vehicle.id}/maintenance-target-preview',json=raw)
    assert target.status_code==200,target.text
    review = {'request_id':str(uuid4()),'expected_review_fingerprint':summary['expected_review_fingerprint'],
        'expected_target_fingerprint':target.json()['expected_target_fingerprint'],'entries':entries}
    monkeypatch.setattr(repair_orders,'send_email',AsyncMock())
    monkeypatch.setattr(repair_orders,'send_sms',AsyncMock())
    monkeypatch.setattr(repair_orders,'broadcast_repair_order_update',AsyncMock())
    monkeypatch.setattr(invoices,'enqueue_invoice_created_email',AsyncMock(return_value=False))
    monkeypatch.setattr(invoices,'notify_invoice_created',AsyncMock())
    if channel=='shop':
        saved = await repair_orders.approve_completion(order.id,body=repair_orders.ApproveCompletionRequest(maintenance_review=review),idempotency_key=None,db=db_session,current_user=a.owner)
    else:
        saved = await fleet.complete_work_order(order.id,body=WorkOrderComplete(maintenance_review=review),db=db_session,current_user=a.owner)
    assert {row.result for row in wire.MaintenanceResult.model_validate(saved.maintenance).items} == {'advanced','pending_evidence'}
    assert await db_session.scalar(select(func.count(Invoice.id)).where(Invoice.repair_order_id==order.id))==1
    assert await db_session.scalar(select(func.count(Completion.id)).where(Completion.source_id==order.id))==2
    await db_session.refresh(order)
    assert order.status==RepairOrderStatus.INVOICED


@pytest.mark.asyncio
async def test_http_late_parts_failure_has_m1_preview_and_no_partial_mutation(db_session,monkeypatch):
    from app.services import parts_pricing_planner
    from fastapi import HTTPException
    from app.db.models.inventory import PartsUsage,Inventory
    a,item,request=await setup(db_session)
    ids=(a.owner.id,a.tenant.id,a.vehicle.id,item.id)
    actor=SimpleNamespace(id=ids[0],tenant_id=ids[1],role=UserRole.GARAGE_OWNER,first_name='Synthetic',last_name='Manager')
    app=http_app(db_session,actor)
    original=parts_pricing_planner.apply_plan_parts
    async def fail_after(*args,**kwargs):
        await original(*args,**kwargs)
        raise HTTPException(409,{'code':'bundle_availability_changed','message':'Review stock.','preview':{'schema_version':1,'private':'not a maintenance preview'}})
    monkeypatch.setattr(parts_pricing_planner,'apply_plan_parts',fail_after)
    path=f'/api/v1/vehicles/{ids[2]}/maintenance-work'
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        preview=await client.post(path+'-preview',json=request.model_dump(mode='json'))
        result=await client.post(path,json={**request.model_dump(mode='json'),'expected_work_fingerprint':preview.json()['expected_work_fingerprint']},headers={'Idempotency-Key':str(uuid4())})
    assert result.status_code==409,result.text
    fresh=result.json()['detail']['preview']
    assert fresh['vehicle_id']==str(ids[2]) and fresh['expected_work_fingerprint'] and 'private' not in fresh
    assert await db_session.scalar(select(func.count(Link.id)))==0
    assert await db_session.scalar(select(func.count(PartsUsage.id)))==0
    assert await db_session.scalar(select(func.count(RepairOrder.id)))==1
    assert (await db_session.get(Inventory,ids[3])).stock_quantity==10
