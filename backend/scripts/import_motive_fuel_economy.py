"""Import explicitly observed Motive summary MPG; dry-run unless --apply is set."""

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from app.db.models.customer import Customer
from app.db.models.fleet_telemetry import FleetTelemetrySnapshot as Snapshot
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_telemetry import TelemetryCapture
from app.services import fleet_telemetry as telemetry


class SourceRow(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=120)
    provider_vehicle_id: str = Field(min_length=1, max_length=120)
    vin: str
    fuel_economy_mpg: float = Field(ge=0, le=100)
    source_read_at: datetime

    @field_validator("fuel_economy_mpg", mode="before")
    @classmethod
    def reject_bool(cls, value):
        if isinstance(value, bool):
            raise ValueError("MPG must be numeric, not boolean")
        return value

    @field_validator("source_read_at", mode="before")
    @classmethod
    def explicit_time(cls, value):
        if not isinstance(value, str):
            raise ValueError("source_read_at must be an explicit timestamp")
        return value

    @field_validator("source_read_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("source_read_at requires timezone")
        return value.astimezone(timezone.utc)


def parse_rows(document, stamp):
    if not isinstance(document, dict) or document.get("period") != "last_30_days":
        raise ValueError("Reporting period must be last_30_days")
    raw_rows = document.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("Nonempty rows required")
    rows = [SourceRow.model_validate(raw) for raw in raw_rows]
    vins, providers = set(), set()
    for row in rows:
        # Reuse the API's exact VIN and measurement rules without fabricating an observation time.
        validated = make_body(row, UUID(int=0))
        row.vin = validated.vin
        if not stamp - timedelta(days=30) <= row.source_read_at <= stamp:
            raise ValueError("source_read_at must be within the past 30 days")
        if row.vin in vins or row.provider_vehicle_id in providers:
            raise ValueError("Duplicate VIN or provider vehicle in input")
        vins.add(row.vin)
        providers.add(row.provider_vehicle_id)
    return rows


def make_body(row, fleet_customer_id):
    read_at = row.source_read_at.isoformat()
    return TelemetryCapture(
        client_request_id=uuid5(NAMESPACE_URL, f"motive-mpg:{row.vin.upper()}:{row.provider_vehicle_id}:{read_at}"),
        fleet_customer_id=fleet_customer_id,
        vin=row.vin,
        provider_vehicle_id=row.provider_vehicle_id,
        provider_vehicle_number=row.unit,
        fuel_economy_mpg=row.fuel_economy_mpg,
        fuel_economy_period="last_30_days",
        evidence_note=f"Motive summary: Average MPG / This vehicle, Last 30 days. Browser source_read_at: {read_at}.",
    )


async def prepare(db, rows, tenant_id, actor_id):
    stamp = telemetry.now()
    tenant = (await db.execute(select(Tenant).where(
        Tenant.id == tenant_id, Tenant.deleted_at.is_(None), Tenant.is_active.is_(True)
    ).with_for_update())).scalar_one_or_none()
    actor = (await db.execute(select(User).where(
        User.id == actor_id, User.tenant_id == tenant_id, User.deleted_at.is_(None), User.is_active.is_(True)
    ).with_for_update())).scalar_one_or_none()
    if tenant is None or actor is None or actor.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        raise ValueError("Active owner/admin in the specified active tenant required")
    plans = []
    for row in rows:
        vehicles = (await db.execute(select(Vehicle).where(
            Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None),
            func.upper(func.trim(Vehicle.vin)) == row.vin,
        ).with_for_update())).scalars().all()
        if len(vehicles) != 1:
            raise ValueError(f"Unit {row.unit}: expected exactly one active vehicle for VIN")
        vehicle = vehicles[0]
        members = (await db.execute(select(FleetMembership).join(Customer, Customer.id == FleetMembership.fleet_customer_id).where(
            FleetMembership.tenant_id == tenant_id, FleetMembership.vehicle_id == vehicle.id,
            Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None),
            *telemetry.active_membership(stamp),
        ).with_for_update())).scalars().all()
        if len(members) != 1 or not telemetry.within(members[0], row.source_read_at):
            raise ValueError(f"Unit {row.unit}: unique active membership covering source read required")
        plans.append((vehicle, make_body(row, members[0].fleet_customer_id)))
    return actor, plans


