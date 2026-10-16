"""Fail-closed reviewed bindings. Never infer identity from a unit or driver name."""

import hashlib
import json
import re
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db.models.customer import Customer
from app.db.models.dashboard_vehicle_binding import DashboardVehicleBinding as Binding
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.services.fleet_diagnostics import authorize
from app.services.fleet_telemetry import active_membership, fail, now, utc, within


def valid_context(binding, vehicle, member, stamp, source_time):
    return bool(
        binding
        and not binding.deleted_at
        and not binding.revoked_at
        and binding.tenant_id == vehicle.tenant_id == member.tenant_id
        and binding.vehicle_id == vehicle.id == member.vehicle_id
        and binding.fleet_membership_id == member.id
        and binding.fleet_customer_id == member.fleet_customer_id
        and not vehicle.deleted_at
        and not member.deleted_at
        and re.fullmatch(r"PENDING-[A-Z0-9-]{1,9}", binding.placeholder_vin or "")
        and vehicle.vin == binding.placeholder_vin
        and utc(binding.reviewed_at)
        <= utc(binding.effective_from)
        <= source_time
        <= stamp
        and utc(binding.effective_from) <= stamp
        and (binding.effective_to is None or stamp < utc(binding.effective_to))
        and (binding.effective_to is None or source_time < utc(binding.effective_to))
        and within(member, source_time)
        and within(member, stamp)
    )


