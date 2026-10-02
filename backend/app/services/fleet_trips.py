"""Tenant- and membership-scoped imported trip history."""
import math
from app.schemas.fleet_trip import TripMetrics
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select, func, or_, and_, cast, Integer
from app.db.models.fleet_trip import FleetTrip as Trip
from app.db.models.vehicle import Vehicle
from app.db.models.customer import Customer
from app.db.models.vehicle_relationship import FleetMembership as Member
from app.services.fleet_telemetry import active_membership, fail, now


def computed_metrics(raw, distance_miles):
    if raw is None:
        return None
    metrics = TripMetrics.model_validate(raw)
    result = metrics.model_dump(mode="json")
    actual = metrics.fuel_used_gallons
    baseline = metrics.estimate_baseline_mpg
    trip_mpg = distance_miles / actual if actual is not None and actual > 0 else None
    estimate = distance_miles / baseline if actual is None and baseline is not None else None
    result["trip_mpg"] = trip_mpg if trip_mpg is not None and math.isfinite(trip_mpg) else None
    result["estimated_fuel_gallons"] = estimate if estimate is not None and math.isfinite(estimate) else None
    return result


def date_window(start_date, end_date, zone):
    if end_date < start_date or (end_date - start_date).days >= 31:
        fail(422, "invalid_date_range")
    try:
        tz = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        fail(422, "invalid_timezone")
    try:
        return (datetime.combine(start_date, time.min, tz).astimezone(timezone.utc),
                datetime.combine(end_date + timedelta(days=1), time.min, tz).astimezone(timezone.utc))
    except (OverflowError, ValueError):
        fail(422, "invalid_date_range")


def visible_query(tenant_id, start, end, stamp, vehicle_id=None, fleet_customer_id=None, dialect="postgresql"):
    if dialect == "sqlite":
        source_covers_minute = cast(func.strftime("%s", Trip.source_read_at), Integer) - cast(func.strftime("%s", Trip.ended_at), Integer) >= 60
        covers_minute = cast(func.strftime("%s", Member.effective_to), Integer) - cast(func.strftime("%s", Trip.ended_at), Integer) >= 60
    else:
        source_covers_minute = Trip.ended_at + timedelta(seconds=60) <= Trip.source_read_at
        covers_minute = Trip.ended_at + timedelta(seconds=60) <= Member.effective_to
    query = select(Trip, Vehicle.unit_number, func.coalesce(Customer.company_name, Customer.first_name + " " + Customer.last_name).label("fleet_name")).join(
        Vehicle, Vehicle.id == Trip.vehicle_id
    ).join(Member, Member.id == Trip.fleet_membership_id).join(
        Customer, Customer.id == Trip.fleet_customer_id
    ).where(
        Trip.tenant_id == tenant_id, Trip.deleted_at.is_(None),
        Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None),
        Member.tenant_id == tenant_id, Member.vehicle_id == Trip.vehicle_id,
        Member.fleet_customer_id == Trip.fleet_customer_id,
        Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None),
        *active_membership(stamp),
        Trip.started_at >= Member.effective_from,
        or_(Member.effective_to.is_(None), and_(Trip.timestamp_precision == "second", Trip.ended_at < Member.effective_to), and_(Trip.timestamp_precision == "minute", covers_minute)),
        Trip.started_at >= start, Trip.started_at < end,
        or_(and_(Trip.timestamp_precision == "second", Trip.ended_at <= Trip.source_read_at), and_(Trip.timestamp_precision == "minute", source_covers_minute)),
        or_(and_(Trip.timestamp_precision == "second", Trip.ended_at <= stamp), and_(Trip.timestamp_precision == "minute", Trip.ended_at <= stamp - timedelta(seconds=60))),
    )
    if vehicle_id:
        query = query.where(Trip.vehicle_id == vehicle_id)
    if fleet_customer_id:
        query = query.where(Trip.fleet_customer_id == fleet_customer_id)
    return query


async def list_trips(db, tenant_id, start_date, end_date, zone, vehicle_id=None, fleet_customer_id=None, limit=50, offset=0):
    start, end = date_window(start_date, end_date, zone)
    if vehicle_id or fleet_customer_id:
        accessible = select(Member.id).join(Vehicle, Vehicle.id == Member.vehicle_id).join(Customer, Customer.id == Member.fleet_customer_id).where(
            Member.tenant_id == tenant_id, Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None),
            Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None), *active_membership(now()))
        if vehicle_id:
            accessible = accessible.where(Member.vehicle_id == vehicle_id)
        if fleet_customer_id:
            accessible = accessible.where(Member.fleet_customer_id == fleet_customer_id)
        if (await db.execute(accessible.limit(1))).scalar_one_or_none() is None:
            fail(404, "not_found")
    query = visible_query(tenant_id, start, end, now(), vehicle_id, fleet_customer_id, db.bind.dialect.name)
    selected = query.subquery()
    totals = (await db.execute(select(func.count(), func.count(func.distinct(selected.c.vehicle_id)), func.coalesce(func.sum(selected.c.distance_miles), 0), func.coalesce(func.sum(selected.c.driving_seconds), 0)).select_from(selected))).one()
    rows = (await db.execute(query.order_by(Trip.started_at.desc(), Trip.id.desc()).limit(limit).offset(offset))).all()
    items = []
    for trip, unit, fleet in rows:
        items.append({**{key: getattr(trip, key) for key in (
            "id", "vehicle_id", "fleet_customer_id", "started_at", "ended_at", "origin_label", "destination_label", "distance_miles", "driving_seconds", "stops", "captured_at", "source", "timestamp_precision"
        )}, "unit_number": unit, "fleet_name": fleet, "metrics": computed_metrics(trip.metrics, trip.distance_miles)})
    return dict(items=items, summary=dict(trip_count=totals[0], truck_count=totals[1], coverage="partial", distance_miles=totals[2], driving_seconds=totals[3]), total=totals[0], limit=limit, offset=offset, timezone=zone, start_date=start_date, end_date=end_date)
