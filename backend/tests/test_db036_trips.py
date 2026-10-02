"""Trip import identity, authorization, temporal scope and read aggregation."""
from datetime import date, timedelta
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db.models.fleet_trip import FleetTrip
from app.db.models.user import UserRole
from app.services.fleet_telemetry import now
from app.services.fleet_trips import date_window, list_trips
from scripts.import_motive_trips import parse_rows, run_import
from tests.test_db036_fleet_telemetry import VIN, prepared

pytestmark = pytest.mark.asyncio


def document():
    stamp = now()
    return {"rows": [dict(vin=VIN, unit="77", provider_vehicle_id="motive-77",
        started_at=(stamp - timedelta(hours=3)).isoformat(), ended_at=(stamp - timedelta(hours=2)).isoformat(),
        source_read_at=(stamp - timedelta(minutes=1)).isoformat(), origin_label="City A", destination_label="City B",
        distance_miles=40, driving_seconds=3600, stops=None)]}


@pytest.mark.parametrize("change", [
    {"distance_miles": True}, {"distance_miles": float("nan")}, {"distance_miles": float("inf")},
    {"distance_miles": -1}, {"driving_seconds": 3601}, {"driving_seconds": True},
    {"vin": "bad"}, {"started_at": "2026-10-01T12:00:00"}, {"origin_label": ""},
    {"ended_at": (now()+timedelta(days=1)).isoformat()}, {"unknown": 1},
])
async def test_invalid(change):
    d = document(); d["rows"][0].update(change)
    with pytest.raises(ValueError):
        parse_rows(d, now())


async def test_timezone_boundaries():
    start, end = date_window(date(2026, 3, 8), date(2026, 3, 8), "America/New_York")
    assert (end-start).total_seconds() == 23*3600
    start, end = date_window(date(2026, 11, 1), date(2026, 11, 1), "America/New_York")
    assert (end-start).total_seconds() == 25*3600
    for a,b,z in [(date(2026,1,2),date(2026,1,1),"UTC"),(date(2026,1,1),date(2026,2,1),"UTC"),(date(2026,1,1),date(2026,1,1),"Bad/Zone")]:
        with pytest.raises(HTTPException) as exc:
            date_window(a,b,z)
        assert exc.value.status_code == 422


async def test_import_retry_conflict_summary_and_preservation(db_session, monkeypatch):
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    rows = parse_rows(document(), now())
    # Fixture membership starts very recently; make this synthetic membership cover trip history.
    member.effective_from = now() - timedelta(days=7)
    await db_session.commit()
    result = await run_import(db_session, rows, actor.tenant_id, actor.id)
    assert result["rows"][0]["action"] == "would_create"
    assert (await db_session.execute(select(func.count()).select_from(FleetTrip))).scalar_one() == 0
    first = await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    await db_session.commit()
    rows[0].source_read_at = now()
    retry = await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    assert retry["rows"][0]["action"] == "unchanged"
    assert retry["rows"][0]["trip_id"] == first["rows"][0]["trip_id"]
    assert vehicle.mileage == 100
    page = await list_trips(db_session, actor.tenant_id, (now()-timedelta(days=1)).date(), now().date(), "UTC", limit=1, offset=1)
    assert page["items"] == []
    assert page["summary"] == dict(trip_count=1, distance_miles=40, driving_seconds=3600)
    foreign = await list_trips(db_session, uuid4(), (now()-timedelta(days=1)).date(), now().date(), "UTC")
    assert foreign["total"] == 0
    with pytest.raises(HTTPException) as exc:
        await list_trips(db_session, uuid4(), now().date(), now().date(), "UTC", vehicle_id=vehicle.id)
    assert exc.value.status_code == 404
    rows[0].distance_miles = 41
    with pytest.raises(ValueError, match="Conflicting"):
        await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    member.effective_to = now() - timedelta(seconds=1)
    await db_session.commit()
    page = await list_trips(db_session, actor.tenant_id, (now()-timedelta(days=1)).date(), now().date(), "UTC")
    assert page["total"] == 0


async def test_invalid_batch_auth_membership(db_session, monkeypatch):
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    rows = parse_rows(document(), now())
    member.effective_from = now() - timedelta(days=7)
    await db_session.commit()
    with pytest.raises(ValueError):
        await run_import(db_session, rows, uuid4(), actor.id, True)
    actor.role = UserRole.FLEET_MANAGER
    await db_session.commit()
    with pytest.raises(ValueError):
        await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    actor.role = UserRole.GARAGE_OWNER
    await db_session.commit()
    bad = rows[0].model_copy(update={"provider_vehicle_id": "other", "vin": "2M8GDM9AXKP042788"})
    with pytest.raises(ValueError):
        await run_import(db_session, [rows[0],bad], actor.tenant_id, actor.id, True)
    assert (await db_session.execute(select(func.count()).select_from(FleetTrip))).scalar_one() == 0
    member.effective_from = now()
    await db_session.commit()
    with pytest.raises(ValueError, match="membership"):
        await run_import(db_session, rows, actor.tenant_id, actor.id, True)


