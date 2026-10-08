"""Dashboard diagnostic identity, scope, unknown timestamps and saved replay."""

import copy
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from app.db.models.fleet_diagnostic import FleetDiagnosticCapture
from app.db.models.user import UserRole
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_diagnostic import DiagnosticCapture, DiagnosticCode
from app.services import fleet_diagnostics as service
from app.services.fleet_telemetry import now
from fastapi import HTTPException
from scripts.motive_health.runner import run
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_db036_fleet_telemetry import VIN, prepared


def code():
    return {
        "spn": "0520216",
        "fmi": "031",
        "description": "Synthetic brake communication condition",
        "severity": "High",
        "network": "J1939",
        "source_address": "11",
        "occurrence_count": 0,
        "first_detected_text": "Sep 25, 2026, 5:50 AM",
        "last_observed_text": "Oct 7, 2026, 6:59 PM",
    }


def body(**values):
    return DiagnosticCapture(
        client_request_id=uuid4(),
        vin=VIN,
        provider_vehicle_id="123",
        source_company_id="KT8934277",
        source_company_label="77 CARGO LLC",
        company_verified_before=True,
        company_verified_after=True,
        source_read_at=now() - timedelta(minutes=1),
        explicit_empty=False,
        count_before=1,
        count_after=1,
        codes=[code()],
        **values,
    )


def document():
    stamp = now()
    return {
        "version": 1,
        "company_label": "77 CARGO LLC",
        "company_id": "KT8934277",
        "company_verified_before": True,
        "company_verified_after": True,
        "timezone_evidence": "Eastern Time - New York",
        "started_at": (stamp - timedelta(minutes=2)).isoformat(),
        "finished_at": stamp.isoformat(),
        "health_directory_count": 1,
        "terminal_evidence": "Showing 1 of 1",
        "complete": True,
        "vehicles": [
            {
                "provider_vehicle_id": "123",
                "unit": "77",
                "vin": VIN,
                "source_read_at": (stamp - timedelta(minutes=1)).isoformat(),
                "state": "captured",
                "count_before": 1,
                "count_after": 1,
                "explicit_empty": False,
                "source_scope": "Current fault codes",
                "codes": [code()],
            }
        ],
    }


def test_unknown_time_and_leading_zeroes_preserved():
    value = DiagnosticCode.model_validate(code())
    assert value.spn == "0520216" and value.fmi == "031"
    assert value.occurrence_count == 0
    assert value.first_detected_at is None and value.last_observed_at is None
    assert (
        value.timestamp_precision == "unknown" and value.timezone_basis == "unverified"
    )
    assert DiagnosticCode.model_validate({"spn": "1"}).occurrence_count is None


@pytest.mark.parametrize(
    "change",
    [
        {"last_observed_at": "2026-10-07T22:00:00Z"},
        {"timestamp_precision": "minute"},
        {"timezone_basis": "America/New_York"},
        {"occurrence_count": -1},
        {"occurrence_count": True},
        {"provider_fault_id": "invented"},
        {"source_status": "closed"},
        {"spn": 1},
    ],
)
def test_no_timestamp_or_lifecycle_invention(change):
    with pytest.raises(ValueError):
        DiagnosticCode.model_validate({**code(), **change})


@pytest.mark.parametrize(
    "change",
    [
        {"count_before": 4},
        {"count_after": 2},
        {"codes": [], "explicit_empty": False, "count_before": 0, "count_after": 0},
        {"company_verified_after": False},
        {"coverage": "partial"},
    ],
)
def test_partial_capture_cannot_become_complete(change):
    original = body().model_dump()
    with pytest.raises(ValueError):
        DiagnosticCapture.model_validate({**original, **change})


