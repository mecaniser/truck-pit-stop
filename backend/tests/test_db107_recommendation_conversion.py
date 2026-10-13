from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import func, select
from tests.test_db099_recommended_work import fixture, headers, actor, order, recommendation
from app.db.models.user import UserRole
from app.db.models.labor import Labor
from app.db.models.recommended_service import RecommendedService
from app.db.models.recommendation_conversion import RecommendationConversion
from app.db.models.repair_order import RepairOrderStatus


def path(f, target=None, rec=None):
    return f"/api/v1/repair-orders/{target or f['context'].id}/recommended-work/{rec or f['rec'].id}/convert"


def body(**extra):
    return dict(request_id=str(uuid4()), hours='1.25', hourly_rate='145.00', **extra)


@pytest.mark.asyncio
async def test_convert_replay_provenance_and_no_resolution(client, db_session, fixture):
    f = fixture
    payload = body()
    first = await client.post(path(f), json=payload, headers=headers(f['owner']))
    assert first.status_code == 201, first.text
    conversion = first.json()['conversion']
    second = await client.post(path(f), json=payload, headers=headers(f['owner']))
    assert second.status_code == 200, second.text
    assert second.json()['conversion']['id'] == conversion['id']
    assert second.json()['replayed'] is True
    lines = (await db_session.scalars(select(Labor).where(Labor.repair_order_id == f['context'].id))).all()
    assert len(lines) == 1
    assert lines[0].total_cost == Decimal('181.25')
    await db_session.refresh(f['rec'])
    assert not f['rec'].is_resolved and f['rec'].resolved_by_repair_order_id is None
    summary = (await client.get(f"/api/v1/repair-orders/{f['context'].id}/price-build", headers=headers(f['owner']))).json()
    assert summary['lines'][0]['recommendation_source']['recommendation_id'] == str(f['rec'].id)
    assert summary['recommendation_hourly_rate'] is not None
    recs = (await client.get(f"/api/v1/repair-orders/{f['source'].id}/recommended-services", headers=headers(f['owner']))).json()
    assert recs[0]['conversion']['id'] == conversion['id']


@pytest.mark.asyncio
@pytest.mark.parametrize('change,state,source_available', [
    ('none', 'active', True),
    ('source_deleted', 'active', False),
    ('source_customer_deleted', 'active', False),
    ('source_foreign_customer', 'active', False),
    ('source_foreign_vehicle', 'active', False),
    ('target_foreign_customer', 'target_deleted', True),
    ('target_deleted', 'target_deleted', True),
    ('target_cancelled', 'target_cancelled', True),
    ('line_deleted', 'operation_removed', True),
    ('superseded_cancelled', 'superseded', True),
])
async def test_single_query_line_provenance_preserves_scope_and_lifecycle(
    client, db_session, fixture, change, state, source_available,
):
    from datetime import datetime, timezone
    from uuid import UUID
    from sqlalchemy import event
    from app.services import recommendation_conversion

    f = fixture
    response = await client.post(path(f), json=body(), headers=headers(f['owner']))
    assert response.status_code == 201, response.text
    conversion = await db_session.get(RecommendationConversion, UUID(response.json()['conversion']['id']))
    line = await db_session.get(Labor, conversion.target_labor_id)
    now = datetime.now(timezone.utc)
    if change == 'source_deleted':
        f['source'].deleted_at = now
    elif change == 'source_customer_deleted':
        f['old'].deleted_at = now
    elif change == 'source_foreign_customer':
        f['source'].customer_id = f['foreign'].id
    elif change == 'source_foreign_vehicle':
        f['source'].vehicle_id = f['foreign_truck'].id
    elif change == 'target_foreign_customer':
        f['context'].customer_id = f['foreign'].id
    elif change == 'target_deleted':
        f['context'].deleted_at = now
    elif change in ('target_cancelled', 'superseded_cancelled'):
        f['context'].status = RepairOrderStatus.CANCELLED
        if change == 'superseded_cancelled':
            conversion.superseded_at = now
    elif change == 'line_deleted':
        line.deleted_at = now
    await db_session.commit()
    canonical = await recommendation_conversion.project(db_session, conversion)
    query_count = 0

    def count_query(*_args):
        nonlocal query_count
        query_count += 1

    sync_engine = db_session.bind.sync_engine
    event.listen(sync_engine, 'before_cursor_execute', count_query)
    try:
        sources = await recommendation_conversion.line_sources(
            db_session, f['a'].id, f['context'].id, [line.id],
        )
    finally:
        event.remove(sync_engine, 'before_cursor_execute', count_query)
    assert query_count == 1
    provenance = sources[line.id]
    assert provenance.state == canonical.state == state
    assert provenance.source_order == canonical.source_order
    assert provenance.source_order.available is source_available
    assert provenance.description == conversion.source_description
    assert await recommendation_conversion.line_sources(
        db_session, f['b'].id, f['context'].id, [line.id],
    ) == {}