async def state(db, ids, tenant_id):
    # Exact database values, including existing snapshots, must survive unchanged.
    vehicles = (await db.execute(select(*Vehicle.__table__.columns).where(Vehicle.tenant_id == tenant_id, Vehicle.id.in_(ids)).order_by(Vehicle.id))).all()
    snapshots = (await db.execute(select(*Snapshot.__table__.columns).where(Snapshot.tenant_id == tenant_id, Snapshot.vehicle_id.in_(ids)).order_by(Snapshot.id))).all()
    return vehicles, {row.id: tuple(row) for row in snapshots}


async def projection(db, plans, tenant_id):
    trucks = [SimpleNamespace(id=v.id, board_membership_customer_id=b.fleet_customer_id, telemetry=None) for v, b in plans]
    await telemetry.attach(db, trucks, tenant_id)
    return {truck.id: truck.telemetry.model_dump() if truck.telemetry else {} for truck in trucks}


async def run_import(db, rows, tenant_id, actor_id, apply=False):
    """Caller owns transaction; checks complete before any commit."""
    actor, plans = await prepare(db, rows, tenant_id, actor_id)
    ids = [vehicle.id for vehicle, _ in plans]
    before_vehicles, before_snapshots = await state(db, ids, tenant_id)
    before_projection = await projection(db, plans, tenant_id)
    receipts = []
    for vehicle, request in plans:
        receipt = {"vehicle_id": str(vehicle.id), "unit": vehicle.unit_number,
                   "provider_vehicle_id": request.provider_vehicle_id,
                   "mpg": request.fuel_economy_mpg, "period": request.fuel_economy_period,
                   "request_id": str(request.client_request_id)}
        if apply:
            snapshot, created = await telemetry.capture(db, actor, vehicle.id, request)
            if snapshot.fuel_economy_mpg != request.fuel_economy_mpg or snapshot.fuel_economy_period != request.fuel_economy_period:
                raise ValueError("Saved MPG differs from requested value")
            for field in ("location_label", "lat", "lng", "speed_mph", "odometer_miles", "engine_hours", "fuel_percent", "fault_count", "observed_at"):
                if getattr(snapshot, field) is not None:
                    raise ValueError("MPG import unexpectedly includes another measurement")
            receipt.update(snapshot_id=str(snapshot.id), created=created, captured_at=telemetry.utc(snapshot.captured_at).isoformat())
        receipts.append(receipt)
    after_vehicles, after_snapshots = await state(db, ids, tenant_id)
    if before_vehicles != after_vehicles or any(after_snapshots.get(key) != value for key, value in before_snapshots.items()):
        raise ValueError("Existing vehicle or telemetry data changed; import aborted")
    after_projection = await projection(db, plans, tenant_id)
    for vehicle, _ in plans:
        old = before_projection[vehicle.id]
        new = after_projection[vehicle.id]
        for field in ("location", "speed", "odometer", "engine_hours", "fuel", "fault_count"):
            left, right = old.get(field), new.get(field)
            # Freshness may naturally cross a clock boundary during a batch.
            left = {k: v for k, v in left.items() if k != "freshness"} if left else None
            right = {k: v for k, v in right.items() if k != "freshness"} if right else None
            if left != right:
                raise ValueError("Unrelated board reading changed; import aborted")
    for receipt in receipts:
        reading = after_projection[UUID(receipt["vehicle_id"])].get("fuel_economy")
        receipt["visible"] = bool(reading and reading["snapshot_id"] == receipt.get("snapshot_id")) if apply else None
        receipt["displayed_mpg"] = reading["value"] if reading else None
    return {"mode": "apply" if apply else "dry_run", "rows": receipts,
            "unchanged": ["existing snapshots", "service mileage", "PM targets", "vehicle records"]}


async def main(args):
    from app.db.session import AsyncSessionLocal
    rows = parse_rows(json.loads(Path(args.input).read_text()), telemetry.now())
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
    result["committed"] = args.apply
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--actor-id", required=True, type=UUID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(main(args))
    except Exception as exc:
        # Never print DB URLs, driver parameters, or source payloads from exception repr.
        print(json.dumps({"committed": False, "error": type(exc).__name__, "message": "Import failed; transaction rolled back. Review input, actor, membership and deployed schema."}))
        raise SystemExit(1) from None
