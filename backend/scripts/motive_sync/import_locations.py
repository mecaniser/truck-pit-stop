"""Bounded Motive UI location import through the existing capture service."""

import hashlib
import json
import math
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

from app.db.models.customer import Customer
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot as Snapshot
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.dashboard_vehicle_binding import BoundTelemetryCapture
from app.schemas.fleet_telemetry import TelemetryCapture
from app.services import dashboard_vehicle_bindings as bindings
from app.services import fleet_telemetry as telemetry
from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, text


def time_value(value):
    if not isinstance(value, str):
        raise TypeError("Explicit timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp timezone required")
    return result.astimezone(UTC)


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
    source_evidence = {
        **document,
        "vehicles": [
            {key: value for key, value in row.items() if not key.startswith("_")}
            for row in rows
        ],
    }
    source_digest = hashlib.sha256(
        json.dumps(source_evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    vins, providers = set(), set()
    for row in rows:
        vin = (row.get("vin") or "").strip().upper()
        provider = row.get("provider_vehicle_id")
        if (
            (
                not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin)
                and not (
                    not vin
                    and (
                        row.get("status") == "unavailable"
                        or row.get("source_vin_state")
                        in {"not_displayed", "explicitly_empty"}
                    )
                )
            )
            or not isinstance(provider, str)
            or not provider
        ):
            raise ValueError("Exact VIN and provider vehicle ID required")
        if (vin and vin in vins) or provider in providers:
            raise ValueError("Duplicate source VIN or provider vehicle")
        vins.add(vin)
        providers.add(provider)
        if vin and row.get("source_vin_state") is not None:
            raise ValueError("Conflicting source VIN evidence")
        row["vin"] = vin if row.get("status") == "unavailable" else vin or None
        if row.get("status") not in ("located", "unavailable"):
            raise ValueError("Invalid collection status")
        if row["status"] == "unavailable":
            continue
        read = time_value(row.get("sourceReadTime"))
        if read > stamp + timedelta(minutes=5) or (
            read < stamp - timedelta(minutes=30) and not allow_replay
        ):
            raise ValueError("Stale or future capture file")
        precision = row.get("precision")
        if precision != "unknown" and (
            row.get("timezone") != "America/New_York" or not row.get("rawTimestamp")
        ):
            raise ValueError("Verified timestamp timezone and source text required")
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
        elif precision == "unknown":
            if any(
                row.get(key) is not None
                for key in (
                    "observed_at",
                    "observed_minute_start",
                    "observed_minute_end",
                )
            ):
                raise ValueError("Unknown precision must not carry an observation time")
            if any(
                row.get(key) is not None and not isinstance(row[key], str)
                for key in ("rawTimestamp", "timezone")
            ):
                raise ValueError("Unknown timestamp evidence must be text or null")
            start = end = None
        else:
            raise ValueError("Unverified observation timestamp")
        if start is not None and (
            (start < stamp - timedelta(days=30) and not allow_replay)
            or start > read + timedelta(minutes=5)
        ):
            raise ValueError("Observation outside admissible window")
        row["_validated_company_id"] = company_id
        row["_validated_source_sha256"] = source_digest
        make_body(
            row,
            "00000000-0000-0000-0000-000000000000",
            "00000000-0000-0000-0000-000000000000",
            company_label,
            company_id,
        )
    return rows


def speed_value(row):
    """Accept only a real bounded measurement with its own verified source time."""
    value = row.get("speed_mph")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 250
        or not math.isfinite(value)
        or row.get("precision") not in ("second", "minute")
    ):
        return None
    return value


