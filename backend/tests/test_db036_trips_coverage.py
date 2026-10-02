"""Minute source precision, complete imported aggregation, and audited CAS."""
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from app.db.models.fleet_trip import FleetTrip, FleetTripRevision
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.db.models.user import UserRole
from app.services.fleet_telemetry import now
from app.services.fleet_trips import list_trips
from scripts.import_motive_trips import parse_rows, run_import, parse_corrections, run_corrections, aware
from tests.test_db036_fleet_telemetry import prepared
from tests.test_db036_trips import document, baseline

pytestmark = pytest.mark.asyncio


def minute_document():
    d = document()
    start = (now()-timedelta(hours=3)).replace(second=0, microsecond=0)
    d['rows'][0].update(timestamp_precision='minute', started_at=start.isoformat(), ended_at=(start+timedelta(minutes=1)).isoformat(), driving_seconds=119)
    return d


async def test_minute_validation_and_legacy_digest():
    d = minute_document()
    assert parse_rows(d, now())[0].driving_seconds == 119
    for delta in ({'driving_seconds':120}, {'metrics':{'idle_seconds':120}}, {'timestamp_precision':'hour'}, {'started_at':(now()-timedelta(hours=3)).replace(second=1).isoformat()}):
        changed = minute_document(); changed['rows'][0].update(delta)
        with pytest.raises(ValueError): parse_rows(changed, now())
    d['rows'][0]['ended_at'] = d['rows'][0]['started_at']
    d['rows'][0]['driving_seconds'] = 59
    assert parse_rows(d, now())[0].driving_seconds == 59
    for duration in (0, 60):
        d['rows'][0]['driving_seconds'] = duration
        with pytest.raises(ValueError): parse_rows(d, now())
    d = minute_document()
    row = parse_rows(d, now())[0]
    d['rows'][0]['source_read_at'] = (row.ended_at+timedelta(seconds=59)).isoformat()
    with pytest.raises(ValueError): parse_rows(d, now())
    d['rows'][0]['source_read_at'] = (row.ended_at+timedelta(seconds=60)).isoformat()
    assert parse_rows(d, now())


async def test_multiple_trucks_full_pagination_summary(db_session, monkeypatch):
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    start = (now()-timedelta(days=2)).replace(second=0, microsecond=0)
    member.effective_from = start-timedelta(days=1)
    other = Vehicle(tenant_id=actor.tenant_id, customer_id=vehicle.customer_id, vin='2M8GDM9AXKP042788', year=2020, make='Example', model='Truck')
    db_session.add(other); await db_session.flush()
    db_session.add(FleetMembership(tenant_id=actor.tenant_id, vehicle_id=other.id, fleet_customer_id=vehicle.customer_id, effective_from=member.effective_from))
    await db_session.commit()
    rows=[]
    for i in range(52):
        d=minute_document()['rows'][0]
        d.update(started_at=(start+timedelta(minutes=i*2)).isoformat(), ended_at=(start+timedelta(minutes=i*2+1)).isoformat(), distance_miles=1, driving_seconds=60)
        if i%2: d.update(vin=other.vin, provider_vehicle_id='other')
        rows.append(d)
    await run_import(db_session, parse_rows({'rows':rows}, now()), actor.tenant_id, actor.id, True)
    page=await list_trips(db_session, actor.tenant_id, start.date(), now().date(), 'UTC', limit=50)
    assert len(page['items'])==50
    assert page['summary']==dict(trip_count=52, truck_count=2, coverage='partial', distance_miles=52, driving_seconds=3120)
    selected=await list_trips(db_session, actor.tenant_id, start.date(), now().date(), 'UTC', vehicle_id=vehicle.id, limit=1, offset=3)
    assert selected['summary']['trip_count']==26 and selected['summary']['truck_count']==1
    foreign=await list_trips(db_session, uuid4(), start.date(), now().date(), 'UTC')
    assert foreign['summary']==dict(trip_count=0, truck_count=0, coverage='partial', distance_miles=0, driving_seconds=0)
    vehicle.deleted_at=now(); await db_session.flush()
    page=await list_trips(db_session, actor.tenant_id, start.date(), now().date(), 'UTC')
    assert page['summary']['truck_count']==1 and page['summary']['trip_count']==26


async def test_minute_read_boundaries_and_import_atomicity(db_session, monkeypatch):
    actor, vehicle, member=await prepared(db_session, monkeypatch)
    member.effective_from=now()-timedelta(days=7); await db_session.commit()
    rows=parse_rows(minute_document(), now())
    row=rows[0]
    receipt=await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    trip=(await db_session.execute(select(FleetTrip))).scalar_one()
    async def total():
        return (await list_trips(db_session, actor.tenant_id, row.started_at.date(), now().date(), 'UTC'))['total']
    assert await total()==1
    trip.source_read_at=row.ended_at+timedelta(seconds=59); await db_session.flush()
    assert await total()==0
    trip.source_read_at=row.ended_at+timedelta(seconds=60); await db_session.flush()
    assert await total()==1
    monkeypatch.setattr('app.services.fleet_trips.now', lambda: row.ended_at+timedelta(seconds=59))
    assert await total()==0
    monkeypatch.setattr('app.services.fleet_trips.now', lambda: row.ended_at+timedelta(seconds=60))
    assert await total()==1
    # A current membership cannot expose a partly covered arrival minute.
    monkeypatch.setattr('app.services.fleet_trips.now', lambda: row.ended_at-timedelta(seconds=1))
    member.effective_to=row.ended_at+timedelta(seconds=59); await db_session.flush()
    from app.services.fleet_trips import visible_query
    query=visible_query(actor.tenant_id, row.started_at-timedelta(days=1), now(), row.ended_at+timedelta(seconds=60), dialect='sqlite')
    assert (await db_session.execute(query)).all()==[]
    member.effective_to=None
    monkeypatch.setattr('app.services.fleet_trips.now', now)
    # Membership still current at test time, but its historical start clips trip.
    member.effective_from=row.started_at+timedelta(seconds=1); await db_session.flush()
    assert await total()==0
    with pytest.raises(ValueError, match='membership'):
        await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    assert receipt['rows'][0]['trip_id']==str(trip.id)


