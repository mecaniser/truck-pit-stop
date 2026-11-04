"""Reviewed provider/VIN exceptions never widen the default fleet scope."""

import copy
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from app.db.models.customer import Customer
from app.db.models.fleet_diagnostic import FleetDiagnosticCapture
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.services.fleet_telemetry import now
from fastapi import HTTPException
from scripts.motive_health.runner import run
from scripts.motive_health.targets import normalize_targets
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_db036_fleet_telemetry import prepared
from tests.test_fleet_diagnostics import document


async def fleet_fixture(db, monkeypatch):
    actor, default, default_member = await prepared(db, monkeypatch)
    customer = Customer(
        tenant_id=actor.tenant_id,
        first_name="Reviewed",
        last_name="Fleet",
        company_name="Synthetic Elis",
        email="reviewed@example.test",
        fleet_enabled=True,
    )
    db.add(customer)
    await db.flush()
    trucks, members = [], []
    for index, vin in enumerate(("2M8GDM9AXKP042788", "3M8GDM9AXKP042788")):
        truck = Vehicle(
            tenant_id=actor.tenant_id,
            customer_id=customer.id,
            vin=vin,
            unit_number=str(609 + index),
            make="Fixture",
            model="Truck",
            mileage=111,
        )
        db.add(truck)
        await db.flush()
        member = FleetMembership(
            tenant_id=actor.tenant_id,
            vehicle_id=truck.id,
            fleet_customer_id=customer.id,
            effective_from=now() - timedelta(days=1),
        )
        db.add(member)
        trucks.append(truck)
        members.append(member)
    await db.commit()
    source = document()
    for index, truck in enumerate(trucks):
        row = copy.deepcopy(source["vehicles"][0])
        row.update(
            provider_vehicle_id=str(456 + index), unit=truck.unit_number, vin=truck.vin
        )
        source["vehicles"].append(row)
    source["health_directory_count"] = 3
    source["terminal_evidence"] = "Showing 3 of 3"
    for row in source["vehicles"]:
        row["vitals"] = {
            "source_read_at": row["source_read_at"],
            "odometer_miles": 600001.25,
            "engine_hours": 0,
        }
    targets = {
        "456": {"vehicle_id": str(trucks[0].id), "fleet_customer_id": str(customer.id)}
    }
    return actor, default, default_member, trucks, members, source, targets


@pytest.mark.parametrize(
    "value",
    [
        [],
        "{}",
        {"456": {}},
        {"unit609": {"vehicle_id": str(uuid4()), "fleet_customer_id": str(uuid4())}},
        {"456": {"vehicle_id": "bad", "fleet_customer_id": str(uuid4())}},
    ],
)
def test_invalid_targets(value):
    with pytest.raises(ValueError):
        normalize_targets(value)


def test_duplicate_local_target_rejected():
    target = {"vehicle_id": str(uuid4()), "fleet_customer_id": str(uuid4())}
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_targets({"123": target, "456": target})