async def test_route_defaults_and_role_guard(db_session, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from app.api.v1.endpoints.fleet import router
    from app.core.dependencies import get_db, get_current_active_user
    from app.db.models.tenant import Tenant
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    tenant = await db_session.get(Tenant, actor.tenant_id)
    tenant.timezone = "America/Chicago"
    await db_session.commit()
    app = FastAPI()
    app.include_router(router, prefix="/fleet")
    async def db_override():
        yield db_session
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_active_user] = lambda: actor
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        query = {"start_date":"2026-10-01", "end_date":"2026-10-02"}
        response = await client.get("/fleet/trips", params=query)
        assert response.status_code == 200
        assert response.json()["timezone"] == "America/Chicago"
        assert response.headers["cache-control"] == "no-store"
        for values in ({"limit": 101}, {"offset": -1}, {"timezone": "Bad/Zone"}):
            assert (await client.get("/fleet/trips", params={**query, **values})).status_code == 422
        assert (await client.get("/fleet/trips", params={**query, "vehicle_id": str(uuid4())})).status_code == 404
        actor.role = UserRole.CUSTOMER
        assert (await client.get("/fleet/trips", params=query)).status_code == 403


async def test_cross_midnight_departure_and_nullable_stops(db_session, monkeypatch):
    from datetime import datetime, timezone
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    start = datetime.combine((now()-timedelta(days=2)).date(), datetime.min.time(), timezone.utc) + timedelta(hours=23, minutes=30)
    member.effective_from = start - timedelta(days=1)
    await db_session.commit()
    d = document()
    d["rows"][0].update(started_at=start.isoformat(), ended_at=(start+timedelta(hours=1)).isoformat(), stops=[dict(location_label="City B", arrived_at=None, departed_at=None, idle_seconds=None)])
    await run_import(db_session, parse_rows(d, now()), actor.tenant_id, actor.id, True)
    first = await list_trips(db_session, actor.tenant_id, start.date(), start.date(), "UTC")
    following = await list_trips(db_session, actor.tenant_id, (start+timedelta(days=1)).date(), (start+timedelta(days=1)).date(), "UTC")
    assert first["total"] == 1 and first["summary"]["distance_miles"] == 40
    assert following["total"] == 0
    assert first["items"][0]["stops"][0]["arrived_at"] is None


@pytest.mark.parametrize("identity", ["duplicate_vin", "deleted_vehicle", "deleted_customer", "replaced_membership"])
async def test_identity_changes_hide_or_reject(db_session, monkeypatch, identity):
    from app.db.models.vehicle import Vehicle
    from app.db.models.customer import Customer
    from app.db.models.vehicle_relationship import FleetMembership
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    rows = parse_rows(document(), now())
    member.effective_from = now() - timedelta(days=7)
    await db_session.commit()
    await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    await db_session.commit()
    if identity == "duplicate_vin":
        db_session.add(Vehicle(tenant_id=actor.tenant_id, customer_id=vehicle.customer_id, vin=VIN, year=2020, make="Example", model="Truck"))
    elif identity == "deleted_vehicle":
        vehicle.deleted_at = now()
    elif identity == "deleted_customer":
        (await db_session.get(Customer, vehicle.customer_id)).deleted_at = now()
    else:
        member.effective_to = now()-timedelta(seconds=1)
        db_session.add(FleetMembership(tenant_id=actor.tenant_id, vehicle_id=vehicle.id, fleet_customer_id=vehicle.customer_id, effective_from=now()))
    await db_session.commit()
    with pytest.raises(ValueError):
        await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    if identity != "duplicate_vin":
        page = await list_trips(db_session, actor.tenant_id, (now()-timedelta(days=1)).date(), now().date(), "UTC")
        assert page["total"] == 0


async def test_input_duplicates_unknown_stops_and_time_numbers():
    d = document()
    with pytest.raises(ValueError):
        parse_rows({"rows": d["rows"] * 2}, now())
    for key in ("started_at", "ended_at", "source_read_at"):
        altered = document(); altered["rows"][0][key] = 1234567890
        with pytest.raises(ValueError):
            parse_rows(altered, now())
    altered = document()
    altered["rows"][0]["stops"] = [dict(location_label="Example", arrived_at=None, departed_at=None, idle_seconds=-1)]
    with pytest.raises(ValueError):
        parse_rows(altered, now())


def baseline():
    return {"estimate_baseline_mpg": 6.5,
            "estimate_baseline_captured_at": (now()-timedelta(days=1)).isoformat(),
            "estimate_baseline_period": "last_30_days"}


