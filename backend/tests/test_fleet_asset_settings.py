"""DB157 follow-up: no active fleet trailer without its own current tractor."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.api.v1.endpoints import customers, fleet, vehicles
from app.db.models.customer import Customer
from app.db.models.fleet_asset_attachment import FleetAssetAttachment
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet import FleetAssetSettingsUpdate, FleetMembershipCreate, FleetTruckCreate, TruckUpdate
from app.schemas.vehicle import VehicleBase, VehicleCreate, VehicleUpdate
from app.services import fleet_assets
from app.services.vehicle_identity import end_fleet_membership, ensure_fleet_membership, sync_customer_fleet_memberships
from tests.test_fleet_assets import admit, body, prepared


def settings(kind, target=None, expected_kind="unknown", expected_target=None):
    return FleetAssetSettingsUpdate(equipment_type=kind, attached_vehicle_id=target,
                                    expected_equipment_type=expected_kind,
                                    expected_attached_vehicle_id=expected_target)


def test_asset_settings_requires_all_four_fields_and_valid_types():
    full = settings("tractor").model_dump()
    for field in full:
        with pytest.raises(ValidationError):
            FleetAssetSettingsUpdate.model_validate({key: value for key, value in full.items() if key != field})
    for field in ("equipment_type", "expected_equipment_type"):
        for bad in (None, "boat", "", 123):
            with pytest.raises(ValidationError):
                FleetAssetSettingsUpdate.model_validate({**full, field: bad})
    assert FleetTruckCreate(customer_id=uuid4(), make="Test", model="Truck").equipment_type == "tractor"


@pytest.mark.asyncio
async def test_atomic_type_and_pair_save_idempotency_reassignment_and_stale_protection(db_session):
    _, _, actor, tractor, _, other_tractor, _, unknown = await prepared(db_session)
    update = settings("trailer", tractor.id)
    first = await fleet.update_asset_settings(unknown.id, update, db_session, actor)
    assert first.equipment_type == "trailer" and first.attached_asset.id == tractor.id
    retry = await fleet.update_asset_settings(unknown.id, update, db_session, actor)
    assert retry.attached_asset.id == tractor.id
    next_update = settings("trailer", other_tractor.id, "trailer", tractor.id)
    moved = await fleet.update_asset_settings(unknown.id, next_update, db_session, actor)
    assert moved.attached_asset.id == other_tractor.id
    with pytest.raises(HTTPException) as exc:
        await fleet.update_asset_settings(unknown.id, settings("tractor", expected_kind="unknown"), db_session, actor)
    assert exc.value.status_code == 409
    rows = (await db_session.execute(select(FleetAssetAttachment).where(FleetAssetAttachment.trailer_id == unknown.id))).scalars().all()
    assert len(rows) == 2 and sum(row.detached_at is None for row in rows) == 1
    old_tractor = await fleet.truck_detail(tractor.id, db_session, actor)
    assert old_tractor.truck.attached_asset is None


@pytest.mark.asyncio
async def test_no_standalone_detach_or_tractor_role_change_can_strand_trailer(db_session):
    _, company, actor, tractor, trailer, other_tractor, _, unknown = await prepared(db_session)
    await admit(db_session, actor, company, trailer, tractor)
    for source, update in (
        (trailer.id, settings("trailer", expected_kind="trailer", expected_target=tractor.id)),
        (tractor.id, settings("tractor", expected_kind="tractor", expected_target=trailer.id)),
        (tractor.id, settings("trailer", other_tractor.id, "tractor", trailer.id)),
        (unknown.id, settings("trailer")),
    ):
        with pytest.raises(HTTPException) as exc:
            await fleet.update_asset_settings(source, update, db_session, actor)
        assert exc.value.status_code == 409
    for source, expected in ((trailer.id, tractor.id), (tractor.id, trailer.id)):
        with pytest.raises(HTTPException) as exc:
            await fleet.update_asset_attachment(source, body(None, expected), db_session, actor)
        assert exc.value.status_code == 409
    pair = (await db_session.execute(select(FleetAssetAttachment))).scalar_one()
    assert pair.detached_at is None


@pytest.mark.asyncio
async def test_legacy_classification_editors_cannot_create_unpaired_fleet_trailer(db_session):
    _, company, actor, _, _, _, _, unknown = await prepared(db_session)
    for action in (
        lambda: fleet.update_truck(unknown.id, TruckUpdate(equipment_type="trailer"), db_session, actor),
        lambda: customers.update_customer_vehicle(company.id, unknown.id, VehicleUpdate(equipment_type="trailer"), db_session, actor),
        lambda: vehicles.update_vehicle(unknown.id, VehicleUpdate(equipment_type="trailer"), db_session, actor),
    ):
        with pytest.raises(HTTPException) as exc:
            await action()
        assert exc.value.status_code == 409
    assert unknown.equipment_type == "unknown"


@pytest.mark.asyncio
async def test_offfleet_customer_trailers_remain_registered_and_bulk_enable_skips_them(db_session, monkeypatch):
    tenant, company, actor, _, trailer, _, _, _ = await prepared(db_session)
    company.fleet_enabled = True
    await db_session.commit()
    async def no_decode(_):
        pass
    monkeypatch.setattr(customers, "sync_vehicle_nhtsa_snapshot", no_decode)
    monkeypatch.setattr(vehicles, "sync_vehicle_nhtsa_snapshot", no_decode)
    created = await customers.create_customer_vehicle(company.id, VehicleBase(
        make="Trailer", model="Dry van", unit_number="Off-fleet 1", equipment_type="trailer"), db_session, actor)
    second = await vehicles.create_vehicle(VehicleCreate(
        customer_id=company.id, make="Trailer", model="Dry van", unit_number="Off-fleet 2", equipment_type="trailer"), db_session, actor)
    await sync_customer_fleet_memberships(db_session, company, enabled=True)
    await db_session.commit()
    memberships = (await db_session.execute(select(FleetMembership).where(
        FleetMembership.vehicle_id.in_([created.id, second.id, trailer.id]), FleetMembership.effective_to.is_(None),
    ))).scalars().all()
    assert memberships == []
    assert (await db_session.get(Vehicle, created.id)).customer_id == company.id
    assert (await db_session.get(Vehicle, second.id)).equipment_type == "trailer"
    with pytest.raises(HTTPException) as exc:
        await ensure_fleet_membership(db_session, tenant_id=tenant.id, vehicle_id=trailer.id, fleet_customer_id=company.id)
    assert exc.value.status_code == 409
    candidates = await fleet.list_fleet_vehicle_candidates(q="Off-fleet", limit=50, db=db_session, current_user=actor)
    assert len(candidates) == 2 and all(item.equipment_type == "trailer" for item in candidates)


@pytest.mark.asyncio
async def test_explicit_membership_admission_requires_tractor_and_is_atomic(db_session):
    _, company, actor, tractor, trailer, _, _, _ = await prepared(db_session)
    for target in (None, uuid4()):
        with pytest.raises(HTTPException) as exc:
            await fleet.add_fleet_membership(FleetMembershipCreate(
                vehicle_id=trailer.id, fleet_customer_id=company.id, tractor_id=target), db_session, actor)
        assert exc.value.status_code in (404, 409)
    assert not (await db_session.execute(select(FleetMembership).where(FleetMembership.vehicle_id == trailer.id))).scalars().all()
    result = await fleet.add_fleet_membership(FleetMembershipCreate(
        vehicle_id=trailer.id, fleet_customer_id=company.id, tractor_id=tractor.id), db_session, actor)
    assert result["vehicle_id"] == str(trailer.id)
    view = await fleet.truck_detail(trailer.id, db_session, actor)
    assert view.truck.attached_asset.id == tractor.id


@pytest.mark.asyncio
async def test_fleet_create_trailer_without_tractor_rolls_back_and_valid_create_pairs(db_session, monkeypatch):
    _, company, actor, tractor, _, _, _, _ = await prepared(db_session)
    async def no_decode(_):
        pass
    monkeypatch.setattr(fleet, "sync_vehicle_nhtsa_snapshot", no_decode)
    with pytest.raises(HTTPException) as exc:
        async with db_session.begin_nested():
            await fleet.create_fleet_truck(FleetTruckCreate(customer_id=company.id, make="Test", model="Trailer",
                equipment_type="trailer", unit_number="Missing tractor"), db_session, actor)
    assert exc.value.status_code == 409
    assert not (await db_session.execute(select(Vehicle).where(Vehicle.unit_number == "Missing tractor"))).scalars().all()
    await db_session.refresh(company)  # the rolled-back request expired its customer edit
    created = await fleet.create_fleet_truck(FleetTruckCreate(customer_id=company.id, make="Test", model="Trailer",
        equipment_type="trailer", unit_number="Paired new trailer", tractor_id=tractor.id), db_session, actor)
    view = await fleet.truck_detail(created.id, db_session, actor)
    assert view.truck.equipment_type == "trailer" and view.truck.attached_asset.id == tractor.id


@pytest.mark.asyncio
async def test_bulk_disable_closes_trailers_before_their_tractors(db_session):
    tenant, company, actor, tractor, trailer, other_tractor, other_trailer, _ = await prepared(db_session)
    await admit(db_session, actor, company, trailer, tractor)
    await admit(db_session, actor, company, other_trailer, other_tractor)
    await sync_customer_fleet_memberships(db_session, company, enabled=False)
    await db_session.commit()
    rows = (await db_session.execute(select(FleetAssetAttachment))).scalars().all()
    assert len(rows) == 2 and all(row.detached_at is not None for row in rows)
    active = (await db_session.execute(select(FleetMembership).where(FleetMembership.tenant_id == tenant.id,
        FleetMembership.effective_to.is_(None)))).scalars().all()
    assert active == []
    assert (await db_session.get(Vehicle, trailer.id)).deleted_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_role", ["tractor", "trailer"])
async def test_future_membership_is_not_a_current_attachment_authority(db_session, exit_role):
    tenant, company, actor, tractor, trailer, _, _, _ = await prepared(db_session)
    await admit(db_session, actor, company, trailer, tractor)
    other = Customer(tenant_id=tenant.id, first_name="Future", last_name="Operator", email=f"{uuid4()}@example.com")
    db_session.add(other)
    await db_session.flush()
    asset = tractor if exit_role == "tractor" else trailer
    db_session.add(FleetMembership(tenant_id=tenant.id, vehicle_id=asset.id, fleet_customer_id=other.id,
        effective_from=datetime.now(timezone.utc) + timedelta(days=1)))
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await end_fleet_membership(db_session, tenant_id=tenant.id, vehicle_id=asset.id, fleet_customer_id=company.id)
    assert exc.value.status_code == 409
    assert (await db_session.execute(select(FleetAssetAttachment))).scalar_one().detached_at is None


@pytest.mark.asyncio
async def test_atomic_settings_foreign_and_occupied_targets_do_not_change_type(db_session):
    _, company, actor, tractor, trailer, _, _, unknown = await prepared(db_session)
    _, _, _, foreign_tractor, _, _, _, foreign_unknown = await prepared(db_session)
    for source, target in ((unknown.id, foreign_tractor.id), (foreign_unknown.id, tractor.id), (unknown.id, uuid4())):
        with pytest.raises(HTTPException) as exc:
            await fleet.update_asset_settings(source, settings("trailer", target), db_session, actor)
        assert exc.value.status_code == 404
    await admit(db_session, actor, company, trailer, tractor)
    with pytest.raises(HTTPException) as exc:
        await fleet.update_asset_settings(unknown.id, settings("trailer", tractor.id), db_session, actor)
    assert exc.value.status_code == 409
    assert unknown.equipment_type == "unknown"
