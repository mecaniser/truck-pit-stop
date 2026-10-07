"""Minute observation contract and legacy immutable receipt compatibility."""

import hashlib
import json
from datetime import timedelta

import pytest
from app.services import fleet_telemetry as service
from fastapi import HTTPException
from pydantic import ValidationError
from tests.test_db036_fleet_telemetry import board, body, prepared

pytestmark = pytest.mark.asyncio


async def test_minute_capture_projection_replay_and_overlap(db_session, monkeypatch):
    actor, truck, _ = await prepared(db_session, monkeypatch)
    stamp = service.now().replace(second=0, microsecond=0) - timedelta(minutes=3)
    request = body(
        truck, lat=35, lng=-80, observed_at=stamp, observed_precision="minute"
    )
    saved, created = await service.capture(db_session, actor, truck.id, request)
    assert created and saved.observed_precision == "minute"
    await db_session.commit()
    projected = board(truck)
    await service.attach(db_session, [projected], actor.tenant_id)
    assert projected.telemetry.location.observed_precision == "minute"
    assert projected.telemetry.location.observed_at == stamp
    repeated, created = await service.capture(db_session, actor, truck.id, request)
    assert not created and repeated.id == saved.id
    # A later exact timestamp inside the uncertain interval must retain prior.
    for second in (0, 30, 59):
        with pytest.raises(HTTPException) as error:
            await service.capture(
                db_session,
                actor,
                truck.id,
                body(
                    truck,
                    lat=36,
                    lng=-81,
                    observed_at=stamp + timedelta(seconds=second),
                ),
            )
        assert error.value.detail["code"] == "overlapping_observation_interval"
    newer, created = await service.capture(
        db_session,
        actor,
        truck.id,
        body(
            truck,
            lat=36,
            lng=-81,
            observed_at=stamp + timedelta(minutes=1),
            observed_precision="minute",
        ),
    )
    assert created and newer.id != saved.id


async def test_minute_cannot_replace_precise_existing_and_legacy_digest(
    db_session, monkeypatch
):
    actor, truck, _ = await prepared(db_session, monkeypatch)
    minute = service.now().replace(second=0, microsecond=0) - timedelta(minutes=3)
    request = body(truck, lat=35, lng=-80, observed_at=minute + timedelta(seconds=30))
    saved, _ = await service.capture(db_session, actor, truck.id, request)
    legacy = request.model_dump(mode="json")
    for name in ("observed_precision", "fuel_economy_mpg", "fuel_economy_period"):
        legacy.pop(name)
    digest = hashlib.sha256(
        json.dumps(
            {"vehicle_id": str(truck.id), **legacy},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert saved.request_digest == digest
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await service.capture(
            db_session,
            actor,
            truck.id,
            body(
                truck, lat=36, lng=-81, observed_at=minute, observed_precision="minute"
            ),
        )
    assert error.value.detail["code"] == "overlapping_observation_interval"


@pytest.mark.parametrize(
    "change",
    [
        {"observed_precision": "minute"},
        {"observed_precision": "second"},
        {"observed_at": "2026-10-07T12:30:12Z", "observed_precision": "minute"},
        {"observed_at": "2026-10-07T12:30:00.000001Z", "observed_precision": "minute"},
        {"observed_at": "2026-10-07T12:30:00Z", "observed_precision": "hour"},
    ],
)
async def test_precision_schema_validation(change):
    from uuid import uuid4

    from app.schemas.fleet_telemetry import TelemetryCapture

    with pytest.raises(ValidationError):
        TelemetryCapture(
            client_request_id=uuid4(),
            fleet_customer_id=uuid4(),
            vin="1M8GDM9AXKP042788",
            lat=35,
            lng=-80,
            **change,
        )


async def test_full_minute_must_belong_to_membership(db_session, monkeypatch):
    actor, truck, member = await prepared(db_session, monkeypatch)
    minute = service.now().replace(second=0, microsecond=0)
    member.effective_to = minute + timedelta(seconds=30)
    monkeypatch.setattr(service, "now", lambda: minute + timedelta(seconds=10))
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await service.capture(
            db_session,
            actor,
            truck.id,
            body(
                truck, lat=35, lng=-80, observed_at=minute, observed_precision="minute"
            ),
        )
    assert error.value.detail["code"] == "invalid_observation_time"
