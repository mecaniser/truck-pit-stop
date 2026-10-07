"""Bounded Motive UI location import through the existing capture service."""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from app.db.models.customer import Customer
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot as Snapshot
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_telemetry import TelemetryCapture
from app.services import fleet_telemetry as telemetry
from sqlalchemy import func, or_, select, text


def time_value(value):
    if not isinstance(value, str):
        raise TypeError("Explicit timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp timezone required")
    return result.astimezone(timezone.utc)


def parse_document(document, company_label, company_id, stamp, allow_replay=False):
    if (
        document.get("company_label") != company_label
        or document.get("company_id") != company_id
        or document.get("company_verified_before") is not True
        or document.get("company_verified_after") is not True
        or document.get("complete") is not True
    ):
        raise ValueError("Incomplete collection or company identity mismatch")
    rows = document.get("vehicles")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Nonempty fleet collection required")
    vins, providers = set(), set()
    for row in rows:
        vin = (row.get("vin") or "").strip().upper()
        provider = row.get("provider_vehicle_id")
        if (
            (
                not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin)
                and not (row.get("status") == "unavailable" and not vin)
            )
            or not isinstance(provider, str)
            or not provider
        ):
            raise ValueError("Exact VIN and provider vehicle ID required")
        if (vin and vin in vins) or provider in providers:
            raise ValueError("Duplicate source VIN or provider vehicle")
        vins.add(vin)
        providers.add(provider)
        row["vin"] = vin
        if row.get("status") not in ("located", "unavailable"):
            raise ValueError("Invalid collection status")
        if row["status"] == "unavailable":
            continue
        read = time_value(row.get("sourceReadTime"))
        if read > stamp + timedelta(minutes=5) or (
            read < stamp - timedelta(minutes=30) and not allow_replay
        ):
            raise ValueError("Stale or future capture file")
        if row.get("timezone") != "America/New_York" or not row.get("rawTimestamp"):
            raise ValueError("Verified timestamp timezone and source text required")
        precision = row.get("precision")
        if precision == "second":
            start = end = time_value(row.get("observed_at"))
            if row.get("observed_minute_start") or row.get("observed_minute_end"):
                raise ValueError("Conflicting timestamp precision")
        elif precision == "minute":
            start, end = (
                time_value(row.get("observed_minute_start")),
                time_value(row.get("observed_minute_end")),
            )
            if (
                row.get("observed_at") is not None
                or end - start != timedelta(minutes=1)
                or start.second
                or start.microsecond
            ):
                raise ValueError(
                    "Minute interval must not invent exact observation time"
                )
        else:
            raise ValueError("Unverified observation timestamp")
        if (
            start < stamp - timedelta(days=30) and not allow_replay
        ) or start > read + timedelta(minutes=5):
            raise ValueError("Observation outside admissible window")
        make_body(
            row,
            "00000000-0000-0000-0000-000000000000",
            "00000000-0000-0000-0000-000000000000",
            company_label,
            company_id,
        )
    return rows


def make_body(row, tenant_id, customer_id, company_label, company_id):
    evidence = {
        key: row.get(key)
        for key in (
            "sourceReadTime",
            "rawTimestamp",
            "timezone",
            "precision",
            "observed_minute_start",
            "observed_minute_end",
        )
    }
    evidence.update(kind="motive_server_ui_v1", company_id=company_id)
    values = {
        "fleet_customer_id": customer_id,
        "vin": row["vin"],
        "observed_at": row.get("observed_at"),
        "lat": row.get("lat"),
        "lng": row.get("lng"),
        "location_label": row.get("address"),
        "source_age_text": row.get("sourceAge"),
        "provider_company_label": company_label,
        "provider_vehicle_id": row["provider_vehicle_id"],
        "provider_vehicle_number": row.get("unit"),
        "evidence_note": json.dumps(evidence, sort_keys=True, separators=(",", ":")),
    }
    if values["lat"] is None or values["lng"] is None:
        raise ValueError("Located row requires coordinate pair")
    digest = hashlib.sha256(
        json.dumps(values, sort_keys=True, default=str).encode()
    ).hexdigest()
    return TelemetryCapture(
        client_request_id=uuid5(NAMESPACE_URL, f"motive-location:{tenant_id}:{digest}"),
        **values,
    )


def interval(row):
    if row.get("observed_at"):
        t = time_value(row["observed_at"])
        return t, t
    return time_value(row["observed_minute_start"]), time_value(
        row["observed_minute_end"]
    )


