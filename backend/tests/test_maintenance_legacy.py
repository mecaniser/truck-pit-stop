"""DB134 legacy adapter regressions from independent boundary review."""
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func
from app.api.v1.endpoints import fleet
from app.schemas.fleet import RecognizePMRequest
from app.services import maintenance as svc
from app.db.models.maintenance import MaintenanceProgram as Program, MaintenanceCompletion as Completion, MaintenanceProgramEvent as Event, MaintenanceWorkLink as Link
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.user import UserRole
from test_fleet_workflows import _seed_fleet

@pytest.fixture
def db_session(db_session):
    db_session.autoflush = False
    return db_session

async def order(db, tenant, vehicle, performed=None):
    item = RepairOrder(id=uuid4(), tenant_id=tenant.id, customer_id=vehicle.customer_id, vehicle_id=vehicle.id,
        order_number='INDEPENDENT-' + uuid4().hex, description='Synthetic independent review',
        status=RepairOrderStatus.PAID, is_pm=False, is_fleet_work=True,
        work_completed_at=datetime.combine(performed, datetime.min.time(), tzinfo=timezone.utc) if performed else None)
    db.add(item)
    await db.commit()
    return item

@pytest.mark.parametrize('invalid', [True, '100', 100.0, 100000000])
def test_legacy_reading_wire_is_strict(invalid):
    with pytest.raises(ValidationError):
        RecognizePMRequest.model_validate({'repair_order_id': str(uuid4()), 'performed_on': '2026-10-01', 'odometer': invalid})

def test_legacy_wire_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RecognizePMRequest.model_validate({'repair_order_id': str(uuid4()), 'performed_on': '2026-10-01', 'odometer': 100, 'actor_id': str(uuid4())})

@pytest.mark.asyncio
async def test_legacy_date_uses_shop_day(db_session, monkeypatch):
    tenant, vehicle, actor = await _seed_fleet(db_session)
    tenant.timezone = 'Australia/Sydney'
    await db_session.commit()
    class ServerDate(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 16)
    monkeypatch.setattr(fleet, 'date', ServerDate)
    monkeypatch.setattr(svc, 'now', lambda: datetime(2026, 10, 16, 22, tzinfo=timezone.utc))
    item = await order(db_session, tenant, vehicle, date(2026, 10, 17))
    result = await fleet.recognize_existing_repair_as_pm(vehicle.id, RecognizePMRequest(repair_order_id=item.id, performed_on=date(2026, 10, 17), odometer=0), db_session, actor)
    assert result.schedule_advanced

@pytest.mark.asyncio
async def test_older_legacy_action_does_not_replace_newer_m1_controlling_evidence(db_session):
    tenant, vehicle, actor = await _seed_fleet(db_session)
    recent_day = date.today() - timedelta(days=2)
    recent = await order(db_session, tenant, vehicle, recent_day)
    body = RecognizePMRequest(repair_order_id=recent.id, performed_on=recent_day, odometer=100000)
    program, attestation = await svc.prepare_legacy_recognition(db_session, actor, vehicle, recent, body)
    evidence = await svc.record_legacy_recognition(db_session, actor, vehicle, recent, body, program, attestation, advance=True)
    await db_session.commit()
    # Contract-valid M1 evidence need not mutate the native source's is_pm flag.
    assert not recent.is_pm
    before = (program.current_cycle, program.controlling_completion_id, program.target_miles, program.target_due_on, vehicle.next_pm_miles, vehicle.pm_due_date)
    older_day = recent_day - timedelta(days=10)
    older = await order(db_session, tenant, vehicle, older_day)
    result = await fleet.recognize_existing_repair_as_pm(vehicle.id, RecognizePMRequest(repair_order_id=older.id, performed_on=older_day, odometer=90000), db_session, actor)
    await db_session.refresh(program)
    await db_session.refresh(vehicle)
    after = (program.current_cycle, program.controlling_completion_id, program.target_miles, program.target_due_on, vehicle.next_pm_miles, vehicle.pm_due_date)
    assert not result.schedule_advanced and after == before

@pytest.mark.asyncio
@pytest.mark.parametrize('blocked', ['active', 'pending_evidence', 'review_required', 'program_review'])
async def test_legacy_refusal_does_not_change_source_or_scalars(db_session, blocked):
    tenant, vehicle, actor = await _seed_fleet(db_session)
    item = await order(db_session, tenant, vehicle)
    program = await svc.sync_legacy_configuration(db_session, actor, vehicle, force=True)
    if blocked == 'program_review':
        program.review_codes = ['source_changed']
    else:
        db_session.add(Link(id=uuid4(), tenant_id=tenant.id, program_id=program.id, cycle=1, repair_order_id=item.id,
            state=blocked, version=1, program_version=program.version, captured_config={}, captured_targets={}))
    await db_session.commit()
    before = (item.is_pm, item.mileage_out, item.work_completed_at, vehicle.mileage, vehicle.next_pm_miles, vehicle.pm_due_date)
    with pytest.raises(HTTPException) as error:
        await fleet.recognize_existing_repair_as_pm(vehicle.id, RecognizePMRequest(repair_order_id=item.id, performed_on=date.today()-timedelta(days=1), odometer=10), db_session, actor)
    assert error.value.status_code == 409 and error.value.detail['code'] == 'maintenance_review_required'
    assert before == (item.is_pm, item.mileage_out, item.work_completed_at, vehicle.mileage, vehicle.next_pm_miles, vehicle.pm_due_date)
    assert await db_session.scalar(select(func.count(Completion.id))) == 0
    assert await db_session.scalar(select(func.count(Event.id))) == 1

