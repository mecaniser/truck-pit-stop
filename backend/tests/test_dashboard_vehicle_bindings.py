"""Reviewed no-VIN identity: imports, replays and projections fail closed."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.models.dashboard_vehicle_binding import DashboardVehicleBinding
from app.db.models.fleet_driver_record import FleetDriverRecordCapture
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.dashboard_vehicle_binding import BindingManifest
from app.schemas.fleet_telemetry import TelemetryCapture
from app.services import dashboard_vehicle_bindings as bindings
from app.services import fleet_driver_records, fleet_telemetry
from fastapi import HTTPException
from pydantic import ValidationError
from scripts.motive_drivers import import_records, runner
from scripts.motive_sync import import_locations
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.exc import IntegrityError
from tests.test_fleet_driver_records import VIN, body, fixture, save
from tests.test_motive_driver_worker import document
from tests.test_motive_sync_import import source


async def setup(db, monkeypatch, *, expires=True):
    actor, vehicle, member = await fixture(db, monkeypatch)
    vehicle.vin = "PENDING-26"
    vehicle.last_lat = vehicle.last_lng = vehicle.last_location_at = None
    await db.flush()
    manifest = BindingManifest(
        vehicle_id=vehicle.id,
        fleet_customer_id=member.fleet_customer_id,
        fleet_membership_id=member.id,
        source_company_id="KT123",
        source_company_label="Synthetic Fleet",
        provider_vehicle_id="123",
        placeholder_vin="PENDING-26",
        effective_to=fleet_telemetry.now() + timedelta(days=30) if expires else None,
        review_note="Synthetic reviewed source identity",
        source_evidence_sha256="a" * 64,
        source_evidence_read_at=fleet_telemetry.now(),
        source_vin_state="not_displayed",
    )
    binding, _action = await bindings.create(
        db, actor.tenant_id, actor.id, manifest, apply=True
    )
    # Synthetic review predates measurements; creation itself never backdates.
    binding.reviewed_at = binding.effective_from = fleet_telemetry.now() - timedelta(
        minutes=5
    )
    await db.commit()
    return actor, vehicle, member, binding, manifest


def driver_body(binding, **changes):
    return body(
        vin=None,
        dashboard_binding_id=binding.id,
        source_vin_state="not_displayed",
        provider_vehicle_id="123",
        **changes,
    )


@pytest.mark.asyncio
async def test_bound_driver_capture_replay_and_revoked_projection(
    db_session, monkeypatch
):
    actor, vehicle, member, binding, _ = await setup(db_session, monkeypatch)
    request = driver_body(binding)
    row, status = await save(db_session, actor, member, request)
    assert (
        status == "created"
        and row.verified_vin is None
        and row.dashboard_binding_id == binding.id
    )
    view = await fleet_driver_records.read(db_session, actor.tenant_id, vehicle.id)
    assert view.record.identity_basis == "motive_current_assignment"
    assert view.record.vehicle_identity_basis == "reviewed_provider_binding"
    assert view.record.vehicle_identity_binding_id == binding.id
    assert view.record.safety_score == 82
    assert (await save(db_session, actor, member, request))[1] == "unchanged"
    binding.revoked_at = fleet_telemetry.now()
    await db_session.flush()
    assert (
        await fleet_driver_records.read(db_session, actor.tenant_id, vehicle.id)
    ).record is None
    with pytest.raises(HTTPException):
        await save(db_session, actor, member, request)
    assert vehicle.vin == "PENDING-26"


@pytest.mark.asyncio
async def test_reviewed_identity_unavailable_preserves_binding_and_other_fleet_capture(
    _db_engine, db_session, monkeypatch, tmp_path
):
    actor, placeholder, member, binding, _manifest = await setup(
        db_session, monkeypatch, expires=False
    )
    other = Vehicle(
        tenant_id=actor.tenant_id,
        customer_id=member.fleet_customer_id,
        vin="2M8GDM9AXKP042788",
        unit_number="77",
        make="Test",
        model="Tractor",
        year=2020,
        driver_name="Other Driver",
    )
    db_session.add(other)
    await db_session.flush()
    other_member = FleetMembership(
        tenant_id=actor.tenant_id,
        vehicle_id=other.id,
        fleet_customer_id=member.fleet_customer_id,
        effective_from=fleet_telemetry.now() - timedelta(days=1),
    )
    db_session.add(other_member)
    await db_session.commit()

    source_doc = document()
    source_doc["drivers"][0].update(
        provider_driver_id="other-provider-driver",
        provider_vehicle_id="other-provider-vehicle",
        driver_name="Other Driver",
        unit="77",
        vin=other.vin,
    )
    source_doc["drivers"].append(
        {
            "provider_driver_id": "reviewed-placeholder-driver",
            "driver_name": "Placeholder Driver",
            "provider_vehicle_id": binding.provider_vehicle_id,
            "unit": "26",
            "vin": None,
            "state": "unavailable",
            "source_read_at": source_doc["finished_at"],
            "assignment_verified_before": True,
            "assignment_verified_after": True,
            "reason": "vehicle_identity_changed",
        }
    )
    source_doc["driver_directory_count"] = 2
    source_doc["terminal_evidence"] = "Showing 2 of 2"
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    receipt = await runner.run(
        factory,
        source_doc,
        actor.tenant_id,
        actor.id,
        "Synthetic Fleet",
        "KT123",
        tmp_path / "reviewed-identity-unavailable.json",
        commit=True,
        expected_customer_id=member.fleet_customer_id,
    )

    assert receipt["stage"] == "verified"
    assert receipt["readback_verified"] == 1
    deferred = next(
        row for row in receipt["rows"]
        if row.get("reason") == "vehicle_identity_changed"
    )
    assert deferred["status"] == "unavailable"
    assert deferred["capture_id"] is None
    async with factory() as db:
        assert await db.scalar(
            select(func.count()).select_from(FleetDriverRecordCapture)
        ) == 1
        capture = (await db.execute(select(FleetDriverRecordCapture))).scalar_one()
        assert capture.vehicle_id == other.id and capture.dashboard_binding_id is None
        persisted = (
            await db.execute(
                select(DashboardVehicleBinding).where(
                    DashboardVehicleBinding.id == binding.id
                )
            )
        ).scalar_one()
        assert persisted.revoked_at is None
        assert persisted.vehicle_id == placeholder.id
        assert persisted.fleet_membership_id == member.id
        assert persisted.provider_vehicle_id == binding.provider_vehicle_id
        assert placeholder.vin == "PENDING-26"


@pytest.mark.parametrize(
    "change",
    [
        "expired",
        "future",
        "membership",
        "placeholder",
        "real_vin",
        "deleted_vehicle",
        "deleted_binding",
        "wrong_company",
        "wrong_provider",
        "wrong_tenant",
        "wrong_customer",
        "old_source",
    ],
)
@pytest.mark.asyncio
async def test_binding_import_and_projection_negative_context(
    db_session, monkeypatch, change
):
    actor, vehicle, member, binding, _ = await setup(db_session, monkeypatch)
    request = driver_body(binding)
    await save(db_session, actor, member, request)
    args = {
        "company_label": "Synthetic Fleet",
        "binding_id": binding.id,
        "expected_customer_id": member.fleet_customer_id,
    }
    tenant, company, provider, read = (
        actor.tenant_id,
        "KT123",
        "123",
        request.source_read_at,
    )
    stamp = fleet_telemetry.now()
    if change == "expired":
        binding.effective_to = stamp - timedelta(seconds=1)
    if change == "future":
        binding.effective_from = stamp + timedelta(seconds=1)
    if change == "membership":
        member.effective_to = stamp - timedelta(seconds=1)
    if change == "placeholder":
        vehicle.vin = "PENDING-27"
    if change == "real_vin":
        vehicle.vin = VIN
    if change == "deleted_vehicle":
        vehicle.deleted_at = stamp
    if change == "deleted_binding":
        binding.deleted_at = stamp
    if change == "wrong_company":
        company = "other"
    if change == "wrong_provider":
        provider = "456"
    if change == "wrong_tenant":
        tenant = uuid4()
    if change == "wrong_customer":
        args["expected_customer_id"] = uuid4()
    if change == "old_source":
        read = stamp - timedelta(hours=1)
    await db_session.flush()
    with pytest.raises(HTTPException):
        await bindings.resolve(db_session, tenant, company, provider, read, **args)
    if change in {
        "expired",
        "future",
        "membership",
        "placeholder",
        "real_vin",
        "deleted_vehicle",
        "deleted_binding",
    }:
        try:
            assert (
                await fleet_driver_records.read(db_session, actor.tenant_id, vehicle.id)
            ).record is None
        except HTTPException as exc:
            assert exc.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_binding_and_ambiguous_membership_rejected(
    db_session, monkeypatch
):
    actor, vehicle, member, binding, manifest = await setup(db_session, monkeypatch)
    repeated, action = await bindings.create(
        db_session, actor.tenant_id, actor.id, manifest, apply=True
    )
    assert repeated.id == binding.id and action == "unchanged"
    with pytest.raises(HTTPException, match="reviewed_vehicle_binding_conflict"):
        await bindings.create(
            db_session,
            actor.tenant_id,
            actor.id,
            manifest.model_copy(
                update={"review_note": "Different request cannot remap"}
            ),
            apply=True,
        )
    duplicate = DashboardVehicleBinding(
        **{
            column.name: getattr(binding, column.name)
            for column in binding.__table__.columns
            if column.name not in {"id", "created_at", "updated_at"}
        }
    )
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(duplicate)
            await db_session.flush()
    db_session.add(
        FleetMembership(
            tenant_id=actor.tenant_id,
            vehicle_id=vehicle.id,
            fleet_customer_id=member.fleet_customer_id,
            effective_from=member.effective_from,
        )
    )
    await db_session.flush()
    with pytest.raises(HTTPException):
        await bindings.resolve(
            db_session,
            actor.tenant_id,
            "KT123",
            "123",
            fleet_telemetry.now(),
            company_label="Synthetic Fleet",
        )


@pytest.mark.asyncio
async def test_inactive_actor_and_changed_assignment_do_not_import(
    db_session, monkeypatch
):
    actor, vehicle, member, binding, _ = await setup(db_session, monkeypatch)
    request = driver_body(binding)
    actor.is_active = False
    await db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await save(db_session, actor, member, request)
    assert exc.value.status_code == 403
    actor.is_active = True
    vehicle.driver_assignment_changed_at = fleet_telemetry.now()
    with pytest.raises(HTTPException, match="source_before_driver_assignment_change"):
        await save(db_session, actor, member, request)


@pytest.mark.asyncio
async def test_driver_worker_requires_exact_binding_and_source_absence(
    db_session, monkeypatch
):
    actor, vehicle, member, _binding, _ = await setup(db_session, monkeypatch)
    doc = document()
    row = doc["drivers"][0]
    row.update(vin=None, provider_vehicle_id="123", source_vin_state="not_displayed")
    import_records.validate(doc, "Synthetic Fleet", "KT123")
    results = await import_records.batch(
        db_session,
        doc,
        actor.tenant_id,
        actor.id,
        "Synthetic Fleet",
        "KT123",
        apply=True,
        expected_customer_id=member.fleet_customer_id,
    )
    assert results[0]["status"] == "created" and results[0]["vehicle_id"] == str(
        vehicle.id
    )
    del row["source_vin_state"]
    with pytest.raises(ValueError):
        import_records.validate(doc, "Synthetic Fleet", "KT123")
    row.update(source_vin_state="not_displayed", vin=VIN)
    with pytest.raises(ValueError):
        import_records.validate(doc, "Synthetic Fleet", "KT123")


@pytest.mark.parametrize("speed_mph", [0, 15])
@pytest.mark.asyncio
async def test_location_speed_worker_bound_capture_and_manual_boundary(
    db_session, monkeypatch, speed_mph
):
    actor, vehicle, member, binding, _ = await setup(db_session, monkeypatch)
    doc = source()
    doc.update(company_id="KT123", company_label="Synthetic Fleet")
    row = doc["vehicles"][0]
    row.update(vin=None, source_vin_state="not_displayed", speed_mph=speed_mph)
    rows = import_locations.parse_document(
        doc, "Synthetic Fleet", "KT123", fleet_telemetry.now()
    )
    results = await import_locations.execute_pass(
        db_session, rows, actor.tenant_id, actor.id, "Synthetic Fleet", "KT123"
    )
    assert results[0]["created"] is True and results[0]["board_verified"] is True
    captured = (await db_session.execute(select(FleetTelemetrySnapshot))).scalar_one()
    assert captured.verified_vin is None and captured.dashboard_binding_id == binding.id
    assert captured.speed_mph == speed_mph and vehicle.vin == "PENDING-26"
    before_revoke = SimpleNamespace(
        id=vehicle.id,
        board_membership_customer_id=member.fleet_customer_id,
        telemetry=None,
    )
    await fleet_telemetry.attach(db_session, [before_revoke], actor.tenant_id)
    assert before_revoke.telemetry.speed.value == speed_mph
    assert before_revoke.telemetry.motion == ("moving" if speed_mph else "stopped")
    actor2, plans, _ = await import_locations.prepare(
        db_session, rows, actor.tenant_id, actor.id, "Synthetic Fleet", "KT123"
    )
    payload = plans[0][1]
    assert (await fleet_telemetry.capture(db_session, actor2, vehicle.id, payload))[
        1
    ] is False
    with pytest.raises(ValidationError):
        TelemetryCapture.model_validate(payload.model_dump())
    binding.revoked_at = fleet_telemetry.now()
    await db_session.flush()
    with pytest.raises(HTTPException):
        await fleet_telemetry.capture(db_session, actor2, vehicle.id, payload)
    truck = SimpleNamespace(
        id=vehicle.id,
        board_membership_customer_id=member.fleet_customer_id,
        telemetry=None,
    )
    await fleet_telemetry.attach(db_session, [truck], actor.tenant_id)
    assert truck.telemetry is None


def test_no_fake_vin_or_mixed_identity_is_accepted():
    with pytest.raises(ValidationError):
        body(vin="PENDING-26")
    with pytest.raises(ValidationError):
        body(vin=None)
    with pytest.raises(ValidationError):
        body(dashboard_binding_id=uuid4(), source_vin_state="not_displayed")


@pytest.mark.parametrize("collector", ["driver", "location"])
@pytest.mark.asyncio
async def test_real_provider_vin_revokes_exact_binding_with_audit(
    db_session, monkeypatch, collector
):
    actor, vehicle, member, binding, _ = await setup(db_session, monkeypatch)
    await save(db_session, actor, member, driver_body(binding))
    if collector == "driver":
        doc = document()
        doc["drivers"][0]["provider_vehicle_id"] = "123"
        await import_records.batch(
            db_session,
            doc,
            actor.tenant_id,
            actor.id,
            "Synthetic Fleet",
            "KT123",
            apply=True,
            expected_customer_id=member.fleet_customer_id,
        )
    else:
        doc = source()
        doc.update(company_id="KT123", company_label="Synthetic Fleet")
        rows = import_locations.parse_document(
            doc, "Synthetic Fleet", "KT123", fleet_telemetry.now()
        )
        await import_locations.execute_pass(
            db_session, rows, actor.tenant_id, actor.id, "Synthetic Fleet", "KT123"
        )
    assert binding.revocation_reason == "provider_vin_available"
    assert binding.revoked_source_vin == VIN and binding.revoked_by_user_id == actor.id
    assert len(binding.revoked_source_sha256) == 64 and binding.revoked_source_read_at
    assert vehicle.vin == "PENDING-26"
    assert (
        await fleet_driver_records.read(db_session, actor.tenant_id, vehicle.id)
    ).record is None


@pytest.mark.asyncio
async def test_unverified_malformed_and_pre_review_source_cannot_revoke(
    db_session, monkeypatch
):
    actor, _, member, binding, _ = await setup(db_session, monkeypatch)
    for changes in [
        {"complete": False},
        {"company_verified_after": False},
        {"company_id": "foreign"},
    ]:
        doc = document()
        doc["drivers"][0]["provider_vehicle_id"] = "123"
        doc.update(changes)
        with pytest.raises(ValueError):
            await import_records.batch(
                db_session,
                doc,
                actor.tenant_id,
                actor.id,
                "Synthetic Fleet",
                "KT123",
                apply=True,
                expected_customer_id=member.fleet_customer_id,
            )
        assert binding.revoked_at is None
    for vin, stamp, digest in [
        ("PENDING-26", fleet_telemetry.now(), "a" * 64),
        (VIN, fleet_telemetry.now() + timedelta(minutes=1), "a" * 64),
        (VIN, fleet_telemetry.now(), "not-a-digest"),
    ]:
        with pytest.raises(HTTPException):
            await bindings.invalidate_source_vin(
                db_session,
                actor.tenant_id,
                actor.id,
                "KT123",
                "Synthetic Fleet",
                "123",
                vin,
                stamp,
                digest,
            )
        assert binding.revoked_at is None
    assert not await bindings.invalidate_source_vin(
        db_session,
        actor.tenant_id,
        actor.id,
        "KT123",
        "Synthetic Fleet",
        "123",
        VIN,
        fleet_telemetry.utc(binding.reviewed_at) - timedelta(seconds=1),
        "a" * 64,
    )
    assert binding.revoked_at is None


@pytest.mark.asyncio
async def test_no_expiry_mapping_is_idempotent_until_revoked(db_session, monkeypatch):
    actor, _, _, binding, manifest = await setup(db_session, monkeypatch, expires=False)
    original = (
        binding.id,
        fleet_telemetry.utc(binding.reviewed_at),
        fleet_telemetry.utc(binding.effective_from),
        binding.effective_to,
    )
    repeated, action = await bindings.create(
        db_session, actor.tenant_id, actor.id, manifest, apply=True
    )
    assert action == "unchanged"
    assert original == (
        repeated.id,
        fleet_telemetry.utc(repeated.reviewed_at),
        fleet_telemetry.utc(repeated.effective_from),
        repeated.effective_to,
    )
    request = driver_body(binding)
    assert (
        await save(
            db_session,
            actor,
            SimpleNamespace(fleet_customer_id=binding.fleet_customer_id),
            request,
        )
    )[1] == "created"
    binding.revoked_at = fleet_telemetry.now()
    with pytest.raises(HTTPException, match="reviewed_vehicle_binding_conflict"):
        await bindings.create(
            db_session, actor.tenant_id, actor.id, manifest, apply=True
        )


@pytest.mark.parametrize("offset", [timedelta(hours=-3), timedelta(minutes=1)])
@pytest.mark.asyncio
async def test_new_binding_requires_fresh_nonfuture_review_evidence(
    db_session, monkeypatch, offset
):
    actor, vehicle, member = await fixture(db_session, monkeypatch)
    vehicle.vin = "PENDING-26"
    manifest = BindingManifest(
        vehicle_id=vehicle.id,
        fleet_customer_id=member.fleet_customer_id,
        fleet_membership_id=member.id,
        source_company_id="KT123",
        source_company_label="Synthetic Fleet",
        provider_vehicle_id="123",
        placeholder_vin="PENDING-26",
        review_note="Synthetic explicit source review",
        source_evidence_sha256="a" * 64,
        source_evidence_read_at=fleet_telemetry.now() + offset,
        source_vin_state="not_displayed",
    )
    with pytest.raises(HTTPException, match="fresh_review_source_required"):
        await bindings.create(
            db_session, actor.tenant_id, actor.id, manifest, apply=True
        )
    assert (
        not (await db_session.execute(select(DashboardVehicleBinding))).scalars().all()
    )
