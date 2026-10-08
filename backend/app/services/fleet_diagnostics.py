"""Tenant-scoped append-only dashboard diagnostics; never a fault lifecycle."""

import hashlib
import json

from sqlalchemy import func, select

from app.db.models.customer import Customer
from app.db.models.fleet_diagnostic import FleetDiagnosticCapture
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_diagnostic import (
    DiagnosticCapture,
    DiagnosticObservationRead,
    TruckDiagnosticsRead,
)
from app.services.fleet_telemetry import active_membership, fail, now, utc, within


async def authorize(db, tenant_id, actor_id):
    tenant = (
        await db.execute(
            select(Tenant)
            .where(
                Tenant.id == tenant_id,
                Tenant.deleted_at.is_(None),
                Tenant.is_active.is_(True),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    actor = (
        await db.execute(
            select(User)
            .where(
                User.id == actor_id,
                User.tenant_id == tenant_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        not tenant
        or not actor
        or actor.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
    ):
        fail(403, "active_tenant_admin_required")


async def resolve(db, tenant_id, vin, stamp, expected_customer_id=None):
    vehicles = (
        (
            await db.execute(
                select(Vehicle)
                .where(
                    Vehicle.tenant_id == tenant_id,
                    Vehicle.deleted_at.is_(None),
                    func.upper(func.trim(Vehicle.vin)) == vin,
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if len(vehicles) != 1:
        fail(409, "exact_unique_vin_required")
    vehicle = vehicles[0]
    members = (
        (
            await db.execute(
                select(FleetMembership)
                .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
                .where(
                    FleetMembership.tenant_id == tenant_id,
                    FleetMembership.vehicle_id == vehicle.id,
                    Customer.tenant_id == tenant_id,
                    Customer.deleted_at.is_(None),
                    *active_membership(stamp),
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if len(members) != 1 or (
        expected_customer_id and members[0].fleet_customer_id != expected_customer_id
    ):
        fail(409, "unique_current_membership_required")
    return vehicle, members[0]


def content_digest(body):
    return hashlib.sha256(
        json.dumps(
            body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


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
    body = DiagnosticCapture.model_validate(body)
    stamp = now()
    await authorize(db, tenant_id, actor_id)
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
    if not within(member, body.source_read_at):
        fail(409, "source_outside_current_membership")
    digest = content_digest(body)
    existing = (
        await db.execute(
            select(FleetDiagnosticCapture).where(
                FleetDiagnosticCapture.tenant_id == tenant_id,
                FleetDiagnosticCapture.client_request_id == body.client_request_id,
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
            fail(409, "conflicting_diagnostic_capture")
        return existing, "unchanged"
    if not apply:
        return None, "would_create"
    row = FleetDiagnosticCapture(
        tenant_id=tenant_id,
        vehicle_id=vehicle.id,
        fleet_customer_id=member.fleet_customer_id,
        fleet_membership_id=member.id,
        verified_vin=body.vin,
        provider_vehicle_id=body.provider_vehicle_id,
        source_company_id=body.source_company_id,
        source_company_label=body.source_company_label,
        source="motive_dashboard",
        source_read_at=body.source_read_at,
        captured_at=stamp,
        captured_by_user_id=actor_id,
        client_request_id=body.client_request_id,
        content_sha256=digest,
        coverage=body.coverage,
        explicit_empty=body.explicit_empty,
        source_scope=body.source_scope,
        codes=[code.model_dump(mode="json") for code in body.codes],
    )
    db.add(row)
    await db.flush()
    return row, "created"


async def read(db, tenant_id, vehicle_id):
    stamp = now()
    tenant = (
        await db.execute(
            select(Tenant.id).where(
                Tenant.id == tenant_id,
                Tenant.is_active.is_(True),
                Tenant.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not tenant:
        fail(404, "not_found")
    vehicle = (
        await db.execute(
            select(Vehicle).where(
                Vehicle.id == vehicle_id,
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    members = (
        (
            await db.execute(
                select(FleetMembership)
                .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
                .where(
                    FleetMembership.tenant_id == tenant_id,
                    FleetMembership.vehicle_id == vehicle_id,
                    Customer.tenant_id == tenant_id,
                    Customer.deleted_at.is_(None),
                    *active_membership(stamp),
                )
            )
        )
        .scalars()
        .all()
    )
    if not vehicle or len(members) != 1:
        fail(404, "not_found")
    member = members[0]
    rows = (
        (
            await db.execute(
                select(FleetDiagnosticCapture)
                .where(
                    FleetDiagnosticCapture.tenant_id == tenant_id,
                    FleetDiagnosticCapture.vehicle_id == vehicle_id,
                    FleetDiagnosticCapture.fleet_membership_id == member.id,
                    FleetDiagnosticCapture.fleet_customer_id
                    == member.fleet_customer_id,
                    FleetDiagnosticCapture.deleted_at.is_(None),
                    FleetDiagnosticCapture.verified_vin
                    == (vehicle.vin or "").strip().upper(),
                    FleetDiagnosticCapture.source_read_at >= member.effective_from,
                )
                .order_by(
                    FleetDiagnosticCapture.source_read_at.desc(),
                    FleetDiagnosticCapture.captured_at.desc(),
                    FleetDiagnosticCapture.id.desc(),
                )
                .limit(4)
            )
        )
        .scalars()
        .all()
    )
    result = TruckDiagnosticsRead(vehicle_id=vehicle_id)
    if not rows:
        return result

    def view(row):
        return DiagnosticObservationRead(
            capture_id=row.id,
            last_checked_at=utc(row.source_read_at),
            coverage=row.coverage,
            explicit_empty=row.explicit_empty,
            source_scope=row.source_scope,
            codes=row.codes,
        )

    latest = view(rows[0])
    return TruckDiagnosticsRead(
        vehicle_id=vehicle_id,
        **latest.model_dump(),
        previously_reported=[view(row) for row in rows[1:]],
    )