@pytest.mark.asyncio
async def test_duplicate_different_key_and_changed_payload(client, db_session, fixture):
    f=fixture
    payload=body()
    first=await client.post(path(f), json=payload, headers=headers(f['owner']))
    assert first.status_code==201, first.text
    same=await client.post(path(f), json=body(), headers=headers(f['owner']))
    assert same.status_code==200, same.text
    changed=await client.post(path(f), json={**payload,'hours':'2'}, headers=headers(f['owner']))
    assert changed.status_code==409 and changed.json()['detail']['code']=='idempotency_key_reused'
    other=await order(db_session,f['a'],f['new'],f['x'])
    await db_session.commit()
    cross=await client.post(path(f,target=other.id),json=body(),headers=headers(f['owner']))
    assert cross.status_code==409 and cross.json()['detail']['code']=='already_converted'


@pytest.mark.asyncio
@pytest.mark.parametrize('role',[UserRole.MECHANIC,UserRole.FLEET_MANAGER,UserRole.CUSTOMER,UserRole.DRIVER])
async def test_conversion_role_denial(client,db_session,fixture,role):
    f=fixture
    user=await actor(db_session,f['a'],role)
    await db_session.commit()
    response=await client.post(path(f),json=body(),headers=headers(user))
    assert response.status_code==403


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('hours','0'),('hours','1.234'),('hourly_rate','-1'),('hourly_rate','1.234'),('hours','999.99')])
async def test_invalid_numbers_no_work(client,db_session,fixture,field,value):
    payload={**body(),field:value}
    if value=='999.99': payload['hourly_rate']='99999999.99'
    response=await client.post(path(fixture),json=payload,headers=headers(fixture['owner']))
    assert response.status_code==422, response.text
    assert await db_session.scalar(select(func.count()).select_from(RecommendationConversion))==0


@pytest.mark.asyncio
async def test_foreign_and_wrong_vehicle_and_terminal_targets(client,db_session,fixture):
    f=fixture
    for target,rec in [(f['foreign_order'].id,None),(None,uuid4())]:
        response=await client.post(path(f,target=target,rec=rec),json=body(),headers=headers(f['owner']))
        assert response.status_code==404,response.text
    f['context'].vehicle_id=f['y'].id
    await db_session.commit()
    response=await client.post(path(f),json=body(),headers=headers(f['owner']))
    assert response.status_code==409
    f['context'].vehicle_id=f['x'].id
    f['context'].status=RepairOrderStatus.PAID
    await db_session.commit()
    response=await client.post(path(f),json=body(),headers=headers(f['owner']))
    assert response.status_code==409


@pytest.mark.asyncio
async def test_remove_retry_then_explicit_replace(client,db_session,fixture):
    f=fixture
    payload=body()
    response=await client.post(path(f),json=payload,headers=headers(f['owner']))
    assert response.status_code==201,response.text
    conv=response.json()['conversion']
    removal=await client.delete(f"/api/v1/repair-orders/{f['context'].id}/price-build/lines/{conv['labor_id']}",headers=headers(f['owner']))
    assert removal.status_code==200,removal.text
    retry=await client.post(path(f),json=payload,headers=headers(f['owner']))
    assert retry.json()['conversion']['state']=='operation_removed'
    assert await db_session.scalar(select(func.count()).select_from(Labor))==0
    accidental=await client.post(path(f),json=body(),headers=headers(f['owner']))
    assert accidental.status_code==409
    replacement=await client.post(path(f),json=body(replaces_conversion_id=conv['id']),headers=headers(f['owner']))
    assert replacement.status_code==201,replacement.text
    assert replacement.json()['conversion']['labor_id']!=conv['labor_id']
    old_retry=await client.post(path(f),json=payload,headers=headers(f['owner']))
    assert old_retry.json()['conversion']['state']=='superseded'


