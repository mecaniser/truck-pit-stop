"""Operational MPG import safety and transactional behavior."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.models.fleet_telemetry import FleetTelemetrySnapshot
from app.services import fleet_telemetry as telemetry
from scripts.import_motive_fuel_economy import make_body, parse_rows, run_import
from tests.test_db036_fleet_telemetry import VIN, prepared

pytestmark = pytest.mark.asyncio


def document():
    return {"period": "last_30_days", "rows": [{
        "unit": "77", "provider_vehicle_id": "fixture-77", "vin": VIN,
        "fuel_economy_mpg": 6.5,
        "source_read_at": (telemetry.now() - timedelta(seconds=10)).isoformat(),
    }]}


@pytest.mark.parametrize("mutation", [
    {"source_read_at": None}, {"source_read_at": "2026-10-02T12:00:00"},
    {"source_read_at": 1234}, {"fuel_economy_mpg": True},
    {"fuel_economy_mpg": -1}, {"fuel_economy_mpg": 101},
    {"fuel_economy_mpg": float("nan")}, {"fuel_economy_mpg": float("inf")},
    {"vin": "invalid"}, {"provider_vehicle_id": ""}, {"odometer_miles": 123},
])
async def test_reject_invalid_source(mutation):
    data = document()
    data["rows"][0].update(mutation)
    with pytest.raises(ValueError):
        parse_rows(data, telemetry.now())


async def test_dates_duplicates_period_and_deterministic_request():
    row = parse_rows(document(), telemetry.now())[0]
    assert make_body(row, uuid4()).client_request_id == make_body(row, uuid4()).client_request_id
    assert make_body(row, uuid4()).observed_at is None
    for date in (telemetry.now() + timedelta(seconds=1), telemetry.now() - timedelta(days=31)):
        bad = document()
        bad["rows"][0]["source_read_at"] = date.isoformat()
        with pytest.raises(ValueError):
            parse_rows(bad, telemetry.now())
    data = document()
    data["rows"].append(data["rows"][0])
    with pytest.raises(ValueError):
        parse_rows(data, telemetry.now())
    data = document()
    data["period"] = "last_7_days"
    with pytest.raises(ValueError):
        parse_rows(data, telemetry.now())


async def test_dry_run_apply_retry_and_canonical_preservation(db_session, monkeypatch):
    actor, vehicle, _ = await prepared(db_session, monkeypatch)
    rows = parse_rows(document(), telemetry.now())
    result = await run_import(db_session, rows, actor.tenant_id, actor.id)
    assert result["mode"] == "dry_run"
    assert (await db_session.execute(select(func.count()).select_from(FleetTelemetrySnapshot))).scalar_one() == 0
    result = await run_import(db_session, rows, actor.tenant_id, actor.id, apply=True)
    await db_session.commit()
    assert result["rows"][0]["created"]
    assert result["rows"][0]["visible"]
    again = await run_import(db_session, rows, actor.tenant_id, actor.id, apply=True)
    assert not again["rows"][0]["created"]
    assert result["rows"][0]["snapshot_id"] == again["rows"][0]["snapshot_id"]
    assert vehicle.mileage == 100


async def test_bad_second_row_and_foreign_actor_prevent_batch(db_session, monkeypatch):
    actor, _, _ = await prepared(db_session, monkeypatch)
    data = document()
    data["rows"].append({**data["rows"][0], "vin": "2M8GDM9AXKP042788", "provider_vehicle_id": "missing"})
    rows = parse_rows(data, telemetry.now())
    with pytest.raises(ValueError):
        await run_import(db_session, rows, actor.tenant_id, actor.id, apply=True)
    assert (await db_session.execute(select(func.count()).select_from(FleetTelemetrySnapshot))).scalar_one() == 0
    with pytest.raises(ValueError):
        await run_import(db_session, rows[:1], uuid4(), actor.id, apply=True)
