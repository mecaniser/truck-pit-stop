"""Shared bounded telemetry selection and immutable manual capture."""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select

from app.db.models.customer import Customer
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot as Snapshot
from app.db.models.motive_oauth import (
    MotiveConnection,
    MotiveFault,
    MotiveRemoteVehicle,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_telemetry import FleetTelemetry
from app.services.motive_oauth import configured


def now():
    return datetime.now(timezone.utc)


def utc(t):
    return (
        t.replace(tzinfo=timezone.utc)
        if t.tzinfo is None
        else t.astimezone(timezone.utc)
    )


def fail(status, code):
    raise HTTPException(
        status,
        {"code": code, "message": code.replace("_", " ")},
        headers={"Cache-Control": "no-store"},
    )


def active_membership(stamp):
    return (
        FleetMembership.deleted_at.is_(None),
        FleetMembership.effective_from <= stamp,
        or_(
            FleetMembership.effective_to.is_(None), FleetMembership.effective_to > stamp
        ),
    )


def within(m, stamp):
    return utc(m.effective_from) <= stamp and (
        m.effective_to is None or stamp < utc(m.effective_to)
    )


def observation_interval(observed, precision=None):
    """Closed possible-time bounds; minute end excludes the following minute."""
    start = utc(observed)
    end = (
        start + timedelta(minutes=1) - timedelta(microseconds=1)
        if precision == "minute"
        else start
    )
    return start, end


async def capture(db, actor, vehicle_id, body):
    stamp = now()
    tenant_id, actor_id = actor.tenant_id, actor.id
    # Tenant serialization also makes cross-vehicle request-id races deterministic.
    tenant = (
        await db.execute(
            select(Tenant)
            .where(
                Tenant.id == tenant_id,
                Tenant.is_active.is_(True),
                Tenant.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    user = (
        await db.execute(
            select(User)
            .where(User.id == actor_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if (
        not tenant
        or not user
        or not user.is_active
        or user.deleted_at
        or user.tenant_id != tenant_id
        or user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
    ):
        fail(403, "forbidden")
    vehicle = (
        await db.execute(
            select(Vehicle)
            .where(
                Vehicle.id == vehicle_id,
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    member = (
        (
            await db.execute(
                select(FleetMembership)
                .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
                .where(
                    FleetMembership.tenant_id == tenant_id,
                    FleetMembership.vehicle_id == vehicle_id,
                    FleetMembership.fleet_customer_id == body.fleet_customer_id,
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
    if not vehicle or len(member) != 1:
        fail(404, "not_found")
    member = member[0]
    vin = (vehicle.vin or "").strip().upper()
    duplicates = (
        await db.execute(
            select(func.count())
            .select_from(Vehicle)
            .where(
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
                func.upper(func.trim(Vehicle.vin)) == vin,
            )
        )
    ).scalar_one()
    if (
        not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin)
        or body.vin != vin
        or duplicates != 1
    ):
        fail(409, "vehicle_identity_mismatch")
    digest_data = body.model_dump(mode="json")
    # Preserve replay hashes for captures made before fuel economy was supported.
    for name in ("fuel_economy_mpg", "fuel_economy_period", "observed_precision"):
        if digest_data[name] is None:
            digest_data.pop(name)
    digest = hashlib.sha256(
        json.dumps(
            {"vehicle_id": str(vehicle_id), **digest_data},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    existing = (
        await db.execute(
            select(Snapshot).where(
                Snapshot.tenant_id == tenant_id,
                Snapshot.client_request_id == body.client_request_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if (
            existing.captured_by_user_id != actor_id
            or existing.request_digest != digest
        ):
            fail(409, "request_conflict")
        if existing.fleet_membership_id != member.id:
            fail(404, "not_found")
        return existing, False
    if body.observed_at and (
        body.observed_at < stamp - timedelta(days=30)
        or body.observed_at > stamp + timedelta(minutes=5)
        or not within(member, body.observed_at)
    ):
        fail(422, "invalid_observation_time")
    if body.observed_at and body.observed_precision == "minute":
        last_possible = (
            body.observed_at + timedelta(minutes=1) - timedelta(microseconds=1)
        )
        if last_possible > stamp + timedelta(minutes=5) or not within(
            member, last_possible
        ):
            fail(422, "invalid_observation_time")
    # Preserve legacy exact captures, but never let an uncertain minute interval
    # replace a location observation anywhere within that interval (or vice versa).
    if body.observed_at and (body.lat is not None or body.location_label):
        start, end = observation_interval(body.observed_at, body.observed_precision)
        previous = (
            (
                await db.execute(
                    select(Snapshot).where(
                        Snapshot.tenant_id == tenant_id,
                        Snapshot.vehicle_id == vehicle_id,
                        Snapshot.fleet_membership_id == member.id,
                        Snapshot.deleted_at.is_(None),
                        Snapshot.observed_at.is_not(None),
                        Snapshot.observed_at >= start - timedelta(minutes=1),
                        Snapshot.observed_at <= end,
                        or_(
                            Snapshot.lat.is_not(None),
                            Snapshot.location_label.is_not(None),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for prior in previous:
            if (
                body.observed_precision != "minute"
                and prior.observed_precision != "minute"
            ):
                continue
            old_start, old_end = observation_interval(
                prior.observed_at, prior.observed_precision
            )
            if max(start, old_start) <= min(end, old_end):
                fail(409, "overlapping_observation_interval")
    data = body.model_dump(exclude={"vin"})
    row = Snapshot(
        **data,
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        fleet_membership_id=member.id,
        verified_vin=vin,
        request_digest=digest,
        source="motive_dashboard_manual",
        captured_at=stamp,
        captured_by_user_id=actor_id,
    )
    db.add(row)
    await db.flush()
    return row, True


async def attach(db, trucks, tenant_id):
    """Six batch queries regardless of truck count; no provider requests."""
    if not trucks:
        return
    stamp = now()
    cutoff = stamp - timedelta(days=30)
    ids = [t.id for t in trucks]
    members = (
        (
            await db.execute(
                select(FleetMembership)
                .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
                .where(
                    FleetMembership.tenant_id == tenant_id,
                    FleetMembership.vehicle_id.in_(ids),
                    Customer.tenant_id == tenant_id,
                    Customer.deleted_at.is_(None),
                    *active_membership(stamp),
                )
            )
        )
        .scalars()
        .all()
    )
    by_pair = {(m.vehicle_id, m.fleet_customer_id): m for m in members}
    selected_membership_ids = [
        by_pair[(t.id, t.board_membership_customer_id)].id
        for t in trucks
        if (t.id, t.board_membership_customer_id) in by_pair
    ]
    # Rank each field independently in SQL: at most seven rows per vehicle are
    # materialized, even if operators captured many observations this month.
    present = [or_(Snapshot.location_label.is_not(None), Snapshot.lat.is_not(None))] + [
        getattr(Snapshot, n).is_not(None)
        for n in (
            "speed_mph",
            "odometer_miles",
            "engine_hours",
            "fuel_percent",
            "fuel_economy_mpg",
            "fault_count",
        )
    ]
    ranked = (
        select(
            Snapshot.id,
            *[
                func.row_number()
                .over(
                    partition_by=Snapshot.vehicle_id,
                    order_by=(
                        p.desc(),
                        Snapshot.observed_at.desc().nulls_last(),
                        Snapshot.captured_at.desc(),
                        Snapshot.id.desc(),
                    ),
                )
                .label(f"rank_{i}")
                for i, p in enumerate(present)
            ],
        )
        .join(FleetMembership, FleetMembership.id == Snapshot.fleet_membership_id)
        .where(
            Snapshot.tenant_id == tenant_id,
            Snapshot.vehicle_id.in_(ids),
            Snapshot.deleted_at.is_(None),
            Snapshot.fleet_membership_id.in_(selected_membership_ids),
            select(Vehicle.id)
            .where(
                Vehicle.id == Snapshot.vehicle_id,
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
            )
            .exists(),
            Snapshot.captured_at >= cutoff,
            *active_membership(stamp),
            or_(
                Snapshot.observed_at.is_(None),
                Snapshot.observed_at.between(cutoff, stamp + timedelta(minutes=5)),
            ),
            func.coalesce(Snapshot.observed_at, Snapshot.captured_at)
            >= FleetMembership.effective_from,
            or_(
                FleetMembership.effective_to.is_(None),
                func.coalesce(Snapshot.observed_at, Snapshot.captured_at)
                < FleetMembership.effective_to,
            ),
        )
        .subquery()
    )
    snapshots = (
        (
            await db.execute(
                select(Snapshot)
                .join(ranked, ranked.c.id == Snapshot.id)
                .where(or_(*[ranked.c[f"rank_{i}"] == 1 for i in range(len(present))]))
            )
        )
        .scalars()
        .all()
    )
    vehicles = (
        (
            await db.execute(
                select(Vehicle).where(
                    Vehicle.tenant_id == tenant_id,
                    Vehicle.id.in_(ids),
                    Vehicle.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    remotes = []
    faults = {}
    if configured(tenant_id):
        remotes = (
            await db.execute(
                select(MotiveRemoteVehicle, MotiveConnection)
                .join(
                    MotiveConnection,
                    MotiveConnection.id == MotiveRemoteVehicle.connection_id,
                )
                .where(
                    MotiveRemoteVehicle.tenant_id == tenant_id,
                    MotiveRemoteVehicle.vehicle_id.in_(ids),
                    MotiveRemoteVehicle.deleted_at.is_(None),
                    select(Vehicle.id)
                    .where(
                        Vehicle.id == MotiveRemoteVehicle.vehicle_id,
                        Vehicle.tenant_id == tenant_id,
                        Vehicle.deleted_at.is_(None),
                    )
                    .exists(),
                    MotiveRemoteVehicle.provider_status == "active",
                    MotiveConnection.tenant_id == tenant_id,
                    select(Tenant.id)
                    .where(
                        Tenant.id == tenant_id,
                        Tenant.is_active.is_(True),
                        Tenant.deleted_at.is_(None),
                    )
                    .exists(),
                    select(Customer.id)
                    .where(
                        Customer.id == MotiveConnection.fleet_customer_id,
                        Customer.tenant_id == tenant_id,
                        Customer.deleted_at.is_(None),
                        or_(
                            Customer.fleet_enabled.is_(True),
                            Customer.is_internal_fleet.is_(True),
                        ),
                    )
                    .exists(),
                    MotiveConnection.deleted_at.is_(None),
                    MotiveConnection.status.in_(["connected", "provider_error"]),
                )
            )
        ).all()
        remote_ids = [r.id for r, c in remotes]
        if remote_ids:
            faults = dict(
                (
                    await db.execute(
                        select(MotiveFault.remote_vehicle_id, func.count())
                        .join(
                            MotiveRemoteVehicle,
                            MotiveRemoteVehicle.id == MotiveFault.remote_vehicle_id,
                        )
                        .where(
                            MotiveFault.tenant_id == tenant_id,
                            MotiveFault.remote_vehicle_id.in_(remote_ids),
                            MotiveFault.deleted_at.is_(None),
                            MotiveFault.status == "open",
                            MotiveFault.mapping_epoch == MotiveRemoteVehicle.mapped_at,
                            MotiveFault.received_at >= cutoff,
                        )
                        .group_by(MotiveFault.remote_vehicle_id)
                    )
                ).all()
            )
    choices = {t.id: {} for t in trucks}
    context = {t.id: t.board_membership_customer_id for t in trucks}

    def add(
        vid,
        field,
        value,
        source,
        observed,
        captured,
        sid=None,
        age=None,
        basis=None,
        unit=None,
        period=None,
        precision=None,
    ):
        observed = utc(observed) if observed else None
        captured = utc(captured) if captured else None
        if (observed and not cutoff <= observed <= stamp + timedelta(minutes=5)) or (
            not observed and (not captured or captured < cutoff)
        ):
            return
        freshness = (
            "unknown"
            if observed is None
            else "fresh"
            if stamp - observed <= timedelta(minutes=5)
            else "delayed"
            if stamp - observed <= timedelta(minutes=15)
            else "stale"
        )
        reading = {
            "source": source,
            "observed_at": observed,
            "observed_precision": precision,
            "captured_at": captured,
            "freshness": freshness,
            "snapshot_id": str(sid) if sid else None,
            "source_age_text": age,
        }
        reading.update(
            value
            if field == "location"
            else {"value": value, "unit": unit, "basis": basis}
        )
        if period is not None:
            reading["period"] = period
        rank = (
            observed is not None,
            observed or datetime.min.replace(tzinfo=timezone.utc),
            source == "motive_api",
            source != "manual_location",
            captured or datetime.min.replace(tzinfo=timezone.utc),
            str(sid or ""),
        )
        old = choices[vid].get(field)
        if old is None or rank > old[0]:
            choices[vid][field] = rank, reading

    for row in snapshots:
        m = by_pair.get((row.vehicle_id, row.fleet_customer_id))
        if (
            not m
            or m.id != row.fleet_membership_id
            or context[row.vehicle_id] != row.fleet_customer_id
            or not within(m, utc(row.observed_at or row.captured_at))
        ):
            continue
        common = (
            row.source,
            row.observed_at,
            row.captured_at,
            row.id,
            row.source_age_text,
        )
        if row.location_label or row.lat is not None:
            add(
                row.vehicle_id,
                "location",
                {"lat": row.lat, "lng": row.lng, "label": row.location_label},
                *common,
                precision=row.observed_precision,
            )
        for attr, field, unit in [
            ("speed_mph", "speed", "mph"),
            ("odometer_miles", "odometer", "mi"),
            ("engine_hours", "engine_hours", "h"),
            ("fuel_percent", "fuel", "percent"),
            ("fuel_economy_mpg", "fuel_economy", "mpg"),
            ("fault_count", "fault_count", "count"),
        ]:
            value = getattr(row, attr)
            if value is not None:
                add(
                    row.vehicle_id,
                    field,
                    value,
                    *common,
                    basis="dashboard_unspecified"
                    if field in ("odometer", "engine_hours")
                    else None,
                    unit=unit,
                    period=row.fuel_economy_period if field == "fuel_economy" else None,
                    precision=row.observed_precision,
                )
    for remote, connection in remotes:
        m = by_pair.get((remote.vehicle_id, connection.fleet_customer_id))
        if (
            not m
            or context[remote.vehicle_id] != connection.fleet_customer_id
            or not remote.mapped_at
            or not within(m, utc(remote.mapped_at))
        ):
            continue

        def admissible(t, remote=remote, m=m):
            return (
                t is not None and utc(t) >= utc(remote.mapped_at) and within(m, utc(t))
            )

        if admissible(remote.located_at):
            common = ("motive_api", remote.located_at, remote.received_at)
            if remote.lat is not None and remote.lng is not None:
                add(
                    remote.vehicle_id,
                    "location",
                    {"lat": remote.lat, "lng": remote.lng, "label": None},
                    *common,
                )
            if remote.speed_mph is not None:
                add(remote.vehicle_id, "speed", remote.speed_mph, *common, unit="mph")
        if admissible(remote.metrics_observed_at):
            for field, true, virtual, unit in [
                ("odometer", "true_odometer_miles", "virtual_odometer_miles", "mi"),
                ("engine_hours", "true_engine_hours", "virtual_engine_hours", "h"),
            ]:
                value = getattr(remote, true)
                basis = "calibrated"
                if value is None:
                    value, basis = getattr(remote, virtual), "virtual"
                if value is not None:
                    add(
                        remote.vehicle_id,
                        field,
                        value,
                        "motive_api",
                        remote.metrics_observed_at,
                        remote.metrics_received_at,
                        basis=basis,
                        unit=unit,
                    )
        if admissible(remote.fault_cursor_at) and remote.faults_synced_at:
            add(
                remote.vehicle_id,
                "fault_count",
                faults.get(remote.id, 0),
                "motive_api",
                remote.fault_cursor_at,
                remote.faults_synced_at,
                unit="count",
            )
    for v in vehicles:
        m = by_pair.get((v.id, context[v.id]))
        if (
            m
            and v.last_location_at
            and within(m, utc(v.last_location_at))
            and (
                v.last_location_label
                or (v.last_lat is not None and v.last_lng is not None)
            )
        ):
            add(
                v.id,
                "location",
                {"lat": v.last_lat, "lng": v.last_lng, "label": v.last_location_label},
                "manual_location",
                None,
                v.last_location_at,
            )
    for truck in trucks:
        fields = {k: v[1] for k, v in choices[truck.id].items()}
        speed = fields.get("speed")
        motion = (
            ("moving" if speed["value"] > 0 else "stopped")
            if speed and speed["freshness"] == "fresh"
            else "unknown"
        )
        truck.telemetry = FleetTelemetry(**fields, motion=motion) if fields else None


async def purge(db):
    await db.execute(
        delete(Snapshot).where(Snapshot.captured_at < now() - timedelta(days=30))
    )