def disposition(row, prior):
    """Never use capture time as evidence that a source position is newer."""
    if row["status"] == "unavailable":
        return "unavailable"
    start, end = interval(row)
    for old in prior:
        if old.observed_at is not None:
            if row["precision"] == "minute":
                return "precision_insufficient_for_projection"
            previous = telemetry.utc(old.observed_at)
            if start < previous:
                return "older"
            if start == previous:
                return (
                    "unchanged"
                    if old.lat == row["lat"] and old.lng == row["lng"]
                    else "conflicting_observation"
                )
        else:
            try:
                note = json.loads(old.evidence_note or "{}")
                previous_start, previous_end = interval(note)
            except (ValueError, TypeError, KeyError):
                captured = getattr(old, "captured_at", None)
                if captured is not None and start > telemetry.utc(captured):
                    continue
                return "prior_time_unknown"
            if end <= previous_start:
                return "older"
            if start < previous_end:
                return (
                    "unchanged"
                    if old.lat == row["lat"] and old.lng == row["lng"]
                    else "overlapping_observation_interval"
                )
    return "update"


async def prepare(db, rows, tenant_id, actor_id, company_label, company_id):
    stamp = telemetry.now()
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
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        tenant is None
        or actor is None
        or actor.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
    ):
        raise ValueError("Active tenant and owner/admin actor required")
    results, plans = [], []
    for row in rows:
        item = {"unit": row.get("unit"), "vin": row["vin"], "status": row["status"]}
        if row.get("reason"):
            item["reason"] = row["reason"]
        results.append(item)
        if not row["vin"]:
            item["status"] = "vin_unavailable"
            continue
        vehicles = (
            (
                await db.execute(
                    select(Vehicle)
                    .where(
                        Vehicle.tenant_id == tenant_id,
                        Vehicle.deleted_at.is_(None),
                        func.upper(func.trim(Vehicle.vin)) == row["vin"],
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        if not vehicles:
            item["status"] = "unmatched_vin"
            continue
        if len(vehicles) != 1:
            raise ValueError("Ambiguous tenant VIN")
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
                        or_(
                            Customer.fleet_enabled.is_(True),
                            Customer.is_internal_fleet.is_(True),
                        ),
                        *telemetry.active_membership(stamp),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        if not members:
            item.update(vehicle_id=str(vehicle.id), status="outside_current_fleet")
            continue
        if len(members) > 1:
            raise ValueError("Expected unique current fleet membership")
        member = members[0]
        if row["status"] == "located" and not telemetry.within(
            member, time_value(row["sourceReadTime"])
        ):
            raise ValueError("Membership does not cover source capture")
        item.update(vehicle_id=str(vehicle.id), membership_id=str(member.id))
        if row["status"] == "unavailable":
            continue
        body = make_body(
            row, tenant_id, member.fleet_customer_id, company_label, company_id
        )
        existing = (
            await db.execute(
                select(Snapshot).where(
                    Snapshot.tenant_id == tenant_id,
                    Snapshot.client_request_id == body.client_request_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            # capture() rechecks actor, membership and complete immutable digest.
            item["status"] = "replay"
            plans.append((vehicle.id, body, item))
            continue
        if time_value(row["sourceReadTime"]) < stamp - timedelta(minutes=30):
            item["status"] = "stale_source_file"
            continue
        start, end = interval(row)
        if start < stamp - timedelta(days=30):
            item["status"] = "older"
            continue
        if not telemetry.within(member, start) or not telemetry.within(member, end):
            raise ValueError("Membership does not cover observation")
        prior = (
            (
                await db.execute(
                    select(Snapshot)
                    .where(
                        Snapshot.tenant_id == tenant_id,
                        Snapshot.vehicle_id == vehicle.id,
                        Snapshot.fleet_membership_id == member.id,
                        Snapshot.deleted_at.is_(None),
                        Snapshot.captured_at >= stamp - timedelta(days=30),
                        Snapshot.lat.is_not(None),
                        Snapshot.lng.is_not(None),
                    )
                    .order_by(
                        Snapshot.observed_at.desc().nulls_last(),
                        Snapshot.captured_at.desc(),
                    )
                    .limit(1001)
                )
            )
            .scalars()
            .all()
        )
        if len(prior) > 1000:
            item["status"] = "history_review_required"
            continue
        # Include canonical unknown-time position: never silently replace it.
        if not prior and vehicle.last_lat is not None and vehicle.last_lng is not None:
            prior = [
                SimpleNamespace(
                    observed_at=None,
                    evidence_note=None,
                    captured_at=vehicle.last_location_at,
                )
            ]
        item["status"] = disposition(row, prior)
        if item["status"] != "update":
            continue
        body = make_body(
            row, tenant_id, member.fleet_customer_id, company_label, company_id
        )
        plans.append((vehicle.id, body, item))
    # Reconcile the whole current fleet, including trucks omitted by the source.
    current = (
        (
            await db.execute(
                select(Vehicle)
                .join(FleetMembership, FleetMembership.vehicle_id == Vehicle.id)
                .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
                .where(
                    Vehicle.tenant_id == tenant_id,
                    Vehicle.deleted_at.is_(None),
                    FleetMembership.tenant_id == tenant_id,
                    Customer.tenant_id == tenant_id,
                    Customer.deleted_at.is_(None),
                    or_(
                        Customer.fleet_enabled.is_(True),
                        Customer.is_internal_fleet.is_(True),
                    ),
                    *telemetry.active_membership(stamp),
                )
            )
        )
        .scalars()
        .all()
    )
    source_vins = {row["vin"] for row in rows if row["vin"]}
    seen = set()
    for vehicle in current:
        if vehicle.id in seen:
            continue
        seen.add(vehicle.id)
        if (vehicle.vin or "").strip().upper() not in source_vins:
            results.append(
                {
                    "vehicle_id": str(vehicle.id),
                    "unit": vehicle.unit_number,
                    "status": "source_missing",
                    "vin": vehicle.vin,
                }
            )
    return actor, plans, results


async def execute_pass(db, rows, tenant_id, actor_id, company_label, company_id):
    actor, plans, results = await prepare(
        db, rows, tenant_id, actor_id, company_label, company_id
    )
    for vehicle_id, body, item in plans:
        saved, created = await telemetry.capture(db, actor, vehicle_id, body)
        item.update(
            snapshot_id=str(saved.id),
            request_id=str(body.client_request_id),
            created=created,
            captured_at=telemetry.utc(saved.captured_at).isoformat(),
        )
    trucks = [
        SimpleNamespace(
            id=vid, board_membership_customer_id=body.fleet_customer_id, telemetry=None
        )
        for vid, body, _ in plans
    ]
    await telemetry.attach(db, trucks, tenant_id)
    for truck, (_, body, item) in zip(trucks, plans):
        loc = truck.telemetry.location if truck.telemetry else None
        matches = bool(
            loc
            and loc.snapshot_id == item["snapshot_id"]
            and loc.lat == body.lat
            and loc.lng == body.lng
        )
        if not matches and item["status"] != "replay":
            raise ValueError("Fleet map projection did not select captured position")
        item["board_verified"] = matches
    return results


async def _run_import(
    session_factory,
    document,
    tenant_id,
    actor_id,
    company_label,
    company_id,
    commit=False,
):
    rows = parse_document(
        document, company_label, company_id, telemetry.now(), allow_replay=True
    )
    async with session_factory() as db:
        try:
            preview = await execute_pass(
                db, rows, tenant_id, actor_id, company_label, company_id
            )
        finally:
            await db.rollback()
    if not commit:
        return {"mode": "dry_run", "committed": False, "rows": preview}
    async with session_factory() as db:
        try:
            result = await execute_pass(
                db, rows, tenant_id, actor_id, company_label, company_id
            )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    # Read on a fresh connection after commit: a preview is never a saved receipt.
    async with session_factory() as db:
        for item in result:
            if not item.get("snapshot_id"):
                continue
            from uuid import UUID

            saved = (
                await db.execute(
                    select(Snapshot).where(
                        Snapshot.tenant_id == tenant_id,
                        Snapshot.id == UUID(item["snapshot_id"]),
                        Snapshot.client_request_id == UUID(item["request_id"]),
                    )
                )
            ).scalar_one_or_none()
            if saved is None:
                raise ValueError(
                    "Committed receipt readback unavailable; retry identical input"
                )
            truck = SimpleNamespace(
                id=saved.vehicle_id,
                board_membership_customer_id=saved.fleet_customer_id,
                telemetry=None,
            )
            await telemetry.attach(db, [truck], tenant_id)
            loc = truck.telemetry.location if truck.telemetry else None
            item["saved_receipt_verified"] = True
            item["board_verified_after_commit"] = bool(
                loc and loc.snapshot_id == str(saved.id)
            )
            if not item["board_verified_after_commit"]:
                item["status"] = "committed_projection_changed"
    return {"mode": "commit", "committed": True, "rows": result}


async def run_import(
    session_factory,
    document,
    tenant_id,
    actor_id,
    company_label,
    company_id,
    commit=False,
):
    """Dedicated PostgreSQL session lock spans rollback, commit and receipt readback."""
    engine = session_factory.kw["bind"]
    if engine.dialect.name != "postgresql":
        # SQLite is supported solely for isolated synthetic tests.
        return await _run_import(
            session_factory,
            document,
            tenant_id,
            actor_id,
            company_label,
            company_id,
            commit,
        )
    key = int.from_bytes(
        hashlib.sha256(f"motive-sync:{tenant_id}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    async with engine.connect() as lock_connection:
        acquired = (
            await lock_connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
            )
        ).scalar_one()
        if not acquired:
            raise ValueError("Another Motive importer holds this tenant lock")
        try:
            return await _run_import(
                session_factory,
                document,
                tenant_id,
                actor_id,
                company_label,
                company_id,
                commit,
            )
        finally:
            await lock_connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": key}
            )
