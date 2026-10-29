"""Read source report dates without rebucketing unverified source timezones."""
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import aliased
from app.db.models.fleet_fuel import FleetFuelDaily as Fuel
from app.db.models.vehicle import Vehicle
from app.db.models.customer import Customer
from app.db.models.vehicle_relationship import FleetMembership as Member
from app.db.models.dashboard_vehicle_binding import DashboardVehicleBinding as Binding
from app.services.fleet_telemetry import active_membership, fail, now


def visible_query(tenant_id, stamp, vehicle_id=None, fleet_customer_id=None):
    query = select(Fuel, Vehicle.unit_number, func.coalesce(Customer.company_name, Customer.first_name + " " + Customer.last_name).label("fleet_name")).join(
        Vehicle, Vehicle.id == Fuel.vehicle_id).join(Member, Member.id == Fuel.fleet_membership_id).join(Customer, Customer.id == Fuel.fleet_customer_id).where(
        Fuel.tenant_id == tenant_id, Fuel.deleted_at.is_(None), Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None),
        Member.tenant_id == tenant_id, Member.vehicle_id == Fuel.vehicle_id, Member.fleet_customer_id == Fuel.fleet_customer_id,
        Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None), *active_membership(stamp),
        Fuel.coverage_start >= Member.effective_from,
        or_(Member.effective_to.is_(None), Fuel.coverage_end <= Member.effective_to),
        Fuel.coverage_end <= Fuel.source_read_at, Fuel.source_read_at <= stamp,
    )
    CurrentMember, CurrentCustomer = aliased(Member), aliased(Customer)
    current_memberships = select(func.count(CurrentMember.id)).join(
        CurrentCustomer, CurrentCustomer.id == CurrentMember.fleet_customer_id
    ).where(
        CurrentMember.tenant_id == tenant_id, CurrentMember.vehicle_id == Fuel.vehicle_id,
        CurrentMember.deleted_at.is_(None), CurrentMember.effective_from <= stamp,
        or_(CurrentMember.effective_to.is_(None), CurrentMember.effective_to > stamp),
        CurrentCustomer.tenant_id == tenant_id, CurrentCustomer.deleted_at.is_(None),
    ).correlate(Fuel).scalar_subquery()
    valid_bound = select(Binding.id).where(
        current_memberships == 1,
        Binding.id == Fuel.dashboard_binding_id, Binding.tenant_id == tenant_id,
        Binding.vehicle_id == Fuel.vehicle_id, Binding.fleet_membership_id == Fuel.fleet_membership_id,
        Binding.fleet_customer_id == Fuel.fleet_customer_id, Binding.deleted_at.is_(None), Binding.revoked_at.is_(None),
        Binding.placeholder_vin == "PENDING-26", Vehicle.vin == Binding.placeholder_vin,
        Binding.source_company_id == Fuel.provider_company_id, Binding.source_company_label == Fuel.source_company_label,
        Binding.provider_vehicle_id == Fuel.provider_vehicle_id, Fuel.provider_company_id == "KT8934277",
        Fuel.source_company_label == "77 CARGO LLC", Fuel.provider_vehicle_id == "5981300", Fuel.verified_vin.is_(None),
        Fuel.source_vin_state.in_(("not_displayed", "explicitly_empty")),
        Binding.reviewed_at <= Binding.effective_from, Binding.effective_from <= Fuel.coverage_start,
        Binding.effective_from <= Fuel.source_read_at, Binding.effective_from <= stamp,
        or_(Binding.effective_to.is_(None), and_(Binding.effective_to > stamp,
            Binding.effective_to > Fuel.source_read_at, Binding.effective_to >= Fuel.coverage_end)),
    ).correlate(Fuel, Vehicle).exists()
    query = query.where(or_(and_(Fuel.dashboard_binding_id.is_(None), Fuel.verified_vin.is_not(None),
        func.upper(func.trim(Vehicle.vin)) == Fuel.verified_vin), valid_bound))
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
    items = [{**{key: getattr(row, key) for key in fields}, "vehicle_identity_basis": "reviewed_provider_binding" if row.dashboard_binding_id else "verified_vin", "vehicle_identity_binding_id": row.dashboard_binding_id, "unit_number": unit, "fleet_name": fleet} for row, unit, fleet in rows]
    return dict(items=items, total=total, limit=limit, offset=offset, start_date=start_date, end_date=end_date,
                imported_start=bounds[0], imported_end=bounds[1], coverage="partial", date_basis="source_report_date")
