"""Internal fleet (house account) repairs: pricing, guards, and helpers.

Internal repair orders price labor at the tenant's internal_labor_rate and parts at
inventory cost — with no customer quote/invoice — while customer ROs are unaffected.
"""
from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import quotes as quotes_endpoint
from app.api.v1.endpoints import fleet as fleet_endpoint
from app.api.v1.endpoints import invoices as invoices_endpoint
from app.api.v1.endpoints.quotes import create_quote, QuoteCreate
from app.api.v1.endpoints.repair_orders import _check_ro_access, create_repair_order
from app.schemas.repair_order import RepairOrderCreate
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory
from app.db.models.invoice import Invoice
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
from app.schemas.fleet import WorkOrderComplete


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
async def test_fleet_customer_rate_changes_labor_but_not_parts(db_session):
    """The fleet setting changes labor only; parts remain at garage cost."""
    _, order, service = await _seed(db_session, is_internal=True, with_part=True)
    order.bill_labor_at_customer_rate = True
    await db_session.commit()

    loaded = await PriceBuildService().load_order(db_session, order.id)
    result = await PriceBuildService().add_flat_service_line(db_session, loaded, service.id)

    assert result.order.labor_items[0].hourly_rate == Decimal("100.00")
    assert result.order.parts_usage[0].unit_price == Decimal("10.00")


@pytest.mark.asyncio
async def test_billable_fleet_invoice_uses_truck_contact_snapshot(db_session, monkeypatch):
    staff_user, order, _ = await _seed(db_session, is_internal=True)
    vehicle = (await db_session.execute(select(Vehicle).where(Vehicle.id == order.vehicle_id))).scalar_one()
    vehicle.billing_contact_name = "Morgan Billing"
    vehicle.billing_contact_email = "morgan@example.test"
    vehicle.billing_contact_phone = "+17045550123"
    order.status = RepairOrderStatus.COMPLETED
    order.total_labor_cost = Decimal("40.00")
    order.total_cost = Decimal("40.00")
    await db_session.commit()

    async def no_op(*_args, **_kwargs):
        return None

    async def invoice_link(*_args, **_kwargs):
        return "https://example.test/invoice/token"

    monkeypatch.setattr(invoices_endpoint, "send_email", no_op)
    monkeypatch.setattr(invoices_endpoint, "broadcast_invoice_created", no_op)
    monkeypatch.setattr(invoices_endpoint, "broadcast_repair_order_update", no_op)
    monkeypatch.setattr(invoices_endpoint, "generate_invoice_access_link", invoice_link)

    tenant = (await db_session.execute(select(Tenant).where(Tenant.id == order.tenant_id))).scalar_one()
    loaded = (await db_session.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order.id)
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )).scalar_one()
    invoice = await invoices_endpoint.auto_create_invoice_for_order(
        db_session, loaded, tenant, created_by_user_id=staff_user.id
    )

    assert invoice is not None
    assert invoice.is_internal is False
    assert invoice.recipient_name == "Morgan Billing"
    assert invoice.recipient_email == "morgan@example.test"
    assert invoice.recipient_phone == "+17045550123"


@pytest.mark.asyncio
async def test_fleet_quality_review_finalizes_and_invoices_atomically(db_session, monkeypatch):
    staff_user, order, _ = await _seed(db_session, is_internal=True)
    vehicle = (await db_session.execute(select(Vehicle).where(Vehicle.id == order.vehicle_id))).scalar_one()
    vehicle.billing_contact_name = "Morgan Billing"
    vehicle.billing_contact_email = "morgan@example.test"
    vehicle.mileage = 120100
    order.status = RepairOrderStatus.PENDING_REVIEW
    order.mileage_in = 120000
    await db_session.commit()

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(invoices_endpoint, "notify_invoice_created", no_op)

    result = await fleet_endpoint.complete_work_order(
        ro_id=order.id,
        body=WorkOrderComplete(mileage_out=120125, review_notes="Verified final repair."),
        db=db_session,
        current_user=staff_user,
    )

    await db_session.refresh(order)
    invoice = (await db_session.execute(
        select(Invoice).where(Invoice.repair_order_id == order.id)
    )).scalar_one()
    saved_notes = json.loads(order.internal_notes)

    assert result.raw_status == RepairOrderStatus.INVOICED.value
    assert order.status == RepairOrderStatus.INVOICED
    assert order.mileage_out == 120125
    assert order.pricing_lock_reason == "invoice_finalized"
    assert saved_notes["reviews"][0]["notes"] == "Verified final repair."
    assert invoice.is_internal is False
    assert invoice.recipient_email == "morgan@example.test"


@pytest.mark.asyncio
async def test_fleet_quality_review_rolls_back_when_invoice_creation_fails(db_session, monkeypatch):
    staff_user, order, _ = await _seed(db_session, is_internal=True)
    vehicle = (await db_session.execute(select(Vehicle).where(Vehicle.id == order.vehicle_id))).scalar_one()
    vehicle.billing_contact_email = "morgan@example.test"
    vehicle.active_warning_lights = "Check engine"
    order.status = RepairOrderStatus.PENDING_REVIEW
    await db_session.commit()

    async def fail_invoice(*_args, **_kwargs):
        raise RuntimeError("invoice snapshot failed")

    monkeypatch.setattr(invoices_endpoint, "auto_create_invoice_for_order", fail_invoice)

    with pytest.raises(HTTPException) as exc:
        await fleet_endpoint.complete_work_order(
            ro_id=order.id,
            body=WorkOrderComplete(mileage_out=120125, review_notes="Do not lose this."),
            db=db_session,
            current_user=staff_user,
        )

    assert exc.value.status_code == 500
    await db_session.refresh(order)
    await db_session.refresh(vehicle)
    assert order.status == RepairOrderStatus.PENDING_REVIEW
    assert order.mileage_out is None
    assert order.internal_notes is None
    assert vehicle.active_warning_lights == "Check engine"
    assert (await db_session.execute(
        select(Invoice).where(Invoice.repair_order_id == order.id)
    )).scalar_one_or_none() is None


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