async def resolve(
    db,
    tenant_id,
    company_id,
    provider_id,
    source_time,
    *,
    company_label,
    binding_id=None,
    expected_customer_id=None,
):
    """Resolve current exact reviewed identity, before replay checks or writes."""
    stamp = now()
    bindings = (
        (
            await db.execute(
                select(Binding)
                .where(
                    Binding.tenant_id == tenant_id,
                    Binding.source_company_id == company_id,
                    Binding.source_company_label == company_label,
                    Binding.provider_vehicle_id == provider_id,
                    Binding.deleted_at.is_(None),
                    Binding.revoked_at.is_(None),
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if len(bindings) != 1 or (binding_id and bindings[0].id != binding_id):
        fail(409, "reviewed_vehicle_binding_required")
    binding = bindings[0]
    vehicle = (
        await db.execute(
            select(Vehicle)
            .where(
                Vehicle.id == binding.vehicle_id,
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    members = (
        (
            await db.execute(
                select(FleetMembership)
                .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
                .where(
                    FleetMembership.tenant_id == tenant_id,
                    FleetMembership.vehicle_id == binding.vehicle_id,
                    Customer.tenant_id == tenant_id,
                    Customer.deleted_at.is_(None),
                    *active_membership(stamp),
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if (
        not vehicle
        or len(members) != 1
        or (
            expected_customer_id
            and members[0].fleet_customer_id != expected_customer_id
        )
        or not valid_context(binding, vehicle, members[0], stamp, utc(source_time))
    ):
        fail(409, "reviewed_vehicle_binding_invalid")
    return vehicle, members[0], binding


async def valid_capture_ids(db, tenant_id, captures):
    """Batch read guard, including revocation and changed current membership."""
    ids = {row.dashboard_binding_id for row in captures if row.dashboard_binding_id}
    if not ids:
        return set()
    bindings = (
        await db.execute(
            select(Binding, Vehicle, FleetMembership)
            .join(Vehicle, Vehicle.id == Binding.vehicle_id)
            .join(FleetMembership, FleetMembership.vehicle_id == Vehicle.id)
            .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
            .where(
                Binding.tenant_id == tenant_id,
                Binding.id.in_(ids),
                Vehicle.tenant_id == tenant_id,
                FleetMembership.tenant_id == tenant_id,
                Customer.tenant_id == tenant_id,
                Customer.deleted_at.is_(None),
                *active_membership(now()),
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    grouped = {}
    for binding, vehicle, member in bindings:
        grouped.setdefault(binding.id, []).append((binding, vehicle, member))
    allowed = set()
    for row in captures:
        contexts = grouped.get(row.dashboard_binding_id, [])
        if len(contexts) != 1:
            continue
        binding, vehicle, member = contexts[0]
        if hasattr(row, "source_company_id"):
            company_id, company_label, source_time = (
                row.source_company_id,
                row.source_company_label,
                utc(row.source_read_at),
            )
        else:
            try:
                note = json.loads(row.evidence_note)
                source_time = datetime.fromisoformat(note["sourceReadTime"])
                if source_time.tzinfo is None:
                    continue
                company_id, company_label = (
                    note["company_id"],
                    row.provider_company_label,
                )
            except (ValueError, TypeError, KeyError):
                continue
        if (
            row.verified_vin is None
            and row.vehicle_id == vehicle.id
            and row.fleet_membership_id == member.id
            and row.provider_vehicle_id == binding.provider_vehicle_id
            and company_id == binding.source_company_id
            and company_label == binding.source_company_label
            and valid_context(binding, vehicle, member, now(), source_time)
        ):
            allowed.add(row.id)
    return allowed


async def create(db, tenant_id, actor_id, manifest, *, apply=False):
    """Explicit operator-reviewed manifest; no ambient or heuristic mapping."""
    await authorize(db, tenant_id, actor_id)
    stamp = now()
    vehicle = (
        await db.execute(
            select(Vehicle)
            .where(Vehicle.id == manifest.vehicle_id, Vehicle.tenant_id == tenant_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    members = (
        (
            await db.execute(
                select(FleetMembership)
                .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
                .where(
                    FleetMembership.tenant_id == tenant_id,
                    FleetMembership.vehicle_id == manifest.vehicle_id,
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
    digest = hashlib.sha256(
        json.dumps(
            {
                "tenant_id": str(tenant_id),
                "reviewer_id": str(actor_id),
                **manifest.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    candidate = Binding(
        review_manifest_sha256=digest,
        tenant_id=tenant_id,
        reviewed_by_user_id=actor_id,
        reviewed_at=stamp,
        effective_from=stamp,
        **manifest.model_dump(),
    )
    if (
        not vehicle
        or len(members) != 1
        or not valid_context(candidate, vehicle, members[0], stamp, stamp)
    ):
        fail(409, "reviewed_vehicle_binding_invalid")
    existing = (
        (
            await db.execute(
                select(Binding)
                .where(
                    Binding.tenant_id == tenant_id,
                    (Binding.vehicle_id == vehicle.id)
                    | (
                        (Binding.source_company_id == candidate.source_company_id)
                        & (Binding.provider_vehicle_id == candidate.provider_vehicle_id)
                    ),
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if existing:
        if (
            len(existing) == 1
            and existing[0].review_manifest_sha256 == digest
            and existing[0].reviewed_by_user_id == actor_id
            and valid_context(existing[0], vehicle, members[0], stamp, stamp)
        ):
            return existing[0], "unchanged"
        fail(409, "reviewed_vehicle_binding_conflict")
    if not stamp - timedelta(hours=2) <= utc(manifest.source_evidence_read_at) <= stamp:
        fail(409, "fresh_review_source_required")
    if apply:
        db.add(candidate)
        await db.flush()
    return candidate, "created" if apply else "would_create"


async def invalidate_source_vin(
    db,
    tenant_id,
    actor_id,
    company_id,
    company_label,
    provider_id,
    vin,
    source_time,
    source_digest,
):
    """A validated complete source document can close, never create, a binding.

    Caller must validate source company/route and before/after collection evidence.
    Review-time ordering prevents old replay from revoking a newer reviewed binding.
    """
    await authorize(db, tenant_id, actor_id)
    row = (
        await db.execute(
            select(Binding)
            .where(
                Binding.tenant_id == tenant_id,
                Binding.source_company_id == company_id,
                Binding.source_company_label == company_label,
                Binding.provider_vehicle_id == provider_id,
                Binding.deleted_at.is_(None),
                Binding.revoked_at.is_(None),
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    if (
        not isinstance(vin, str)
        or not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin)
        or not re.fullmatch(r"[0-9a-f]{64}", source_digest or "")
        or source_time.tzinfo is None
        or source_time > now()
    ):
        fail(409, "invalid_binding_revocation_evidence")
    if source_time < utc(row.reviewed_at) or source_time < utc(row.effective_from):
        return False
    row.revoked_at = now()
    row.revoked_by_user_id = actor_id
    row.revocation_reason = "provider_vin_available"
    row.revoked_source_vin = vin
    row.revoked_source_read_at = source_time
    row.revoked_source_sha256 = source_digest
    await db.flush()
    return True