def make_body(
    row,
    tenant_id,
    customer_id,
    company_label,
    company_id,
    *,
    location=True,
    speed=True,
):
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
    if row["vin"] is None:
        evidence.update(source_vin=None, source_vin_state=row.get("source_vin_state"))
    accepted_speed = speed_value(row) if speed else None
    if accepted_speed is not None:
        # Do not add null speed fields to legacy location request digests.
        evidence["speedText"] = row.get("speedText")
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
    if row.get("precision") == "minute":
        values["observed_at"] = row["observed_minute_start"]
        values["observed_precision"] = "minute"
    if location:
        if values["lat"] is None or values["lng"] is None:
            raise ValueError("Located row requires coordinate pair")
    else:
        for name in ("lat", "lng", "location_label"):
            values.pop(name)
    if accepted_speed is not None:
        values["speed_mph"] = accepted_speed
    digest = hashlib.sha256(
        json.dumps(values, sort_keys=True, default=str).encode()
    ).hexdigest()
    if row["vin"] is None:
        if row.get("source_vin_state") not in {"not_displayed", "explicitly_empty"}:
            raise ValueError("Explicit source VIN state proof required")
        values.update(
            dashboard_binding_id=row.get("_dashboard_binding_id", UUID(int=0)),
            source_company_id=company_id,
            source_read_at=row["sourceReadTime"],
            source_vin_state=row["source_vin_state"],
        )
        digest = hashlib.sha256(
            json.dumps(values, sort_keys=True, default=str).encode()
        ).hexdigest()
        return BoundTelemetryCapture(
            client_request_id=uuid5(
                NAMESPACE_URL, f"motive-location:{tenant_id}:{digest}"
            ),
            **values,
        )
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


def disposition(row, prior, field="location"):
    """Never use capture time as evidence that a source position is newer."""
    if row["status"] == "unavailable":
        return "unavailable"
    if field == "speed" and speed_value(row) is None:
        return (
            "speed_timestamp_unavailable"
            if row.get("precision") == "unknown"
            else "speed_unavailable"
        )
    if row["precision"] == "unknown":
        if not prior:
            return "update"
        if any(old.observed_at is not None for old in prior):
            return "prior_time_unknown"
        return (
            "unchanged"
            if all(
                getattr(old, "lat", None) == row["lat"]
                and getattr(old, "lng", None) == row["lng"]
                for old in prior
            )
            else "prior_time_unknown"
        )
    start, end = interval(row)
    if row["precision"] == "minute":
        end -= timedelta(microseconds=1)
    unchanged = False
    for old in prior:
        if old.observed_at is not None:
            previous_start, previous_end = telemetry.observation_interval(
                old.observed_at, getattr(old, "observed_precision", None)
            )
        else:
            if field == "speed":
                captured = getattr(old, "captured_at", None)
                if captured is not None and start > telemetry.utc(captured):
                    continue
                return "prior_time_unknown"
            try:
                note = json.loads(old.evidence_note or "{}")
                previous_start, previous_end = interval(note)
                if note.get("precision") == "minute":
                    previous_end -= timedelta(microseconds=1)
            except (ValueError, TypeError, KeyError):
                captured = getattr(old, "captured_at", None)
                if captured is not None and start > telemetry.utc(captured):
                    continue
                return "prior_time_unknown"
        if end < previous_start:
            return "older"
        if start > previous_end:
            continue
        if start == previous_start and end == previous_end:
            same = (
                old.speed_mph == row["speed_mph"]
                if field == "speed"
                else old.lat == row["lat"] and old.lng == row["lng"]
            )
            if not same:
                return "conflicting_observation"
            unchanged = True
            continue
        return "overlapping_observation_interval"
    return "unchanged" if unchanged else "update"


