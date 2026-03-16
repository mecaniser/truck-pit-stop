from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints import repair_orders
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import RepairOrderUpdate


async def _seed_context(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name="Test Garage", slug=f"test-garage-{suffix}", is_active=True)
    db_session.add(tenant)
    await db_session.flush()

    user = User(
        email=f"owner-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Owner",
        last_name="User",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    customer = Customer(
        tenant_id=tenant.id,
        first_name="John",
        last_name="Doe",
        email=f"customer-{suffix}@example.com",
        billing_country="USA",
    )
    db_session.add_all([user, customer])
    await db_session.flush()

    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2020,
    )
    db_session.add(vehicle)
    await db_session.commit()

    return user, customer, vehicle


async def _create_order(db_session, *, tenant_id, customer_id, vehicle_id, status: RepairOrderStatus):
    order = RepairOrder(
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=status,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest.mark.asyncio
async def test_cancel_repair_order_rejects_completed_status(db_session):
    user, customer, vehicle = await _seed_context(db_session)
    order = await _create_order(
        db_session,
        tenant_id=user.tenant_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        status=RepairOrderStatus.COMPLETED,
    )

    with pytest.raises(HTTPException) as exc:
        await repair_orders.update_repair_order(
            order.id,
            RepairOrderUpdate(status=RepairOrderStatus.CANCELLED),
            db=db_session,
            current_user=user,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Repair orders can only be cancelled when status is draft or quoted"

    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    assert stored.status == RepairOrderStatus.COMPLETED


@pytest.mark.asyncio
async def test_delete_repair_order_rejects_completed_status(db_session):
    user, customer, vehicle = await _seed_context(db_session)
    order = await _create_order(
        db_session,
        tenant_id=user.tenant_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        status=RepairOrderStatus.COMPLETED,
    )

    with pytest.raises(HTTPException) as exc:
        await repair_orders.delete_repair_order(
            order.id,
            db=db_session,
            current_user=user,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Repair orders can only be deleted when status is draft or quoted"

    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one_or_none()
    assert stored is not None
    assert stored.status == RepairOrderStatus.COMPLETED


@pytest.mark.asyncio
async def test_cancel_repair_order_allows_quoted_status(db_session, monkeypatch):
    user, customer, vehicle = await _seed_context(db_session)
    order = await _create_order(
        db_session,
        tenant_id=user.tenant_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        status=RepairOrderStatus.QUOTED,
    )

    async def _noop_async(**_kwargs):
        return None

    monkeypatch.setattr(repair_orders, "broadcast_repair_order_update", _noop_async)

    response = await repair_orders.update_repair_order(
        order.id,
        RepairOrderUpdate(status=RepairOrderStatus.CANCELLED),
        db=db_session,
        current_user=user,
    )

    assert response.status == RepairOrderStatus.CANCELLED

    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    assert stored.status == RepairOrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_delete_repair_order_allows_draft_status(db_session, monkeypatch):
    user, customer, vehicle = await _seed_context(db_session)
    order = await _create_order(
        db_session,
        tenant_id=user.tenant_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        status=RepairOrderStatus.DRAFT,
    )

    async def _noop_async(**_kwargs):
        return None

    monkeypatch.setattr(repair_orders, "broadcast_repair_order_update", _noop_async)

    response = await repair_orders.delete_repair_order(
        order.id,
        db=db_session,
        current_user=user,
    )

    assert response.status_code == 204

    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one_or_none()
    assert stored is None
