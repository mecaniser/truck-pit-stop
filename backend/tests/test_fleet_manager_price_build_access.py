"""A fleet manager drives the same price-build API as the shop.

The FleetBoard price builder is a second client of the existing price-build
endpoints rather than a parallel implementation, so these tests pin the two
things that make that safe: the fleet manager reaches the endpoints for fleet
and internal work (and only those), and the pricing the engine applies to a
fleet order matches the fleet pricing rules.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import repair_orders as ro_endpoints
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.service import Service, ServicePart
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import PartsUsageCreate, PriceBuildFlatServiceRequest
from app.services.price_build_service import PriceBuildService


async def _seed(db_session, *, is_internal=True, is_fleet_work=True,
                bill_labor_at_customer_rate=False):
    tenant = Tenant(
        id=uuid4(), name="Fleet Garage", slug=f"fg-{uuid4().hex[:8]}",
        labor_rate=Decimal("100.00"), internal_labor_rate=Decimal("40.00"),
    )
    db_session.add(tenant)
    await db_session.commit()

    customer = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="House", last_name="Account",
        company_name="House Account", email=f"house-{uuid4().hex[:8]}@example.test",
        is_internal_fleet=is_internal,
    )
    vehicle = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id,
        make="Freightliner", model="Cascadia", year=2021, unit_number="T-90",
    )
    manager = User(
        id=uuid4(), tenant_id=tenant.id, email=f"fm-{uuid4().hex[:8]}@example.test",
        hashed_password="x", first_name="Fleet", last_name="Manager",
        role=UserRole.FLEET_MANAGER, is_active=True, is_verified=True,
    )
    order = RepairOrder(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id,
        vehicle_id=vehicle.id, order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.DRAFT,
        is_internal=is_internal, is_fleet_work=is_fleet_work,
        bill_labor_at_customer_rate=bill_labor_at_customer_rate,
        total_parts_cost=Decimal("0.00"), total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    inventory = Inventory(
        id=uuid4(), tenant_id=tenant.id, sku=f"SKU-{uuid4().hex[:6]}",
        name="Oil Filter", stock_quantity=50,
        cost=Decimal("10.00"), selling_price=Decimal("25.00"),
    )
    service = Service(
        id=uuid4(), tenant_id=tenant.id, name="Oil Change",
        duration_minutes=60, base_price=Decimal("0.00"),
        is_active=True, requires_vehicle=True,
    )
    db_session.add_all([customer, vehicle, manager, order, inventory, service])
    await db_session.commit()
    db_session.add(ServicePart(
        id=uuid4(), tenant_id=tenant.id, service_id=service.id,
        inventory_id=inventory.id, quantity=1,
    ))
    await db_session.commit()
    return tenant, manager, order, inventory, service


@pytest.mark.asyncio
async def test_fleet_manager_reads_price_build_summary(db_session):
    _, manager, order, _, _ = await _seed(db_session)
    summary = await ro_endpoints.get_price_build_summary(
        order_id=order.id, db=db_session, current_user=manager)
    assert summary.order_id == order.id
    assert summary.can_edit_work is True


@pytest.mark.asyncio
async def test_fleet_manager_adds_flat_service_and_parts(db_session):
    _, manager, order, inventory, service = await _seed(db_session)

    await ro_endpoints.add_price_build_flat_service(
        order_id=order.id,
        body=PriceBuildFlatServiceRequest(service_id=service.id),
        db=db_session, current_user=manager)

    await ro_endpoints.add_parts_to_repair_order(
        order_id=order.id,
        body=PartsUsageCreate(inventory_id=inventory.id, quantity=Decimal("2")),
        db=db_session, current_user=manager)

    summary = await ro_endpoints.get_price_build_summary(
        order_id=order.id, db=db_session, current_user=manager)
    assert summary.lines, "flat service line was not added"
    assert summary.parts, "part was not added"


@pytest.mark.asyncio
async def test_fleet_manager_denied_on_plain_customer_order(db_session):
    """The role alone is not enough — the order must be fleet or internal work."""
    _, manager, order, _, _ = await _seed(
        db_session, is_internal=False, is_fleet_work=False)

    with pytest.raises(HTTPException) as exc:
        await ro_endpoints.get_price_build_summary(
            order_id=order.id, db=db_session, current_user=manager)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_internal_order_prices_parts_at_cost_and_labor_at_internal_rate(db_session):
    _, manager, order, _, service = await _seed(db_session)

    await ro_endpoints.add_price_build_flat_service(
        order_id=order.id,
        body=PriceBuildFlatServiceRequest(service_id=service.id),
        db=db_session, current_user=manager)

    loaded = await PriceBuildService().load_order(db_session, order.id)
    assert loaded.labor_items[0].hourly_rate == Decimal("40.00")   # internal rate
    assert loaded.parts_usage[0].unit_price == Decimal("10.00")    # at cost


@pytest.mark.asyncio
async def test_member_truck_bills_labor_at_customer_rate_but_parts_stay_at_cost(db_session):
    """A fleet member's truck: at-cost parts, customer-rate labor."""
    _, manager, order, _, service = await _seed(
        db_session, bill_labor_at_customer_rate=True)

    await ro_endpoints.add_price_build_flat_service(
        order_id=order.id,
        body=PriceBuildFlatServiceRequest(service_id=service.id),
        db=db_session, current_user=manager)

    loaded = await PriceBuildService().load_order(db_session, order.id)
    assert loaded.labor_items[0].hourly_rate == Decimal("100.00")  # customer rate
    assert loaded.parts_usage[0].unit_price == Decimal("10.00")    # still at cost
