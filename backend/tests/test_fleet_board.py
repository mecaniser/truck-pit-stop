"""Fleet board + truck detail: status derivation, KPI stats, detail aggregation."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4
import os

import pytest

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import fleet
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.internal_fleet import ensure_internal_fleet_customer


async def _seed(db):
    tenant = Tenant(id=uuid4(), name="Board Garage", slug=f"bg-{uuid4().hex[:8]}", labor_rate=Decimal("100.00"))
    db.add(tenant)
    await db.commit()
    fc = await ensure_internal_fleet_customer(db, tenant.id)
    await db.commit()
    user = User(id=uuid4(), tenant_id=tenant.id, email=f"fm-{uuid4().hex[:8]}@x.com",
                hashed_password="x", first_name="Fleet", last_name="Mgr",
                role=UserRole.FLEET_MANAGER, is_active=True, is_verified=True)
    db.add(user)
    await db.commit()
    return tenant, fc, user


def _vehicle(tenant_id, fc_id, **kw):
    base = dict(id=uuid4(), tenant_id=tenant_id, customer_id=fc_id, make="Volvo", model="VNL",
                year=2021, mileage=100000, pm_interval_miles=25000)
    base.update(kw)
    return Vehicle(**base)


def _ro(tenant_id, fc_id, vehicle_id, status, **kw):
    base = dict(id=uuid4(), tenant_id=tenant_id, customer_id=fc_id, vehicle_id=vehicle_id,
                order_number=f"RO-{uuid4().hex[:8]}", status=status, is_internal=True,
                total_parts_cost=Decimal("0"), total_labor_cost=Decimal("0"), total_cost=Decimal("0"))
    base.update(kw)
    return RepairOrder(**base)


@pytest.mark.asyncio
async def test_board_status_derivation(db_session):
    tenant, fc, user = await _seed(db_session)
    # active: PM far out, no open RO
    v_active = _vehicle(tenant.id, fc.id, unit_number="A", mileage=100000, next_pm_miles=120000)
    # pm: overdue
    v_pm = _vehicle(tenant.id, fc.id, unit_number="P", mileage=100000, next_pm_miles=99500)
    # shop: open internal RO
    v_shop = _vehicle(tenant.id, fc.id, unit_number="S", mileage=100000, next_pm_miles=120000)
    # parts: open RO on hold for parts
    v_parts = _vehicle(tenant.id, fc.id, unit_number="R", mileage=100000, next_pm_miles=120000)
    db_session.add_all([v_active, v_pm, v_shop, v_parts])
    await db_session.commit()
    db_session.add(_ro(tenant.id, fc.id, v_shop.id, RepairOrderStatus.IN_PROGRESS))
    db_session.add(_ro(tenant.id, fc.id, v_parts.id, RepairOrderStatus.IN_PROGRESS, hold_reason="awaiting_parts"))
    await db_session.commit()

    board = await fleet.fleet_board(db=db_session, current_user=user)
    by_unit = {t.unit_number: t for t in board.trucks}
    assert by_unit["A"].status == "active"
    assert by_unit["P"].status == "pm"
    assert by_unit["S"].status == "shop"
    assert by_unit["R"].status == "parts"
    # work order surfaced for shop truck
    assert by_unit["S"].work_order is not None
    assert by_unit["S"].work_order.status == "In progress"
    assert by_unit["R"].work_order.status == "Awaiting parts"


@pytest.mark.asyncio
async def test_board_stats(db_session):
    tenant, fc, user = await _seed(db_session)
    v1 = _vehicle(tenant.id, fc.id, unit_number="1", next_pm_miles=120000)
    v2 = _vehicle(tenant.id, fc.id, unit_number="2", next_pm_miles=99000)  # overdue -> pm
    db_session.add_all([v1, v2])
    await db_session.commit()
    db_session.add(_ro(tenant.id, fc.id, v1.id, RepairOrderStatus.IN_PROGRESS))
    await db_session.commit()

    board = await fleet.fleet_board(db=db_session, current_user=user)
    assert board.stats.total == 2
    assert board.stats.shop == 1
    assert board.stats.pm == 1
    assert board.stats.open_wo == 1


@pytest.mark.asyncio
async def test_truck_detail_history_and_spend(db_session):
    tenant, fc, user = await _seed(db_session)
    v = _vehicle(tenant.id, fc.id, unit_number="H", mileage=200000, next_pm_miles=210000,
                 driver_name="Marcus Reed", driver_phone="+17045551234")
    db_session.add(v)
    await db_session.commit()
    # two completed internal ROs (one PM, one repair) + one open
    db_session.add(_ro(tenant.id, fc.id, v.id, RepairOrderStatus.COMPLETED, is_pm=True,
                       total_cost=Decimal("500.00"), mileage_out=180000, description="PM service A"))
    db_session.add(_ro(tenant.id, fc.id, v.id, RepairOrderStatus.COMPLETED, is_pm=False,
                       total_cost=Decimal("1200.00"), mileage_out=190000, description="Brake job"))
    db_session.add(_ro(tenant.id, fc.id, v.id, RepairOrderStatus.IN_PROGRESS, description="Open"))
    await db_session.commit()

    detail = await fleet.truck_detail(vehicle_id=v.id, db=db_session, current_user=user)
    assert detail.driver_phone == "+17045551234"
    assert detail.lifetime_spend == 1700.0
    kinds = sorted(h.kind for h in detail.history)
    assert kinds == ["PM", "Repair"]
    assert detail.truck.work_order is not None  # the open one


@pytest.mark.asyncio
async def test_truck_detail_does_not_rescan_the_fleet_for_nearby_units(db_session, monkeypatch):
    """Nearby units are derived from the board payload already in the browser."""
    tenant, fc, user = await _seed(db_session)
    vehicle = _vehicle(
        tenant.id,
        fc.id,
        unit_number="NEAR",
        next_pm_miles=120000,
        last_lat=35.11,
        last_lng=-80.72,
    )
    db_session.add(vehicle)
    await db_session.commit()

    async def fleet_scan_should_not_run(*_args, **_kwargs):
        raise AssertionError("truck detail must not scan the full fleet")

    monkeypatch.setattr(fleet, "_fleet_vehicles", fleet_scan_should_not_run)
    detail = await fleet.truck_detail(vehicle_id=vehicle.id, db=db_session, current_user=user)

    assert detail.nearest == []


@pytest.mark.asyncio
async def test_board_truck_from_legacy_internal_account_can_open_detail(db_session):
    """Board and detail must agree when a tenant has more than one fleet account."""
    tenant, _fleet_customer, user = await _seed(db_session)
    legacy_fleet_customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Legacy",
        last_name="Fleet",
        email=f"legacy-fleet-{uuid4().hex[:8]}@example.com",
        is_internal_fleet=True,
    )
    vehicle = _vehicle(tenant.id, legacy_fleet_customer.id, unit_number="LEGACY", next_pm_miles=120000)
    db_session.add_all([legacy_fleet_customer, vehicle])
    await db_session.commit()

    board = await fleet.fleet_board(db=db_session, current_user=user)
    assert vehicle.id in {truck.id for truck in board.trucks}

    detail = await fleet.truck_detail(vehicle_id=vehicle.id, db=db_session, current_user=user)
    assert detail.truck.id == vehicle.id


@pytest.mark.asyncio
async def test_schedule_pm_and_new_work_order(db_session):
    tenant, fc, user = await _seed(db_session)
    v = _vehicle(tenant.id, fc.id, unit_number="W", next_pm_miles=120000)
    db_session.add(v)
    await db_session.commit()

    from app.schemas.fleet import SchedulePMRequest
    res = await fleet.schedule_pm(vehicle_id=v.id, body=SchedulePMRequest(create_work_order=True),
                                  db=db_session, current_user=user)
    assert res.work_order is not None
    # the spawned PM work order is surfaced on its own field, flagged and in draft
    assert res.pm_work_order is not None
    assert res.pm_work_order.is_pm is True
    assert res.pm_work_order.raw_status == "draft"
    # the spawned RO is an internal PM order
    ros = (await db_session.execute(
        __import__("sqlalchemy").select(RepairOrder).where(RepairOrder.vehicle_id == v.id)
    )).scalars().all()
    assert len(ros) == 1 and ros[0].is_internal and ros[0].is_pm

    # A non-PM work order must not populate pm_work_order.
    res2 = await fleet.new_work_order(vehicle_id=v.id, db=db_session, current_user=user)
    assert res2.work_order is not None
    assert res2.pm_work_order is not None  # the PM WO still exists
    assert res2.pm_work_order.repair_order_id == res.pm_work_order.repair_order_id


@pytest.mark.asyncio
async def test_pm_services_default_package_and_seeding(db_session):
    """Setting a truck's default PM package, then scheduling a PM with a work
    order, copies the services onto the RO, rolls their names into the
    description, and seeds owner-facing labor + parts cost lines at internal
    cost."""
    import sqlalchemy as sa
    from app.db.models.service import Service, ServicePart
    from app.db.models.inventory import Inventory, PartsUsage
    from app.db.models.labor import Labor
    from app.schemas.fleet import SchedulePMRequest, PMServicesUpdate

    tenant, fc, user = await _seed(db_session)
    # Internal labor rate drives seeded labor cost.
    tenant.internal_labor_rate = Decimal("50.00")
    await db_session.commit()

    v = _vehicle(tenant.id, fc.id, unit_number="SVC", next_pm_miles=120000)
    part = Inventory(id=uuid4(), tenant_id=tenant.id, sku="OIL-1", name="Oil filter",
                     stock_quantity=10, cost=Decimal("8.00"), selling_price=Decimal("20.00"))
    svc = Service(id=uuid4(), tenant_id=tenant.id, name="Oil change", duration_minutes=60)
    db_session.add_all([v, part, svc])
    await db_session.commit()
    db_session.add(ServicePart(id=uuid4(), tenant_id=tenant.id, service_id=svc.id,
                               inventory_id=part.id, quantity=2))
    await db_session.commit()

    # Set the truck's default PM package.
    entries = await fleet.set_truck_pm_services(
        vehicle_id=v.id, body=PMServicesUpdate(service_ids=[svc.id]),
        db=db_session, current_user=user)
    assert [e.name for e in entries] == ["Oil change"]

    # Scheduling a PM + work order (no explicit services) uses the default.
    res = await fleet.schedule_pm(
        vehicle_id=v.id, body=SchedulePMRequest(create_work_order=True),
        db=db_session, current_user=user)
    ro_id = res.pm_work_order.repair_order_id

    ro = (await db_session.execute(sa.select(RepairOrder).where(RepairOrder.id == ro_id))).scalar_one()
    assert "Oil change" in (ro.description or "")

    # Owner-facing labor: 1h × $50 = $50, tagged to the source service.
    labor = (await db_session.execute(sa.select(Labor).where(Labor.repair_order_id == ro_id))).scalars().all()
    assert len(labor) == 1
    assert labor[0].source_service_id == svc.id
    assert Decimal(str(labor[0].total_cost)) == Decimal("50.00")

    # Owner-facing parts: 2 × cost $8 = $16, at internal cost (not selling price).
    parts = (await db_session.execute(sa.select(PartsUsage).where(PartsUsage.repair_order_id == ro_id))).scalars().all()
    assert len(parts) == 1
    assert parts[0].quantity == 2
    assert Decimal(str(parts[0].unit_price)) == Decimal("8.00")
    assert Decimal(str(parts[0].total_price)) == Decimal("16.00")

    # RO totals reflect the seeded lines.
    ro = (await db_session.execute(sa.select(RepairOrder).where(RepairOrder.id == ro_id))).scalar_one()
    assert Decimal(str(ro.total_cost)) == Decimal("66.00")


@pytest.mark.asyncio
async def test_set_wo_pm_services_on_existing_draft(db_session):
    """A PM work order created without services (the screenshot case) can have
    services added afterward via the work-order endpoint, which seeds the cost
    lines. Re-selecting replaces the previously seeded lines idempotently."""
    import sqlalchemy as sa
    from app.db.models.service import Service
    from app.db.models.labor import Labor
    from app.schemas.fleet import SchedulePMRequest, PMServicesUpdate

    tenant, fc, user = await _seed(db_session)
    tenant.internal_labor_rate = Decimal("40.00")
    await db_session.commit()

    v = _vehicle(tenant.id, fc.id, unit_number="DRF", next_pm_miles=120000)
    s1 = Service(id=uuid4(), tenant_id=tenant.id, name="Brake check", duration_minutes=30)
    s2 = Service(id=uuid4(), tenant_id=tenant.id, name="Air filter", duration_minutes=90)
    db_session.add_all([v, s1, s2])
    await db_session.commit()

    # PM work order created with NO services (empty default package).
    res = await fleet.schedule_pm(
        vehicle_id=v.id, body=SchedulePMRequest(create_work_order=True),
        db=db_session, current_user=user)
    ro_id = res.pm_work_order.repair_order_id
    assert res.pm_work_order.raw_status == "draft"
    labor0 = (await db_session.execute(sa.select(Labor).where(Labor.repair_order_id == ro_id))).scalars().all()
    assert labor0 == []  # nothing seeded yet

    # Add both services via the work-order endpoint → seeds 0.5h + 1.5h = 2h × $40.
    entries = await fleet.set_wo_pm_services(
        ro_id=ro_id, body=PMServicesUpdate(service_ids=[s1.id, s2.id]),
        db=db_session, current_user=user)
    assert [e.name for e in entries] == ["Brake check", "Air filter"]
    ro = (await db_session.execute(sa.select(RepairOrder).where(RepairOrder.id == ro_id))).scalar_one()
    assert Decimal(str(ro.total_labor_cost)) == Decimal("80.00")

    # Re-select just one service → old seeded lines are replaced, not duplicated.
    await fleet.set_wo_pm_services(
        ro_id=ro_id, body=PMServicesUpdate(service_ids=[s1.id]),
        db=db_session, current_user=user)
    labor = (await db_session.execute(sa.select(Labor).where(Labor.repair_order_id == ro_id))).scalars().all()
    assert len(labor) == 1  # only Brake check remains
    ro = (await db_session.execute(sa.select(RepairOrder).where(RepairOrder.id == ro_id))).scalar_one()
    assert Decimal(str(ro.total_labor_cost)) == Decimal("20.00")  # 0.5h × $40


@pytest.mark.asyncio
async def test_pm_service_catalog_only_pm_category(db_session):
    """The PM catalog endpoint returns only services in a PM-flagged category
    (is_pm) — not brakes, tires, or uncategorized services. The category name is
    irrelevant; only the flag matters."""
    from app.db.models.service import Service, ServiceCategory

    tenant, fc, user = await _seed(db_session)
    # Deliberately NOT named "PM Services" — the flag is what counts.
    pm_cat = ServiceCategory(id=uuid4(), tenant_id=tenant.id, name="Scheduled Maintenance", is_pm=True)
    brake_cat = ServiceCategory(id=uuid4(), tenant_id=tenant.id, name="Brakes", is_pm=False)
    db_session.add_all([pm_cat, brake_cat])
    await db_session.commit()
    db_session.add_all([
        Service(id=uuid4(), tenant_id=tenant.id, name="PM Level A", category_id=pm_cat.id, duration_minutes=60),
        Service(id=uuid4(), tenant_id=tenant.id, name="Oil Change Only", category_id=pm_cat.id, duration_minutes=30),
        Service(id=uuid4(), tenant_id=tenant.id, name="Brake Job", category_id=brake_cat.id, duration_minutes=120),
        Service(id=uuid4(), tenant_id=tenant.id, name="Uncategorized", category_id=None, duration_minutes=45),
        # Inactive PM service must be excluded.
        Service(id=uuid4(), tenant_id=tenant.id, name="Old PM", category_id=pm_cat.id, is_active=False),
    ])
    await db_session.commit()

    catalog = await fleet.pm_service_catalog(db=db_session, current_user=user)
    names = {e.name for e in catalog}
    assert names == {"PM Level A", "Oil Change Only"}


@pytest.mark.asyncio
async def test_delete_pm_work_order_with_services(db_session):
    """A PM work order with attached services (and seeded labor/parts) can be
    deleted — the repair_order_pm_services rows don't block the FK."""
    import sqlalchemy as sa
    from app.db.models.service import Service
    from app.db.models.fleet import RepairOrderPMService
    from app.api.v1.endpoints.repair_orders import delete_repair_order
    from app.schemas.fleet import SchedulePMRequest

    tenant, fc, user = await _seed(db_session)
    v = _vehicle(tenant.id, fc.id, unit_number="DEL", next_pm_miles=120000)
    svc = Service(id=uuid4(), tenant_id=tenant.id, name="Oil change", duration_minutes=60)
    db_session.add_all([v, svc])
    await db_session.commit()

    res = await fleet.schedule_pm(
        vehicle_id=v.id,
        body=SchedulePMRequest(create_work_order=True, service_ids=[svc.id]),
        db=db_session, current_user=user)
    ro_id = res.pm_work_order.repair_order_id
    # Sanity: the PM service link row exists (this is what used to block delete).
    links = (await db_session.execute(
        sa.select(RepairOrderPMService).where(RepairOrderPMService.repair_order_id == ro_id)
    )).scalars().all()
    assert len(links) == 1

    # Delete must succeed (no FK error) — it's a soft delete, so the RO and
    # its PM service links survive, just hidden.
    await delete_repair_order(order_id=ro_id, db=db_session, current_user=user)

    stored = (await db_session.execute(
        sa.select(RepairOrder).where(RepairOrder.id == ro_id)
    )).scalar_one()
    assert stored.deleted_at is not None
    assert (await db_session.execute(
        sa.select(RepairOrderPMService).where(RepairOrderPMService.repair_order_id == ro_id)
    )).scalars().all() != []


