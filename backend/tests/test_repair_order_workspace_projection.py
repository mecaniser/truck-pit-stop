"""Repair-workspace deep links use the compact read-model projection."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.api.v1.endpoints.repair_orders import get_repair_order_workspace
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_read_model import RepairOrderReadModel
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import RepairOrderResponse


async def _seed_workspace_projection(db):
    tenant = Tenant(id=uuid4(), name="Workspace", slug=f"workspace-{uuid4().hex[:8]}")
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Sam",
        last_name="Driver",
        email=f"sam-{uuid4().hex[:8]}@example.com",
    )
    owner = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password="not-used",
        first_name="Owner",
        last_name="User",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, make="Volvo", model="VNL")
    order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.IN_PROGRESS,
        total_parts_cost=Decimal("80.00"),
        total_labor_cost=Decimal("120.00"),
        total_cost=Decimal("200.00"),
    )
    db.add_all([tenant, customer, owner, vehicle, order])
    await db.flush()
    db.add(RepairOrderReadModel(
        repair_order_id=order.id,
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        status=order.status.value,
        is_internal=False,
        is_deleted=False,
        created_at=order.created_at,
        search_document=order.order_number,
        search_compact=order.order_number,
        payload=RepairOrderResponse.model_validate(order).model_dump(mode="json"),
    ))
    await db.commit()
    return owner, order


@pytest.mark.asyncio
async def test_workspace_deep_link_reads_only_the_projection(db_session):
    owner, order = await _seed_workspace_projection(db_session)
    query_count = 0

    def _count_query(*_args):
        nonlocal query_count
        query_count += 1

    sync_engine = db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _count_query)
    try:
        response = await get_repair_order_workspace(
            order_id=order.id,
            db=db_session,
            current_user=owner,
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", _count_query)

    assert response.id == order.id
    assert response.status == RepairOrderStatus.IN_PROGRESS
    assert query_count == 1