def relevant_speed_history(start):
    """Only intervals that can hold this observation count toward the bound.

    Strictly earlier non-overlapping fields cannot change disposition. Exclude
    them without relying on purge, but retain every overlapping/later interval
    and unknown-time reading whose capture is not strictly before this start.
    """
    return or_(
        and_(
            Snapshot.observed_at.is_not(None),
            or_(
                and_(
                    Snapshot.observed_precision == "minute",
                    Snapshot.observed_at > start - timedelta(minutes=1),
                ),
                and_(
                    or_(
                        Snapshot.observed_precision.is_(None),
                        Snapshot.observed_precision == "second",
                    ),
                    Snapshot.observed_at >= start,
                ),
            ),
        ),
        and_(
            Snapshot.observed_at.is_(None),
            Snapshot.captured_at >= start,
        ),
    )


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
        if (
            row["vin"]
            and row["status"] == "located"
            and row.get("_validated_company_id") == company_id
        ):
            await bindings.invalidate_source_vin(
                db,
                tenant_id,
                actor_id,
                company_id,
                company_label,
                row["provider_vehicle_id"],
                row["vin"],
                time_value(row["sourceReadTime"]),
                row["_validated_source_sha256"],
            )
        bound_vehicle = None
        if not row["vin"]:
            if row["status"] != "located" or row.get("source_vin_state") not in {
                "not_displayed",
                "explicitly_empty",
            }:
                item["status"] = "vin_unavailable"
                continue
            try:
                bound_vehicle, _, binding = await bindings.resolve(
                    db,
                    tenant_id,
                    company_id,
                    row["provider_vehicle_id"],
                    time_value(row["sourceReadTime"]),
                    company_label=company_label,
                )
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
                item.update(status="binding_unavailable", reason=exc.detail["code"])
                continue
            if row["precision"] != "unknown":
                start, end = interval(row)
                if start < telemetry.utc(binding.effective_from) or (
                    binding.effective_to is not None
                    and end >= telemetry.utc(binding.effective_to)
                ):
                    raise ValueError("Observation outside binding")
            row["_dashboard_binding_id"] = binding.id
        vehicles = (
            (
                await db.execute(
                    select(Vehicle)
                    .where(
                        Vehicle.tenant_id == tenant_id,
                        Vehicle.deleted_at.is_(None),
                        Vehicle.id == bound_vehicle.id
                        if bound_vehicle
                        else func.upper(func.trim(Vehicle.vin)) == row["vin"],
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
        # A prior import may have written only one admissible field. Discover
        # its immutable request before freshness or unchanged checks.
        subset_replays = {}
        if speed_value(row) is not None:
            for field in ("location", "speed"):
                candidate = make_body(
                    row,
                    tenant_id,
                    member.fleet_customer_id,
                    company_label,
                    company_id,
                    location=field == "location",
                    speed=field == "speed",
                )
                saved = (
                    await db.execute(
                        select(Snapshot).where(
                            Snapshot.tenant_id == tenant_id,
                            Snapshot.client_request_id == candidate.client_request_id,
                        )
                    )
                ).scalar_one_or_none()
                if saved is not None:
                    subset_replays[field] = candidate
        if time_value(row["sourceReadTime"]) < stamp - timedelta(minutes=30):
            if subset_replays:
                body = subset_replays.get("speed", subset_replays.get("location"))
                item["status"] = "replay"
                plans.append((vehicle.id, body, item))
            else:
                item["status"] = "stale_source_file"
            continue
        if row["precision"] != "unknown":
            start, end = interval(row)
            if start < stamp - timedelta(days=30):
                if subset_replays:
                    body = subset_replays.get("speed", subset_replays.get("location"))
                    item["status"] = "replay"
                    plans.append((vehicle.id, body, item))
                else:
                    item["status"] = "older"
                continue
            if not telemetry.within(member, start) or not telemetry.within(
                member,
                end - timedelta(microseconds=1)
                if row["precision"] == "minute"
                else end,
            ):
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
                        *(
                            []
                            if row["precision"] == "unknown"
                            else [Snapshot.captured_at >= stamp - timedelta(days=30)]
                        ),
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
        location_history_overflow = len(prior) > 1000
        # Include canonical unknown-time position: never silently replace it.
        if (
            (not prior or row["precision"] == "unknown")
            and vehicle.last_lat is not None
            and vehicle.last_lng is not None
        ):
            prior += [
                SimpleNamespace(
                    observed_at=None,
                    evidence_note=None,
                    captured_at=vehicle.last_location_at,
                    lat=vehicle.last_lat,
                    lng=vehicle.last_lng,
                )
            ]
        if row["precision"] == "unknown":
            # Include the effective projection (for example an API position or
            # a timestamped address-only observation), not just coordinate rows.
            projected = SimpleNamespace(
                id=vehicle.id,
                board_membership_customer_id=member.fleet_customer_id,
                telemetry=None,
            )
            await telemetry.attach(db, [projected], tenant_id)
            location = projected.telemetry.location if projected.telemetry else None
            if location is not None:
                prior.append(
                    SimpleNamespace(
                        observed_at=location.observed_at,
                        evidence_note=None,
                        captured_at=location.captured_at,
                        lat=location.lat,
                        lng=location.lng,
                    )
                )
        location_status = (
            "replay"
            if "location" in subset_replays
            else "history_review_required"
            if location_history_overflow
            else disposition(row, prior)
        )
        speed_status = disposition(row, [], "speed")
        if speed_value(row) is not None:
            speed_prior = (
                (
                    await db.execute(
                        select(Snapshot)
                        .where(
                            Snapshot.tenant_id == tenant_id,
                            Snapshot.vehicle_id == vehicle.id,
                            Snapshot.fleet_membership_id == member.id,
                            Snapshot.deleted_at.is_(None),
                            Snapshot.speed_mph.is_not(None),
                            relevant_speed_history(interval(row)[0]),
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
            speed_status = (
                "replay"
                if "speed" in subset_replays
                else "history_review_required"
                if len(speed_prior) > 1000
                else disposition(row, speed_prior, "speed")
            )
        if "speed_mph" in row or "speedReason" in row:
            item.update(location_status=location_status, speed_status=speed_status)
        writes_location, writes_speed = (
            location_status == "update",
            speed_status == "update",
        )
        if writes_location or writes_speed:
            item["status"] = "update"
            body = make_body(
                row,
                tenant_id,
                member.fleet_customer_id,
                company_label,
                company_id,
                location=writes_location,
                speed=writes_speed,
            )
        elif subset_replays:
            item["status"] = "replay"
            body = subset_replays.get("speed", subset_replays.get("location"))
        else:
            item["status"] = location_status
            continue
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
        if (vehicle.vin or "").strip().upper() not in source_vins and not any(
            item.get("vehicle_id") == str(vehicle.id) for item in results
        ):
            results.append(
                {
                    "vehicle_id": str(vehicle.id),
                    "unit": vehicle.unit_number,
                    "status": "source_missing",
                    "vin": vehicle.vin,
                }
            )
    return actor, plans, results


def projection_matches(projected, payload, snapshot_id):
    """Verify only written fields, including speed-only supplemental snapshots."""
    if projected is None:
        return False
    expected_time = telemetry.utc(payload.observed_at) if payload.observed_at else None

    def provenance(reading):
        return bool(
            reading
            and reading.snapshot_id == str(snapshot_id)
            and reading.observed_at == expected_time
            and reading.observed_precision == payload.observed_precision
        )

    matches = []
    if payload.lat is not None or payload.location_label:
        loc = projected.location
        matches.append(
            provenance(loc) and loc.lat == payload.lat and loc.lng == payload.lng
        )
    if payload.speed_mph is not None:
        speed = projected.speed
        matches.append(provenance(speed) and speed.value == payload.speed_mph)
    return bool(matches) and all(matches)


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
        matches = projection_matches(truck.telemetry, body, item["snapshot_id"])
        if not matches and item["status"] != "replay":
            raise ValueError("Fleet projection did not select captured fields")
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
            item["saved_receipt_verified"] = True
            item["board_verified_after_commit"] = projection_matches(
                truck.telemetry, saved, saved.id
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
