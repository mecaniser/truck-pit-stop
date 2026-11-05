"""Permanent asset identity, cached projection, pairing and tenant boundaries."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.v1.endpoints import customers, fleet, vehicles
from app.db.models.customer import Customer
from app.db.models.fleet_asset_attachment import FleetAssetAttachment
from app.db.models.fleet_board_read_model import FleetBoardReadModel
from app.db.models.maintenance import MaintenanceProgram, MaintenanceReading
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet import FleetAttachmentUpdate, TruckUpdate
from app.schemas.vehicle import VehicleUpdate
from app.schemas.vehicle import VehicleRelationshipSync
from app.services import fleet_assets
from test_fleet_board import _join_fleet, _seed, _vehicle


async def prepared(db):
    tenant, company, actor = await _seed(db)
    tractor = _vehicle(tenant.id, company.id, unit_number="603", equipment_type="tractor")
    trailer = _vehicle(tenant.id, company.id, unit_number="24", equipment_type="trailer")
    other_tractor = _vehicle(tenant.id, company.id, unit_number="609", equipment_type="tractor")
    other_trailer = _vehicle(tenant.id, company.id, unit_number="42", equipment_type="trailer")
    unknown = _vehicle(tenant.id, company.id, unit_number="Unknown", equipment_type="unknown")
    db.add_all([tractor, trailer, other_tractor, other_trailer, unknown])
    await db.commit()
    await _join_fleet(db, tenant.id, company.id, tractor, trailer, other_tractor, other_trailer, unknown)
    return tenant, company, actor, tractor, trailer, other_tractor, other_trailer, unknown


def body(target=None, expected=None):
    return FleetAttachmentUpdate(attached_vehicle_id=target, expected_attached_vehicle_id=expected)


def test_attachment_contract_requires_explicit_expected_and_rejects_invalid_classification():
    assert body().model_dump() == {"attached_vehicle_id": None, "expected_attached_vehicle_id": None}
    for value in ({}, {"attached_vehicle_id": None}, {"expected_attached_vehicle_id": None},
                  {"attached_vehicle_id": None, "expected_attached_vehicle_id": None, "tractor_id": str(uuid4())}):
        with pytest.raises(ValidationError):
            FleetAttachmentUpdate.model_validate(value)
    for value in (None, "boat", "", 42):
        with pytest.raises(ValidationError):
            TruckUpdate(equipment_type=value)
    assert "equipment_type" not in TruckUpdate(unit_number="x").model_fields_set


@pytest.mark.asyncio
async def test_attachment_both_perspectives_idempotent_swap_detach_and_history(db_session):
    tenant, company, actor, tractor, trailer, _, other_trailer, _ = await prepared(db_session)
    first = await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    assert first.equipment_type == "tractor"
    assert first.attached_asset.id == trailer.id
    assert first.attached_asset.equipment_type == "trailer"
    # Retry a successful PUT, including from the inverse perspective.
    await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    inverse = await fleet.update_asset_attachment(trailer.id, body(tractor.id), db_session, actor)
    assert inverse.attached_asset.id == tractor.id
    assert len((await db_session.execute(select(FleetAssetAttachment))).scalars().all()) == 1
    second = await fleet.update_asset_attachment(tractor.id, body(other_trailer.id, trailer.id), db_session, actor)
    assert second.attached_asset.id == other_trailer.id
    old = (await db_session.execute(select(FleetAssetAttachment).where(FleetAssetAttachment.trailer_id == trailer.id))).scalar_one()
    assert old.detached_at is not None and old.detached_by_user_id == actor.id
    detached = await fleet.update_asset_attachment(other_trailer.id, body(None, tractor.id), db_session, actor)
    assert detached.attached_asset is None
    await fleet.update_asset_attachment(other_trailer.id, body(), db_session, actor)
    rows = (await db_session.execute(select(FleetAssetAttachment))).scalars().all()
    assert len(rows) == 2 and all(row.detached_at is not None for row in rows)
    assert all(row.attached_by_user_id == actor.id for row in rows)


@pytest.mark.asyncio
async def test_stale_swap_detach_and_occupied_counterpart_never_steal_pair(db_session):
    _, _, actor, tractor, trailer, other_tractor, other_trailer, _ = await prepared(db_session)
    await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    for source, update in ((other_tractor.id, body(trailer.id)), (tractor.id, body(other_trailer.id)),
                           (tractor.id, body(None)), (tractor.id, body(other_trailer.id, other_tractor.id))):
        with pytest.raises(HTTPException) as exc:
            await fleet.update_asset_attachment(source, update, db_session, actor)
        assert exc.value.status_code == 409
    current = (await db_session.execute(select(FleetAssetAttachment))).scalar_one()
    assert current.tractor_id == tractor.id and current.trailer_id == trailer.id and current.detached_at is None


@pytest.mark.asyncio
async def test_only_classified_opposite_types_can_attach(db_session):
    _, _, actor, tractor, trailer, other_tractor, other_trailer, unknown = await prepared(db_session)
    for source, target in ((tractor, tractor), (tractor, other_tractor), (trailer, other_trailer),
                           (unknown, trailer), (tractor, unknown)):
        with pytest.raises(HTTPException) as exc:
            await fleet.update_asset_attachment(source.id, body(target.id), db_session, actor)
        assert exc.value.status_code == 409
    assert not (await db_session.execute(select(FleetAssetAttachment))).scalars().all()


@pytest.mark.asyncio
async def test_foreign_deleted_offboard_and_future_membership_assets_are_not_found(db_session):
    _, _, actor, tractor, trailer, _, _, _ = await prepared(db_session)
    _, _, _, _, foreign_trailer, _, _, _ = await prepared(db_session)
    for source, target in ((tractor.id, foreign_trailer.id), (foreign_trailer.id, trailer.id), (tractor.id, uuid4())):
        with pytest.raises(HTTPException) as exc:
            await fleet.update_asset_attachment(source, body(target), db_session, actor)
        assert exc.value.status_code == 404
    membership = (await db_session.execute(select(FleetMembership).where(FleetMembership.vehicle_id == trailer.id))).scalar_one()
    membership.effective_from = datetime.now(timezone.utc) + timedelta(days=1)
    await db_session.commit()
    future_board = await fleet.fleet_board(db_session, actor)
    future_card = next(card for card in future_board.trucks if card.id == trailer.id)
    assert future_card.equipment_type == "trailer" and future_card.attached_asset is None
    with pytest.raises(HTTPException) as exc:
        await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    assert exc.value.status_code == 404
    membership.effective_from = datetime.now(timezone.utc) - timedelta(days=2)
    membership.effective_to = datetime.now(timezone.utc)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    assert exc.value.status_code == 404
    membership.effective_to = None
    trailer.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_distinct_customers_do_not_imply_distinct_asset_authorization(db_session):
    tenant, _, actor, tractor, trailer, _, _, _ = await prepared(db_session)
    owner = Customer(tenant_id=tenant.id, first_name="Trailer", last_name="Owner", email=f"{uuid4()}@example.com")
    db_session.add(owner)
    await db_session.flush()
    trailer.customer_id = owner.id
    await db_session.commit()
    response = await fleet.update_asset_attachment(trailer.id, body(tractor.id), db_session, actor)
    assert response.attached_asset.id == tractor.id and trailer.customer_id == owner.id


@pytest.mark.asyncio
async def test_current_classification_overrides_cached_projection_and_detail(db_session):
    tenant, _, actor, tractor, trailer, _, _, unknown = await prepared(db_session)
    await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    # Legacy materialized JSON has no classification and must not require
    # rewriting the read-model SQL function or waiting for another asset edit.
    db_session.add(FleetBoardReadModel(
        vehicle_id=trailer.id, tenant_id=tenant.id,
        vehicle_data={"unit_number": "24", "make": "Test", "model": "Trailer", "equipment_type": "tractor"},
        open_work_order_count=0, open_incident_count=0,
    ))
    await db_session.commit()
    board = await fleet.fleet_board(db_session, actor)
    cards = {card.id: card for card in board.trucks}
    assert cards[trailer.id].equipment_type == "trailer"
    assert cards[tractor.id].equipment_type == "tractor"
    assert cards[unknown.id].equipment_type == "unknown"
    assert cards[trailer.id].attached_asset.id == tractor.id
    assert cards[tractor.id].attached_asset.id == trailer.id
    detail = await fleet.truck_detail(trailer.id, db_session, actor)
    assert detail.truck.equipment_type == "trailer"
    assert detail.truck.attached_asset.id == tractor.id


@pytest.mark.asyncio
async def test_pair_projection_does_not_expose_an_unavailable_counterpart(db_session):
    _, _, actor, tractor, trailer, _, _, _ = await prepared(db_session)
    await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    membership = (await db_session.execute(select(FleetMembership).where(FleetMembership.vehicle_id == trailer.id))).scalar_one()
    membership.effective_to = datetime.now(timezone.utc)
    await db_session.commit()
    detail = await fleet.truck_detail(tractor.id, db_session, actor)
    assert detail.truck.attached_asset is None
    # Removing the surviving side's pairing can still close its old timeline.
    result = await fleet.update_asset_attachment(tractor.id, body(None, trailer.id), db_session, actor)
    assert result.attached_asset is None


@pytest.mark.asyncio
async def test_classification_edit_guards_every_existing_editor(db_session, monkeypatch):
    _, company, actor, tractor, trailer, _, _, unknown = await prepared(db_session)
    async def no_decode(_):
        pass
    monkeypatch.setattr(customers, "sync_vehicle_nhtsa_snapshot", no_decode)
    monkeypatch.setattr(vehicles, "sync_vehicle_nhtsa_snapshot", no_decode)
    updated = await fleet.update_truck(unknown.id, TruckUpdate(equipment_type="tractor"), db_session, actor)
    assert updated.equipment_type == "tractor"
    await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    for update in (
        lambda: fleet.update_truck(trailer.id, TruckUpdate(equipment_type="other"), db_session, actor),
        lambda: customers.update_customer_vehicle(company.id, trailer.id, VehicleUpdate(equipment_type="tractor"), db_session, actor),
        lambda: vehicles.update_vehicle(trailer.id, VehicleUpdate(equipment_type="unknown"), db_session, actor),
    ):
        with pytest.raises(HTTPException) as exc:
            await update()
        assert exc.value.status_code == 409
    same = await fleet.update_truck(trailer.id, TruckUpdate(equipment_type="trailer"), db_session, actor)
    assert same.equipment_type == "trailer" and same.attached_asset.id == tractor.id
    await fleet.update_asset_attachment(tractor.id, body(None, trailer.id), db_session, actor)
    updated = await fleet.update_truck(trailer.id, TruckUpdate(equipment_type="other"), db_session, actor)
    assert updated.equipment_type == "other"


@pytest.mark.asyncio
async def test_pairing_preserves_separate_repair_maintenance_readings_and_history(db_session):
    tenant, company, actor, tractor, trailer, _, other_trailer, _ = await prepared(db_session)
    originals = []
    for asset in (tractor, trailer):
        order = RepairOrder(tenant_id=tenant.id, customer_id=company.id, vehicle_id=asset.id,
                            order_number=f"RO-{uuid4()}", status=RepairOrderStatus.COMPLETED,
                            is_internal=True, total_cost=Decimal("123.45"))
        program = MaintenanceProgram(tenant_id=tenant.id, vehicle_id=asset.id,
                                     name=f"Service {asset.unit_number}", interval_days=30, target_provenance={})
        reading = MaintenanceReading(tenant_id=tenant.id, vehicle_id=asset.id,
                                     observed_at=datetime.now(timezone.utc), odometer_miles=12345,
                                     source="staff_observed", actor_id=actor.id, request_id=uuid4())
        db_session.add_all([order, program, reading])
        await db_session.flush()
        originals.append((asset.id, order.id, program.id, reading.id, asset.customer_id, asset.mileage))
    await db_session.commit()
    await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    await fleet.update_asset_attachment(tractor.id, body(other_trailer.id, trailer.id), db_session, actor)
    await fleet.update_asset_attachment(tractor.id, body(None, other_trailer.id), db_session, actor)
    for asset_id, order_id, program_id, reading_id, customer_id, odometer in originals:
        assert (await db_session.get(RepairOrder, order_id)).vehicle_id == asset_id
        assert (await db_session.get(MaintenanceProgram, program_id)).vehicle_id == asset_id
        assert (await db_session.get(MaintenanceReading, reading_id)).vehicle_id == asset_id
        detail = await fleet.truck_detail(asset_id, db_session, actor)
        history = await fleet.truck_history(asset_id, db=db_session, current_user=actor)
        assert Decimal(str(detail.lifetime_spend)) == Decimal("123.45")
        assert {entry.id for entry in history} == {order_id}
        asset = tractor if asset_id == tractor.id else trailer
        assert asset.customer_id == customer_id and asset.mileage == odometer


@pytest.mark.asyncio
async def test_active_unique_index_rejects_duplicate_pairing(db_session):
    tenant, _, actor, tractor, trailer, other_tractor, _, _ = await prepared(db_session)
    await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    db_session.add(FleetAssetAttachment(tenant_id=tenant.id, tractor_id=other_tractor.id, trailer_id=trailer.id,
                                      attached_at=datetime.now(timezone.utc), attached_by_user_id=actor.id))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_attached_asset_lifecycle_edits_require_detach_and_preserve_identity(db_session):
    from app.services.vehicle_identity import end_fleet_membership, sync_customer_fleet_memberships
    from app.services.vehicle_merge import merge_vehicles
    tenant, company, actor, tractor, trailer, other_tractor, _, _ = await prepared(db_session)
    await fleet.update_asset_attachment(tractor.id, body(trailer.id), db_session, actor)
    for action in (
        lambda: end_fleet_membership(db_session, tenant_id=tenant.id, vehicle_id=trailer.id, fleet_customer_id=company.id),
        lambda: sync_customer_fleet_memberships(db_session, company, enabled=False),
        lambda: vehicles.sync_vehicle_relationships(trailer.id, VehicleRelationshipSync(customer_id=company.id, operating_authority_customer_id=None), db_session, actor),
        lambda: customers.delete_customer_vehicle(company.id, trailer.id, db_session, actor),
        lambda: customers.delete_customer(company.id, db_session, actor),
        lambda: merge_vehicles(db_session, tenant_id=tenant.id, canonical_id=other_tractor.id, duplicate_id=tractor.id, merged_by_user_id=actor.id),
    ):
        with pytest.raises(HTTPException) as exc:
            await action()
        assert exc.value.status_code == 409
    assert trailer.deleted_at is None and tractor.deleted_at is None
    memberships = (await db_session.execute(select(FleetMembership).where(FleetMembership.vehicle_id.in_([tractor.id, trailer.id])))).scalars().all()
    assert all(member.effective_to is None for member in memberships)
    await fleet.update_asset_attachment(tractor.id, body(None, trailer.id), db_session, actor)
    assert await end_fleet_membership(db_session, tenant_id=tenant.id, vehicle_id=trailer.id, fleet_customer_id=company.id)
