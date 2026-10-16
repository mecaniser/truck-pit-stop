# ruff: noqa: F811
"""Database replay serialization and authenticated principal isolation."""

import asyncio
from types import SimpleNamespace

import pytest
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.services import fleet_telemetry as s
from fastapi import HTTPException
from sqlalchemy import update
from tests.test_db036_fleet_telemetry import body, prepared
from tests.test_db036_motive_oauth_postgres import oauth_pg  # noqa: F401

pytestmark = pytest.mark.asyncio


async def test_concurrent_replay(oauth_pg, monkeypatch):
    async with oauth_pg() as db:
        actor, v, _m = await prepared(db, monkeypatch)
        principal = SimpleNamespace(id=actor.id, tenant_id=actor.tenant_id)
        vid = v.id
        request = body(v, speed_mph=0)

    async def capture():
        async with oauth_pg() as db:
            row, created = await s.capture(db, principal, vid, request)
            await db.commit()
            return row.id, created

    a, b = await asyncio.gather(capture(), capture())
    assert a[0] == b[0] and {a[1], b[1]} == {True, False}


async def test_reloaded_user_cannot_change_authenticated_tenant(oauth_pg, monkeypatch):
    async with oauth_pg() as db:
        actor, v, _m = await prepared(db, monkeypatch)
        other = Tenant(name="Other synthetic", slug="other-synthetic")
        db.add(other)
        await db.commit()
        original = actor.tenant_id
        async with oauth_pg() as writer:
            await writer.execute(
                update(User).where(User.id == actor.id).values(tenant_id=other.id)
            )
            await writer.commit()
        assert actor.tenant_id == original
        with pytest.raises(HTTPException) as exc:
            await s.capture(db, actor, v.id, body(v, speed_mph=0))
        assert exc.value.status_code == 403


async def test_concurrent_minute_speed_conflict_is_serialized(oauth_pg, monkeypatch):
    from datetime import timedelta

    async with oauth_pg() as db:
        actor, truck, _ = await prepared(db, monkeypatch)
        principal = SimpleNamespace(id=actor.id, tenant_id=actor.tenant_id)
        vehicle_id = truck.id
        minute = s.now().replace(second=0, microsecond=0) - timedelta(minutes=2)
        requests = [
            body(
                truck, speed_mph=value, observed_at=minute, observed_precision="minute"
            )
            for value in (0, 10)
        ]

    async def capture(request):
        async with oauth_pg() as db:
            try:
                row, created = await s.capture(db, principal, vehicle_id, request)
                await db.commit()
                return "created", row.id, created
            except HTTPException as exc:
                await db.rollback()
                return exc.detail["code"], None, False

    outcomes = await asyncio.gather(*(capture(request) for request in requests))
    assert sorted(result[0] for result in outcomes) == [
        "created",
        "overlapping_observation_interval",
    ]


async def test_postgres_location_speed_supplement_commit_and_replay(
    oauth_pg, monkeypatch
):
    from app.db.models.fleet_telemetry import FleetTelemetrySnapshot
    from scripts.motive_sync import import_locations as worker
    from sqlalchemy import select
    from tests.test_motive_sync_import import minute_source

    async with oauth_pg() as db:
        actor, truck, member = await prepared(db, monkeypatch)
        truck.last_lat = truck.last_lng = None
        await db.commit()
        tenant_id, actor_id = actor.tenant_id, actor.id
    doc = minute_source()
    args = (oauth_pg, doc, tenant_id, actor_id, "77 CARGO LLC", "KT8934277")
    first = (await worker.run_import(*args, commit=True))["rows"][0]
    doc["vehicles"][0].update(speed_mph=0, speedText="0 MPH")
    second = (await worker.run_import(*args, commit=True))["rows"][0]
    third = (await worker.run_import(*args, commit=True))["rows"][0]
    assert second["saved_receipt_verified"] and second["board_verified_after_commit"]
    assert third["status"] == "replay" and third["snapshot_id"] == second["snapshot_id"]
    assert third["snapshot_id"] != first["snapshot_id"]
    async with oauth_pg() as db:
        snapshots = (await db.execute(select(FleetTelemetrySnapshot))).scalars().all()
        assert len(snapshots) == 2
        assert len([row for row in snapshots if row.lat is not None]) == 1
        assert (
            len([row for row in snapshots if row.speed_mph == 0 and row.lat is None])
            == 1
        )
