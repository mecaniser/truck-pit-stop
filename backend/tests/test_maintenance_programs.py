"""DB134 authorized foundation and retained-source contracts (production autoflush)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from app.db.models.maintenance import MaintenanceProgram as Program, MaintenanceProgramEvent as Event, MaintenanceReading as Reading, MaintenanceWorkLink as Link
from app.db.models.vehicle_relationship import FleetMembership
from app.db.models.user import UserRole
from app.schemas import maintenance as wire
from app.services import maintenance as service
from test_service_checklists import seed


@pytest.fixture
def db_session(db_session):
    db_session.autoflush = False
    return db_session


def config(a, **changes):
    return {'name': 'Oil service', 'intervals': {'days': 30, 'miles': 1000, 'engine_hours': None}, 'service_id': str(a.service.id), **changes}


def explicit(**changes):
    return {'kind': 'explicit', 'targets': {'due_on': '2026-12-01', 'odometer_miles': 100000, 'engine_hours': None, **changes}}


async def create(db, a, *, cfg=None, initial=None, key=None, channel='shop'):
    cfg, initial = cfg or config(a), initial or explicit()
    preview = await service.target_preview(db, a.owner, a.vehicle.id, wire.ConfigPreview.model_validate({
        'purpose': 'configuration', 'channel': channel, 'program': None, 'config': cfg, 'action': 'create', 'seed': initial, 'reason': None}))
    body = wire.ProgramCreate.model_validate({'channel': channel, 'config': cfg, 'targets': {'kind': 'replace', 'seed': initial,
        'expected_target_fingerprint': preview['expected_target_fingerprint'], 'reason': None}})
    return await service.program_command(db, a.owner, a.vehicle.id, body, key or str(uuid4())), body


@pytest.mark.asyncio
async def test_configuration_preview_replay_preserves_scalars_and_history(db_session):
    a = await seed(db_session)
    a.vehicle.next_pm_miles = 42000
    await db_session.commit()
    key = str(uuid4())
    first, body = await create(db_session, a, key=key)
    assert not first['replayed'] and first['program']['version'] == 1
    assert first['program']['target_provenance']['kind'] == 'explicit'
    assert first['program']['legacy_package'] is None
    repeat = await service.program_command(db_session, a.owner, a.vehicle.id, body, key)
    assert repeat['replayed'] and repeat['program'] == first['program']
    assert await db_session.scalar(select(func.count(Program.id))) == 1
    assert await db_session.scalar(select(func.count(Event.id))) == 1
    await db_session.refresh(a.vehicle)
    assert a.vehicle.next_pm_miles == 42000
    program_id = UUID(first['program']['id'])
    rename = wire.ProgramUpdate.model_validate({'channel': 'shop', 'expected_version': 1, 'config': config(a, name='Renamed'), 'targets': {'kind': 'preserve'}})
    saved = await service.program_command(db_session, a.owner, a.vehicle.id, rename, str(uuid4()), program_id=program_id)
    assert saved['program']['version'] == 2 and saved['program']['targets'] == first['program']['targets']
    archive = wire.ArchiveCommand(channel='shop', expected_version=2)
    await service.program_command(db_session, a.owner, a.vehicle.id, archive, str(uuid4()), program_id=program_id, action='archive')
    assert (await service.program_page(db_session, a.owner, 'shop', vehicle_id=a.vehicle.id))['total'] == 0
    archived = (await service.program_page(db_session, a.owner, 'shop', vehicle_id=a.vehicle.id, include_archived=True))['items'][0]
    assert archived['capabilities']['can_archive'] is True  # same reversible control offers Restore
    assert archived['capabilities']['can_edit'] is False
    history = await service.program_history(db_session, a.owner, 'shop', a.vehicle.id, program_id)
    assert [item['version'] for item in history['items']] == [3, 2, 1]
    restore = wire.ArchiveCommand(channel='shop', expected_version=3)
    assert (await service.program_command(db_session, a.owner, a.vehicle.id, restore, str(uuid4()), program_id=program_id, action='restore'))['program']['targets'] == first['program']['targets']


@pytest.mark.asyncio
async def test_source_change_and_cas_are_atomic(db_session):
    a = await seed(db_session)
    result, _ = await create(db_session, a)
    program_id = UUID(result['program']['id'])
    body = wire.ProgramUpdate.model_validate({'channel': 'shop', 'expected_version': 1, 'config': config(a, name='Other name'), 'targets': {'kind': 'preserve'}})
    await service.program_command(db_session, a.owner, a.vehicle.id, body, str(uuid4()), program_id=program_id)
    with pytest.raises(HTTPException) as exc:
        await service.program_command(db_session, a.owner, a.vehicle.id, body, str(uuid4()), program_id=program_id)
    assert exc.value.detail['code'] == 'maintenance_version_conflict'
    await db_session.rollback()
    assert await db_session.scalar(select(func.count(Event.id))) == 2


@pytest.mark.asyncio
async def test_baseline_missing_reading_is_unknown_and_manual_precision_is_retained(db_session):
    a = await seed(db_session)
    initial = {'kind': 'baseline', 'attestation': {'performed_on': '2026-01-01', 'readings': {'odometer_miles': None, 'engine_hours': None}, 'confirm_actual_service_readings': True}}
    first, _ = await create(db_session, a, initial=initial)
    assert first['program']['targets'] == {'due_on': '2026-01-31', 'odometer_miles': None, 'engine_hours': None}
    assert first['program']['due']['needs_baseline'] == ['odometer_miles']
    initial['attestation']['readings']['odometer_miles'] = {'kind': 'manual', 'value': '42000', 'basis': 'staff_reported', 'note': None}
    second, _ = await create(db_session, a, initial=initial)
    assert second['program']['targets']['odometer_miles'] == 43000
    reading = second['program']['due']['miles']['reading']
    assert reading['observed_at'] is None and reading['observed_on'] == '2026-01-01'
    assert reading['observed_precision'] == 'date' and reading['basis'] == 'staff_reported'


@pytest.mark.asyncio
async def test_manual_current_zero_replay_never_resets_target_or_vehicle_mileage(db_session):
    a = await seed(db_session)
    result, _ = await create(db_session, a)
    now = datetime.now(timezone.utc)
    key = str(uuid4())
    body = wire.ReadingCreate.model_validate({'channel': 'shop', 'observed_at': now.isoformat(), 'odometer_miles': 0, 'engine_hours': '0', 'source': 'staff_observed', 'note': None})
    first = await service.reading_command(db_session, a.owner, a.vehicle.id, body, key)
    replay = await service.reading_command(db_session, a.owner, a.vehicle.id, body, key)
    assert replay['replayed'] and replay['observation_id'] == first['observation_id']
    assert await db_session.scalar(select(func.count(Reading.id))) == 1
    page = await service.program_page(db_session, a.owner, 'shop', vehicle_id=a.vehicle.id)
    assert page['items'][0]['targets'] == result['program']['targets']
    assert page['items'][0]['due']['miles']['reading']['comparison_value'] == '0'
    await db_session.refresh(a.vehicle)
    assert a.vehicle.mileage is None


@pytest.mark.asyncio
async def test_role_and_membership_loss_checked_before_replay(db_session):
    a = await seed(db_session)
    member = FleetMembership(tenant_id=a.tenant.id, vehicle_id=a.vehicle.id, fleet_customer_id=a.customer.id)
    db_session.add(member)
    await db_session.commit()
    key = str(uuid4())
    first, body = await create(db_session, a, channel='fleet', key=key)
    a.owner.role = UserRole.FLEET_MANAGER
    await db_session.commit()
    assert (await service.program_command(db_session, a.owner, a.vehicle.id, body, key))['replayed']
    member.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await service.program_command(db_session, a.owner, a.vehicle.id, body, key)
    assert exc.value.status_code == 404
    await db_session.rollback()
    await db_session.refresh(a.owner)
    await db_session.refresh(a.vehicle)
    a.owner.role = UserRole.MECHANIC
    with pytest.raises(HTTPException) as exc:
        await service.program_command(db_session, a.owner, a.vehicle.id, body, key)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_foreign_ids_and_receipt_semantics_no_partial_write(db_session):
    a, b = await seed(db_session), await seed(db_session)
    first, body = await create(db_session, a)
    with pytest.raises(HTTPException) as exc:
        await service.program_page(db_session, a.owner, 'shop', vehicle_id=b.vehicle.id)
    assert exc.value.status_code == 404
    assert (await service.program_page(db_session, a.owner, 'shop', customer_id=b.customer.id))['total'] == 0
    with pytest.raises(HTTPException) as exc:
        await service.program_history(db_session, a.owner, 'shop', a.vehicle.id, UUID(str(uuid4())))
    assert exc.value.status_code == 404
    key = str(uuid4())
    _, original = await create(db_session, a, key=key)
    changed = original.model_copy(update={'config': wire.Config.model_validate(config(a, name='Different request'))})
    with pytest.raises(HTTPException) as exc:
        await service.program_command(db_session, a.owner, a.vehicle.id, changed, key)
    assert exc.value.detail['code'] == 'idempotency_conflict'
    await db_session.rollback()
    assert await db_session.scalar(select(func.count(Program.id))) == 2


@pytest.mark.asyncio
async def test_literal_search_filter_and_paging_counts_are_access_scoped(db_session):
    a, b = await seed(db_session), await seed(db_session)
    await create(db_session, a, cfg=config(a, name='Filter_% literal'))
    await create(db_session, a, cfg=config(a, name='Filter_other'))
    await create(db_session, b, cfg=config(b, name='Filter_% foreign'))
    page = await service.program_page(db_session, a.owner, 'shop', search='_%', limit=1)
    assert page['total'] == 1 and page['items'][0]['name'] == 'Filter_% literal'
    assert page['counts']['active'] == 1
    assert (await service.program_page(db_session, a.owner, 'shop', limit=1))['has_more']


@pytest.mark.asyncio
async def test_active_configuration_rename_only_and_archived_template_retains_read(db_session):
    a = await seed(db_session)
    result, _ = await create(db_session, a)
    program = await db_session.get(Program, UUID(result['program']['id']))
    link = Link(id=uuid4(), tenant_id=a.tenant.id, program_id=program.id, cycle=1, repair_order_id=a.order.id,
        program_version=program.version, captured_config=service.configuration(program), captured_targets=service.targets(program), state='active', version=1)
    db_session.add(link)
    a.service.is_active = False
    await db_session.commit()
    rename = wire.ProgramUpdate.model_validate({'channel': 'shop', 'expected_version': 1, 'config': config(a, name='Rename occupied'), 'targets': {'kind': 'preserve'}})
    saved = await service.program_command(db_session, a.owner, a.vehicle.id, rename, str(uuid4()), program_id=program.id)
    assert saved['program']['service']['availability'] == 'archived'
    assert saved['program']['work']['work_link_id'] == str(link.id)
    changed = rename.model_copy(update={'expected_version': 2, 'config': wire.Config.model_validate(config(a, intervals={'days': 60, 'miles': 1000, 'engine_hours': None}))})
    with pytest.raises(HTTPException) as exc:
        await service.program_command(db_session, a.owner, a.vehicle.id, changed, str(uuid4()), program_id=program.id)
    assert exc.value.detail['code'] == 'maintenance_operation_linked'


@pytest.mark.asyncio
async def test_http_current_authority_and_uuid_replay_bypass_redis(db_session):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.api.v1.endpoints.maintenance import router
    from app.core.dependencies import get_current_active_user
    from app.db.session import get_db
    from app.middleware.idempotency import IdempotencyMiddleware
    a = await seed(db_session)
    actor = SimpleNamespace(id=a.owner.id, tenant_id=a.tenant.id, role=UserRole.GARAGE_OWNER)
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.add_middleware(IdempotencyMiddleware)
    async def database():
        try:
            yield db_session
        except Exception:
            await db_session.rollback()
            raise
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_active_user] = lambda: actor
    path = f'/api/v1/vehicles/{a.vehicle.id}/maintenance-programs'
    preview_path = f'/api/v1/vehicles/{a.vehicle.id}/maintenance-target-preview'
    cfg = config(a)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        preview = await client.post(preview_path, json={'purpose':'configuration','channel':'shop','program':None,'config':cfg,'action':'create','seed':explicit(),'reason':None})
        assert preview.status_code == 200, preview.text
        request = {'channel':'shop','config':cfg,'targets':{'kind':'replace','seed':explicit(),'reason':None,'expected_target_fingerprint':preview.json()['expected_target_fingerprint']}}
        headers = {'Idempotency-Key':str(uuid4())}
        first = await client.post(path, json=request, headers=headers)
        assert first.status_code == 201, first.text
        assert {'private','no-store'} <= set(first.headers['cache-control'].replace(' ','').split(','))
        repeat = await client.post(path, json=request, headers=headers)
        assert repeat.status_code == 200 and repeat.json()['replayed']
        actor.role = UserRole.MECHANIC
        denied = await client.post(path, json=request, headers=headers)
        assert denied.status_code == 403
        actor.role = UserRole.RECEPTIONIST
        invalid = await client.post(path, json={**request,'actor_id':str(uuid4())}, headers={'Idempotency-Key':str(uuid4())})
        assert invalid.status_code == 422 and invalid.json()['detail']['code'] == 'maintenance_invalid_input'
        assert (await client.get(path, params={'channel':'fleet'})).status_code == 403


@pytest.mark.asyncio
async def test_selected_source_dates_and_foreign_observations_are_checked(db_session):
    a, b = await seed(db_session), await seed(db_session)
    stamp = datetime.now(timezone.utc) - timedelta(days=1)
    observed = stamp.astimezone(__import__('zoneinfo').ZoneInfo(a.tenant.timezone)).date().isoformat()
    row = Reading(id=uuid4(), tenant_id=a.tenant.id, vehicle_id=a.vehicle.id, observed_at=stamp, odometer_miles=125000, source='staff_observed', actor_id=a.owner.id, request_id=uuid4())
    foreign = Reading(id=uuid4(), tenant_id=b.tenant.id, vehicle_id=b.vehicle.id, observed_at=stamp, odometer_miles=125000, source='staff_observed', actor_id=b.owner.id, request_id=uuid4())
    db_session.add_all([row,foreign]);await db_session.commit()
    payload = {'purpose':'configuration','channel':'shop','program':None,'config':config(a),'action':'create','reason':None,
        'seed':{'kind':'baseline','attestation':{'performed_on':observed,'confirm_actual_service_readings':True,
        'readings':{'odometer_miles':{'kind':'source','meter':'odometer_miles','source_kind':'maintenance_reading','source_id':str(row.id)},'engine_hours':None}}}}
    preview = await service.target_preview(db_session,a.owner,a.vehicle.id,wire.ConfigPreview.model_validate(payload))
    assert preview['items'][0]['resolved_attestation']['readings']['odometer_miles']['value'] == '125000'
    payload['seed']['attestation']['performed_on']='2020-01-01'
    with pytest.raises(HTTPException) as exc:
        await service.target_preview(db_session,a.owner,a.vehicle.id,wire.ConfigPreview.model_validate(payload))
    assert exc.value.detail['code']=='maintenance_invalid_reading'
    payload['seed']['attestation']['readings']['odometer_miles']['source_id']=str(foreign.id)
    with pytest.raises(HTTPException) as exc:
        await service.target_preview(db_session,a.owner,a.vehicle.id,wire.ConfigPreview.model_validate(payload))
    assert exc.value.status_code==404


@pytest.mark.asyncio
async def test_vehicle_merge_guard_keeps_archived_identity_and_reading_only_history(db_session):
    a = await seed(db_session)
    from app.db.models.vehicle import Vehicle
    losing = Vehicle(tenant_id=a.tenant.id,customer_id=a.customer.id,make='Test',model='Duplicate')
    db_session.add(losing);await db_session.commit()
    await service.guard_vehicle_merge(db_session,a.vehicle,losing)
    result,_=await create(db_session,a)
    p=await db_session.get(Program,UUID(result['program']['id']));p.archived_at=datetime.now(timezone.utc);await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await service.guard_vehicle_merge(db_session,losing,a.vehicle)
    assert exc.value.detail['code']=='maintenance_vehicle_merge_requires_review'
    losing.next_pm_miles=100000;await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await service.guard_vehicle_merge(db_session,a.vehicle,losing)
    assert exc.value.detail['code']=='maintenance_vehicle_merge_requires_review'


@pytest.mark.asyncio
async def test_rebaseline_generation_excludes_earlier_same_day_reading(db_session):
    a = await seed(db_session)
    first,_=await create(db_session,a)
    program_id=UUID(first['program']['id'])
    stamp=datetime.now(timezone.utc)
    old=Reading(tenant_id=a.tenant.id,vehicle_id=a.vehicle.id,observed_at=stamp-timedelta(minutes=1),created_at=stamp-timedelta(seconds=30),odometer_miles=120000,source='staff_observed',actor_id=a.owner.id,request_id=uuid4())
    db_session.add(old);await db_session.commit()
    day=stamp.astimezone(__import__('zoneinfo').ZoneInfo(a.tenant.timezone)).date().isoformat()
    initial={'kind':'baseline','attestation':{'performed_on':day,'readings':{'odometer_miles':{'kind':'manual','value':'1000','basis':'staff_observed','note':None},'engine_hours':None},'confirm_actual_service_readings':True}}
    payload={'purpose':'configuration','channel':'shop','program':{'program_id':str(program_id),'expected_version':1},'config':config(a),'action':'rebaseline','seed':initial,'reason':'Meter replaced'}
    preview=await service.target_preview(db_session,a.owner,a.vehicle.id,wire.ConfigPreview.model_validate(payload))
    update=wire.ProgramUpdate.model_validate({'channel':'shop','expected_version':1,'config':config(a),'targets':{'kind':'rebaseline','seed':initial,'reason':'Meter replaced','expected_target_fingerprint':preview['expected_target_fingerprint']}})
    result=await service.program_command(db_session,a.owner,a.vehicle.id,update,str(uuid4()),program_id=program_id)
    assert result['program']['targets']['odometer_miles']==2000
    assert result['program']['due']['miles']['reading']['comparison_value']=='1000'
    assert result['program']['due']['miles']['state']=='current'
    key=str(uuid4())
    fresh=wire.ReadingCreate.model_validate({'channel':'shop','observed_at':(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat(),'odometer_miles':1500,'engine_hours':None,'source':'staff_observed','note':None})
    await service.reading_command(db_session,a.owner,a.vehicle.id,fresh,key)
    assert (await service.program_page(db_session,a.owner,'shop',vehicle_id=a.vehicle.id))['items'][0]['due']['miles']['remaining']==500


def test_fleet_reading_projection_removes_private_nested_source_identity():
    original={'odometer_miles':{'source':'service_evidence','source_id':str(uuid4()),'value':'120000'},'engine_hours':None}
    assert service.safe_readings(original,'fleet')['odometer_miles']['source_id'] is None
    assert service.safe_readings(original,'shop')==original
    assert original['odometer_miles']['source_id'] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize('outgoing', [None, 0, 110000])
async def test_native_order_meters_are_never_actual_service_evidence(db_session, outgoing):
    from app.db.models.repair_order import RepairOrderStatus
    a = await seed(db_session)
    a.order.status = RepairOrderStatus.COMPLETED
    a.order.mileage_in, a.order.mileage_out = 100000, outgoing
    performed = datetime.now(timezone.utc).date() - timedelta(days=1)
    a.order.work_completed_at = datetime.combine(performed, datetime.min.time(), tzinfo=timezone.utc)
    await db_session.commit()
    attestation = wire.Attestation.model_validate({'performed_on': performed.isoformat(), 'confirm_actual_service_readings': True,
        'readings': {'odometer_miles': {'kind': 'source', 'source_kind': 'repair_order', 'source_id': str(a.order.id), 'meter': 'odometer_miles'}, 'engine_hours': None}})
    with pytest.raises(HTTPException) as error:
        await service.resolved_attestation(db_session, a.owner, 'shop', a.vehicle, a.tenant, attestation)
    assert error.value.status_code == 422 and error.value.detail['code'] == 'maintenance_invalid_reading'
    manual = attestation.model_dump(mode='json')
    manual['readings']['odometer_miles'] = {'kind': 'manual', 'value': '0', 'basis': 'staff_reported', 'note': None}
    accepted, _ = await service.resolved_attestation(db_session, a.owner, 'shop', a.vehicle, a.tenant, wire.Attestation.model_validate(manual))
    assert accepted['readings']['odometer_miles']['comparison_value'] == '0'
    assert accepted['readings']['odometer_miles']['observed_at'] is None
    assert accepted['readings']['odometer_miles']['observed_precision'] == 'date'
    assert a.order.mileage_in == 100000 and a.order.mileage_out == outgoing


@pytest.mark.asyncio
async def test_legacy_recognition_is_one_staff_reported_atomic_advance(db_session):
    from app.api.v1.endpoints import fleet
    from app.schemas.fleet import RecognizePMRequest
    from app.db.models.repair_order import RepairOrderStatus, RepairOrder
    from app.db.models.maintenance import MaintenanceCompletion as Completion
    from test_fleet_workflows import _seed_fleet
    tenant, vehicle, actor = await _seed_fleet(db_session)
    performed = datetime.now(timezone.utc).date() - timedelta(days=1)
    order = RepairOrder(id=uuid4(), tenant_id=tenant.id, customer_id=vehicle.customer_id, vehicle_id=vehicle.id,
        order_number='M1-' + uuid4().hex, description='Legacy actual', status=RepairOrderStatus.PAID, is_pm=False)
    db_session.add(order)
    await db_session.commit()
    request = RecognizePMRequest(repair_order_id=order.id, performed_on=performed, odometer=0)
    result = await fleet.recognize_existing_repair_as_pm(vehicle.id, request, db_session, actor)
    assert result.schedule_advanced and result.next_pm_miles == 25000
    evidence = await db_session.scalar(select(Completion).where(Completion.source_id == order.id))
    assert evidence.result == 'advanced' and evidence.readings['odometer_miles']['comparison_value'] == '0'
    assert evidence.readings['odometer_miles']['basis'] == 'staff_reported'
    assert evidence.readings['odometer_miles']['observed_at'] is None
    program = await db_session.scalar(select(Program).where(Program.vehicle_id == vehicle.id))
    assert program.current_cycle == 2 and program.controlling_completion_id == evidence.id
    with pytest.raises(HTTPException) as error:
        await fleet.recognize_existing_repair_as_pm(vehicle.id, request, db_session, actor)
    assert error.value.status_code == 409
    await db_session.rollback()
    assert await db_session.scalar(select(func.count(Completion.id))) == 1


@pytest.mark.asyncio
async def test_legacy_recognition_and_schedule_cannot_bypass_independent_program(db_session):
    from app.api.v1.endpoints import fleet
    from app.schemas.fleet import RecognizePMRequest, SchedulePMRequest
    from app.db.models.repair_order import RepairOrderStatus
    a = await seed(db_session)
    db_session.add(FleetMembership(tenant_id=a.tenant.id, vehicle_id=a.vehicle.id, fleet_customer_id=a.customer.id))
    a.order.status = RepairOrderStatus.COMPLETED
    await db_session.commit()
    await create(db_session, a)
    vehicle_id, order_id = a.vehicle.id, a.order.id
    for kind in ['recognize', 'schedule']:
        if kind == 'recognize':
            call = fleet.recognize_existing_repair_as_pm(vehicle_id, RecognizePMRequest(repair_order_id=order_id,
                performed_on=datetime.now(timezone.utc).date() - timedelta(days=1), odometer=100), db_session, a.owner)
        else:
            call = fleet.schedule_pm(vehicle_id, SchedulePMRequest(next_pm_miles=100), str(uuid4()), db_session, a.owner)
        with pytest.raises(HTTPException) as error:
            await call
        assert error.value.status_code == 409 and error.value.detail['code'] == 'maintenance_review_required'
        await db_session.rollback()
        await db_session.refresh(a.owner)
        await db_session.refresh(a.order)
        await db_session.refresh(a.vehicle)
        assert not a.order.is_pm and a.order.mileage_out is None and a.vehicle.next_pm_miles is None


@pytest.mark.asyncio
@pytest.mark.parametrize('observed,captured,value,expected_value,expected_admission,zone', [
    ('2026-10-16T18:39:00+00:00','2026-10-16T18:39:46+00:00','100713','101000','accepted','America/New_York'),
    ('2026-10-16T18:39:00+00:00','2026-10-16T19:10:00+00:00','100713','101000','accepted','America/New_York'),
    ('2026-10-16T19:05:00+00:00','2026-10-16T19:06:00+00:00','100800','100800','regression','America/New_York'),
    ('2026-10-16T18:39:00+00:00','2026-10-16T18:40:00+00:00','101500','101500','accepted','America/New_York'),
    ('2026-10-17T18:39:00+00:00','2026-10-17T18:40:00+00:00','100800','100800','regression','America/New_York'),
    ('2026-10-16T19:05:00+00:00',None,'100800','101000','accepted','America/New_York'),
    ('2026-10-15T18:39:00+00:00','2026-10-15T18:40:00+00:00','102000','101000','accepted','America/New_York'),
    ('2026-10-16T04:00:00+00:00','2026-10-16T04:01:00+00:00','100800','101000','accepted','Pacific/Honolulu'),
])
async def test_date_only_acceptance_is_same_local_day_admission_only(db_session,observed,captured,value,expected_value,expected_admission,zone):
    from types import SimpleNamespace
    from app.services import maintenance_rules as rules
    a=await seed(db_session)
    at=datetime.fromisoformat('2026-10-18T19:30:00+00:00')
    baseline=rules.observation('101000','odometer_miles',source='service_evidence',basis='staff_observed',observed_on='2026-10-16',as_of=at,zone=zone)
    candidate=rules.observation(value,'odometer_miles',source='maintenance_manual',basis='staff_observed',observed_at=observed,captured_at=captured,as_of=at,zone=zone)
    # The later-day row was already captured when historical evidence was entered.
    accepted='2026-10-18T19:03:00+00:00' if observed.startswith('2026-10-17') else '2026-10-16T19:03:00+00:00'
    program=SimpleNamespace(baseline_snapshot={'attestation':{'performed_on':'2026-10-16','readings':{'odometer_miles':baseline,'engine_hours':None}},'confirmed_at':accepted},controlling_completion_id=None)
    result=await service.current_readings(db_session,program,a.vehicle,at,zone,candidates={'odometer_miles':[candidate],'engine_hours':[]})
    assert result['odometer_miles']['value']==expected_value and result['odometer_miles']['admission']==expected_admission
    assert candidate['comparison_value']==value  # shared candidates are never mutated
