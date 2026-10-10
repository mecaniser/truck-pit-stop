"""Company/tenant-scoped driver observations with conservative assignment reads."""

from datetime import timedelta

from sqlalchemy import func, select

from app.db.models.customer import Customer
from app.db.models.fleet_driver_record import (
    FleetDriverDirectoryCapture,
    FleetDriverRecordCapture,
)
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_driver_record import (
    DriverRecordCapture,
    DriverRecordContent,
    DriverRecordDetail,
    DriverRecordSummary,
    TruckDriverRecordRead,
)
from app.services.fleet_diagnostics import authorize, content_digest, resolve
from app.services.fleet_telemetry import active_membership, fail, now, utc, within


async def capture(
    db,
    tenant_id,
    actor_id,
    body,
    company_label,
    company_id,
    *,
    apply=False,
    expected_customer_id=None,
):
    body = DriverRecordCapture.model_validate(body)
    stamp = now()
    await authorize(db, tenant_id, actor_id)
    if not expected_customer_id:
        fail(409, "configured_fleet_customer_required")
    if (
        body.source_company_label != company_label
        or body.source_company_id != company_id
    ):
        fail(409, "source_company_mismatch")
    if body.source_read_at > stamp:
        fail(409, "future_source_read")
    vehicle, member = await resolve(
        db, tenant_id, body.vin, stamp, expected_customer_id
    )
    # Locks protect concurrency; refresh also discards any older ORM identity-map
    # snapshot loaded by a caller before another transaction changed assignment.
    await db.refresh(vehicle)
    await db.refresh(member)
    if not within(member, body.source_read_at):
        fail(409, "source_outside_current_membership")
    digest = content_digest(body)
    existing = (
        await db.execute(
            select(FleetDriverRecordCapture).where(
                FleetDriverRecordCapture.tenant_id == tenant_id,
                FleetDriverRecordCapture.client_request_id == body.client_request_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if (
            existing.deleted_at
            or existing.content_sha256 != digest
            or existing.vehicle_id != vehicle.id
            or existing.fleet_membership_id != member.id
        ):
            fail(409, "conflicting_driver_record_capture")
        return existing, "unchanged"
    if vehicle.driver_assignment_changed_at and body.source_read_at < utc(
        vehicle.driver_assignment_changed_at
    ):
        fail(409, "source_before_driver_assignment_change")
    if not apply:
        return None, "would_create"
    content = DriverRecordContent.model_validate(
        {
            key: value
            for key, value in body.model_dump(mode="json").items()
            if key in DriverRecordContent.model_fields
        }
    )
    row = FleetDriverRecordCapture(
        tenant_id=tenant_id,
        vehicle_id=vehicle.id,
        fleet_customer_id=member.fleet_customer_id,
        fleet_membership_id=member.id,
        verified_vin=body.vin,
        provider_vehicle_id=body.provider_vehicle_id,
        provider_driver_id=body.provider_driver_id,
        driver_name=body.driver_name,
        local_driver_name=vehicle.driver_name,
        local_driver_phone=vehicle.driver_phone,
        driver_assignment_revision=vehicle.driver_assignment_revision or 0,
        source_company_id=body.source_company_id,
        source_company_label=body.source_company_label,
        source="motive_dashboard",
        source_read_at=body.source_read_at,
        captured_at=stamp,
        captured_by_user_id=actor_id,
        client_request_id=body.client_request_id,
        content_sha256=digest,
        payload=content.model_dump(mode="json"),
    )
    db.add(row)
    await db.flush()
    return row, "created"


async def _contexts(db, tenant_id, vehicle_ids):
    rows = (
        await db.execute(
            select(Vehicle, FleetMembership)
            .join(Tenant, Tenant.id == Vehicle.tenant_id)
            .join(FleetMembership, FleetMembership.vehicle_id == Vehicle.id)
            .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
            .where(
                Vehicle.tenant_id == tenant_id,
                Vehicle.id.in_(vehicle_ids),
                Vehicle.deleted_at.is_(None),
                Tenant.is_active.is_(True),
                Tenant.deleted_at.is_(None),
                FleetMembership.tenant_id == tenant_id,
                Customer.tenant_id == tenant_id,
                Customer.deleted_at.is_(None),
                *active_membership(now()),
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    grouped = {}
    for vehicle, member in rows:
        grouped.setdefault(vehicle.id, []).append((vehicle, member))
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}


async def _latest(db, tenant_id, contexts):
    if not contexts:
        return {}, {}
    ranked = (
        select(
            FleetDriverRecordCapture.id,
            func.row_number()
            .over(
                partition_by=FleetDriverRecordCapture.vehicle_id,
                order_by=(
                    FleetDriverRecordCapture.source_read_at.desc(),
                    FleetDriverRecordCapture.captured_at.desc(),
                    FleetDriverRecordCapture.id.desc(),
                ),
            )
            .label("rank"),
        )
        .where(
            FleetDriverRecordCapture.tenant_id == tenant_id,
            FleetDriverRecordCapture.vehicle_id.in_(contexts),
            FleetDriverRecordCapture.fleet_membership_id.in_(
                [member.id for _, member in contexts.values()]
            ),
            FleetDriverRecordCapture.deleted_at.is_(None),
        )
        .subquery()
    )
    rows = (
        (
            await db.execute(
                select(FleetDriverRecordCapture)
                .join(ranked, ranked.c.id == FleetDriverRecordCapture.id)
                .where(ranked.c.rank == 1)
            )
        )
        .scalars()
        .all()
    )
    directories = (
        select(
            FleetDriverDirectoryCapture.id,
            func.row_number()
            .over(
                partition_by=FleetDriverDirectoryCapture.fleet_customer_id,
                order_by=(
                    FleetDriverDirectoryCapture.source_read_at.desc(),
                    FleetDriverDirectoryCapture.created_at.desc(),
                    FleetDriverDirectoryCapture.id.desc(),
                ),
            )
            .label("rank"),
        )
        .where(
            FleetDriverDirectoryCapture.tenant_id == tenant_id,
            FleetDriverDirectoryCapture.fleet_customer_id.in_(
                [member.fleet_customer_id for _, member in contexts.values()]
            ),
            FleetDriverDirectoryCapture.deleted_at.is_(None),
        )
        .subquery()
    )
    latest_directories = (
        (
            await db.execute(
                select(FleetDriverDirectoryCapture)
                .join(directories, directories.c.id == FleetDriverDirectoryCapture.id)
                .where(directories.c.rank == 1)
            )
        )
        .scalars()
        .all()
    )
    directory_by_customer = {row.fleet_customer_id: row for row in latest_directories}
    return {row.vehicle_id: row for row in rows}, directory_by_customer


def _view(vehicle, member, row, directory):
    result = TruckDriverRecordRead(vehicle_id=vehicle.id)
    if not row:
        result.unavailable_reason = "no_capture"
        return result
    if (
        row.verified_vin != (vehicle.vin or "").strip().upper()
        or row.fleet_customer_id != member.fleet_customer_id
        or not within(member, utc(row.source_read_at))
    ):
        result.unavailable_reason = "vehicle_identity_changed"
        return result
    if (
        row.driver_assignment_revision != (vehicle.driver_assignment_revision or 0)
        or row.local_driver_name != vehicle.driver_name
        or row.local_driver_phone != vehicle.driver_phone
    ):
        result.availability = "assignment_unverified"
        result.unavailable_reason = "local_assignment_changed"
        return result
    if not directory:
        result.availability = "assignment_unverified"
        result.unavailable_reason = "directory_missing"
        return result
    vehicle_assignments = [
        item
        for item in directory.assignments
        if item.get("provider_vehicle_id") == row.provider_vehicle_id
    ]
    driver_assignments = [
        item
        for item in directory.assignments
        if item.get("provider_driver_id") == row.provider_driver_id
    ]
    if (
        directory.source_company_id != row.source_company_id
        or directory.source_company_label != row.source_company_label
        or utc(directory.source_read_at) < utc(row.source_read_at)
        or utc(directory.source_read_at) > now()
        or not within(member, utc(directory.source_read_at))
        or len(vehicle_assignments) != 1
        or len(driver_assignments) != 1
        or vehicle_assignments[0].get("provider_driver_id") != row.provider_driver_id
        or driver_assignments[0].get("provider_vehicle_id") != row.provider_vehicle_id
    ):
        result.availability = "assignment_unverified"
        result.unavailable_reason = "provider_assignment_unverified"
        return result
    payload = DriverRecordContent.model_validate(row.payload)
    result.availability = "available"
    result.record = DriverRecordDetail(
        capture_id=row.id,
        provider_driver_id=row.provider_driver_id,
        driver_name=row.driver_name,
        source_company_id=row.source_company_id,
        provider_vehicle_id=row.provider_vehicle_id,
        local_driver_name=row.local_driver_name,
        local_assignment_revision=row.driver_assignment_revision,
        assignment_verified_at=utc(directory.source_read_at),
        safety_score=payload.safety.score,
        safety_band=payload.safety.band,
        safety_band_label=payload.safety.band_label,
        safety_period_text=payload.safety.period_text,
        last_checked_at=utc(row.source_read_at),
        stale=now() - utc(row.source_read_at) > timedelta(hours=48),
        **payload.model_dump(),
    )
    return result


async def read(db, tenant_id, vehicle_id):
    contexts = await _contexts(db, tenant_id, [vehicle_id])
    if vehicle_id not in contexts:
        fail(404, "not_found")
    rows, directories = await _latest(db, tenant_id, contexts)
    vehicle, member = contexts[vehicle_id]
    return _view(
        vehicle, member, rows.get(vehicle_id), directories.get(member.fleet_customer_id)
    )


async def attach(db, trucks, tenant_id):
    if not trucks:
        return
    contexts = await _contexts(db, tenant_id, [truck.id for truck in trucks])
    rows, directories = await _latest(db, tenant_id, contexts)
    for truck in trucks:
        truck.driver_record = None
        if truck.id not in contexts:
            continue
        vehicle, member = contexts[truck.id]
        result = _view(
            vehicle,
            member,
            rows.get(truck.id),
            directories.get(member.fleet_customer_id),
        )
        # Stale board contact or fleet labels must not inherit a current score.
        if (
            result.record
            and truck.driver_name == vehicle.driver_name
            and getattr(truck, "board_membership_customer_id", member.fleet_customer_id)
            == member.fleet_customer_id
        ):
            truck.driver_record = DriverRecordSummary.model_validate(
                result.record.model_dump()
            )
