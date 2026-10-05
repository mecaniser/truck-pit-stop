"""Append verified source daily fuel. Dry run by default; never change trip metrics."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID
from sqlalchemy import select, func
from app.db.models.fleet_fuel import FleetFuelDaily
from app.db.models.fleet_trip import FleetTrip
from app.db.models.vehicle import Vehicle
from app.db.models.customer import Customer
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_fuel import FuelDailyImport
from app.services.fleet_telemetry import active_membership, now, within
from scripts.import_motive_trips import authorize, aware


def parse_rows(document, stamp):
    if not isinstance(document, dict) or set(document) != {"rows"} or not isinstance(document["rows"], list) or not 1 <= len(document["rows"]) <= 1000:
        raise ValueError("Expected 1 to 1000 fuel rows")
    rows = [FuelDailyImport.model_validate(row) for row in document["rows"]]
    keys, mapping, reverse = set(), {}, {}
    for row in rows:
        key = (row.provider_company_id, row.provider_vehicle_id, row.report_date)
        if key in keys or row.source_read_at > stamp or row.membership_window()[1] > row.source_read_at:
            raise ValueError("Duplicate, future or incomplete fuel date")
        identity = (row.provider_company_id, row.provider_vehicle_id)
        if mapping.setdefault(identity, row.vin) != row.vin or reverse.setdefault((row.provider_company_id, row.vin), row.provider_vehicle_id) != row.provider_vehicle_id:
            raise ValueError("Conflicting provider identity")
        keys.add(key)
    return rows


def digest(row):
    payload = row.model_dump(mode="json", exclude={"source_read_at", "source_receipt_sha256", "identity_receipt_sha256"})
    # Normalize decimals so JSON 1, 1.0 and 1.000 have identical semantics.
    for key, value in row.model_dump().items():
        if key.endswith("gallons") or key == "source_distance_miles":
            payload[key] = format(value.normalize(), 'f') if value is not None else None
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def resolve_identity(db, row, tenant_id, stamp):
    vehicles = (await db.execute(select(Vehicle).where(Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None), func.upper(func.trim(Vehicle.vin)) == row.vin).with_for_update())).scalars().all()
    if len(vehicles) != 1:
        raise ValueError("VIN must match exactly one active truck")
    vehicle = vehicles[0]
    members = (await db.execute(select(FleetMembership).join(Customer, Customer.id == FleetMembership.fleet_customer_id).where(
        FleetMembership.tenant_id == tenant_id, FleetMembership.vehicle_id == vehicle.id,
        Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None), *active_membership(stamp)).with_for_update())).scalars().all()
    start, end = row.membership_window()
    if len(members) != 1 or not within(members[0], start) or not within(members[0], row.source_read_at):
        raise ValueError("Unique current membership covering source date required")
    member = members[0]
    if member.effective_to and end > aware(member.effective_to):
        raise ValueError("Membership does not cover source date")
    # Existing verified trip/provider bindings are additional identity evidence.
    trips = (await db.execute(select(FleetTrip).where(FleetTrip.tenant_id == tenant_id, FleetTrip.provider_vehicle_id == row.provider_vehicle_id))).scalars().all()
    if any(trip.verified_vin != row.vin or trip.vehicle_id != vehicle.id for trip in trips):
        raise ValueError("Provider identity conflicts with existing trip history")
    bindings = (await db.execute(select(FleetFuelDaily).where(FleetFuelDaily.tenant_id == tenant_id, FleetFuelDaily.provider_company_id == row.provider_company_id,
        ((FleetFuelDaily.provider_vehicle_id == row.provider_vehicle_id) | (FleetFuelDaily.verified_vin == row.vin))))).scalars().all()
    if any(fuel.verified_vin != row.vin or fuel.provider_vehicle_id != row.provider_vehicle_id or fuel.vehicle_id != vehicle.id for fuel in bindings):
        raise ValueError("Provider identity conflicts with fuel history")
    return vehicle, member


async def run_import(db, rows, tenant_id, actor_id, apply=False):
    stamp = now()
    await authorize(db, tenant_id, actor_id)
    rows = parse_rows({"rows": [row.model_dump(mode="json") for row in rows]}, stamp)
    plans = []
    for row in rows:
        vehicle, member = await resolve_identity(db, row, tenant_id, stamp)
        existing = (await db.execute(select(FleetFuelDaily).where(FleetFuelDaily.tenant_id == tenant_id,
            FleetFuelDaily.provider_company_id == row.provider_company_id, FleetFuelDaily.provider_vehicle_id == row.provider_vehicle_id,
            FleetFuelDaily.report_date == row.report_date))).scalar_one_or_none()
        checksum = digest(row)
        if existing and (existing.deleted_at or existing.request_digest != checksum or existing.vehicle_id != vehicle.id or existing.fleet_membership_id != member.id):
            raise ValueError("Conflicting immutable fuel record")
        plans.append((row, vehicle, member, existing, checksum))
    receipts = []
    for row, vehicle, member, existing, checksum in plans:
        fuel = existing
        if apply and fuel is None:
            start, end = row.membership_window()
            fuel = FleetFuelDaily(**row.model_dump(exclude={"vin", "unit"}), provider_unit=row.unit,
                tenant_id=tenant_id, vehicle_id=vehicle.id, fleet_customer_id=member.fleet_customer_id, fleet_membership_id=member.id,
                verified_vin=row.vin, request_digest=checksum, source="motive_vehicle_fuel_performance", coverage_start=start, coverage_end=end,
                captured_at=stamp, captured_by_user_id=actor_id)
            db.add(fuel)
            await db.flush()
        receipts.append(dict(vehicle_id=str(vehicle.id), report_date=row.report_date.isoformat(), fuel_id=str(fuel.id) if fuel else None,
            action="unchanged" if existing else "created" if apply else "would_create"))
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
        print(json.dumps({"committed": False, "error": "Import rolled back. Check source evidence, identity, membership and schema."}))
        raise SystemExit(1) from None
