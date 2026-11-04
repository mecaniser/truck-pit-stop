"""Health vitals reuse reviewed no-VIN authority, including Fleet projection."""

import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.models.dashboard_vehicle_binding import DashboardVehicleBinding
from app.db.models.fleet_diagnostic import FleetDiagnosticCapture
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot
from app.db.models.vehicle_relationship import FleetMembership
from app.services import fleet_telemetry
from fastapi import HTTPException
from scripts.motive_health.import_health import validate
from scripts.motive_health.runner import run
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_dashboard_vehicle_bindings import setup
from tests.test_fleet_diagnostics import document


def bound_source(binding, *, mileage=548550.82, hours=0):
    source = document()
    source.update(
        company_id=binding.source_company_id, company_label=binding.source_company_label
    )
    source["vehicles"][0].update(
        vin=None,
        source_vin_state="not_displayed",
        provider_vehicle_id=binding.provider_vehicle_id,
        unit="26",
        state="unavailable",
        explicit_empty=False,
        codes=[],
        count_before=None,
        count_after=None,
        reason="vin_unavailable",
    )
    row = source["vehicles"][0]
    row["vitals"] = {
        "odometer_miles": mileage,
        "engine_hours": hours,
        "source_read_at": row["source_read_at"],
    }
    return source


@pytest.mark.asyncio
async def test_bound_health_dry_run_commit_replay_projection_and_revocation(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, vehicle, member, binding, _ = await setup(
        db_session, monkeypatch, expires=False
    )
    source = bound_source(binding)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    args = (
        factory,
        source,
        actor.tenant_id,
        actor.id,
        binding.source_company_label,
        binding.source_company_id,
        tmp_path / "bound.json",
    )
    options = {"expected_customer_id": member.fleet_customer_id}
    dry = await run(*args, **options)
    assert dry["rows"][0]["status"] == "would_create"
    assert (
        await db_session.execute(
            select(func.count()).select_from(FleetTelemetrySnapshot)
        )
    ).scalar_one() == 0
    first = await run(*args, **options, commit=True)
    assert first["stage"] == "verified" and first["readback_verified"] == 1
    assert [r["status"] for r in first["rows"]] == ["created", "unavailable"]
    repeated = await run(*args, **options, commit=True, recovery=True)
    assert repeated["rows"][0]["capture_id"] == first["rows"][0]["capture_id"]
    async with factory() as db:
        snapshot = (await db.execute(select(FleetTelemetrySnapshot))).scalar_one()
        assert (
            snapshot.verified_vin is None
            and snapshot.dashboard_binding_id == binding.id
        )
        assert (
            snapshot.fleet_customer_id == member.fleet_customer_id
            and snapshot.fleet_membership_id == member.id
        )
        note = json.loads(snapshot.evidence_note)
        assert (
            note["sourceReadTime"] == source["vehicles"][0]["vitals"]["source_read_at"]
        )
        assert note["company_id"] == binding.source_company_id
        projected = SimpleNamespace(
            id=vehicle.id,
            board_membership_customer_id=member.fleet_customer_id,
            telemetry=None,
        )
        await fleet_telemetry.attach(db, [projected], actor.tenant_id)
        assert projected.telemetry.odometer.value == 548550.82
        assert projected.telemetry.engine_hours.value == 0
        assert projected.telemetry.odometer.snapshot_id == str(snapshot.id)
        assert (
            await db.execute(select(func.count()).select_from(FleetDiagnosticCapture))
        ).scalar_one() == 0
    await db_session.refresh(vehicle)
    assert vehicle.vin == "PENDING-26" and vehicle.mileage == 100
    binding.revoked_at = fleet_telemetry.now()
    await db_session.commit()
    async with factory() as db:
        projected = SimpleNamespace(
            id=vehicle.id,
            board_membership_customer_id=member.fleet_customer_id,
            telemetry=None,
        )
        await fleet_telemetry.attach(db, [projected], actor.tenant_id)
        assert projected.telemetry is None or projected.telemetry.odometer is None
    with pytest.raises(HTTPException):
        await run(*args, **options, commit=True, recovery=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "revoked",
        "expired",
        "company",
        "tenant",
        "customer",
        "provider",
        "placeholder",
        "duplicate_member",
        "source_before_binding",
        "source_before_member",
    ],
)
async def test_bound_authority_rejections_never_write(
    _db_engine, db_session, monkeypatch, tmp_path, change
):
    actor, vehicle, member, binding, _ = await setup(
        db_session, monkeypatch, expires=False
    )
    source = bound_source(binding)
    tenant = actor.tenant_id
    customer = member.fleet_customer_id
    if change == "missing":
        binding.deleted_at = fleet_telemetry.now()
    elif change == "revoked":
        binding.revoked_at = fleet_telemetry.now()
    elif change == "expired":
        binding.effective_to = fleet_telemetry.now() - timedelta(seconds=1)
    elif change == "company":
        source["company_id"] = "KT999"
    elif change == "tenant":
        binding.tenant_id = uuid4()
    elif change == "customer":
        customer = uuid4()
    elif change == "provider":
        source["vehicles"][0]["provider_vehicle_id"] = "456"
    elif change == "placeholder":
        vehicle.vin = "PENDING-99"
    elif change == "duplicate_member":
        db_session.add(
            FleetMembership(
                tenant_id=tenant,
                vehicle_id=vehicle.id,
                fleet_customer_id=customer,
                effective_from=fleet_telemetry.now() - timedelta(days=1),
            )
        )
    elif change == "source_before_binding":
        binding.effective_from = fleet_telemetry.now() - timedelta(seconds=5)
    elif change == "source_before_member":
        member.effective_from = fleet_telemetry.now() - timedelta(seconds=5)
    await db_session.commit()
    receipt = await run(
        async_sessionmaker(_db_engine, expire_on_commit=False),
        source,
        tenant,
        actor.id,
        source["company_label"],
        source["company_id"],
        tmp_path / "invalid.json",
        expected_customer_id=customer,
        commit=False,
    )
    assert receipt["rows"][0]["status"] == "excluded"
    assert receipt["rows"][0]["reason"] in {
        "reviewed_vehicle_binding_required",
        "reviewed_vehicle_binding_invalid",
    }
    assert (
        await db_session.execute(
            select(func.count()).select_from(FleetTelemetrySnapshot)
        )
    ).scalar_one() == 0


