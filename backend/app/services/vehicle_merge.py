"""Transactional deduplication for two records representing one physical truck."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.appointment import Appointment
from app.db.models.customer import Customer
from app.db.models.fleet import FleetIncident, FleetInspection, VehiclePMService
from app.db.models.fleet_board_read_model import FleetBoardReadModel
from app.db.models.repair_order import RepairOrder
from app.db.models.repair_order_read_model import RepairOrderReadModel
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_merge import VehicleMergeRecord, VehicleSourceAlias
from app.db.models.vehicle_relationship import FleetMembership, VehicleCustomerRelationship
from app.services.vehicle_identity import normalize_vin


class VehicleMergeError(ValueError):
    pass


async def _count(db: AsyncSession, model: Any, vehicle_id: UUID) -> int:
    return int((await db.execute(select(func.count(model.id)).where(model.vehicle_id == vehicle_id))).scalar() or 0)


async def vehicle_merge_summary(db: AsyncSession, vehicle: Vehicle) -> dict[str, Any]:
    customer_name = (await db.execute(
        select(Customer.company_name, Customer.first_name, Customer.last_name).where(Customer.id == vehicle.customer_id)
    )).one()
    source_rows = (await db.execute(
        select(func.coalesce(RepairOrder.source, "truck_pit_stop"), func.count(RepairOrder.id))
        .where(RepairOrder.vehicle_id == vehicle.id)
        .group_by(RepairOrder.source)
    )).all()
    return {
        "id": vehicle.id,
        "customer_id": vehicle.customer_id,
        "customer_name": customer_name.company_name or f"{customer_name.first_name} {customer_name.last_name}".strip(),
        "vin": normalize_vin(vehicle.vin) or "",
        "unit_number": vehicle.unit_number,
        "make": vehicle.make,
        "model": vehicle.model,
        "year": vehicle.year,
        "license_plate": vehicle.license_plate,
        "mileage": vehicle.mileage,
        "source": vehicle.source,
        "ets_external_id": vehicle.ets_external_id,
        "repair_order_count": await _count(db, RepairOrder, vehicle.id),
        "appointment_count": await _count(db, Appointment, vehicle.id),
        "inspection_count": await _count(db, FleetInspection, vehicle.id),
        "incident_count": await _count(db, FleetIncident, vehicle.id),
        "active_relationship_count": int((await db.execute(select(func.count(VehicleCustomerRelationship.id)).where(
            VehicleCustomerRelationship.vehicle_id == vehicle.id,
            VehicleCustomerRelationship.effective_to.is_(None),
            VehicleCustomerRelationship.deleted_at.is_(None),
        ))).scalar() or 0),
        "active_fleet_membership_count": int((await db.execute(select(func.count(FleetMembership.id)).where(
            FleetMembership.vehicle_id == vehicle.id,
            FleetMembership.effective_to.is_(None),
            FleetMembership.deleted_at.is_(None),
        ))).scalar() or 0),
        "repair_orders_by_source": {str(source): int(count) for source, count in source_rows},
    }


def validate_same_physical_vehicle(canonical: Vehicle, duplicate: Vehicle, confirm_vin: str | None = None) -> str:
    canonical_vin = normalize_vin(canonical.vin)
    duplicate_vin = normalize_vin(duplicate.vin)
    if not canonical_vin or len(canonical_vin) != 17 or canonical_vin != duplicate_vin:
        raise VehicleMergeError("Safe merge requires two active truck records with the same complete 17-character VIN")
    if confirm_vin is not None and normalize_vin(confirm_vin) != canonical_vin:
        raise VehicleMergeError("VIN confirmation does not match the selected trucks")
    return canonical_vin


async def load_merge_pair(
    db: AsyncSession, tenant_id: UUID, canonical_id: UUID, duplicate_id: UUID, *, lock: bool = False
) -> tuple[Vehicle, Vehicle]:
    if canonical_id == duplicate_id:
        raise VehicleMergeError("Choose two different truck records")
    query = select(Vehicle).where(
        Vehicle.id.in_((canonical_id, duplicate_id)),
        Vehicle.tenant_id == tenant_id,
        Vehicle.deleted_at.is_(None),
    )
    if lock:
        query = query.order_by(Vehicle.id).with_for_update()
    rows = {vehicle.id: vehicle for vehicle in (await db.execute(query)).scalars().all()}
    if canonical_id not in rows or duplicate_id not in rows:
        raise VehicleMergeError("One of these truck records is no longer available")
    return rows[canonical_id], rows[duplicate_id]


async def find_duplicate_candidates(db: AsyncSession, tenant_id: UUID, vehicle: Vehicle) -> list[Vehicle]:
    vin = normalize_vin(vehicle.vin)
    if not vin or len(vin) != 17:
        return []
    compact = func.upper(func.replace(func.replace(Vehicle.vin, " ", ""), "-", ""))
    return list((await db.execute(select(Vehicle).where(
        Vehicle.tenant_id == tenant_id,
        Vehicle.id != vehicle.id,
        Vehicle.deleted_at.is_(None),
        compact == vin,
    ).order_by(Vehicle.created_at))).scalars().all())


async def _merge_relationships(db: AsyncSession, canonical_id: UUID, duplicate_id: UUID, now: datetime) -> int:
    canonical_rows = list((await db.execute(select(VehicleCustomerRelationship).where(
        VehicleCustomerRelationship.vehicle_id == canonical_id,
        VehicleCustomerRelationship.deleted_at.is_(None),
    ))).scalars().all())
    duplicate_rows = list((await db.execute(select(VehicleCustomerRelationship).where(
        VehicleCustomerRelationship.vehicle_id == duplicate_id,
        VehicleCustomerRelationship.deleted_at.is_(None),
    ))).scalars().all())
    moved = 0
    for row in duplicate_rows:
        exact_active = next((current for current in canonical_rows if
            current.customer_id == row.customer_id
            and current.relationship_type == row.relationship_type
            and current.effective_to is None
            and row.effective_to is None), None)
        if exact_active:
            row.deleted_at = now
            continue
        competing_primary = any(
            current.relationship_type == row.relationship_type
            and current.is_primary
            and current.effective_to is None
            for current in canonical_rows
        )
        if competing_primary and row.is_primary and row.effective_to is None:
            row.is_primary = False
            row.effective_to = now
        row.vehicle_id = canonical_id
        canonical_rows.append(row)
        moved += 1
    return moved


async def _merge_memberships(db: AsyncSession, canonical_id: UUID, duplicate_id: UUID, now: datetime) -> int:
    canonical_rows = list((await db.execute(select(FleetMembership).where(
        FleetMembership.vehicle_id == canonical_id,
        FleetMembership.deleted_at.is_(None),
    ))).scalars().all())
    duplicate_rows = list((await db.execute(select(FleetMembership).where(
        FleetMembership.vehicle_id == duplicate_id,
        FleetMembership.deleted_at.is_(None),
    ))).scalars().all())
    moved = 0
    canonical_has_active = any(row.effective_to is None for row in canonical_rows)
    for row in duplicate_rows:
        exact_active = next((current for current in canonical_rows if
            current.fleet_customer_id == row.fleet_customer_id
            and current.effective_to is None
            and row.effective_to is None), None)
        if exact_active:
            row.deleted_at = now
            continue
        if canonical_has_active and row.effective_to is None:
            row.effective_to = now
        row.vehicle_id = canonical_id
        canonical_rows.append(row)
        moved += 1
    return moved


async def _merge_pm_services(db: AsyncSession, canonical_id: UUID, duplicate_id: UUID) -> int:
    existing = set((await db.execute(select(VehiclePMService.service_id).where(
        VehiclePMService.vehicle_id == canonical_id,
        VehiclePMService.deleted_at.is_(None),
    ))).scalars().all())
    rows = list((await db.execute(select(VehiclePMService).where(
        VehiclePMService.vehicle_id == duplicate_id,
        VehiclePMService.deleted_at.is_(None),
    ))).scalars().all())
    moved = 0
    for row in rows:
        if row.service_id in existing:
            await db.delete(row)
        else:
            row.vehicle_id = canonical_id
            existing.add(row.service_id)
            moved += 1
    return moved


async def _preserve_source_alias(db: AsyncSession, canonical: Vehicle, source: str | None, external_id: str | None) -> None:
    if not source or not external_id:
        return
    existing = (await db.execute(select(VehicleSourceAlias).where(
        VehicleSourceAlias.tenant_id == canonical.tenant_id,
        VehicleSourceAlias.source == source,
        VehicleSourceAlias.external_id == external_id,
    ))).scalar_one_or_none()
    if existing and existing.vehicle_id != canonical.id:
        raise VehicleMergeError(f"Source identity {source}:{external_id} already belongs to another truck")
    if not existing:
        db.add(VehicleSourceAlias(
            tenant_id=canonical.tenant_id, vehicle_id=canonical.id, source=source, external_id=external_id
        ))


async def merge_vehicles(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    canonical_id: UUID,
    duplicate_id: UUID,
    merged_by_user_id: UUID,
    confirm_vin: str,
) -> tuple[Vehicle, VehicleMergeRecord, dict[str, int]]:
    canonical, duplicate = await load_merge_pair(db, tenant_id, canonical_id, duplicate_id, lock=True)
    vin = validate_same_physical_vehicle(canonical, duplicate, confirm_vin)
    now = datetime.now(timezone.utc)
    before = {
        "canonical": {key: str(value) if isinstance(value, UUID) else value for key, value in (await vehicle_merge_summary(db, canonical)).items()},
        "duplicate": {key: str(value) if isinstance(value, UUID) else value for key, value in (await vehicle_merge_summary(db, duplicate)).items()},
    }

    await _preserve_source_alias(db, canonical, canonical.source, canonical.ets_external_id)
    await _preserve_source_alias(db, canonical, duplicate.source, duplicate.ets_external_id)

    moved = {
        "repair_orders": await _count(db, RepairOrder, duplicate.id),
        "appointments": await _count(db, Appointment, duplicate.id),
        "inspections": await _count(db, FleetInspection, duplicate.id),
        "incidents": await _count(db, FleetIncident, duplicate.id),
    }
    moved["relationships"] = await _merge_relationships(db, canonical.id, duplicate.id, now)
    moved["fleet_memberships"] = await _merge_memberships(db, canonical.id, duplicate.id, now)
    moved["pm_services"] = await _merge_pm_services(db, canonical.id, duplicate.id)

    for model in (RepairOrder, Appointment, FleetInspection, FleetIncident):
        await db.execute(update(model).where(model.vehicle_id == duplicate.id).values(vehicle_id=canonical.id))
    # SQLite tests do not run the PostgreSQL projection triggers. Production
    # triggers rebuild these rows from the changed repair orders.
    await db.execute(update(RepairOrderReadModel).where(
        RepairOrderReadModel.vehicle_id == duplicate.id
    ).values(vehicle_id=canonical.id))
    await db.execute(delete(FleetBoardReadModel).where(FleetBoardReadModel.vehicle_id == duplicate.id))

    fill_if_blank = (
        "unit_number", "license_plate", "color", "notes", "driver_name", "driver_phone",
        "billing_contact_name", "billing_contact_email", "billing_contact_phone",
        "telematics_device_id", "last_location_label", "last_location_city",
    )
    for field in fill_if_blank:
        if not getattr(canonical, field) and getattr(duplicate, field):
            setattr(canonical, field, getattr(duplicate, field))
    if duplicate.mileage is not None and (canonical.mileage is None or duplicate.mileage > canonical.mileage):
        canonical.mileage = duplicate.mileage
    if not canonical.ets_external_id and duplicate.ets_external_id:
        canonical.ets_external_id = duplicate.ets_external_id
        canonical.source = duplicate.source
    canonical.vin = vin

    duplicate.deleted_at = now
    record = VehicleMergeRecord(
        tenant_id=tenant_id,
        canonical_vehicle_id=canonical.id,
        duplicate_vehicle_id=duplicate.id,
        merged_by_user_id=merged_by_user_id,
        snapshot={"before": before, "moved": moved, "confirmed_vin": vin},
    )
    db.add(record)
    await db.flush()
    return canonical, record, moved