@pytest.mark.asyncio
@pytest.mark.parametrize("faults", [True, False])
async def test_default_and_reviewed_fleet_atomic_replay(
    _db_engine, db_session, monkeypatch, tmp_path, faults
):
    (
        actor,
        default,
        default_member,
        trucks,
        members,
        source,
        targets,
    ) = await fleet_fixture(db_session, monkeypatch)
    if not faults:
        source["vehicles"][1].update(
            state="unavailable", codes=[], explicit_empty=False
        )
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    args = (
        factory,
        source,
        actor.tenant_id,
        actor.id,
        "77 CARGO LLC",
        "KT8934277",
        tmp_path / "reviewed.json",
    )
    options = {
        "expected_customer_id": default_member.fleet_customer_id,
        "reviewed_targets": targets,
    }
    dry = await run(*args, **options)
    assert not dry["committed"]
    assert dry["reviewed_targets"] == targets
    assert (
        await db_session.execute(
            select(func.count()).select_from(FleetTelemetrySnapshot)
        )
    ).scalar_one() == 0
    first = await run(*args, **options, commit=True)
    repeated = await run(*args, **options, commit=True, recovery=True)
    assert first["stage"] == repeated["stage"] == "verified"
    assert first["readback_verified"] == (4 if faults else 3)
    async with factory() as db:
        snapshots = (await db.execute(select(FleetTelemetrySnapshot))).scalars().all()
        assert {s.vehicle_id for s in snapshots} == {default.id, trucks[0].id}
        reviewed = next(s for s in snapshots if s.vehicle_id == trucks[0].id)
        assert reviewed.fleet_membership_id == members[0].id
        assert reviewed.fleet_customer_id == members[0].fleet_customer_id
        assert reviewed.verified_vin == trucks[0].vin and reviewed.engine_hours == 0
        diagnostics = (await db.execute(select(FleetDiagnosticCapture))).scalars().all()
        assert len(diagnostics) == (2 if faults else 1)
        assert all(d.vehicle_id != trucks[1].id for d in diagnostics)
    await db_session.refresh(trucks[0])
    assert trucks[0].mileage == 111 and default.mileage == 100
    assert not any(
        r.get("vehicle_id") == str(trucks[1].id) and r["status"] == "source_missing"
        for r in first["rows"]
    )
    # Removing OR retargeting an approved exception cannot recover an old attempt.
    for changed in ({}, {"456": {**targets["456"], "vehicle_id": str(uuid4())}}):
        with pytest.raises(ValueError, match="immutable identity mismatch"):
            await run(
                *args,
                expected_customer_id=default_member.fleet_customer_id,
                reviewed_targets=changed,
                commit=True,
                recovery=True,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "vehicle",
        "customer",
        "vin",
        "deleted",
        "duplicate_member",
        "old_read",
        "foreign_tenant",
    ],
)
async def test_reviewed_target_drift_fails_without_writes(
    _db_engine, db_session, monkeypatch, tmp_path, change
):
    (
        actor,
        default,
        default_member,
        trucks,
        members,
        source,
        targets,
    ) = await fleet_fixture(db_session, monkeypatch)
    if change == "vehicle":
        targets["456"]["vehicle_id"] = str(default.id)
    elif change == "customer":
        targets["456"]["fleet_customer_id"] = str(default_member.fleet_customer_id)
    elif change == "vin":
        source["vehicles"][1]["vin"] = "4M8GDM9AXKP042788"
    elif change == "deleted":
        trucks[0].deleted_at = now()
    elif change == "duplicate_member":
        db_session.add(
            FleetMembership(
                tenant_id=actor.tenant_id,
                vehicle_id=trucks[0].id,
                fleet_customer_id=members[0].fleet_customer_id,
                effective_from=now() - timedelta(days=1),
            )
        )
    elif change == "old_read":
        members[0].effective_from = now() - timedelta(seconds=5)
    elif change == "foreign_tenant":
        # Source VIN exists only in a different tenant; resolver must not borrow it.
        from app.db.models.tenant import Tenant

        tenant = Tenant(name="Other", slug=uuid4().hex)
        db_session.add(tenant)
        await db_session.flush()
        trucks[0].tenant_id = tenant.id
    await db_session.commit()
    with pytest.raises((HTTPException, ValueError)):
        await run(
            async_sessionmaker(_db_engine, expire_on_commit=False),
            source,
            actor.tenant_id,
            actor.id,
            "77 CARGO LLC",
            "KT8934277",
            tmp_path / "bad.json",
            expected_customer_id=default_member.fleet_customer_id,
            reviewed_targets=targets,
            commit=True,
        )
    assert (
        await db_session.execute(
            select(func.count()).select_from(FleetTelemetrySnapshot)
        )
    ).scalar_one() == 0
    assert (
        await db_session.execute(
            select(func.count()).select_from(FleetDiagnosticCapture)
        )
    ).scalar_one() == 0


@pytest.mark.asyncio
async def test_missing_target_reporting_does_not_expand_whole_fleet(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, default_member, trucks, _, source, targets = await fleet_fixture(
        db_session, monkeypatch
    )
    source["vehicles"] = source["vehicles"][:1]
    source["health_directory_count"] = 1
    source["terminal_evidence"] = "Showing 1 of 1"
    receipt = await run(
        async_sessionmaker(_db_engine, expire_on_commit=False),
        source,
        actor.tenant_id,
        actor.id,
        "77 CARGO LLC",
        "KT8934277",
        tmp_path / "missing.json",
        expected_customer_id=default_member.fleet_customer_id,
        reviewed_targets=targets,
    )
    missing = {
        r["vehicle_id"] for r in receipt["rows"] if r["status"] == "source_missing"
    }
    assert missing == {str(trucks[0].id)}


@pytest.mark.asyncio
async def test_targets_need_pin_and_legacy_receipt_stays_legacy(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, default_member, _, _, source, targets = await fleet_fixture(
        db_session, monkeypatch
    )
    args = (
        async_sessionmaker(_db_engine, expire_on_commit=False),
        source,
        actor.tenant_id,
        actor.id,
        "77 CARGO LLC",
        "KT8934277",
        tmp_path / "legacy.json",
    )
    with pytest.raises(ValueError, match="default fleet pin"):
        await run(*args, reviewed_targets=targets)
    first = await run(
        *args, expected_customer_id=default_member.fleet_customer_id, commit=True
    )
    assert "reviewed_targets" not in json.loads(
        (tmp_path / "legacy.json.attempt.json").read_text()
    )
    again = await run(
        *args,
        expected_customer_id=default_member.fleet_customer_id,
        commit=True,
        recovery=True,
    )
    assert first["readback_verified"] == again["readback_verified"] == 2
