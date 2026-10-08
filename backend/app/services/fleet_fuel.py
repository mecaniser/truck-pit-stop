"""Read source report dates without rebucketing unverified source timezones."""
from sqlalchemy import select, func, or_
from app.db.models.fleet_fuel import FleetFuelDaily as Fuel
from app.db.models.vehicle import Vehicle
from app.db.models.customer import Customer
from app.db.models.vehicle_relationship import FleetMembership as Member
from app.services.fleet_telemetry import active_membership, fail, now


def visible_query(tenant_id, stamp, vehicle_id=None, fleet_customer_id=None):
    query = select(Fuel, Vehicle.unit_number, func.coalesce(Customer.company_name, Customer.first_name + " " + Customer.last_name).label("fleet_name")).join(
        Vehicle, Vehicle.id == Fuel.vehicle_id).join(Member, Member.id == Fuel.fleet_membership_id).join(Customer, Customer.id == Fuel.fleet_customer_id).where(
        Fuel.tenant_id == tenant_id, Fuel.deleted_at.is_(None), Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None),
        Member.tenant_id == tenant_id, Member.vehicle_id == Fuel.vehicle_id, Member.fleet_customer_id == Fuel.fleet_customer_id,
        Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None), *active_membership(stamp),
        func.upper(func.trim(Vehicle.vin)) == Fuel.verified_vin,
        Fuel.coverage_start >= Member.effective_from,
        or_(Member.effective_to.is_(None), Fuel.coverage_end <= Member.effective_to),
        Fuel.coverage_end <= Fuel.source_read_at, Fuel.source_read_at <= stamp,
    )
    if vehicle_id:
        query = query.where(Fuel.vehicle_id == vehicle_id)
    if fleet_customer_id:
        query = query.where(Fuel.fleet_customer_id == fleet_customer_id)
    return query


async def list_fuel_daily(db, tenant_id, start_date, end_date, vehicle_id=None, fleet_customer_id=None, limit=50, offset=0):
    if end_date < start_date or (end_date - start_date).days >= 31 or not 1 <= limit <= 100 or offset < 0:
        fail(422, "invalid_date_range")
    stamp = now()
    if vehicle_id or fleet_customer_id:
        accessible = select(Member.id).join(Vehicle, Vehicle.id == Member.vehicle_id).join(Customer, Customer.id == Member.fleet_customer_id).where(
            Member.tenant_id == tenant_id, Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None),
            Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None), *active_membership(stamp))
        if vehicle_id:
            accessible = accessible.where(Member.vehicle_id == vehicle_id)
        if fleet_customer_id:
            accessible = accessible.where(Member.fleet_customer_id == fleet_customer_id)
        if (await db.execute(accessible.limit(1))).scalar_one_or_none() is None:
            fail(404, "not_found")
    base = visible_query(tenant_id, stamp, vehicle_id, fleet_customer_id)
    history = base.subquery()
    bounds = (await db.execute(select(func.min(history.c.report_date), func.max(history.c.report_date)))).one()
    query = base.where(Fuel.report_date >= start_date, Fuel.report_date <= end_date)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(Fuel.report_date, Fuel.id).limit(limit).offset(offset))).all()
    fields = ("id", "vehicle_id", "fleet_customer_id", "report_date", "source", "source_timezone", "timezone_status",
              "driving_fuel_gallons", "idling_fuel_gallons", "reported_total_fuel_gallons", "source_distance_miles",
              "source_driving_seconds", "source_idling_seconds", "source_read_at", "captured_at")
    items = [{**{key: getattr(row, key) for key in fields}, "unit_number": unit, "fleet_name": fleet} for row, unit, fleet in rows]
    return dict(items=items, total=total, limit=limit, offset=offset, start_date=start_date, end_date=end_date,
                imported_start=bounds[0], imported_end=bounds[1], coverage="partial", date_basis="source_report_date")