@pytest.mark.asyncio
async def test_source_delete_and_explicit_resolution(client,db_session,fixture):
    f=fixture
    response=await client.post(path(f),json=body(),headers=headers(f['owner']))
    assert response.status_code==201,response.text
    src=f"/api/v1/repair-orders/{f['source'].id}/recommended-services/{f['rec'].id}"
    deletion=await client.delete(src,headers=headers(f['owner']))
    assert deletion.status_code==409
    resolve=await client.patch(src,json={'is_resolved':True,'resolved_by_repair_order_id':str(f['context'].id)},headers=headers(f['owner']))
    assert resolve.status_code==409,resolve.text
    f['context'].status=RepairOrderStatus.COMPLETED
    await db_session.commit()
    resolve=await client.patch(src,json={'is_resolved':True,'resolved_by_repair_order_id':str(f['context'].id)},headers=headers(f['owner']))
    assert resolve.status_code==200,resolve.text
    assert resolve.json()['is_resolved'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('removed_state',['cancelled','deleted'])
async def test_cancel_delete_replacement_reactivation_guard(client,db_session,fixture,removed_state):
    f=fixture
    auth=headers(f['owner'])
    payload=body()
    created=await client.post(path(f),json=payload,headers=auth)
    assert created.status_code==201,created.text
    original=created.json()['conversion']
    targetpath=f"/api/v1/repair-orders/{f['context'].id}"
    if removed_state=='cancelled':
        removed=await client.put(targetpath,json={'status':'cancelled'},headers=auth)
    else:
        removed=await client.delete(targetpath,headers=auth)
    assert removed.status_code in (200,204),removed.text
    # A retry is a read of the original result, including unavailable state.
    retry=await client.post(path(f),json=payload,headers=auth)
    assert retry.status_code==200,retry.text
    assert retry.json()['conversion']['state']==f'target_{removed_state}'
    other=await order(db_session,f['a'],f['new'],f['x'])
    await db_session.commit()
    replacement=await client.post(path(f,target=other.id),json=body(replaces_conversion_id=original['id']),headers=auth)
    assert replacement.status_code==201,replacement.text
    if removed_state=='cancelled':
        restore=await client.put(targetpath,json={'status':'draft'},headers=auth)
    else:
        restore=await client.post(targetpath+'/restore',headers=auth)
    assert restore.status_code==409,restore.text
    assert restore.json()['detail']['code']=='superseded_recommendation_work'


@pytest.mark.asyncio
async def test_internal_rate_ets_and_provenance_role_boundary(client,db_session,fixture):
    f=fixture
    f['context'].is_internal=True
    f['a'].internal_labor_rate=Decimal('55')
    await db_session.commit()
    mismatch=await client.post(path(f),json=body(),headers=headers(f['owner']))
    assert mismatch.status_code==409 and mismatch.json()['detail']['code']=='pricing_changed'
    creation=await client.post(path(f),json={**body(),'hourly_rate':'55'},headers=headers(f['owner']))
    assert creation.status_code==201,creation.text
    mechanic=await actor(db_session,f['a'],UserRole.MECHANIC)
    f['context'].assigned_mechanic_id=mechanic.id
    await db_session.commit()
    response=await client.get(f"/api/v1/repair-orders/{f['context'].id}/price-build",headers=headers(mechanic))
    assert response.status_code==200,response.text
    assert response.json()['recommendation_hourly_rate'] is None
    assert response.json()['can_convert_recommendations'] is False
    assert response.json()['lines'][0]['recommendation_source'] is None
    foreign_target=await order(db_session,f['a'],f['new'],f['x'],source='easy_truck_shop_import')
    newrec=await recommendation(db_session,f['a'],f['source'])
    await db_session.commit()
    refused=await client.post(path(f,target=foreign_target.id,rec=newrec.id),json=body(),headers=headers(f['owner']))
    assert refused.status_code==409 and refused.json()['detail']['code']=='target_ets_managed'


@pytest.mark.asyncio
async def test_rename_keeps_immutable_source_and_no_extra_inputs(client,db_session,fixture):
    f=fixture
    malformed=await client.post(path(f),json={**body(),'source_description':'forged'},headers=headers(f['owner']))
    assert malformed.status_code==422
    creation=await client.post(path(f),json=body(),headers=headers(f['owner']))
    conv=creation.json()['conversion']
    linepath=f"/api/v1/repair-orders/{f['context'].id}/price-build/lines/{conv['labor_id']}"
    rename=await client.patch(linepath,json={'description':'New operation name','hours':'2'},headers=headers(f['owner']))
    assert rename.status_code==200,rename.text
    source=rename.json()['lines'][0]['recommendation_source']
    assert source['description']=='Inspect wheel seal'
    assert source['recommendation_id']==str(f['rec'].id)


@pytest.mark.asyncio
async def test_converted_resolution_reference_and_nonstaff_error_privacy(client,db_session,fixture):
    f=fixture
    creation=await client.post(path(f),json=body(),headers=headers(f['owner']))
    assert creation.status_code==201
    mechanic=await actor(db_session,f['a'],UserRole.MECHANIC)
    f['source'].assigned_mechanic_id=mechanic.id
    await db_session.commit()
    src=f"/api/v1/repair-orders/{f['source'].id}/recommended-services/{f['rec'].id}"
    denied=await client.patch(src,json={'is_resolved':True},headers=headers(mechanic))
    assert denied.status_code==403,denied.text
    assert 'conversion' not in denied.json()['detail']
    assert str(f['context'].id) not in denied.text
    f['context'].status=RepairOrderStatus.COMPLETED
    await db_session.commit()
    resolution=await client.patch(src,json={'is_resolved':True,'resolved_by_repair_order_id':str(f['context'].id)},headers=headers(f['owner']))
    assert resolution.status_code==200
    clearing=await client.patch(src,json={'resolved_by_repair_order_id':None},headers=headers(f['owner']))
    assert clearing.status_code==409,clearing.text
    reopened=await client.patch(src,json={'is_resolved':False},headers=headers(f['owner']))
    assert reopened.status_code==200
    assert reopened.json()['resolved_by_repair_order_id'] is None


@pytest.mark.asyncio
async def test_vehicle_snapshot_drift_does_not_release_live_operation(client,db_session,fixture):
    f=fixture
    creation=await client.post(path(f),json=body(),headers=headers(f['owner']))
    assert creation.status_code==201
    conversion=await db_session.scalar(select(RecommendationConversion))
    # A canonical vehicle merge may rewrite current order truck IDs, while the
    # historical conversion snapshot deliberately remains immutable.
    conversion.vehicle_id=f['y'].id
    await db_session.commit()
    other=await order(db_session,f['a'],f['new'],f['x'])
    await db_session.commit()
    refused=await client.post(path(f,target=other.id),json=body(replaces_conversion_id=str(conversion.id)),headers=headers(f['owner']))
    assert refused.status_code==409
    assert refused.json()['detail']['code']=='already_converted'
    assert refused.json()['detail']['conversion']['can_replace'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('role',[UserRole.MECHANIC,UserRole.FLEET_MANAGER,UserRole.CUSTOMER])
async def test_shared_order_detail_does_not_disclose_source_order(client,db_session,fixture,role):
    from app.db.models.user_customer_link import UserCustomerLink
    f=fixture
    created=await client.post(path(f),json=body(),headers=headers(f['owner']))
    assert created.status_code==201
    user=await actor(db_session,f['a'],role)
    if role==UserRole.MECHANIC: f['context'].assigned_mechanic_id=user.id
    if role==UserRole.FLEET_MANAGER: f['context'].is_fleet_work=True
    if role==UserRole.CUSTOMER:
        user.customer_id=f['new'].id
        db_session.add(UserCustomerLink(user_id=user.id,tenant_id=f['a'].id,customer_id=f['new'].id))
    await db_session.commit()
    response=await client.get(f"/api/v1/repair-orders/{f['context'].id}/detail",headers=headers(user))
    assert response.status_code==200,response.text
    assert f['source'].order_number not in response.text
    assert str(f['source'].id) not in response.text
    assert str(f['rec'].id) not in response.text


@pytest.mark.asyncio
async def test_failed_replacement_rolls_back_supersession_and_new_work(client,db_session,fixture,monkeypatch):
    from fastapi import HTTPException
    from app.api.v1.endpoints import repair_orders
    from app.db.models.repair_order_history import RepairOrderHistoryEvent
    f=fixture
    auth=headers(f['owner'])
    first=await client.post(path(f),json=body(),headers=auth)
    original=first.json()['conversion']
    removed=await client.delete(f"/api/v1/repair-orders/{f['context'].id}/price-build/lines/{original['labor_id']}",headers=auth)
    assert removed.status_code==200
    original_refresh=repair_orders._refresh_repair_order_totals
    async def fail_totals(*args,**kwargs):
        raise HTTPException(status_code=503,detail='Synthetic totals failure')
    monkeypatch.setattr(repair_orders,'_refresh_repair_order_totals',fail_totals)
    retrybody=body(replaces_conversion_id=original['id'])
    failed=await client.post(path(f),json=retrybody,headers=auth)
    assert failed.status_code==503
    conversions=(await db_session.scalars(select(RecommendationConversion))).all()
    assert len(conversions)==1 and conversions[0].superseded_at is None
    assert await db_session.scalar(select(func.count()).select_from(Labor))==0
    assert await db_session.scalar(select(func.count()).select_from(RepairOrderHistoryEvent).where(RepairOrderHistoryEvent.event_type=='recommendation_converted'))==1
    monkeypatch.setattr(repair_orders,'_refresh_repair_order_totals',original_refresh)
    successful=await client.post(path(f),json=retrybody,headers=auth)
    assert successful.status_code==201,successful.text