@pytest.mark.asyncio
async def test_capture_dry_run_replay_empty_history_and_membership(
    db_session, monkeypatch
):
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=1)
    await db_session.commit()
    args = (db_session, actor.tenant_id, actor.id)
    empty_read = await service.read(db_session, actor.tenant_id, vehicle.id)
    assert empty_read.coverage == "unknown" and empty_read.explicit_empty is None
    first = body()
    dry, status = await service.capture(*args, first, "77 CARGO LLC", "KT8934277")
    assert dry is None and status == "would_create"
    assert (
        await db_session.execute(
            select(func.count()).select_from(FleetDiagnosticCapture)
        )
    ).scalar_one() == 0
    saved, status = await service.capture(
        *args, first, "77 CARGO LLC", "KT8934277", apply=True
    )
    await db_session.commit()
    saved_id, saved_read = saved.id, saved.source_read_at
    again, status = await service.capture(
        *args, first, "77 CARGO LLC", "KT8934277", apply=True
    )
    assert (
        again.id == saved_id
        and status == "unchanged"
        and again.source_read_at == saved_read
    )
    altered = first.model_copy(
        update={
            "explicit_empty": True,
            "codes": [],
            "count_before": 0,
            "count_after": 0,
        }
    )
    with pytest.raises(HTTPException) as exc:
        await service.capture(*args, altered, "77 CARGO LLC", "KT8934277", apply=True)
    assert exc.value.detail["code"] == "conflicting_diagnostic_capture"
    zero = altered.model_copy(
        update={"client_request_id": uuid4(), "source_read_at": now()}
    )
    await service.capture(*args, zero, "77 CARGO LLC", "KT8934277", apply=True)
    await db_session.commit()
    latest = await service.read(db_session, actor.tenant_id, vehicle.id)
    assert latest.explicit_empty is True and latest.codes == []
    assert latest.previously_reported[0].codes[0].spn == "0520216"
    assert vehicle.mileage == 100 and vehicle.last_lat == 1
    with pytest.raises(HTTPException) as exc:
        await service.read(db_session, uuid4(), vehicle.id)
    assert exc.value.status_code == 404
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
    assert (
        await service.read(db_session, actor.tenant_id, vehicle.id)
    ).coverage == "unknown"


@pytest.mark.asyncio
async def test_wrong_actor_company_customer_and_read_membership(
    db_session, monkeypatch
):
    actor, _vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=1)
    await db_session.commit()
    b = body()
    for tenant_id, actor_id, company, customer in [
        (uuid4(), actor.id, "77 CARGO LLC", None),
        (actor.tenant_id, uuid4(), "77 CARGO LLC", None),
        (actor.tenant_id, actor.id, "Wrong", None),
        (actor.tenant_id, actor.id, "77 CARGO LLC", uuid4()),
    ]:
        with pytest.raises(HTTPException):
            await service.capture(
                db_session,
                tenant_id,
                actor_id,
                b,
                company,
                "KT8934277",
                apply=True,
                expected_customer_id=customer,
            )
    actor.role = UserRole.FLEET_MANAGER
    await db_session.commit()
    with pytest.raises(HTTPException):
        await service.capture(
            db_session,
            actor.tenant_id,
            actor.id,
            b,
            "77 CARGO LLC",
            "KT8934277",
            apply=True,
        )
    actor.role = UserRole.GARAGE_OWNER
    member.effective_from = now()
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await service.capture(
            db_session,
            actor.tenant_id,
            actor.id,
            b,
            "77 CARGO LLC",
            "KT8934277",
            apply=True,
        )
    assert exc.value.detail["code"] == "source_outside_current_membership"


@pytest.mark.asyncio
async def test_runner_receipt_recovery_and_missing_source(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=1)
    await db_session.commit()
    tenant, actor_id = actor.tenant_id, actor.id
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    source = document()
    args = (
        factory,
        source,
        tenant,
        actor_id,
        "77 CARGO LLC",
        "KT8934277",
        tmp_path / "receipt.json",
    )
    first = await run(*args, commit=True)
    assert first["stage"] == "verified" and first["readback_verified"] == 1
    repeated = await run(*args, commit=True, recovery=True)
    assert repeated["rows"][0]["capture_id"] == first["rows"][0]["capture_id"]
    assert repeated["rows"][0]["status"] == "unchanged"
    broken = copy.deepcopy(source)
    broken["vehicles"][0]["codes"][0]["spn"] = "different"
    with pytest.raises(ValueError, match="immutable identity"):
        await run(
            factory,
            broken,
            tenant,
            actor_id,
            "77 CARGO LLC",
            "KT8934277",
            tmp_path / "receipt.json",
            commit=True,
            recovery=True,
        )
    absent = copy.deepcopy(source)
    absent.update(
        vehicles=[], health_directory_count=0, terminal_evidence="Showing 0 of 0"
    )
    receipt = await run(
        factory,
        absent,
        tenant,
        actor_id,
        "77 CARGO LLC",
        "KT8934277",
        tmp_path / "missing.json",
        commit=True,
    )
    assert receipt["rows"][0]["status"] == "source_missing"
    async with factory() as db:
        assert (
            await db.execute(select(func.count()).select_from(FleetDiagnosticCapture))
        ).scalar_one() == 1
    assert json.loads((tmp_path / "receipt.json.attempt.json").read_text())[
        "eligible_requests"
    ]