@pytest.mark.parametrize('role', [UserRole.RECEPTIONIST, UserRole.MECHANIC, UserRole.DRIVER])
def test_legacy_route_role_guard(role):
    from types import SimpleNamespace
    with pytest.raises(HTTPException) as error:
        fleet.require_fleet_access(SimpleNamespace(role=role, tenant_id=uuid4()))
    assert error.value.status_code == 403

@pytest.mark.asyncio
async def test_wire_overrange_returns_validation_not_unhandled_exception(db_session):
    tenant, vehicle, actor = await _seed_fleet(db_session)
    item = await order(db_session, tenant, vehicle)
    # Invalid wire values must stop at validation, never an internal Decimal error.
    try:
        body = RecognizePMRequest(repair_order_id=item.id, performed_on=date.today()-timedelta(days=1), odometer=100000000)
    except ValidationError:
        return
    with pytest.raises(HTTPException) as error:
        await fleet.recognize_existing_repair_as_pm(vehicle.id, body, db_session, actor)
    assert error.value.status_code == 422

@pytest.mark.asyncio
@pytest.mark.parametrize('problem', ['foreign_source', 'deleted_source', 'nonmember'])
async def test_legacy_scope_refusal_is_404_without_source_change(db_session, problem):
    from app.db.models.vehicle_relationship import FleetMembership
    tenant, vehicle, actor = await _seed_fleet(db_session)
    item = await order(db_session, tenant, vehicle)
    if problem == 'foreign_source':
        other_tenant, other_vehicle, _ = await _seed_fleet(db_session)
        item = await order(db_session, other_tenant, other_vehicle)
    elif problem == 'deleted_source':
        item.deleted_at = datetime.now(timezone.utc)
    else:
        membership = await db_session.scalar(select(FleetMembership).where(FleetMembership.vehicle_id == vehicle.id))
        membership.effective_to = date.today()
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await fleet.recognize_existing_repair_as_pm(vehicle.id, RecognizePMRequest(repair_order_id=item.id, performed_on=date.today()-timedelta(days=1), odometer=10), db_session, actor)
    assert error.value.status_code == 404
    assert not item.is_pm and item.mileage_out is None and vehicle.next_pm_miles is None
    assert await db_session.scalar(select(func.count(Program.id))) == 0
    assert await db_session.scalar(select(func.count(Completion.id))) == 0

@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['regression', 'older_flagged_source'])
async def test_legacy_regression_refusal_and_existing_older_history(db_session, action):
    tenant, vehicle, actor = await _seed_fleet(db_session)
    newer_day = date.today()-timedelta(days=10)
    newer = await order(db_session, tenant, vehicle, newer_day)
    await fleet.recognize_existing_repair_as_pm(vehicle.id, RecognizePMRequest(repair_order_id=newer.id, performed_on=newer_day, odometer=100000), db_session, actor)
    program = await db_session.scalar(select(Program).where(Program.vehicle_id==vehicle.id))
    saved = (program.current_cycle, program.controlling_completion_id, program.target_miles, program.target_due_on, vehicle.next_pm_miles, vehicle.pm_due_date)
    candidate_day = newer_day + timedelta(days=1) if action == 'regression' else newer_day - timedelta(days=1)
    candidate = await order(db_session, tenant, vehicle, candidate_day)
    request = RecognizePMRequest(repair_order_id=candidate.id, performed_on=candidate_day, odometer=90000)
    if action == 'regression':
        with pytest.raises(HTTPException) as error:
            await fleet.recognize_existing_repair_as_pm(vehicle.id, request, db_session, actor)
        assert error.value.status_code==422 and error.value.detail['code']=='maintenance_invalid_reading'
        assert not candidate.is_pm and candidate.mileage_out is None
    else:
        result = await fleet.recognize_existing_repair_as_pm(vehicle.id, request, db_session, actor)
        assert not result.schedule_advanced
        completion = await db_session.scalar(select(Completion).where(Completion.source_id==candidate.id))
        assert completion.result=='history_only'
    assert saved == (program.current_cycle, program.controlling_completion_id, program.target_miles, program.target_due_on, vehicle.next_pm_miles, vehicle.pm_due_date)


