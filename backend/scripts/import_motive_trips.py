"""Import completed Motive dashboard trips. Dry run unless --apply is supplied."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID
from sqlalchemy import func, select
from app.db.models.customer import Customer
from app.db.models.fleet_trip import FleetTrip
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
    return hashlib.sha256(json.dumps(row.model_dump(mode="json", exclude={"source_read_at"}), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def run_import(db, rows, tenant_id, actor_id, apply=False):
    """Caller owns transaction. Tenant lock serializes imports and identity checks."""
    stamp = now()
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None), Tenant.is_active.is_(True)).with_for_update())).scalar_one_or_none()
    actor = (await db.execute(select(User).where(User.id == actor_id, User.tenant_id == tenant_id, User.deleted_at.is_(None), User.is_active.is_(True)).with_for_update())).scalar_one_or_none()
    if not tenant or not actor or actor.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise ValueError("Active tenant owner/admin required")
    receipts = []
    # Validate the entire batch before staging any inserts, including direct callers.
    rows = parse_rows({"rows": [row.model_dump(mode="json") for row in rows]}, stamp)
    plans = []
    for row in rows:
        vehicles = (await db.execute(select(Vehicle).where(Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None), func.upper(func.trim(Vehicle.vin)) == row.vin).with_for_update())).scalars().all()
        if len(vehicles) != 1:
            raise ValueError("VIN must match exactly one active truck")
        vehicle = vehicles[0]
        members = (await db.execute(select(FleetMembership).join(Customer, Customer.id == FleetMembership.fleet_customer_id).where(FleetMembership.tenant_id == tenant_id, FleetMembership.vehicle_id == vehicle.id, Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None), *active_membership(stamp)).with_for_update())).scalars().all()
        if len(members) != 1 or not within(members[0], row.started_at) or not within(members[0], row.ended_at) or not within(members[0], row.source_read_at):
            raise ValueError("Unique current membership covering the full trip required")
        member = members[0]
        existing = (await db.execute(select(FleetTrip).where(FleetTrip.tenant_id == tenant_id, FleetTrip.provider_vehicle_id == row.provider_vehicle_id, FleetTrip.started_at == row.started_at))).scalar_one_or_none()
        checksum = digest(row)
        if existing and (existing.deleted_at or existing.request_digest != checksum or existing.vehicle_id != vehicle.id or existing.fleet_membership_id != member.id):
            raise ValueError("Conflicting immutable trip")
        plans.append((row, vehicle, member, existing, checksum))
    for row, vehicle, member, existing, checksum in plans:
        trip = existing
        if apply and trip is None:
            data = row.model_dump(exclude={"vin", "stops", "unit"})
            trip = FleetTrip(**data, provider_unit=row.unit, stops=[stop.model_dump(mode="json") for stop in row.stops] if row.stops is not None else None,
                tenant_id=tenant_id, vehicle_id=vehicle.id, fleet_customer_id=member.fleet_customer_id, fleet_membership_id=member.id,
                verified_vin=row.vin, request_digest=checksum, source="motive_dashboard_manual", captured_at=stamp, captured_by_user_id=actor_id)
            db.add(trip)
            await db.flush()
        receipts.append(dict(vehicle_id=str(vehicle.id), unit_number=vehicle.unit_number, started_at=row.started_at.isoformat(), trip_id=str(trip.id) if trip else None, action="unchanged" if existing else "created" if apply else "would_create"))
    return dict(mode="apply" if apply else "dry_run", rows=receipts)


async def main(args):
    from app.db.session import AsyncSessionLocal
    rows = parse_rows(json.loads(Path(args.input).read_text()), now())
    async with AsyncSessionLocal() as db:
        try:
            result = await run_import(db, rows, args.tenant_id, args.actor_id, args.apply)
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
    parser.add_argument("--apply", action="store_true")
    try:
        asyncio.run(main(parser.parse_args()))
    except Exception:
        print(json.dumps({"committed": False, "error": "Import rolled back. Check input, identity, membership and schema."}))
        raise SystemExit(1) from None
