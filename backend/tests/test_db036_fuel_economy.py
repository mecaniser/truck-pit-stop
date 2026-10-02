"""Fuel economy capture and isolated sparse field projection."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import update

from app.db.models.fleet_telemetry import FleetTelemetrySnapshot
from app.schemas.fleet_telemetry import TelemetryCapture
from app.services import fleet_telemetry as s
from tests.test_db036_fleet_telemetry import VIN, board, body, prepared

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("values", [
    {"fuel_economy_mpg": 6.5},
    {"fuel_economy_period": "last_30_days"},
    {"fuel_economy_mpg": 6.5, "fuel_economy_period": "last_7_days"},
    *[{"fuel_economy_mpg": value, "fuel_economy_period": "last_30_days"}
      for value in [-1, 101, True, False, float("nan"), float("inf")]],
])
async def test_invalid_fuel_economy(values):
    with pytest.raises(ValidationError):
        TelemetryCapture(client_request_id=uuid4(), fleet_customer_id=uuid4(), vin=VIN, **values)


async def test_mpg_only_zero_replay_sparse_and_no_canonical_write(db_session, monkeypatch):
    actor, v, _ = await prepared(db_session, monkeypatch)
    v.next_pm_miles = 25000
    initial, _ = await s.capture(db_session, actor, v.id, body(v, speed_mph=43, fuel_percent=68, odometer_miles=123))
    request = body(v, fuel_economy_mpg=0, fuel_economy_period="last_30_days")
    row, created = await s.capture(db_session, actor, v.id, request)
    await db_session.commit()
    assert created
    replay, created = await s.capture(db_session, actor, v.id, request)
    assert replay.id == row.id and not created
    with pytest.raises(HTTPException) as exc:
        await s.capture(db_session, actor, v.id, request.model_copy(update={"fuel_economy_mpg": 6.5}))
    assert exc.value.status_code == 409
    for i in range(8):
        await s.capture(db_session, actor, v.id, body(v, speed_mph=i))
    await db_session.commit()
    truck = board(v)
    await s.attach(db_session, [truck], actor.tenant_id)
    reading = truck.telemetry.fuel_economy
    assert (reading.value, reading.unit, reading.period) == (0, "mpg", "last_30_days")
    assert reading.snapshot_id == str(row.id)
    assert reading.captured_at == s.utc(row.captured_at)
    assert reading.observed_at is None
    assert truck.telemetry.fuel.value == 68
    assert truck.telemetry.odometer.snapshot_id == str(initial.id)
    assert truck.telemetry.speed.value == 7
    assert v.mileage == 100 and v.next_pm_miles == 25000


async def test_mpg_scope_retention_and_period_same_snapshot(db_session, monkeypatch):
    actor, v, m = await prepared(db_session, monkeypatch)
    request = body(v, fuel_economy_mpg=6.5, fuel_economy_period="last_30_days")
    row, _ = await s.capture(db_session, actor, v.id, request)
    await db_session.commit()
    truck = board(v)
    foreign, _, _ = await prepared(db_session, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await s.capture(db_session, foreign, v.id, request)
    assert exc.value.status_code == 404
    await s.attach(db_session, [truck], foreign.tenant_id)
    assert truck.telemetry is None
    wrong_fleet = board(v)
    wrong_fleet.board_membership_customer_id = uuid4()
    await s.attach(db_session, [wrong_fleet], actor.tenant_id)
    assert wrong_fleet.telemetry is None
    await db_session.execute(update(FleetTelemetrySnapshot).where(FleetTelemetrySnapshot.id == row.id).values(captured_at=s.now() - timedelta(days=31)))
    await db_session.commit()
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry is None or truck.telemetry.fuel_economy is None
    fresh, _ = await s.capture(db_session, actor, v.id, body(v, fuel_economy_mpg=7.2, fuel_economy_period="last_30_days"))
    await db_session.commit()
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry.fuel_economy.value == 7.2
    assert truck.telemetry.fuel_economy.snapshot_id == str(fresh.id)
    assert truck.telemetry.fuel_economy.period == "last_30_days"
    m.effective_to = s.now()
    await db_session.commit()
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry is None


async def test_legacy_capture_digest_still_replays(db_session, monkeypatch):
    actor, v, _ = await prepared(db_session, monkeypatch)
    request = body(v, speed_mph=20)
    row, _ = await s.capture(db_session, actor, v.id, request)
    legacy = request.model_dump(mode="json", exclude={"fuel_economy_mpg", "fuel_economy_period"})
    row.request_digest = hashlib.sha256(json.dumps({"vehicle_id": str(v.id), **legacy}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    await db_session.commit()
    replay, created = await s.capture(db_session, actor, v.id, request)
    assert replay.id == row.id and not created