@pytest.mark.parametrize("metrics", [
    {"fuel_used_gallons": -1}, {"fuel_used_gallons": 100001}, {"fuel_used_gallons": "unknown"}, {"fuel_used_gallons": True}, {"fuel_used_gallons": float("nan")},
    {"fuel_used_gallons": float("inf")}, {"idle_seconds": True}, {"idle_seconds": -1},
    {"idle_seconds": 3601}, {"fuel_start_percent": 101}, {"fuel_end_percent": -1},
    {"estimate_baseline_mpg": 6.5}, {"estimate_baseline_captured_at": "2026-10-02T12:00:00"},
    {"trip_mpg": 5}, {"estimated_fuel_gallons": 5},
])
async def test_invalid_metrics(metrics):
    d = document(); d["rows"][0]["metrics"] = metrics
    with pytest.raises(ValueError):
        parse_rows(d, now())


async def test_baseline_dates_numeric_validation():
    for change in ({"estimate_baseline_mpg": 0}, {"estimate_baseline_mpg": 101}, {"estimate_baseline_mpg": True},
                   {"estimate_baseline_mpg": float("inf")},
                   {"estimate_baseline_period": "last_7_days"},
                   {"estimate_baseline_captured_at": now().isoformat()},
                   {"estimate_baseline_captured_at": (now()-timedelta(days=31)).isoformat()}):
        d = document(); d["rows"][0]["metrics"] = {**baseline(), **change}
        with pytest.raises(ValueError):
            parse_rows(d, now())


async def test_metric_calculations_preserve_zero_and_actual_precedence():
    from app.services.fleet_trips import computed_metrics
    assert computed_metrics(None, 40) is None
    unknown = computed_metrics({}, 40)
    assert unknown["trip_mpg"] is None and unknown["estimated_fuel_gallons"] is None
    estimated = computed_metrics(baseline(), 65)
    assert estimated["estimated_fuel_gallons"] == 10
    assert estimated["trip_mpg"] is None
    actual = computed_metrics({**baseline(), "fuel_used_gallons": 5, "fuel_start_percent": 0, "idle_seconds": 0}, 40)
    assert actual["trip_mpg"] == 8 and actual["estimated_fuel_gallons"] is None
    assert actual["fuel_start_percent"] == 0 and actual["idle_seconds"] == 0
    zero = computed_metrics({**baseline(), "fuel_used_gallons": 0}, 40)
    assert zero["fuel_used_gallons"] == 0
    assert zero["trip_mpg"] is None and zero["estimated_fuel_gallons"] is None
    assert computed_metrics({"fuel_used_gallons": 5}, 0)["trip_mpg"] == 0


async def test_metrics_import_roundtrip_retry_and_legacy_hash(db_session, monkeypatch):
    import hashlib
    import json
    from scripts.import_motive_trips import digest
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = now()-timedelta(days=7)
    await db_session.commit()
    d = document()
    old_row = parse_rows(d, now())[0]
    old_payload = old_row.model_dump(mode="json", exclude={"source_read_at", "metrics"})
    assert digest(old_row) == hashlib.sha256(json.dumps(old_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    from app.schemas.fleet_trip import TripMetrics
    old_row.metrics = TripMetrics()
    assert digest(old_row) == hashlib.sha256(json.dumps(old_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    d["rows"][0]["metrics"] = {**baseline(), "idle_seconds": 0, "fuel_end_percent": 0}
    rows = parse_rows(d, now())
    receipt = await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    await db_session.commit()
    retry = await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    assert retry["rows"][0]["action"] == "unchanged"
    assert retry["rows"][0]["trip_id"] == receipt["rows"][0]["trip_id"]
    page = await list_trips(db_session, actor.tenant_id, (now()-timedelta(days=1)).date(), now().date(), "UTC")
    metrics = page["items"][0]["metrics"]
    assert metrics["estimated_fuel_gallons"] == pytest.approx(40/6.5)
    assert metrics["trip_mpg"] is None and metrics["idle_seconds"] == 0 and metrics["fuel_end_percent"] == 0
    assert metrics["estimate_baseline_captured_at"] == rows[0].metrics.estimate_baseline_captured_at.isoformat().replace("+00:00", "Z")
    rows[0].metrics.fuel_used_gallons = 5
    with pytest.raises(ValueError, match="Conflicting"):
        await run_import(db_session, rows, actor.tenant_id, actor.id, True)
    assert vehicle.mileage == 100


@pytest.mark.parametrize("metric", ["fuel_used_gallons", "estimate_baseline_mpg"])
async def test_reject_nonfinite_derived_metric(metric):
    d = document()
    d["rows"][0]["metrics"] = {**(baseline() if metric == "estimate_baseline_mpg" else {}), metric: 1e-309}
    with pytest.raises(ValueError, match="nonfinite derived"):
        parse_rows(d, now())
