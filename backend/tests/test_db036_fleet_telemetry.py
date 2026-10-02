"""Synthetic manual observations and field-level board projection acceptance."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot
from app.db.models.motive_oauth import MotiveRemoteVehicle
from app.db.models.user import UserRole
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_telemetry import TelemetryCapture
from app.services import fleet_telemetry as s
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from tests.test_db036_motive_oauth import connect, setup

pytestmark = pytest.mark.asyncio
VIN = "1M8GDM9AXKP042788"


async def prepared(db, monkeypatch):
    actor, truck, m = await setup(db, monkeypatch)
    truck.vin = VIN
    await db.commit()
    return actor, truck, m


def body(truck, **values):
    return TelemetryCapture(
        client_request_id=uuid4(),
        fleet_customer_id=truck.customer_id,
        vin=VIN,
        **values,
    )


def board(truck):
    return SimpleNamespace(
        id=truck.id, board_membership_customer_id=truck.customer_id, telemetry=None
    )


async def test_partial_zero_unknown_replay_and_no_canonical_write(
    db_session, monkeypatch
):
    actor, v, _m = await prepared(db_session, monkeypatch)
    b = body(v, speed_mph=0, fuel_percent=0, source_age_text="2 minutes ago")
    row, created = await s.capture(db_session, actor, v.id, b)
    assert created and row.observed_at is None
    await db_session.commit()
    again, created = await s.capture(db_session, actor, v.id, b)
    assert again.id == row.id and not created
    assert v.mileage == 100 and v.last_lat == 1
    truck = board(v)
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry.speed.value == 0
    assert truck.telemetry.speed.freshness == "unknown"
    assert truck.telemetry.motion == "unknown"
    with pytest.raises(HTTPException) as exc:
        await s.capture(db_session, actor, v.id, b.model_copy(update={"speed_mph": 2}))
    assert exc.value.status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"lat": 1},
        {"lat": 91, "lng": 0},
        {"speed_mph": -1},
        {"speed_mph": True},
        {"fuel_percent": 101},
        {"fault_count": 1.1},
        {"speed_mph": float("nan")},
        {"observed_at": "2026-10-01T12:00:00"},
        {"observed_at": 1234567890},
        {"evidence_note": "bad\x00"},
        {"location_label": "bad\ud800"},
    ],
)
async def test_validation(change):
    with pytest.raises(ValidationError):
        TelemetryCapture(
            client_request_id=uuid4(), fleet_customer_id=uuid4(), vin=VIN, **change
        )


async def test_authorization_identity_and_membership(db_session, monkeypatch):
    actor, v, m = await prepared(db_session, monkeypatch)
    b = body(v, speed_mph=10)
    for role in (UserRole.CUSTOMER, UserRole.FLEET_MANAGER):
        actor.role = role
        await db_session.commit()
        with pytest.raises(HTTPException) as exc:
            await s.capture(db_session, actor, v.id, b)
        assert exc.value.status_code == 403
    actor.role = UserRole.GARAGE_OWNER
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await s.capture(
            db_session, actor, v.id, b.model_copy(update={"vin": "2M8GDM9AXKP042788"})
        )
    assert exc.value.detail["code"] == "vehicle_identity_mismatch"
    with pytest.raises(HTTPException) as exc:
        await s.capture(
            db_session, actor, v.id, b.model_copy(update={"fleet_customer_id": uuid4()})
        )
    assert exc.value.status_code == 404
    await s.capture(db_session, actor, v.id, b)
    m.effective_to = s.now()
    await db_session.commit()
    db_session.add(
        FleetMembership(
            tenant_id=actor.tenant_id,
            vehicle_id=v.id,
            fleet_customer_id=v.customer_id,
            effective_from=s.now(),
        )
    )
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await s.capture(db_session, actor, v.id, b)
    assert exc.value.status_code == 404
    truck = board(v)
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry is None


async def test_field_selection_fresh_stale_retention(db_session, monkeypatch):
    actor, v, _m = await prepared(db_session, monkeypatch)
    await s.capture(
        db_session,
        actor,
        v.id,
        body(
            v,
            speed_mph=60,
            observed_at=s.now() - timedelta(minutes=20),
            odometer_miles=1000,
        ),
    )
    await s.capture(
        db_session,
        actor,
        v.id,
        body(v, location_label="Synthetic highway", source_age_text="2 minutes ago"),
    )
    await s.capture(db_session, actor, v.id, body(v, speed_mph=0, observed_at=s.now()))
    await db_session.commit()
    truck = board(v)
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry.motion == "stopped"
    assert truck.telemetry.odometer.value == 1000
    assert truck.telemetry.odometer.basis == "dashboard_unspecified"
    assert truck.telemetry.location.lat is None
    await db_session.execute(
        update(FleetTelemetrySnapshot).values(captured_at=s.now() - timedelta(days=31))
    )
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", False)
    from app.services.motive_oauth import purge

    await purge(db_session)
    assert (
        await db_session.execute(select(FleetTelemetrySnapshot))
    ).scalars().all() == []
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry is None


async def test_api_tie_virtual_disconnect_and_company_eligibility(
    db_session, monkeypatch
):
    actor, v, _m = await prepared(db_session, monkeypatch)
    conn = await connect(db_session, actor, v)
    stamp = s.now() - timedelta(minutes=1)
    remote = MotiveRemoteVehicle(
        tenant_id=actor.tenant_id,
        connection_id=conn.id,
        provider_vehicle_id="fixture",
        vehicle_id=v.id,
        mapped_at=s.now() - timedelta(hours=1),
        discovered_at=stamp,
        provider_status="active",
        located_at=stamp,
        received_at=stamp,
        lat=30,
        lng=-80,
        speed_mph=25,
        metrics_observed_at=stamp,
        virtual_odometer_miles=2000,
        metrics_received_at=stamp,
        faults_synced_at=stamp,
        fault_cursor_at=stamp - timedelta(days=2),
    )
    db_session.add(remote)
    await s.capture(db_session, actor, v.id, body(v, speed_mph=10, observed_at=stamp))
    await db_session.commit()
    truck = board(v)
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry.speed.source == "motive_api"
    assert truck.telemetry.odometer.basis == "virtual"
    assert truck.telemetry.fault_count is None
    company = await db_session.get(Customer, v.customer_id)
    company.fleet_enabled = False
    await db_session.commit()
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry.speed.source == "motive_dashboard_manual"
    company.fleet_enabled = True
    conn.status = "disconnected"
    await db_session.commit()
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry.odometer is None


async def test_legacy_unknown_and_observation_window(db_session, monkeypatch):
    actor, v, _m = await prepared(db_session, monkeypatch)
    v.last_location_at = s.now()
    await db_session.commit()
    truck = board(v)
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry.location.source == "manual_location"
    assert truck.telemetry.location.observed_at is None
    for observed in (
        s.now() + timedelta(minutes=6),
        s.now() - timedelta(days=31),
        s.now() - timedelta(days=2),
    ):
        with pytest.raises(HTTPException) as exc:
            await s.capture(
                db_session, actor, v.id, body(v, speed_mph=10, observed_at=observed)
            )
        assert exc.value.status_code == 422


async def test_http_privacy_replay_and_origin(db_session, monkeypatch):
    import httpx
    from app.api.v1.endpoints.fleet_telemetry import router
    from app.core.dependencies import get_current_active_user, get_db
    from app.middleware.idempotency import IdempotencyMiddleware
    from fastapi import FastAPI

    actor, v, _m = await prepared(db_session, monkeypatch)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/fleet")

    async def db_override():
        yield db_session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_active_user] = lambda: actor
    path = f"/api/v1/fleet/trucks/{v.id}/telemetry-snapshots"
    assert not IdempotencyMiddleware._should_apply(
        {"type": "http", "method": "POST", "path": path}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = body(v, speed_mph=0).model_dump(mode="json")
        first = await client.post(path, json=payload)
        assert first.status_code == 201, first.text
        assert first.headers["cache-control"] == "no-store"
        assert (await client.post(path, json=payload)).status_code == 200
        bad = await client.post(path, json={**payload, "vin": "PRIVATE_BAD_VALUE"})
        assert bad.status_code == 422 and "PRIVATE_BAD_VALUE" not in bad.text
        assert bad.headers["cache-control"] == "no-store"
        origin = await client.post(
            path,
            json=payload,
            headers={"Cookie": "access_token=fake", "Origin": "https://evil.example"},
        )
        assert origin.status_code == 403


async def test_board_detail_projection_parity_and_bounded_queries(
    db_session, monkeypatch
):
    from app.api.v1.endpoints import fleet
    from app.db.models.fleet_board_read_model import FleetBoardReadModel
    from sqlalchemy import event

    actor, v, _m = await prepared(db_session, monkeypatch)
    v.mileage = 652767
    v.next_pm_miles = 677767
    await s.capture(
        db_session,
        actor,
        v.id,
        body(v, speed_mph=0, odometer_miles=660951, location_label="Synthetic depot"),
    )
    await db_session.commit()
    legacy = await fleet.fleet_board(db=db_session, current_user=actor)
    assert legacy.trucks[0].telemetry.speed.value == 0
    detail = await fleet.truck_detail(v.id, db=db_session, current_user=actor)
    assert detail.truck.telemetry == legacy.trucks[0].telemetry
    assert detail.truck.pm_remaining == legacy.trucks[0].pm_remaining == 16816
    assert detail.truck.odometer == v.mileage == 652767
    db_session.add(
        FleetBoardReadModel(
            vehicle_id=v.id,
            tenant_id=actor.tenant_id,
            vehicle_data={
                "make": v.make,
                "model": v.model,
                "mileage": v.mileage,
                "next_pm_miles": v.next_pm_miles,
                "pm_interval_miles": 25000,
                "pm_interval_days": 70,
            },
            urgent_work_order=None,
            pm_work_order=None,
            open_work_order_count=0,
            open_incident_count=0,
        )
    )
    await db_session.commit()
    projection = await fleet.fleet_board(db=db_session, current_user=actor)
    assert projection.trucks[0].telemetry == legacy.trucks[0].telemetry
    assert projection.trucks[0].pm_remaining == 16816
    counts = []

    def query(*args):
        counts.append(1)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", query)
    try:
        await s.attach(db_session, [board(v)], actor.tenant_id)
        one = len(counts)
        counts.clear()
        await s.attach(db_session, [board(v) for _ in range(100)], actor.tenant_id)
        assert len(counts) == one and one <= 5
    finally:
        event.remove(engine, "before_cursor_execute", query)


async def test_foreign_tenant_and_other_actor_replay(db_session, monkeypatch):
    from app.db.models.user import User

    actor, v, _ = await prepared(db_session, monkeypatch)
    request = body(v, speed_mph=0)
    await s.capture(db_session, actor, v.id, request)
    await db_session.commit()
    other = User(
        tenant_id=actor.tenant_id,
        email=f"{uuid4()}@example.test",
        hashed_password="synthetic",
        first_name="Other",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
    )
    db_session.add(other)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await s.capture(db_session, other, v.id, request)
    assert exc.value.status_code == 409
    foreign, _, _ = await prepared(db_session, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await s.capture(db_session, foreign, v.id, request)
    assert exc.value.status_code == 404


async def test_partial_latest_rows_do_not_hide_older_field(db_session, monkeypatch):
    actor, v, _ = await prepared(db_session, monkeypatch)
    await s.capture(
        db_session,
        actor,
        v.id,
        body(v, odometer_miles=0, observed_at=s.now() - timedelta(minutes=20)),
    )
    for i in range(20):
        await s.capture(
            db_session,
            actor,
            v.id,
            body(v, speed_mph=i, observed_at=s.now() - timedelta(minutes=2)),
        )
    await db_session.commit()
    truck = board(v)
    await s.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry.speed.value == 19
    assert truck.telemetry.odometer.value == 0
    assert truck.telemetry.odometer.freshness == "stale"


async def test_snapshot_due_status_stats_and_service_reset(db_session, monkeypatch):
    from app.api.v1.endpoints import fleet

    actor, v, _ = await prepared(db_session, monkeypatch)
    v.mileage, v.next_pm_miles, v.status_override = 100000, 125000, None
    await s.capture(db_session, actor, v.id, body(v, odometer_miles=126000))
    await db_session.commit()
    board_response = await fleet.fleet_board(db=db_session, current_user=actor)
    detail = await fleet.truck_detail(v.id, db=db_session, current_user=actor)
    assert board_response.stats.pm == 1
    assert board_response.trucks[0].status == detail.truck.status == 'pm'
    assert board_response.trucks[0].pm_remaining == detail.truck.pm_remaining == -1000
    # Later service mileage supersedes an older lower snapshot after PM completion.
    v.mileage, v.next_pm_miles = 127000, 152000
    await db_session.commit()
    refreshed = await fleet.truck_detail(v.id, db=db_session, current_user=actor)
    assert refreshed.truck.pm_remaining == 25000
    assert refreshed.truck.odometer == 127000