async def correction_fixture(db, monkeypatch):
    actor, vehicle, member=await prepared(db, monkeypatch)
    member.effective_from=now()-timedelta(days=7); await db.commit()
    d=minute_document(); d['rows'][0].update(timestamp_precision='second', driving_seconds=60, metrics={**baseline(), 'idle_seconds':20})
    rows=parse_rows(d, now())
    await run_import(db, rows, actor.tenant_id, actor.id, True); await db.commit()
    trip=(await db.execute(select(FleetTrip))).scalar_one()
    replacement=rows[0].model_dump(mode='json')
    replacement.update(timestamp_precision='minute', driving_seconds=119, distance_miles=39.89, source_read_at=now().isoformat())
    correction=dict(trip_id=str(trip.id), expected_digest=trip.request_digest, reason='Verified measured source duration and distance', row=replacement)
    return actor, vehicle, member, trip, correction


async def test_correction_audit_dry_run_retry_and_preservation(db_session, monkeypatch):
    actor, vehicle, member, trip, correction=await correction_fixture(db_session, monkeypatch)
    old_capture=trip.captured_at; old_source=trip.source_read_at; old_metrics=trip.metrics.copy()
    corrections=parse_corrections({'corrections':[correction]}, now())
    plan=await run_corrections(db_session, corrections, actor.tenant_id, actor.id)
    assert plan['rows'][0]['action']=='would_correct'
    assert trip.distance_miles==40 and (await db_session.execute(select(func.count()).select_from(FleetTripRevision))).scalar_one()==0
    result=await run_corrections(db_session, corrections, actor.tenant_id, actor.id, True)
    await db_session.commit()
    assert result['rows'][0]['action']=='corrected' and trip.distance_miles==39.89
    audit=(await db_session.execute(select(FleetTripRevision))).scalar_one()
    assert audit.old_snapshot['distance_miles']==40 and audit.old_snapshot['request_digest']==correction['expected_digest']
    assert audit.old_snapshot['captured_at']==aware(old_capture).isoformat()
    assert audit.old_snapshot['source_read_at']==aware(old_source).isoformat()
    assert set(audit.old_snapshot)=={column.name for column in FleetTrip.__table__.columns}
    assert trip.metrics==old_metrics and vehicle.mileage==100
    retry=await run_corrections(db_session, corrections, actor.tenant_id, actor.id, True)
    assert retry['rows'][0]['action']=='unchanged'
    assert (await db_session.execute(select(func.count()).select_from(FleetTripRevision))).scalar_one()==1
    assert (await db_session.execute(select(func.count()).select_from(FleetTrip))).scalar_one()==1
    assert (await list_trips(db_session, actor.tenant_id, (now()-timedelta(days=1)).date(), now().date(), 'UTC'))['summary']['trip_count']==1


@pytest.mark.parametrize('case',['digest','tenant','actor','identity','distance','deleted','metrics','stale','batch'])
async def test_correction_failures_leave_everything_untouched(db_session, monkeypatch, case):
    actor, vehicle, member, trip, correction=await correction_fixture(db_session, monkeypatch)
    tenant=actor.tenant_id
    if case=='digest': correction['expected_digest']='0'*64
    if case=='tenant': tenant=uuid4()
    if case=='actor': actor.role=UserRole.FLEET_MANAGER
    if case=='identity': correction['row']['origin_label']='Different'
    if case=='distance': correction['row']['distance_miles']=41
    if case=='deleted': trip.deleted_at=now()
    if case=='metrics': correction['row']['metrics']=None
    if case=='stale': correction['row']['source_read_at']=(trip.source_read_at-timedelta(seconds=1)).isoformat()
    await db_session.flush()
    corrections=[correction]
    if case=='batch':
        second=dict(correction, trip_id=str(uuid4()), row={**correction['row'], 'provider_vehicle_id':'bad', 'started_at':(now()-timedelta(hours=4)).replace(second=0,microsecond=0).isoformat()})
        corrections.append(second)
    with pytest.raises(ValueError):
        await run_corrections(db_session, parse_corrections({'corrections':corrections}, now()), tenant, actor.id, True)
    assert trip.distance_miles==40
    assert (await db_session.execute(select(func.count()).select_from(FleetTripRevision))).scalar_one()==0
