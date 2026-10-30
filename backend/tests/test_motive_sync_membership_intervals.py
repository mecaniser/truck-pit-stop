"""Prospective enrollment excludes older readings without aborting a fleet batch."""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot as Snapshot
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.services import fleet_telemetry as telemetry
from scripts.motive_sync import import_locations as worker
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_db036_fleet_telemetry import VIN, prepared
from tests.test_motive_sync_import import source

VIN2 = "1M8GDM9AXKP042789"


async def fleet_fixture(db, monkeypatch, engine):
    actor, truck9, membership9 = await prepared(db, monkeypatch)
    base = telemetry.now().replace(second=0, microsecond=0)
    now = base + timedelta(minutes=2)
    monkeypatch.setattr(telemetry, "now", lambda: now)
    truck9.unit_number = "9"
    truck9.last_lat = truck9.last_lng = None
    membership9.effective_from = base + timedelta(seconds=30)
    other = Vehicle(
        id=uuid4(),
        tenant_id=actor.tenant_id,
        customer_id=truck9.customer_id,
        vin=VIN2,
        unit_number="17",
        make="Fixture",
        model="Truck",
        mileage=100,
    )
    db.add(other)
    await db.flush()
    other_membership = FleetMembership(
        tenant_id=actor.tenant_id,
        vehicle_id=other.id,
        fleet_customer_id=membership9.fleet_customer_id,
        effective_from=base - timedelta(days=1),
    )
    db.add(other_membership)
    await db.commit()
    doc = source(now)
    doc["vehicles"][0].update(unit="9")
    other_source = deepcopy(doc["vehicles"][0])
    other_source.update(
        provider_vehicle_id="456", unit="17", vin=VIN2, lat=36.1, lng=-81.2
    )
    doc["vehicles"].append(other_source)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    args = (factory, doc, actor.tenant_id, actor.id, "77 CARGO LLC", "KT8934277")
    return actor, truck9, membership9, other, other_membership, base, doc, args


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,reason",
    [
        ("capture_before", "source_capture_outside_membership"),
        ("observation_before", "observation_outside_membership"),
        ("minute_straddles", "observation_outside_membership"),
        ("minute_after_end", "observation_outside_membership"),
    ],
)
async def test_prospective_member_old_reading_does_not_abort_other_updates(
    db_session, monkeypatch, _db_engine, case, reason
):
    actor, truck9, membership9, other, _, base, doc, args = await fleet_fixture(
        db_session, monkeypatch, _db_engine
    )
    row = doc["vehicles"][0]
    row.update(
        sourceReadTime=(base + timedelta(seconds=60)).isoformat(),
        observed_at=(base + timedelta(seconds=29)).isoformat(),
    )
    if case == "capture_before":
        row.update(
            sourceReadTime=(base + timedelta(seconds=29)).isoformat(),
            observed_at=(base + timedelta(seconds=10)).isoformat(),
        )
    if case.startswith("minute"):
        start = base if case == "minute_straddles" else base + timedelta(minutes=2)
        row.update(
            precision="minute",
            observed_at=None,
            observed_minute_start=start.isoformat(),
            observed_minute_end=(start + timedelta(minutes=1)).isoformat(),
        )
    if case == "minute_after_end":
        # Capture time is inside this currently active interval; part of the
        # source minute would occur after it ended and must remain excluded.
        row["sourceReadTime"] = (base + timedelta(seconds=140)).isoformat()
        membership9.effective_to = base + timedelta(seconds=150)
    await db_session.commit()
    result = await worker.run_import(*args, commit=True)
    held, saved = result["rows"][:2]
    assert result["committed"]
    assert held["status"] == "outside_membership_interval" and held["reason"] == reason
    assert held["vehicle_id"] == str(truck9.id)
    assert held["membership_id"] == str(membership9.id)
    assert "snapshot_id" not in held and "request_id" not in held
    assert saved["status"] == "update" and saved["saved_receipt_verified"]
    assert saved["board_verified_after_commit"]
    snapshots = (await db_session.execute(select(Snapshot))).scalars().all()
    assert len(snapshots) == 1 and snapshots[0].vehicle_id == other.id
    await db_session.refresh(truck9)
    assert truck9.vin == VIN and truck9.customer_id == other.customer_id
    assert truck9.last_lat is None and truck9.last_lng is None
    assert telemetry.utc(membership9.effective_from) == base + timedelta(seconds=30)


@pytest.mark.asyncio
async def test_future_fully_covered_reading_is_saved_once_and_old_reading_stays_held(
    db_session, monkeypatch, _db_engine
):
    actor, truck9, membership9, other, _, base, doc, args = await fleet_fixture(
        db_session, monkeypatch, _db_engine
    )
    row = doc["vehicles"][0]
    row.update(
        sourceReadTime=(base + timedelta(seconds=60)).isoformat(),
        observed_at=(base + timedelta(seconds=29)).isoformat(),
    )
    old = await worker.run_import(*args, commit=True)
    assert old["rows"][0]["status"] == "outside_membership_interval"
    other_id = old["rows"][1]["snapshot_id"]
    future = deepcopy(doc)
    future["vehicles"][0].update(
        sourceReadTime=(base + timedelta(seconds=100)).isoformat(),
        observed_at=(base + timedelta(seconds=80)).isoformat(),
    )
    future_args = (args[0], future, *args[2:])
    accepted = (await worker.run_import(*future_args, commit=True))["rows"][0]
    assert accepted["status"] == "update" and accepted["created"]
    assert (
        accepted["saved_receipt_verified"] and accepted["board_verified_after_commit"]
    )
    replay = (await worker.run_import(*future_args, commit=True))["rows"][0]
    assert replay["status"] == "replay" and replay["created"] is False
    assert replay["snapshot_id"] == accepted["snapshot_id"]
    later = deepcopy(future)
    later["vehicles"][0]["sourceReadTime"] = (base + timedelta(seconds=101)).isoformat()
    unchanged = (await worker.run_import(args[0], later, *args[2:], commit=True))[
        "rows"
    ][0]
    assert unchanged["status"] == "unchanged" and "snapshot_id" not in unchanged
    still_old = (await worker.run_import(*args, commit=True))["rows"][0]
    assert still_old["status"] == "outside_membership_interval"
    snapshots = (await db_session.execute(select(Snapshot))).scalars().all()
    assert len(snapshots) == 2
    assert {str(saved.id) for saved in snapshots} == {other_id, accepted["snapshot_id"]}
    assert sum(saved.vehicle_id == truck9.id for saved in snapshots) == 1
    assert (
        await db_session.execute(select(func.count()).select_from(FleetMembership))
    ).scalar_one() == 2
    await db_session.refresh(truck9)
    assert truck9.vin == VIN and truck9.customer_id == other.customer_id
    assert truck9.last_lat is None and truck9.last_lng is None
    assert telemetry.utc(membership9.effective_from) == base + timedelta(seconds=30)
