"""Import completed Motive dashboard trips. Dry run unless --apply is supplied."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from app.db.models.customer import Customer
from app.db.models.fleet_trip import FleetTrip, FleetTripRevision
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_trip import TripImport
from app.services.fleet_telemetry import active_membership, now, within


def parse_rows(document, stamp):
    if not isinstance(document, dict) or set(document) != {"rows"} or not isinstance(document["rows"], list) or not 1 <= len(document["rows"]) <= 1000:
        raise ValueError("Expected 1 to 1000 rows")
    rows = [TripImport.model_validate(row) for row in document["rows"]]
    keys = set()
    provider_vins = {}
    for row in rows:
        key = (row.provider_vehicle_id, row.started_at)
        if key in keys or row.source_read_at > stamp:
            raise ValueError("Duplicate or incomplete trip")
        if provider_vins.setdefault(row.provider_vehicle_id, row.vin) != row.vin:
            raise ValueError("Provider vehicle maps to conflicting VINs")
        keys.add(key)
    return rows


def digest(row):
    payload = row.model_dump(mode="json", exclude={"source_read_at"})
    # Retain exact hashes from pre-metrics trips and normalize all-unknown input.
    if payload["metrics"] is None or all(value is None for value in payload["metrics"].values()):
        payload.pop("metrics")
    if payload["timestamp_precision"] == "second":
        payload.pop("timestamp_precision")
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def authorize(db, tenant_id, actor_id):
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None), Tenant.is_active.is_(True)).with_for_update())).scalar_one_or_none()
    actor = (await db.execute(select(User).where(User.id == actor_id, User.tenant_id == tenant_id, User.deleted_at.is_(None), User.is_active.is_(True)).with_for_update())).scalar_one_or_none()
    if not tenant or not actor or actor.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise ValueError("Active tenant owner/admin required")


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def resolve_identity(db, row, tenant_id, stamp):
    vehicles = (await db.execute(select(Vehicle).where(Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None), func.upper(func.trim(Vehicle.vin)) == row.vin).with_for_update())).scalars().all()
    if len(vehicles) != 1:
        raise ValueError("VIN must match exactly one active truck")
    vehicle = vehicles[0]
    members = (await db.execute(select(FleetMembership).join(Customer, Customer.id == FleetMembership.fleet_customer_id).where(FleetMembership.tenant_id == tenant_id, FleetMembership.vehicle_id == vehicle.id, Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None), *active_membership(stamp)).with_for_update())).scalars().all()
    upper = row.ended_at + timedelta(seconds=60 if row.timestamp_precision == "minute" else 0)
    if len(members) != 1 or not within(members[0], row.started_at) or not within(members[0], row.source_read_at):
        raise ValueError("Unique current membership covering the full trip required")
    member = members[0]
    covers_end = upper <= aware(member.effective_to) if row.timestamp_precision == "minute" and member.effective_to else within(member, upper)
    if not covers_end or upper > stamp:
        raise ValueError("Unique current membership covering the full trip required")
    return vehicle, member


async def run_import(db, rows, tenant_id, actor_id, apply=False):
    """Caller owns transaction. Tenant lock serializes imports and identity checks."""
    stamp = now()
    await authorize(db, tenant_id, actor_id)
    receipts = []
    # Validate the entire batch before staging any inserts, including direct callers.
    rows = parse_rows({"rows": [row.model_dump(mode="json") for row in rows]}, stamp)
    plans = []
    for row in rows:
        vehicle, member = await resolve_identity(db, row, tenant_id, stamp)
        existing = (await db.execute(select(FleetTrip).where(FleetTrip.tenant_id == tenant_id, FleetTrip.provider_vehicle_id == row.provider_vehicle_id, FleetTrip.started_at == row.started_at))).scalar_one_or_none()
        checksum = digest(row)
        if existing and (existing.deleted_at or existing.request_digest != checksum or existing.vehicle_id != vehicle.id or existing.fleet_membership_id != member.id):
            raise ValueError("Conflicting immutable trip")
        plans.append((row, vehicle, member, existing, checksum))
    for row, vehicle, member, existing, checksum in plans:
        trip = existing
        if apply and trip is None:
            data = row.model_dump(exclude={"vin", "stops", "unit", "metrics"})
            trip = FleetTrip(**data, provider_unit=row.unit, metrics=row.metrics.model_dump(mode="json") if row.metrics else None, stops=[stop.model_dump(mode="json") for stop in row.stops] if row.stops is not None else None,
                tenant_id=tenant_id, vehicle_id=vehicle.id, fleet_customer_id=member.fleet_customer_id, fleet_membership_id=member.id,
                verified_vin=row.vin, request_digest=checksum, source="motive_dashboard_manual", captured_at=stamp, captured_by_user_id=actor_id)
            db.add(trip)
            await db.flush()
        receipts.append(dict(vehicle_id=str(vehicle.id), unit_number=vehicle.unit_number, started_at=row.started_at.isoformat(), trip_id=str(trip.id) if trip else None, action="unchanged" if existing else "created" if apply else "would_create"))
    return dict(mode="apply" if apply else "dry_run", rows=receipts)


class TripCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    trip_id: UUID
    expected_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=500)
    row: TripImport


def parse_corrections(document, stamp):
    if not isinstance(document, dict) or set(document) != {"corrections"} or not isinstance(document["corrections"], list) or not 1 <= len(document["corrections"]) <= 1000:
        raise ValueError("Expected 1 to 1000 corrections")
    corrections = [TripCorrection.model_validate(value) for value in document["corrections"]]
    parse_rows({"rows": [value.row.model_dump(mode="json") for value in corrections]}, stamp)
    if len({value.trip_id for value in corrections}) != len(corrections):
        raise ValueError("Duplicate correction identity")
    return corrections


def snapshot(trip):
    result = {}
    for column in FleetTrip.__table__.columns:
        value = getattr(trip, column.name)
        result[column.name] = aware(value).isoformat() if isinstance(value, datetime) else str(value) if isinstance(value, UUID) else value
    return result


def canonical_metrics(value):
    # Match normal import's null/all-unknown equivalence without dropping readings.
    return value if value is not None and any(v is not None for v in value.values()) else None


async def run_corrections(db, corrections, tenant_id, actor_id, apply=False):
    """Explicit, audited CAS; caller must commit/rollback the entire batch."""
    stamp = now()
    await authorize(db, tenant_id, actor_id)
    corrections = parse_corrections({"corrections": [value.model_dump(mode="json") for value in corrections]}, stamp)
    plans = []
    for correction in corrections:
        row = correction.row
        vehicle, member = await resolve_identity(db, row, tenant_id, stamp)
        trip = (await db.execute(select(FleetTrip).where(FleetTrip.id == correction.trip_id, FleetTrip.tenant_id == tenant_id).with_for_update())).scalar_one_or_none()
        if not trip or trip.deleted_at or trip.vehicle_id != vehicle.id or trip.fleet_membership_id != member.id:
            raise ValueError("Correction trip is inaccessible")
        checksum = digest(row)
        fixed = ((trip.verified_vin, row.vin), (trip.provider_vehicle_id, row.provider_vehicle_id),
                 (trip.provider_unit, row.unit), (aware(trip.started_at), row.started_at),
                 (aware(trip.ended_at), row.ended_at), (trip.origin_label, row.origin_label),
                 (trip.destination_label, row.destination_label), (trip.stops, [stop.model_dump(mode="json") for stop in row.stops] if row.stops is not None else None),
                 (canonical_metrics(trip.metrics), canonical_metrics(row.metrics.model_dump(mode="json") if row.metrics else None)))
        if any(old != new for old, new in fixed) or row.source_read_at < aware(trip.source_read_at):
            raise ValueError("Correction changes identity, frozen data or uses stale source")
        previous = (await db.execute(select(FleetTripRevision).where(FleetTripRevision.tenant_id == tenant_id, FleetTripRevision.trip_id == trip.id, FleetTripRevision.old_digest == correction.expected_digest))).scalar_one_or_none()
        unchanged = trip.request_digest == checksum and previous is not None and previous.replacement_digest == checksum
        if not unchanged and (trip.request_digest != correction.expected_digest or previous is not None):
            raise ValueError("Correction predecessor mismatch")
        if not unchanged and abs(trip.distance_miles - row.distance_miles) >= 1:
            raise ValueError("Correction distance delta must be less than one mile")
        if not unchanged and trip.request_digest == checksum:
            raise ValueError("Correction must change measured data")
        plans.append((correction, trip, checksum, unchanged))
    receipts = []
    for correction, trip, checksum, unchanged in plans:
        if apply and not unchanged:
            db.add(FleetTripRevision(tenant_id=tenant_id, trip_id=trip.id,
                old_digest=trip.request_digest, replacement_digest=checksum, old_snapshot=snapshot(trip),
                reason=correction.reason, corrected_at=stamp, corrected_by_user_id=actor_id))
            row = correction.row
            trip.distance_miles = row.distance_miles
            trip.driving_seconds = row.driving_seconds
            trip.timestamp_precision = row.timestamp_precision
            trip.source_read_at = row.source_read_at
            trip.captured_at = stamp
            trip.captured_by_user_id = actor_id
            trip.request_digest = checksum
        receipts.append(dict(trip_id=str(trip.id), action="unchanged" if unchanged else "corrected" if apply else "would_correct", replacement_digest=checksum))
    if apply:
        await db.flush()
    return dict(mode="apply" if apply else "dry_run", rows=receipts)


async def main(args):
    from app.db.session import AsyncSessionLocal
    document = json.loads(Path(args.input).read_text())
    rows = parse_corrections(document, now()) if args.correct else parse_rows(document, now())
    async with AsyncSessionLocal() as db:
        try:
            result = await (run_corrections if args.correct else run_import)(db, rows, args.tenant_id, args.actor_id, args.apply)
            if args.apply:
                await db.commit()
            else:
                await db.rollback()
        except Exception:
            await db.rollback()
            raise
    print(json.dumps({**result, "committed": args.apply}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--actor-id", required=True, type=UUID)
    parser.add_argument("--correct", action="store_true", help="Audited compare-and-swap correction input")
    parser.add_argument("--apply", action="store_true")
    try:
        asyncio.run(main(parser.parse_args()))
    except Exception:
        print(json.dumps({"committed": False, "error": "Import rolled back. Check input, identity, membership and schema."}))
        raise SystemExit(1) from None
