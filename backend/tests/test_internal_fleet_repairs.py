"""Internal fleet (house account) repairs: pricing, guards, and helpers.

Internal repair orders price labor at the tenant's internal_labor_rate and parts at
inventory cost — with no customer quote/invoice — while customer ROs are unaffected.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import quotes as quotes_endpoint
from app.api.v1.endpoints.quotes import create_quote, QuoteCreate
from app.api.v1.endpoints.repair_orders import _check_ro_access, create_repair_order
from app.schemas.repair_order import RepairOrderCreate
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.service import Service, ServicePart
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.internal_fleet import (
    ensure_internal_fleet_customer,
    get_internal_fleet_customer,
)
from app.services.price_build_service import PriceBuildService


async def _seed(db_session, *, is_internal: bool, with_part: bool = False):
    tenant = Tenant(
        id=uuid4(),
        name="Fleet Test Garage",
        slug=f"fleet-{uuid4().hex[:8]}",
        labor_rate=Decimal("100.00"),
        internal_labor_rate=Decimal("40.00"),
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Internal" if is_internal else "Acme",
        last_name="Fleet" if is_internal else "Logistics",
        email=f"cust-{uuid4().hex[:8]}@example.com",
        is_internal_fleet=is_internal,
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
        is_internal=is_internal,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    service = Service(
        id=uuid4(),
        tenant_id=tenant.id,
        name="Oil Change",
        duration_minutes=60,  # 1 hour
        base_price=Decimal("0.00"),
        is_active=True,
        requires_vehicle=True,
    )
    objects = [tenant, customer, vehicle, staff_user, order, service]
    if with_part:
        inv = Inventory(
            id=uuid4(),
            tenant_id=tenant.id,
            sku=f"SKU-{uuid4().hex[:6]}",
            name="Oil Filter",
            stock_quantity=100,
            cost=Decimal("10.00"),
            selling_price=Decimal("25.00"),
        )
        service_part = ServicePart(
            id=uuid4(),
            tenant_id=tenant.id,
            service_id=service.id,
            inventory_id=inv.id,
            quantity=1,
        )
        objects += [inv, service_part]
    db_session.add_all(objects)
    await db_session.commit()
    return staff_user, order, service


@pytest.mark.asyncio
async def test_internal_repair_labor_uses_internal_rate(db_session):
    _, order, service = await _seed(db_session, is_internal=True)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    result = await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)

    labor = result.order.labor_items[0]
    assert labor.hourly_rate == Decimal("40.00")  # internal_labor_rate, not 100
    assert labor.total_cost == Decimal("40.00")


@pytest.mark.asyncio
async def test_customer_repair_labor_uses_billable_rate(db_session):
    _, order, service = await _seed(db_session, is_internal=False)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    result = await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)

    labor = result.order.labor_items[0]
    assert labor.hourly_rate == Decimal("100.00")  # billable labor_rate


@pytest.mark.asyncio
async def test_internal_repair_parts_priced_at_cost(db_session):
    _, order, service = await _seed(db_session, is_internal=True, with_part=True)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    result = await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)

    part = result.order.parts_usage[0]
    assert part.unit_price == Decimal("10.00")  # inventory cost, not selling_price 25
    assert part.list_price == Decimal("10.00")
    assert part.total_price == Decimal("10.00")


@pytest.mark.asyncio
async def test_customer_repair_parts_priced_at_selling(db_session):
    _, order, service = await _seed(db_session, is_internal=False, with_part=True)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    result = await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)

    part = result.order.parts_usage[0]
    assert part.unit_price == Decimal("25.00")  # selling_price


@pytest.mark.asyncio
async def test_quote_creation_rejected_for_internal_order(db_session):
    staff_user, order, _ = await _seed(db_session, is_internal=True)
    with pytest.raises(HTTPException) as exc:
        await create_quote(
            body=QuoteCreate(repair_order_id=order.id, notes=None, expires_at=None),
            db=db_session,
            current_user=staff_user,
        )
    assert exc.value.status_code == 400
    assert "internal" in exc.value.detail.lower()


def _fleet_manager(tenant_id):
    return User(
        id=uuid4(),
        tenant_id=tenant_id,
        email=f"fleet-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        first_name="Fleet",
        last_name="Manager",
        role=UserRole.FLEET_MANAGER,
        is_active=True,
        is_verified=True,
    )


def test_check_ro_access_blocks_fleet_manager_on_customer_order():
    tenant_id = uuid4()
    fm = _fleet_manager(tenant_id)
    customer_order = RepairOrder(
        id=uuid4(), tenant_id=tenant_id, customer_id=uuid4(),
        vehicle_id=uuid4(), order_number="RO-X", is_internal=False,
    )
    with pytest.raises(HTTPException) as exc:
        _check_ro_access(fm, customer_order)
    assert exc.value.status_code == 403


def test_check_ro_access_allows_fleet_manager_on_internal_order():
    tenant_id = uuid4()
    fm = _fleet_manager(tenant_id)
    internal_order = RepairOrder(
        id=uuid4(), tenant_id=tenant_id, customer_id=uuid4(),
        vehicle_id=uuid4(), order_number="RO-Y", is_internal=True,
    )
    # Should not raise.
    _check_ro_access(fm, internal_order)


@pytest.mark.asyncio
async def test_fleet_manager_cannot_create_external_repair_order(db_session):
    staff_user, order, _ = await _seed(db_session, is_internal=False)
    fm = _fleet_manager(order.tenant_id)
    db_session.add(fm)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await create_repair_order(
            order_data=RepairOrderCreate(
                customer_id=order.customer_id, vehicle_id=order.vehicle_id
            ),
            db=db_session,
            current_user=fm,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_ensure_internal_fleet_customer_idempotent(db_session):
    tenant = Tenant(id=uuid4(), name="Garage X", slug=f"gx-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.commit()

    first = await ensure_internal_fleet_customer(db_session, tenant.id)
    await db_session.commit()
    second = await ensure_internal_fleet_customer(db_session, tenant.id)
    await db_session.commit()

    assert first.id == second.id
    assert first.is_internal_fleet is True

    found = await get_internal_fleet_customer(db_session, tenant.id)
    assert found is not None and found.id == first.id