@pytest.mark.asyncio
async def test_ro_detail_includes_pm_services(db_session):
    """The repair-order detail payload surfaces the PM services (scope) and the
    seeded parts/labor, so the owner's dashboard can display an in-progress PM."""
    from app.db.models.service import Service, ServicePart
    from app.db.models.inventory import Inventory
    from app.api.v1.endpoints.repair_orders import get_repair_order_detail
    from app.schemas.fleet import SchedulePMRequest

    tenant, fc, user = await _seed(db_session)
    tenant.internal_labor_rate = Decimal("50.00")
    await db_session.commit()

    v = _vehicle(tenant.id, fc.id, unit_number="DET", next_pm_miles=120000)
    part = Inventory(id=uuid4(), tenant_id=tenant.id, sku="OIL", name="Oil filter",
                     stock_quantity=5, cost=Decimal("8.00"), selling_price=Decimal("20.00"))
    svc = Service(id=uuid4(), tenant_id=tenant.id, name="PM Level A", duration_minutes=60)
    db_session.add_all([v, part, svc])
    await db_session.commit()
    db_session.add(ServicePart(id=uuid4(), tenant_id=tenant.id, service_id=svc.id,
                               inventory_id=part.id, quantity=2))
    await db_session.commit()

    res = await fleet.schedule_pm(
        vehicle_id=v.id,
        body=SchedulePMRequest(create_work_order=True, service_ids=[svc.id]),
        db=db_session, current_user=user)
    ro_id = res.pm_work_order.repair_order_id

    detail = await get_repair_order_detail(order_id=ro_id, db=db_session, current_user=user)
    assert detail.is_pm is True
    assert detail.customer_company_name == fc.company_name
    assert detail.vehicle_make == "Volvo"
    assert detail.vehicle_model == "VNL"
    assert detail.vehicle_unit_number == "DET"
    assert [s.name for s in detail.pm_services] == ["PM Level A"]
    # Seeded parts & labor are on the payload for display.
    assert any(p.inventory_name == "Oil filter" and p.quantity == 2 for p in detail.parts_usage)
    assert any(Decimal(str(l.total_cost)) == Decimal("50.00") for l in detail.labor_items)
