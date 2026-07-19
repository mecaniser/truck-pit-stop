"""Fractional part quantity for fluids (oil, coolant, DEF).

Fluids are dispensed in fractional amounts (e.g. 1.25 gal), unlike discrete
parts (filters, belts) which are always whole units. quantity on PartsUsage
is Numeric(6,2); Inventory.unit_type marks which parts are fluids so the
Price Builder can offer quarter-increment quantities. Stock (stock_quantity)
still tracks whole packages/jugs on hand, rounded up per package consumed.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import select

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints.repair_orders import (
    add_parts_to_repair_order,
    get_repair_order_detail,
    update_parts_quantity,
    remove_parts_from_repair_order,
    _packages_consumed,
)
from app.schemas.repair_order import PartsUsageCreate, PartsUsageUpdate
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.service import Service, ServicePart
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.price_build_service import PriceBuildService


async def _seed(db_session, *, stock_quantity: int = 10, unit_type: str = "gallon"):
    tenant = Tenant(
        id=uuid4(),
        name="Fluid Test Garage",
        slug=f"fluid-{uuid4().hex[:8]}",
        labor_rate=Decimal("100.00"),
        internal_labor_rate=Decimal("40.00"),
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Jane",
        last_name="Doe",
        email=f"cust-{uuid4().hex[:8]}@example.com",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Peterbilt",
        model="579",
        year=2021,
    )
    staff_user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"staff-{uuid4().hex[:8]}@example.com",
        hashed_password="hashed-password",
        first_name="Shop",
        last_name="Admin",
        role=UserRole.GARAGE_ADMIN,
        is_active=True,
        is_verified=True,
    )
    order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.DRAFT,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    inv = Inventory(
        id=uuid4(),
        tenant_id=tenant.id,
        sku=f"OIL-{uuid4().hex[:6]}",
        name="Diesel Engine Oil 15W-40 (5 Gal)",
        stock_quantity=stock_quantity,
        cost=Decimal("15.00"),
        selling_price=Decimal("24.00"),
        unit_type=unit_type,
    )
    db_session.add_all([tenant, customer, vehicle, staff_user, order, inv])
    await db_session.commit()
    return staff_user, order, inv


def test_packages_consumed_rounds_up_fractional_quantity():
    assert _packages_consumed(Decimal("0.25")) == 1
    assert _packages_consumed(Decimal("1.00")) == 1
    assert _packages_consumed(Decimal("1.25")) == 2
    assert _packages_consumed(Decimal("5.00")) == 5
    assert _packages_consumed(Decimal("0")) == 0


@pytest.mark.asyncio
async def test_add_part_accepts_fractional_gallon_quantity(db_session):
    user, order, inv = await _seed(db_session, stock_quantity=10)

    body = PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("1.25"))
    resp = await add_parts_to_repair_order(order.id, body, db_session, user)

    assert resp.quantity == Decimal("1.25")
    assert resp.unit_type == "gallon"
    assert resp.total_price == Decimal("24.00") * Decimal("1.25")

    await db_session.refresh(inv)
    # 1.25 gal rounds up to 2 packages consumed (any quantity over 1 whole
    # unit draws from a second package under the round-up-to-whole-packages rule).
    assert inv.stock_quantity == 8


@pytest.mark.asyncio
async def test_add_part_can_attach_to_service_operation(db_session):
    user, order, inv = await _seed(db_session, stock_quantity=10)
    service = Service(
        id=uuid4(),
        tenant_id=order.tenant_id,
        name="Battery Test & Replacement",
        duration_minutes=60,
        base_price=Decimal("0.00"),
        is_active=True,
        requires_vehicle=True,
    )
    db_session.add(service)
    await db_session.commit()

    body = PartsUsageCreate(
        inventory_id=inv.id,
        quantity=Decimal("1.00"),
        source_service_id=service.id,
    )
    resp = await add_parts_to_repair_order(order.id, body, db_session, user)

    assert resp.source_service_id == service.id
    assert order.parts_usage[0].source_service_id == service.id


@pytest.mark.asyncio
async def test_add_part_can_attach_to_free_form_operation_line(db_session):
    """A free-form repair operation (no source_service_id) can still take parts,
    linked via source_line_id."""
    from app.db.models.labor import Labor, LaborLineType

    user, order, inv = await _seed(db_session, stock_quantity=10)
    line = Labor(
        id=uuid4(),
        tenant_id=order.tenant_id,
        repair_order_id=order.id,
        description="Replace Trailer Tires",
        hours=Decimal("0.50"),
        hourly_rate=Decimal("100.00"),
        total_cost=Decimal("50.00"),
        line_type=LaborLineType.REPAIR_OPERATION,
        source_service_id=None,
    )
    db_session.add(line)
    await db_session.commit()

    body = PartsUsageCreate(
        inventory_id=inv.id,
        quantity=Decimal("2"),
        source_line_id=line.id,
    )
    resp = await add_parts_to_repair_order(order.id, body, db_session, user)

    assert resp.source_line_id == line.id
    assert resp.source_service_id is None
    assert order.parts_usage[0].source_line_id == line.id


@pytest.mark.asyncio
async def test_add_part_rejects_source_line_id_from_another_order(db_session):
    """source_line_id must reference a labor line on this order."""
    user, order, inv = await _seed(db_session, stock_quantity=10)

    body = PartsUsageCreate(
        inventory_id=inv.id,
        quantity=Decimal("1"),
        source_line_id=uuid4(),  # not a real line on this order
    )
    with pytest.raises(HTTPException) as exc_info:
        await add_parts_to_repair_order(order.id, body, db_session, user)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_deleting_line_orphans_its_parts_via_set_null(db_session):
    """Deleting a labor line SET NULLs its parts' source_line_id (the part
    survives as a standalone/orphan part rather than being force-deleted)."""
    from app.db.models.labor import Labor, LaborLineType
    from app.services.price_build_service import PriceBuildService

    user, order, inv = await _seed(db_session, stock_quantity=10)
    line = Labor(
        id=uuid4(),
        tenant_id=order.tenant_id,
        repair_order_id=order.id,
        description="Replace Trailer Tires",
        hours=Decimal("0.50"),
        hourly_rate=Decimal("100.00"),
        total_cost=Decimal("50.00"),
        line_type=LaborLineType.REPAIR_OPERATION,
        source_service_id=None,
    )
    db_session.add(line)
    await db_session.commit()

    body = PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("1"), source_line_id=line.id)
    resp = await add_parts_to_repair_order(order.id, body, db_session, user)

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.remove_line(db_session, loaded, line_id=line.id)

    refreshed = await db_session.get(PartsUsage, resp.id)
    assert refreshed is not None  # part not deleted
    assert refreshed.source_line_id is None  # link cleared by ON DELETE SET NULL


@pytest.mark.asyncio
async def test_add_part_rejects_zero_or_negative_quantity(db_session):
    user, order, inv = await _seed(db_session)

    for bad_qty in (Decimal("0"), Decimal("-0.25")):
        body = PartsUsageCreate(inventory_id=inv.id, quantity=bad_qty)
        with pytest.raises(HTTPException) as exc_info:
            await add_parts_to_repair_order(order.id, body, db_session, user)
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_add_part_insufficient_stock_counts_whole_packages(db_session):
    user, order, inv = await _seed(db_session, stock_quantity=0)

    body = PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("0.25"))
    with pytest.raises(HTTPException) as exc_info:
        await add_parts_to_repair_order(order.id, body, db_session, user)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "insufficient_stock"
    assert exc_info.value.detail["available_packages"] == 0
    assert exc_info.value.detail["required_packages"] == 1
    assert exc_info.value.detail["can_override"] is True


@pytest.mark.asyncio
async def test_add_part_stock_shortage_override_records_only_available_reservation(db_session):
    user, order, inv = await _seed(db_session, stock_quantity=1, unit_type="each")

    response = await add_parts_to_repair_order(
        order.id,
        PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("2"), allow_stock_shortage=True),
        db_session,
        user,
    )

    assert response.quantity == Decimal("2")
    assert response.stock_shortage_override is True
    stored = await db_session.get(PartsUsage, response.id)
    assert stored.stock_reserved_packages == 1
    history_result = await db_session.execute(
        select(RepairOrderHistoryEvent)
        .where(RepairOrderHistoryEvent.repair_order_id == order.id)
    )
    history_event = history_result.scalar_one()
    assert history_event.label == "Part added with stock override"
    await db_session.refresh(inv)
    assert inv.stock_quantity == 0

    # Removing an override must restore only the one package actually reserved,
    # not the two units billed on the repair order.
    await remove_parts_from_repair_order(order.id, response.id, db_session, user)
    await db_session.refresh(inv)
    assert inv.stock_quantity == 1


@pytest.mark.asyncio
async def test_part_add_quantity_update_and_removal_are_recorded_in_order_history(db_session):
    user, order, inv = await _seed(db_session, stock_quantity=5, unit_type="each")

    part = await add_parts_to_repair_order(
        order.id,
        PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("2")),
        db_session,
        user,
    )
    await update_parts_quantity(
        order.id,
        part.id,
        PartsUsageUpdate(quantity=Decimal("3")),
        db_session,
        user,
    )
    await remove_parts_from_repair_order(order.id, part.id, db_session, user)

    result = await db_session.execute(
        select(RepairOrderHistoryEvent)
        .where(RepairOrderHistoryEvent.repair_order_id == order.id)
        .order_by(RepairOrderHistoryEvent.created_at.asc(), RepairOrderHistoryEvent.id.asc())
    )
    events = result.scalars().all()
    assert [(event.event_type, event.label, event.detail) for event in events] == [
        ("part_added", "Part added to repair order", "Diesel Engine Oil 15W-40 (5 Gal) · 2 ea"),
        ("part_quantity_updated", "Part quantity updated", "Diesel Engine Oil 15W-40 (5 Gal) · 2 ea → 3 ea"),
        ("part_removed", "Part removed from repair order", "Diesel Engine Oil 15W-40 (5 Gal) · 3 ea"),
    ]

    detail = await get_repair_order_detail(order.id, db_session, user)
    assert [event.label for event in detail.history_events] == [
        "Part added to repair order",
        "Part quantity updated",
        "Part removed from repair order",
    ]


@pytest.mark.asyncio
async def test_quantity_increase_can_use_stock_shortage_override_without_negative_inventory(db_session):
    user, order, inv = await _seed(db_session, stock_quantity=1, unit_type="each")
    part = await add_parts_to_repair_order(
        order.id,
        PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("1")),
        db_session,
        user,
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_parts_quantity(
            order.id,
            part.id,
            PartsUsageUpdate(quantity=Decimal("2")),
            db_session,
            user,
        )
    assert exc_info.value.detail["code"] == "insufficient_stock"

    updated = await update_parts_quantity(
        order.id,
        part.id,
        PartsUsageUpdate(quantity=Decimal("2"), allow_stock_shortage=True),
        db_session,
        user,
    )
    assert updated.stock_shortage_override is True
    await db_session.refresh(inv)
    assert inv.stock_quantity == 0

    await remove_parts_from_repair_order(order.id, part.id, db_session, user)
    await db_session.refresh(inv)
    assert inv.stock_quantity == 1


@pytest.mark.asyncio
async def test_update_quantity_within_same_package_does_not_touch_stock(db_session):
    user, order, inv = await _seed(db_session, stock_quantity=10)

    body = PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("0.25"))
    resp = await add_parts_to_repair_order(order.id, body, db_session, user)
    await db_session.refresh(inv)
    assert inv.stock_quantity == 9  # one jug opened

    # Bumping 0.25 -> 0.75 gal still rounds up to the same single package.
    update_body = PartsUsageUpdate(quantity=Decimal("0.75"))
    updated = await update_parts_quantity(order.id, resp.id, update_body, db_session, user)
    assert updated.quantity == Decimal("0.75")

    await db_session.refresh(inv)
    assert inv.stock_quantity == 9  # unchanged — still within package 1


@pytest.mark.asyncio
async def test_update_quantity_crossing_into_next_package_decrements_stock(db_session):
    user, order, inv = await _seed(db_session, stock_quantity=10)

    body = PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("1.00"))
    resp = await add_parts_to_repair_order(order.id, body, db_session, user)
    await db_session.refresh(inv)
    assert inv.stock_quantity == 9

    # 1.00 -> 5.25 gal crosses from 1 package needed to 6 packages needed.
    update_body = PartsUsageUpdate(quantity=Decimal("5.25"))
    updated = await update_parts_quantity(order.id, resp.id, update_body, db_session, user)
    assert updated.quantity == Decimal("5.25")

    await db_session.refresh(inv)
    assert inv.stock_quantity == 4  # 5 more packages consumed (9 - 5)


@pytest.mark.asyncio
async def test_update_quantity_rejects_zero(db_session):
    user, order, inv = await _seed(db_session)
    body = PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("1.00"))
    resp = await add_parts_to_repair_order(order.id, body, db_session, user)

    with pytest.raises(HTTPException) as exc_info:
        await update_parts_quantity(
            order.id, resp.id, PartsUsageUpdate(quantity=Decimal("0")), db_session, user
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_remove_part_restores_whole_packages_to_stock(db_session):
    user, order, inv = await _seed(db_session, stock_quantity=10)

    body = PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("1.25"))
    resp = await add_parts_to_repair_order(order.id, body, db_session, user)
    await db_session.refresh(inv)
    assert inv.stock_quantity == 8  # 1.25 gal rounds up to 2 packages consumed

    await remove_parts_from_repair_order(order.id, resp.id, db_session, user)
    await db_session.refresh(inv)
    assert inv.stock_quantity == 10  # both packages it drew from are restored


@pytest.mark.asyncio
async def test_each_unit_part_still_behaves_as_whole_number(db_session):
    user, order, inv = await _seed(db_session, stock_quantity=5, unit_type="each")

    body = PartsUsageCreate(inventory_id=inv.id, quantity=Decimal("2"))
    resp = await add_parts_to_repair_order(order.id, body, db_session, user)
    assert resp.quantity == Decimal("2")
    assert resp.unit_type == "each"

    await db_session.refresh(inv)
    assert inv.stock_quantity == 3


@pytest.mark.asyncio
async def test_service_bundled_fluid_part_uses_fractional_quantity(db_session):
    """An 'Oil Change' service bundling 5.0 gal of oil should price and
    consume stock using the fractional ServicePart.quantity, not round it
    to a whole number."""
    user, order, inv = await _seed(db_session, stock_quantity=10)
    service = Service(
        id=uuid4(),
        tenant_id=order.tenant_id,
        name="Oil Change",
        duration_minutes=45,
        base_price=Decimal("0.00"),
        is_active=True,
        requires_vehicle=True,
    )
    service_part = ServicePart(
        id=uuid4(),
        tenant_id=order.tenant_id,
        service_id=service.id,
        inventory_id=inv.id,
        quantity=Decimal("5.00"),
    )
    db_session.add_all([service, service_part])
    await db_session.commit()

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    result = await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)

    part = result.order.parts_usage[0]
    assert part.quantity == Decimal("5.00")
    assert part.total_price == Decimal("24.00") * Decimal("5.00")

    await db_session.refresh(inv)
    assert inv.stock_quantity == 5  # 5 whole packages (5.0 gal) consumed
