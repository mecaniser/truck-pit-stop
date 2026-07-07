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
    assert exc.value.detail == "Repair orders can only be deleted when status is draft, quoted, or cancelled"

    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one_or_none()
    assert stored is not None
    assert stored.status == RepairOrderStatus.COMPLETED


@pytest.mark.asyncio
async def test_delete_repair_order_allows_cancelled_status(db_session, monkeypatch):
    user, customer, vehicle = await _seed_context(db_session)
    order = await _create_order(
        db_session,
        tenant_id=user.tenant_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        status=RepairOrderStatus.CANCELLED,
    )

    async def _noop_async(**_kwargs):
        return None

    monkeypatch.setattr(repair_orders, "broadcast_repair_order_update", _noop_async)

    await repair_orders.delete_repair_order(
        order.id,
        db=db_session,
        current_user=user,
    )

    # Soft delete: the row survives, hidden and stamped with who/when.
    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    assert stored.deleted_at is not None
    assert stored.deleted_by_user_id == user.id
    assert stored.status == RepairOrderStatus.CANCELLED


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

    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    assert stored.deleted_at is not None
    assert stored.deleted_by_user_id == user.id
    assert stored.status == RepairOrderStatus.DRAFT


@pytest.mark.asyncio
async def test_cancel_repair_order_records_actor_and_timestamp(db_session, monkeypatch):
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

    await repair_orders.update_repair_order(
        order.id,
        RepairOrderUpdate(status=RepairOrderStatus.CANCELLED),
        db=db_session,
        current_user=user,
    )

    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    assert stored.cancelled_at is not None
    assert stored.cancelled_by_user_id == user.id


@pytest.mark.asyncio
async def test_restore_repair_order(db_session, monkeypatch):
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

    await repair_orders.delete_repair_order(order.id, db=db_session, current_user=user)

    restored = await repair_orders.restore_repair_order(order.id, db=db_session, current_user=user)

    assert restored.status == RepairOrderStatus.DRAFT
    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    assert stored.deleted_at is None
    assert stored.deleted_by_user_id is None


@pytest.mark.asyncio
async def test_restore_repair_order_rejects_non_deleted(db_session):
    user, customer, vehicle = await _seed_context(db_session)
    order = await _create_order(
        db_session,
        tenant_id=user.tenant_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        status=RepairOrderStatus.DRAFT,
    )

    with pytest.raises(HTTPException) as exc:
        await repair_orders.restore_repair_order(order.id, db=db_session, current_user=user)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_restore_repair_order_requires_owner_or_admin_role(db_session):
    user, customer, vehicle = await _seed_context(db_session)
    user.role = UserRole.RECEPTIONIST
    await db_session.commit()

    order = await _create_order(
        db_session,
        tenant_id=user.tenant_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        status=RepairOrderStatus.DRAFT,
    )

    checker = repair_orders.require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
    with pytest.raises(HTTPException) as exc:
        await checker(current_user=user)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_repair_orders_excludes_deleted(db_session, monkeypatch):
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

    await repair_orders.delete_repair_order(order.id, db=db_session, current_user=user)

    active_list = await repair_orders.list_repair_orders(
        customer_id=None, vehicle_id=None, status=None, deleted=False,
        skip=0, limit=100, paginated=False,
        db=db_session, current_user=user,
    )
    assert order.id not in [o.id for o in active_list]

    deleted_list = await repair_orders.list_repair_orders(
        customer_id=None, vehicle_id=None, status=None, deleted=True,
        skip=0, limit=100, paginated=False,
        db=db_session, current_user=user,
    )
    assert order.id in [o.id for o in deleted_list]