@pytest.mark.asyncio
async def test_one_time_legacy_package_retains_defaults_and_maps_actual_order(db_session):
    from app.db.models.service import Service
    from app.db.models.fleet import VehiclePMService
    from app.db.models.maintenance import MaintenanceOperationLink as Mapping
    from app.db.models.labor import Labor
    from app.schemas.fleet import SchedulePMRequest
    tenant, vehicle, actor = await _seed_fleet(db_session)
    templates = [Service(id=uuid4(), tenant_id=tenant.id, name=name, duration_minutes=60) for name in ['A', 'B', 'C']]
    db_session.add_all(templates)
    await db_session.flush()
    await fleet._set_vehicle_pm_services(db_session, tenant.id, vehicle.id, templates[:2])
    legacy = await svc.sync_legacy_configuration(db_session, actor, vehicle)
    await db_session.commit()
    default_ids = [str(row.id) for row in templates[:2]]
    key = str(uuid4())
    body = SchedulePMRequest(service_ids=[templates[0].id, templates[2].id], save_as_default=False, create_work_order=True)
    await fleet.schedule_pm(vehicle.id, body, key, db_session, actor)
    repeat = await fleet.schedule_pm(vehicle.id, body, key, db_session, actor)
    await db_session.refresh(legacy)
    assert [row['id'] for row in legacy.legacy_package] == default_ids
    assert set((await db_session.scalars(select(VehiclePMService.service_id).where(VehiclePMService.vehicle_id == vehicle.id))).all()) == {row.id for row in templates[:2]}
    links = list((await db_session.scalars(select(Link).where(Link.program_id == legacy.id))).all())
    assert len(links) == 1
    assert [row['id'] for row in links[0].captured_config['legacy_package']] == [str(templates[0].id), str(templates[2].id)]
    assert await db_session.scalar(select(func.count(Mapping.id)).where(Mapping.work_link_id == links[0].id)) == 2
    assert await db_session.scalar(select(func.count(Labor.id)).where(Labor.repair_order_id == links[0].repair_order_id)) == 2
    saved_order = await db_session.get(RepairOrder, links[0].repair_order_id)
    await svc.order_lifecycle(db_session, actor, saved_order, 'delete')
    saved_order.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    await svc.order_lifecycle(db_session, actor, saved_order, 'restore')
    saved_order.deleted_at = None
    await db_session.commit()
    assert links[0].state == 'active' and len(links[0].captured_config['legacy_package']) == 2
    from app.schemas import maintenance as wire
    from test_maintenance_evidence import actual
    for labor in (await db_session.scalars(select(Labor).where(Labor.repair_order_id == saved_order.id))).all():
        labor.execution_status = 'completed'
        labor.completed_at = datetime.now(timezone.utc)
    saved_order.status = RepairOrderStatus.PENDING_REVIEW
    saved_order.work_completed_at = datetime.now(timezone.utc)
    await db_session.commit()
    summary = await svc.order_maintenance(db_session, actor, 'fleet', saved_order.id)
    entries = [{'work_link_id': str(links[0].id), 'expected_link_version': links[0].version,
        'program': {'program_id': str(legacy.id), 'expected_version': legacy.version}, 'attestation': actual('100000')}]
    preview = await svc.target_preview(db_session, actor, vehicle.id, wire.CompletionPreview.model_validate({
        'purpose': 'completion', 'channel': 'fleet', 'repair_order_id': str(saved_order.id),
        'expected_review_fingerprint': summary['expected_review_fingerprint'], 'entries': entries}))
    assert preview['items'][0]['outcome'] == 'advanced'
    review = wire.MaintenanceReview.model_validate({'request_id':str(uuid4()), 'expected_review_fingerprint':summary['expected_review_fingerprint'],
        'expected_target_fingerprint':preview['expected_target_fingerprint'], 'entries':entries})
    prepared = await svc.prepare_finalization(db_session,actor,saved_order,review,channel='fleet')
    saved_order.status = RepairOrderStatus.COMPLETED
    result = await svc.finish_finalization(db_session,actor,saved_order,prepared)
    await db_session.commit()
    assert len(result['items']) == 1 and result['items'][0]['result'] == 'advanced'
    assert legacy.current_cycle == 2 and vehicle.next_pm_miles == 125000
    from app.services.internal_fleet import next_pm_service_day
    assert vehicle.pm_due_date == next_pm_service_day(date.fromisoformat(actual()['performed_on']) + timedelta(days=42))
    assert [row['id'] for row in legacy.legacy_package] == default_ids


@pytest.mark.asyncio
async def test_legacy_schedule_only_saves_default_without_claim(db_session):
    from app.db.models.service import Service
    from app.schemas.fleet import SchedulePMRequest
    tenant, vehicle, actor = await _seed_fleet(db_session)
    template = Service(id=uuid4(), tenant_id=tenant.id, name='Saved default', duration_minutes=60)
    db_session.add(template)
    await db_session.commit()
    await fleet.schedule_pm(vehicle.id, SchedulePMRequest(service_ids=[template.id], save_as_default=True,
        create_work_order=False, next_pm_miles=123000), str(uuid4()), db_session, actor)
    program = await db_session.scalar(select(Program).where(Program.vehicle_id == vehicle.id))
    assert program.target_miles == 123000 and program.legacy_package[0]['id'] == str(template.id)
    assert await db_session.scalar(select(func.count(Link.id))) == 0