@pytest.mark.asyncio
async def test_route_uses_fleet_access_and_tenant_isolation(db_session, monkeypatch):
    import httpx
    from app.api.v1.endpoints.fleet import router
    from app.core.dependencies import get_current_active_user, get_db
    from fastapi import FastAPI

    actor, vehicle, _ = await prepared(db_session, monkeypatch)
    original_tenant = actor.tenant_id
    app = FastAPI()
    app.include_router(router, prefix="/fleet")

    async def db_override():
        yield db_session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_active_user] = lambda: actor
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        url = f"/fleet/trucks/{vehicle.id}/diagnostics"
        response = await client.get(url)
        assert response.status_code == 200
        assert (
            response.json()["coverage"] == "unknown"
            and response.json()["explicit_empty"] is None
        )
        assert response.headers["cache-control"] == "no-store"
        actor.tenant_id = uuid4()
        assert (await client.get(url)).status_code == 404
        actor.tenant_id = original_tenant
        actor.role = UserRole.CUSTOMER
        assert (await client.get(url)).status_code == 403


@pytest.mark.asyncio
async def test_runner_replay_failure_rolls_back_and_recovers_same_request(
    _db_engine, db_session, monkeypatch, tmp_path
):
    from scripts.motive_health import runner

    actor, _, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=1)
    await db_session.commit()
    tenant, actor_id = actor.tenant_id, actor.id
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    source = document()
    args = (
        factory,
        source,
        tenant,
        actor_id,
        "77 CARGO LLC",
        "KT8934277",
        tmp_path / "rollback.json",
    )
    original = runner.batch
    calls = 0

    async def fail_replay(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = await original(*args, **kwargs)
        if calls == 3:
            raise ValueError("Injected replay failure")
        return result

    monkeypatch.setattr(runner, "batch", fail_replay)
    with pytest.raises(ValueError, match="Injected replay"):
        await runner.run(*args, commit=True)
    receipt = json.loads((tmp_path / "rollback.json").read_text())
    request_id = receipt["rows"][0]["client_request_id"]
    assert receipt["committed"] is False
    async with factory() as db:
        assert (
            await db.execute(select(func.count()).select_from(FleetDiagnosticCapture))
        ).scalar_one() == 0
    monkeypatch.setattr(runner, "batch", original)
    recovered = await runner.run(*args, commit=True, recovery=True)
    assert (
        recovered["committed"]
        and recovered["rows"][0]["client_request_id"] == request_id
    )


@pytest.mark.parametrize(
    "change",
    [
        {"company_id": "foreign"},
        {"company_verified_after": False},
        {"complete": False},
        {"health_directory_count": 2},
        {"terminal_evidence": None},
        {"version": True},
    ],
)
def test_incomplete_or_foreign_health_document_rejected(change):
    from scripts.motive_health.import_health import validate

    with pytest.raises(ValueError):
        validate({**document(), **change}, "77 CARGO LLC", "KT8934277")


@pytest.mark.asyncio
async def test_current_vin_and_membership_read_bounds_hide_old_capture(
    db_session, monkeypatch
):
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = now() - timedelta(days=1)
    await db_session.commit()
    first = body()
    await service.capture(
        db_session,
        actor.tenant_id,
        actor.id,
        first,
        "77 CARGO LLC",
        "KT8934277",
        apply=True,
    )
    second = first.model_copy(
        update={
            "client_request_id": uuid4(),
            "source_read_at": now() - timedelta(seconds=30),
        }
    )
    await service.capture(
        db_session,
        actor.tenant_id,
        actor.id,
        second,
        "77 CARGO LLC",
        "KT8934277",
        apply=True,
    )
    await db_session.commit()
    original = await service.read(db_session, actor.tenant_id, vehicle.id)
    assert original.coverage == "complete" and len(original.previously_reported) == 1
    vehicle.vin = f"  {VIN.lower()}  "
    await db_session.commit()
    normalized = await service.read(db_session, actor.tenant_id, vehicle.id)
    assert (
        normalized.capture_id == original.capture_id
        and len(normalized.previously_reported) == 1
    )
    vehicle.vin = "2M8GDM9AXKP042788"
    await db_session.commit()
    changed = await service.read(db_session, actor.tenant_id, vehicle.id)
    assert changed.coverage == "unknown" and changed.capture_id is None
    assert changed.codes == [] and changed.previously_reported == []
    vehicle.vin = VIN
    member.effective_from = now() - timedelta(seconds=10)
    await db_session.commit()
    rebound = await service.read(db_session, actor.tenant_id, vehicle.id)
    assert rebound.coverage == "unknown" and rebound.last_checked_at is None
    assert rebound.codes == [] and rebound.previously_reported == []
    from app.db.models.tenant import Tenant

    tenant = await db_session.get(Tenant, actor.tenant_id)
    tenant.is_active = False
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await service.read(db_session, actor.tenant_id, vehicle.id)
    assert exc.value.status_code == 404
