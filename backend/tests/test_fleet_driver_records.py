"""Driver record tenant isolation, immutable replay and identity invalidation."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from app.db.models.fleet_driver_record import FleetDriverRecordCapture
from app.db.models.user import UserRole
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_driver_record import DriverRecordCapture, DriverSafety
from app.services import fleet_driver_records as service
from app.services.fleet_telemetry import now
from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select
from tests.test_db036_fleet_telemetry import VIN, prepared


def body(**changes):
    data = {
        "client_request_id": uuid4(),
        "vin": VIN,
        "provider_vehicle_id": "vehicle-123",
        "provider_driver_id": "driver-456",
        "driver_name": "Synthetic Driver",
        "source_company_id": "KT123",
        "source_company_label": "Synthetic Fleet",
        "company_verified_before": True,
        "company_verified_after": True,
        "assignment_verified_before": True,
        "assignment_verified_after": True,
        "source_read_at": now(),
        "safety": {
            "score": 82,
            "coaching_label": "Coaching",
            "period_text": "Sep 28 - Oct 4, 2026",
            "top_behaviors": [{"behavior": "Close following", "score_impact": -9}],
        },
        "fuel": {
            "period_text": "Last 30 days",
            "utilization_percent": 41.4,
            "active_time_text": "68h 14m",
            "idle_time_text": "96h 26m",
        },
        "coaching": {
            "status_label": "Driver needs coaching",
            "open_count": 4,
            "last_coached_text": "Never coached",
        },
        "recent_events": [
            {
                "behavior": "Close following",
                "status": "Pending review",
                "occurred_at_text": "Oct 9, 2026, 2:29 PM",
            }
        ],
        "sections": {
            "safety": "available",
            "fuel": "available",
            "coaching": "available",
            "recent_events": "available",
        },
    }
    return DriverRecordCapture.model_validate({**data, **changes})


async def fixture(db, monkeypatch):
    actor, vehicle, member = await prepared(db, monkeypatch)
    vehicle.driver_name = "Synthetic Driver"
    vehicle.driver_phone = "+15555550101"
    member.effective_from = now() - timedelta(days=7)
    await db.commit()
    return actor, vehicle, member


async def save(db, actor, member, source=None, apply=True, **kwargs):
    return await service.capture(
        db,
        actor.tenant_id,
        actor.id,
        source or body(),
        "Synthetic Fleet",
        "KT123",
        apply=apply,
        expected_customer_id=member.fleet_customer_id,
        **kwargs,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"assignment_verified_after": False},
        {"assignment_verified_after": 1},
        {"company_verified_before": False},
        {"source_read_at": "2026-10-09T12:00:00"},
        {"source_read_at": 123456},
        {"driver_name": "bad\x00"},
        {"provider_driver_id": "bad\ud800"},
        {"safety": {"score": True}},
        {"safety": {"score": 101}},
        {"safety": {"band": "red"}},
        {"safety": {"band": "green", "band_label": "Coaching"}},
        {"fuel": {"utilization_percent": float("nan")}},
        {"coaching": {"open_count": True}},
        {"sections": {"safety": "unavailable"}},
        {"coverage": "complete", "sections": {"fuel": "unavailable"}, "fuel": {}},
    ],
)
def test_invalid_or_invented_source_rejected(changes):
    with pytest.raises(ValueError):
        body(**changes)


def test_zero_unknown_band_and_optional_data():
    value = body(safety={"score": 0}, fuel={"utilization_percent": 0})
    assert value.safety.score == 0 and value.safety.band == "unknown"
    assert value.fuel.utilization_percent == 0
    assert value.source_timezone is None
    assert DriverSafety().score is None


@pytest.mark.asyncio
async def test_dry_run_replay_projection_and_bounded_batch(db_session, monkeypatch):
    actor, vehicle, member = await fixture(db_session, monkeypatch)
    source = body()
    assert (
        await service.read(db_session, actor.tenant_id, vehicle.id)
    ).availability == "unknown"
    row, status = await save(db_session, actor, member, source, apply=False)
    assert row is None and status == "would_create"
    assert (
        await db_session.scalar(
            select(func.count()).select_from(FleetDriverRecordCapture)
        )
        == 0
    )
    row, status = await save(db_session, actor, member, source)
    assert status == "created"
    await db_session.commit()
    replay, status = await save(db_session, actor, member, source)
    assert status == "unchanged" and replay.id == row.id
    assert (
        await db_session.scalar(
            select(func.count()).select_from(FleetDriverRecordCapture)
        )
        == 1
    )
    record = (await service.read(db_session, actor.tenant_id, vehicle.id)).record
    assert record.safety_score == 82 and record.safety_band == "unknown"
    assert (
        record.safety.coaching_label == "Coaching" and record.coaching.open_count == 4
    )
    assert record.fuel.utilization_percent == 41.4 and record.stale is False
    board = SimpleNamespace(id=vehicle.id, driver_name=vehicle.driver_name)
    await service.attach(db_session, [board], actor.tenant_id)
    assert board.driver_record.capture_id == row.id
    board.driver_name = "Different cached label"
    await service.attach(db_session, [board], actor.tenant_id)
    assert board.driver_record is None
    altered = source.model_copy(update={"provider_driver_id": "changed"})
    with pytest.raises(HTTPException) as error:
        await save(db_session, actor, member, altered)
    assert error.value.detail["code"] == "conflicting_driver_record_capture"
    assert vehicle.mileage == 100 and vehicle.last_lat == 1


@pytest.mark.asyncio
async def test_local_assignment_switch_back_and_phone_edit_invalidate(
    db_session, monkeypatch
):
    actor, vehicle, member = await fixture(db_session, monkeypatch)
    source = body()
    row, _ = await save(db_session, actor, member, source)
    await db_session.commit()
    revision = vehicle.driver_assignment_revision
    vehicle.driver_name = "Other Driver"
    await db_session.commit()
    vehicle.driver_name = "Synthetic Driver"
    await db_session.commit()
    assert vehicle.driver_assignment_revision == revision + 2
    read = await service.read(db_session, actor.tenant_id, vehicle.id)
    assert read.availability == "assignment_unverified" and read.record is None
    # Exact receipt replay is still stable, but does not rebind the old capture.
    assert (await save(db_session, actor, member, source))[0].id == row.id
    with pytest.raises(HTTPException) as error:
        await save(
            db_session,
            actor,
            member,
            source.model_copy(update={"client_request_id": uuid4()}),
        )
    assert error.value.detail["code"] == "source_before_driver_assignment_change"
    await save(db_session, actor, member)
    await db_session.commit()
    assert (await service.read(db_session, actor.tenant_id, vehicle.id)).record
    vehicle.driver_phone = "+15555550202"
    await db_session.commit()
    assert (await service.read(db_session, actor.tenant_id, vehicle.id)).record is None


@pytest.mark.asyncio
async def test_provider_identity_change_and_name_mismatch_do_not_resurface_old_driver(
    db_session, monkeypatch
):
    actor, vehicle, member = await fixture(db_session, monkeypatch)
    await save(db_session, actor, member)
    await db_session.commit()
    await save(
        db_session,
        actor,
        member,
        body(provider_driver_id="new-driver", driver_name="Other Driver"),
    )
    await db_session.commit()
    result = await service.read(db_session, actor.tenant_id, vehicle.id)
    assert result.availability == "assignment_unverified" and result.record is None


@pytest.mark.asyncio
async def test_company_actor_customer_membership_and_time_rejected(
    db_session, monkeypatch
):
    actor, _vehicle, member = await fixture(db_session, monkeypatch)
    source = body()
    for overrides in [
        {"tenant_id": uuid4()},
        {"actor_id": uuid4()},
        {"company_label": "Wrong"},
        {"company_id": "Wrong"},
        {"expected_customer_id": uuid4()},
        {"expected_customer_id": None},
        {
            "body": source.model_copy(
                update={"source_read_at": now() + timedelta(minutes=1)}
            )
        },
    ]:
        args = {
            "db": db_session,
            "tenant_id": actor.tenant_id,
            "actor_id": actor.id,
            "body": source,
            "company_label": "Synthetic Fleet",
            "company_id": "KT123",
            "expected_customer_id": member.fleet_customer_id,
            "apply": True,
        }
        with pytest.raises(HTTPException):
            await service.capture(**{**args, **overrides})
    actor.role = UserRole.FLEET_MANAGER
    await db_session.commit()
    with pytest.raises(HTTPException):
        await save(db_session, actor, member, source)
    actor.role = UserRole.GARAGE_OWNER
    await db_session.commit()
    with pytest.raises(HTTPException):
        await save(
            db_session, actor, member, body(source_read_at=now() - timedelta(days=8))
        )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(FleetDriverRecordCapture)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_vin_membership_and_inactive_tenant_hide_records(db_session, monkeypatch):
    from app.db.models.tenant import Tenant

    actor, vehicle, member = await fixture(db_session, monkeypatch)
    await save(db_session, actor, member)
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await service.read(db_session, uuid4(), vehicle.id)
    assert error.value.status_code == 404
    vehicle.vin = "2M8GDM9AXKP042788"
    await db_session.commit()
    assert (await service.read(db_session, actor.tenant_id, vehicle.id)).record is None
    vehicle.vin = VIN
    member.effective_to = now() - timedelta(seconds=1)
    await db_session.commit()
    with pytest.raises(HTTPException):
        await service.read(db_session, actor.tenant_id, vehicle.id)
    replacement = FleetMembership(
        tenant_id=actor.tenant_id,
        vehicle_id=vehicle.id,
        fleet_customer_id=member.fleet_customer_id,
        effective_from=now(),
    )
    db_session.add(replacement)
    await db_session.commit()
    assert (await service.read(db_session, actor.tenant_id, vehicle.id)).record is None
    tenant = await db_session.get(Tenant, actor.tenant_id)
    tenant.is_active = False
    await db_session.commit()
    with pytest.raises(HTTPException):
        await service.read(db_session, actor.tenant_id, vehicle.id)


@pytest.mark.asyncio
async def test_stale_is_explicit_and_empty_does_not_become_zero(
    db_session, monkeypatch
):
    actor, vehicle, member = await fixture(db_session, monkeypatch)
    await save(
        db_session,
        actor,
        member,
        body(
            safety={},
            fuel={},
            coaching={},
            recent_events=[],
            sections={
                "safety": "empty",
                "fuel": "unavailable",
                "coaching": "empty",
                "recent_events": "empty",
            },
        ),
    )
    await db_session.commit()
    monkeypatch.setattr(service, "now", lambda: now() + timedelta(days=3))
    record = (await service.read(db_session, actor.tenant_id, vehicle.id)).record
    assert (
        record.stale
        and record.safety_score is None
        and record.fuel.utilization_percent is None
    )


@pytest.mark.asyncio
async def test_authenticated_route_no_store_and_access(db_session, monkeypatch):
    from app.api.v1.endpoints.fleet import router
    from app.core.dependencies import get_current_active_user, get_db

    actor, vehicle, member = await fixture(db_session, monkeypatch)
    await save(db_session, actor, member)
    await db_session.commit()
    app = FastAPI()
    app.include_router(router, prefix="/fleet")

    async def db_override():
        yield db_session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_active_user] = lambda: actor
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        url = f"/fleet/trucks/{vehicle.id}/driver-record"
        response = await client.get(url)
        assert (
            response.status_code == 200
            and response.json()["record"]["safety_score"] == 82
        )
        assert response.headers["cache-control"] == "no-store"
        actor.role = UserRole.CUSTOMER
        assert (await client.get(url)).status_code == 403
        actor.role = UserRole.GARAGE_OWNER
        actor.tenant_id = uuid4()
        assert (await client.get(url)).status_code == 404
