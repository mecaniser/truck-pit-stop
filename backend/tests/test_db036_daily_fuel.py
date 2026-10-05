"""Source fuel must remain distinct, immutable, date-scoped and tenant-isolated."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db.models.fleet_fuel import FleetFuelDaily
from app.db.models.user import UserRole
from app.services.fleet_telemetry import now
from app.services.fleet_fuel import list_fuel_daily
from app.schemas.fleet_fuel import FuelDailyPage
from scripts.import_motive_daily_fuel import parse_rows, run_import, digest
from tests.test_db036_fleet_telemetry import VIN, prepared

pytestmark = pytest.mark.asyncio


def document():
    return {"rows": [dict(vin=VIN, unit="77", provider_vehicle_id="motive-77", provider_company_id="company-77",
        report_date=(now()-timedelta(days=3)).date().isoformat(), source_read_at=now().isoformat(),
        driving_fuel_gallons=30, idling_fuel_gallons=2.1, reported_total_fuel_gallons=32.2,
        source_distance_miles=180, source_driving_seconds=12000, source_idling_seconds=3000,
        source_receipt_sha256="a"*64, identity_receipt_sha256="b"*64)]}


@pytest.mark.parametrize("change", [
    {"driving_fuel_gallons": True}, {"idling_fuel_gallons": float("nan")}, {"reported_total_fuel_gallons": float("inf")},
    {"driving_fuel_gallons": -1}, {"source_driving_seconds": True}, {"source_idling_seconds": 2678401},
    {"vin": "bad"}, {"source_read_at": "2026-10-01T12:00:00"}, {"provider_company_id": ""},
    {"source_read_at": (now()+timedelta(days=1)).isoformat()}, {"estimated_fuel_gallons": 4},
    {"report_date": now().date().isoformat()}, {"report_date": 1234},
    {"source_timezone": "America/New_York"}, {"timezone_status": "verified"},
    {"reported_total_fuel_gallons": 40}, {"source_receipt_sha256": "bad"},
    {"driving_fuel_gallons": None, "idling_fuel_gallons": None, "reported_total_fuel_gallons": None},
])
async def test_invalid(change):
    d = document(); d["rows"][0].update(change)
    with pytest.raises((ValueError, KeyError)):
        parse_rows(d, now())


async def test_identity_duplicates_and_windows():
    d=document(); d["rows"].append(dict(d["rows"][0]))
    with pytest.raises(ValueError): parse_rows(d,now())
    row=parse_rows(document(),now())[0]
    start,end=row.membership_window()
    assert (end-start).total_seconds()==50*3600
    assert start.hour==10 and end.hour==12
    original=digest(row)
    row.driving_fuel_gallons=Decimal('30.000')
    row.source_receipt_sha256='c'*64
    row.source_read_at=now()
    assert digest(row)==original


async def test_import_replay_read_preserves_trip_and_vehicle(db_session, monkeypatch):
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = now()-timedelta(days=10)
    await db_session.commit()
    rows=parse_rows(document(),now()); day=rows[0].report_date
    result=await run_import(db_session,rows,actor.tenant_id,actor.id)
    assert result['rows'][0]['action']=='would_create'
    assert (await db_session.execute(select(func.count()).select_from(FleetFuelDaily))).scalar_one()==0
    first=await run_import(db_session,rows,actor.tenant_id,actor.id,True)
    await db_session.commit()
    replay=await run_import(db_session,rows,actor.tenant_id,actor.id,True)
    assert replay['rows'][0]['action']=='unchanged'
    assert first['rows'][0]['fuel_id']==replay['rows'][0]['fuel_id']
    assert vehicle.mileage==100
    page=await list_fuel_daily(db_session,actor.tenant_id,day,day)
    parsed=FuelDailyPage.model_validate(page).model_dump(mode='json')
    assert parsed['items'][0]['driving_fuel_gallons']==30
    assert parsed['items'][0]['idling_fuel_gallons']==2.1
    assert parsed['items'][0]['reported_total_fuel_gallons']==32.2
    assert parsed['items'][0]['source_timezone'] is None
    assert parsed['items'][0]['timezone_status']=='unverified'
    assert 'estimated_fuel_gallons' not in parsed['items'][0]
    assert parsed['date_basis']=='source_report_date'
    assert (await list_fuel_daily(db_session,actor.tenant_id,day,day,limit=1,offset=1))['items']==[]
    assert (await list_fuel_daily(db_session,uuid4(),day,day))['total']==0
    with pytest.raises(HTTPException) as exc:
        await list_fuel_daily(db_session,uuid4(),day,day,vehicle_id=vehicle.id)
    assert exc.value.status_code==404
    rows[0].driving_fuel_gallons=Decimal('30.1')
    with pytest.raises(ValueError,match='Conflicting'):
        await run_import(db_session,rows,actor.tenant_id,actor.id,True)
    member.effective_to=now()-timedelta(seconds=1)
    await db_session.commit()
    assert (await list_fuel_daily(db_session,actor.tenant_id,day,day))['total']==0


async def test_auth_atomic_batch_and_conservative_membership(db_session,monkeypatch):
    actor,vehicle,member=await prepared(db_session,monkeypatch)
    member.effective_from=now()-timedelta(days=10)
    await db_session.commit()
    rows=parse_rows(document(),now())
    with pytest.raises(ValueError): await run_import(db_session,rows,uuid4(),actor.id,True)
    actor.role=UserRole.FLEET_MANAGER
    await db_session.commit()
    with pytest.raises(ValueError): await run_import(db_session,rows,actor.tenant_id,actor.id,True)
    actor.role=UserRole.GARAGE_OWNER
    await db_session.commit()
    bad=rows[0].model_copy(update={'vin':'2M8GDM9AXKP042788','provider_vehicle_id':'other'})
    with pytest.raises(ValueError): await run_import(db_session,[rows[0],bad],actor.tenant_id,actor.id,True)
    assert (await db_session.execute(select(func.count()).select_from(FleetFuelDaily))).scalar_one()==0
    member.effective_from=rows[0].membership_window()[0]+timedelta(seconds=1)
    await db_session.commit()
    with pytest.raises(ValueError,match='membership'): await run_import(db_session,rows,actor.tenant_id,actor.id,True)


async def test_route_bounds_roles_and_cache(db_session,monkeypatch):
    import httpx
    from fastapi import FastAPI
    from app.api.v1.endpoints.fleet import router
    from app.core.dependencies import get_db,get_current_active_user
    actor,_,_=await prepared(db_session,monkeypatch)
    app=FastAPI();app.include_router(router,prefix='/fleet')
    async def db_override(): yield db_session
    app.dependency_overrides[get_db]=db_override
    app.dependency_overrides[get_current_active_user]=lambda:actor
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        query={'start_date':'2026-09-01','end_date':'2026-09-30'}
        response=await client.get('/fleet/fuel-daily',params=query)
        assert response.status_code==200
        assert response.headers['cache-control']=='no-store'
        assert response.json()['date_basis']=='source_report_date'
        for changes in ({'limit':101},{'offset':-1},{'end_date':'2026-10-02'},{'end_date':'2026-08-31'}):
            assert (await client.get('/fleet/fuel-daily',params={**query,**changes})).status_code==422
        actor.role=UserRole.CUSTOMER
        assert (await client.get('/fleet/fuel-daily',params=query)).status_code==403


async def test_zero_is_a_record_missing_day_not_zero_and_page_reconciles(db_session,monkeypatch):
    actor,vehicle,member=await prepared(db_session,monkeypatch)
    member.effective_from=now()-timedelta(days=10)
    await db_session.commit()
    d=document(); zero=dict(d['rows'][0],report_date=(now()-timedelta(days=4)).date().isoformat(),
        driving_fuel_gallons=0,idling_fuel_gallons=0,reported_total_fuel_gallons=0,source_distance_miles=0)
    d['rows'].append(zero)
    rows=parse_rows(d,now())
    await run_import(db_session,rows,actor.tenant_id,actor.id,True)
    await db_session.commit()
    start,end=rows[1].report_date,rows[0].report_date
    pages=[await list_fuel_daily(db_session,actor.tenant_id,start,end,limit=1,offset=i) for i in range(2)]
    assert all(p['total']==2 for p in pages)
    assert len({p['items'][0]['id'] for p in pages})==2
    assert pages[0]['items'][0]['driving_fuel_gallons']==0
    assert (await list_fuel_daily(db_session,actor.tenant_id,end+timedelta(days=1),end+timedelta(days=1)))['total']==0


@pytest.mark.parametrize('mutation',['deleted_vehicle','deleted_customer','ended_member','changed_member','duplicate_vin'])
async def test_hidden_identity_and_import_reject(db_session,monkeypatch,mutation):
    from app.db.models.customer import Customer
    from app.db.models.vehicle import Vehicle
    actor,vehicle,member=await prepared(db_session,monkeypatch)
    member.effective_from=now()-timedelta(days=10)
    await db_session.commit()
    rows=parse_rows(document(),now());day=rows[0].report_date
    await run_import(db_session,rows,actor.tenant_id,actor.id,True)
    await db_session.commit()
    if mutation=='deleted_vehicle': vehicle.deleted_at=now()
    elif mutation=='deleted_customer':
        customer=await db_session.get(Customer,member.fleet_customer_id);customer.deleted_at=now()
    elif mutation=='ended_member': member.effective_to=now()-timedelta(seconds=1)
    elif mutation=='changed_member': member.effective_from=now()-timedelta(days=1)
    else:
        db_session.add(Vehicle(tenant_id=actor.tenant_id,customer_id=member.fleet_customer_id,vin=VIN,unit_number='duplicate',make='Test',model='Test',year=2020))
    await db_session.commit()
    with pytest.raises(ValueError): await run_import(db_session,rows,actor.tenant_id,actor.id,True)
    if mutation!='duplicate_vin':
        assert (await list_fuel_daily(db_session,actor.tenant_id,day,day))['total']==0


async def test_provider_duration_longer_than_day_preserved(db_session, monkeypatch):
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=10)
    await db_session.commit()
    d = document()
    d["rows"][0].update(source_driving_seconds=117600, source_idling_seconds=117660)
    rows = parse_rows(d, now())
    assert rows[0].source_idling_seconds == 117660
    await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    await db_session.commit()
    page = await list_fuel_daily(db_session, actor.tenant_id, rows[0].report_date, rows[0].report_date)
    assert page["items"][0]["source_driving_seconds"] == 117600
    assert page["items"][0]["source_idling_seconds"] == 117660