@pytest.mark.asyncio
async def test_explicit_target_cannot_retarget_bound_provider(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, member, binding, _ = await setup(db_session, monkeypatch, expires=False)
    source = bound_source(binding)
    with pytest.raises(HTTPException) as caught:
        await run(
            async_sessionmaker(_db_engine, expire_on_commit=False),
            source,
            actor.tenant_id,
            actor.id,
            source["company_label"],
            source["company_id"],
            tmp_path / "wrong-target.json",
            expected_customer_id=member.fleet_customer_id,
            reviewed_targets={
                binding.provider_vehicle_id: {
                    "vehicle_id": str(uuid4()),
                    "fleet_customer_id": str(member.fleet_customer_id),
                }
            },
        )
    assert caught.value.detail["code"] == "reviewed_health_target_mismatch"


@pytest.mark.asyncio
async def test_bound_source_with_no_readings_is_present_without_healthy_diagnostics(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, _, member, binding, _ = await setup(db_session, monkeypatch, expires=False)
    source = bound_source(binding, mileage=None, hours=None)
    result = await run(
        async_sessionmaker(_db_engine, expire_on_commit=False),
        source,
        actor.tenant_id,
        actor.id,
        source["company_label"],
        source["company_id"],
        tmp_path / "unavailable.json",
        expected_customer_id=member.fleet_customer_id,
        commit=True,
    )
    assert [row["status"] for row in result["rows"]] == ["unavailable"]
    assert result["readback_verified"] == 0
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
@pytest.mark.parametrize(
    "change", ["replace_member", "placeholder", "expire", "replace_binding"]
)
async def test_bound_recovery_cannot_drop_or_rebind_an_eligible_request(
    _db_engine, db_session, monkeypatch, tmp_path, change
):
    actor, vehicle, member, binding, _ = await setup(
        db_session, monkeypatch, expires=False
    )
    source = bound_source(binding)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    args = (
        factory,
        source,
        actor.tenant_id,
        actor.id,
        source["company_label"],
        source["company_id"],
        tmp_path / "recovery.json",
    )
    options = {"expected_customer_id": member.fleet_customer_id}
    first = await run(*args, **options, commit=True)
    if change == "replace_member":
        member.effective_to = fleet_telemetry.now()
        db_session.add(
            FleetMembership(
                tenant_id=actor.tenant_id,
                vehicle_id=vehicle.id,
                fleet_customer_id=member.fleet_customer_id,
                effective_from=fleet_telemetry.now(),
            )
        )
    elif change == "placeholder":
        vehicle.vin = "PENDING-OTHER"
    elif change == "expire":
        binding.effective_to = fleet_telemetry.now() - timedelta(seconds=1)
    elif change == "replace_binding":
        # A replacement can be otherwise valid but cannot inherit an older request's digest.
        binding.deleted_at = fleet_telemetry.now()
        fields = {
            column.name: getattr(binding, column.name)
            for column in DashboardVehicleBinding.__table__.columns
            if column.name not in {"id", "created_at", "updated_at", "deleted_at"}
        }
        replacement = DashboardVehicleBinding(**fields)
        db_session.add(replacement)
    await db_session.commit()
    with pytest.raises((HTTPException, ValueError)):
        await run(*args, **options, commit=True, recovery=True)
    async with factory() as db:
        snapshots = (await db.execute(select(FleetTelemetrySnapshot))).scalars().all()
        assert (
            len(snapshots) == 1
            and str(snapshots[0].id) == first["rows"][0]["capture_id"]
        )


@pytest.mark.parametrize(
    "change", ["no_absence", "invalid_absence", "contradictory_vin", "healthy_faults"]
)
def test_bound_source_proof_cannot_be_fabricated(change):
    from types import SimpleNamespace

    binding = SimpleNamespace(
        source_company_id="KT123",
        source_company_label="Synthetic Fleet",
        provider_vehicle_id="123",
    )
    source = bound_source(binding)
    row = source["vehicles"][0]
    if change == "no_absence":
        row.pop("source_vin_state")
    elif change == "invalid_absence":
        row["source_vin_state"] = "unknown"
    elif change == "contradictory_vin":
        row["vin"] = "1M8GDM9AXKP042788"
    elif change == "healthy_faults":
        row.update(state="captured", explicit_empty=True)
    with pytest.raises(ValueError):
        validate(source, binding.source_company_label, binding.source_company_id)
