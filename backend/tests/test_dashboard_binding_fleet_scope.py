"""One shared source directory must commit independently for each approved fleet."""

import copy
from datetime import timedelta

import pytest
from app.db.models.customer import Customer
from app.db.models.fleet_driver_record import FleetDriverRecordCapture
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.services import fleet_driver_records, fleet_telemetry
from fastapi import HTTPException
from scripts.motive_drivers import import_records, runner
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_dashboard_vehicle_bindings import setup
from tests.test_fleet_driver_records import VIN
from tests.test_motive_driver_worker import document


@pytest.mark.asyncio
async def test_shared_directory_primary_secondary_and_empty_scope_commit_and_readback(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, vehicle, member, binding, _ = await setup(db_session, monkeypatch)
    customers = [
        Customer(
            tenant_id=actor.tenant_id,
            first_name="Other",
            last_name=str(n),
            email=f"other-{n}@example.invalid",
            company_name=f"Approved fleet {n}",
            fleet_enabled=True,
        )
        for n in (1, 2)
    ]
    db_session.add_all(customers)
    await db_session.flush()
    other = Vehicle(
        tenant_id=actor.tenant_id,
        customer_id=customers[0].id,
        vin=VIN,
        make="Synthetic",
        model="Truck",
        driver_name="Synthetic Driver",
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        FleetMembership(
            tenant_id=actor.tenant_id,
            vehicle_id=other.id,
            fleet_customer_id=customers[0].id,
            effective_from=fleet_telemetry.now() - timedelta(days=1),
        )
    )
    await db_session.commit()
    doc = document()
    doc["drivers"][0].update(
        vin=None, provider_vehicle_id="123", source_vin_state="not_displayed"
    )
    second = copy.deepcopy(doc["drivers"][0])
    second.update(vin=VIN, provider_vehicle_id="456", provider_driver_id="driver-other")
    second.pop("source_vin_state")
    doc["drivers"].append(second)
    doc.update(driver_directory_count=2, terminal_evidence="Showing 2 of 2")
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    scopes = [member.fleet_customer_id, customers[0].id, customers[1].id]
    for ordinal, customer in enumerate(scopes):
        receipt = await runner.run(
            factory,
            doc,
            actor.tenant_id,
            actor.id,
            "Synthetic Fleet",
            "KT123",
            tmp_path / f"scope-{ordinal}.json",
            commit=True,
            expected_customer_id=customer,
        )
        expected = 0 if ordinal == 2 else 1
        assert receipt["stage"] == "verified" and receipt["committed"] is True
        assert receipt["readback_verified"] == receipt["replay_unchanged"] == expected
    captures = (
        (await db_session.execute(select(FleetDriverRecordCapture))).scalars().all()
    )
    assert {(row.vehicle_id, row.fleet_customer_id) for row in captures} == {
        (vehicle.id, member.fleet_customer_id),
        (other.id, customers[0].id),
    }
    assert len(captures) == 2 and binding.revoked_at is None
    assert (
        await fleet_driver_records.read(db_session, actor.tenant_id, vehicle.id)
    ).record.safety_score == 82
    assert (
        await fleet_driver_records.read(db_session, actor.tenant_id, other.id)
    ).record.safety_score == 82


@pytest.mark.parametrize("change", ["revoked", "local_vin"])
@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.asyncio
async def test_saved_eligible_binding_rechecks_context_during_commit_or_readback(
    db_session, monkeypatch, change, apply
):
    actor, vehicle, member, binding, _ = await setup(db_session, monkeypatch)
    doc = document()
    doc["drivers"][0].update(
        vin=None, provider_vehicle_id="123", source_vin_state="not_displayed"
    )
    args = (db_session, doc, actor.tenant_id, actor.id, "Synthetic Fleet", "KT123")
    dry = await import_records.batch(
        *args, apply=False, expected_customer_id=member.fleet_customer_id
    )
    eligible = {
        row["client_request_id"]
        for row in dry
        if row["status"] in {"would_create", "unchanged"}
    }
    assert len(eligible) == 1
    await import_records.batch(
        *args,
        apply=True,
        expected_customer_id=member.fleet_customer_id,
        eligible=eligible,
    )
    if change == "revoked":
        binding.revoked_at = fleet_telemetry.now()
    else:
        vehicle.vin = VIN
    await db_session.flush()
    with pytest.raises(HTTPException):
        await import_records.batch(
            *args,
            apply=apply,
            expected_customer_id=member.fleet_customer_id,
            eligible=eligible,
        )
