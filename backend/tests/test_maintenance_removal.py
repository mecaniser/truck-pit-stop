from uuid import UUID, uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db.models.labor import Labor
from app.db.models.inventory import PartsUsage,Inventory
from app.db.models.maintenance import MaintenanceWorkLink as Link
from app.db.models.repair_order import RepairOrder,RepairOrderStatus
from app.api.v1.endpoints import repair_orders,fleet
from app.schemas import maintenance as wire
from app.schemas.fleet import PMServicesUpdate
from app.services import maintenance as service
from test_maintenance_work import setup

@pytest.fixture
def db_session(db_session):
    db_session.autoflush=False
    return db_session

async def attached(db,channel='shop'):
    a,item,body=await setup(db,channel=channel)
    preview=await service.work_preview(db,a.owner,a.vehicle.id,body)
    result=await service.work_command(db,a.owner,a.vehicle.id,wire.WorkCommit.model_validate({**body.model_dump(mode='json'),'expected_work_fingerprint':preview['expected_work_fingerprint']}),str(uuid4()))
    order=await db.get(RepairOrder,UUID(result['repair_order_id']))
    line=await db.scalar(select(Labor).where(Labor.repair_order_id==order.id))
    return a,item,order,line

@pytest.mark.asyncio
@pytest.mark.parametrize('route',['labor','price_build'])
async def test_direct_removal_confirmation_precedes_all_side_effects(db_session,route):
    a,item,order,line=await attached(db_session)
    summary=await service.order_maintenance(db_session,a.owner,'shop',order.id)
    async def remove(token):
        if route=='labor':
            return await repair_orders.remove_labor_from_repair_order(order.id,line.id,db=db_session,current_user=a.owner,expected_maintenance_fingerprint=token)
        return await repair_orders.delete_price_build_line(order.id,line.id,db=db_session,current_user=a.owner,expected_maintenance_fingerprint=token)
    with pytest.raises(HTTPException) as error:
        await remove(None)
    assert error.value.status_code==409 and error.value.detail['code']=='maintenance_preview_changed'
    assert all(row.state=='active' for row in (await db_session.scalars(select(Link))).all())
    assert await db_session.scalar(select(func.count(PartsUsage.id)))==1
    assert (await db_session.get(Inventory,item.id)).stock_quantity==8
    await remove(summary['expected_review_fingerprint'])
    assert all(row.state=='detached' for row in (await db_session.scalars(select(Link))).all())
    assert await db_session.scalar(select(func.count(Labor.id)).where(Labor.repair_order_id==order.id))==0
    assert (await db_session.get(Inventory,item.id)).stock_quantity==(10 if route=='price_build' else 8)

@pytest.mark.asyncio
@pytest.mark.parametrize('channel',['shop','fleet'])
async def test_pm_replace_projects_affected_links_and_confirms_before_removal(db_session,channel):
    from app.db.models.fleet import RepairOrderPMService
    from app.schemas.parts_pricing import ResolveRequest
    from app.services.parts_pricing_planner import build_plan
    a,item,order,line=await attached(db_session,'fleet')
    # The additive writer exposes its actual package to the existing PM adapter.
    assert await db_session.scalar(select(func.count(RepairOrderPMService.id)).where(RepairOrderPMService.repair_order_id==order.id)) == 1
    request=ResolveRequest.model_validate({'context':{'kind':'repair_order','repair_order_id':str(order.id)},'plan':{'kind':'pm_replace','service_ids':[]},'pricing_presentation':channel})
    plan=await build_plan(db_session,a.owner,request)
    assert plan.response['confirmation_required']
    assert len(plan.response['maintenance']['affected_work'])==2
    with pytest.raises(HTTPException) as error:
        await fleet.set_wo_pm_services(order.id,PMServicesUpdate(service_ids=[],pricing_presentation=channel),idempotency_key=str(uuid4()),db=db_session,current_user=a.owner)
    assert error.value.status_code==409
    assert all(row.state=='active' for row in (await db_session.scalars(select(Link))).all())
    await fleet.set_wo_pm_services(order.id,PMServicesUpdate(service_ids=[],pricing_presentation=channel,pricing_preview_fingerprint=plan.response['pricing_preview_fingerprint']),idempotency_key=str(uuid4()),db=db_session,current_user=a.owner)
    assert all(row.state=='detached' for row in (await db_session.scalars(select(Link))).all())
    assert await db_session.scalar(select(func.count(Labor.id)).where(Labor.repair_order_id==order.id))==0
    assert (await db_session.get(Inventory,item.id)).stock_quantity==10  # Fleet did not reserve stock
