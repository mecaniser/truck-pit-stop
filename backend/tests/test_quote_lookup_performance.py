"""Workspace quote lookup keeps order access and quote retrieval to one read."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.api.v1.endpoints.quotes import get_quote_by_repair_order
from app.db.models.customer import Customer
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


async def _seed_quote_context(db):
    tenant = Tenant(id=uuid4(), name="Performance", slug=f"performance-{uuid4().hex[:8]}")
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Pat",
        last_name="Customer",
        email=f"pat-{uuid4().hex[:8]}@example.com",
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
        status=RepairOrderStatus.DRAFT,
    )
    quote = Quote(
        id=uuid4(),
        tenant_id=tenant.id,
        repair_order_id=order.id,
        quote_number=f"Q-{uuid4().hex[:8]}",
        total_amount=Decimal("125.00"),
    )
    db.add_all([tenant, customer, owner, vehicle, order, quote])
    await db.commit()
    return owner, order, quote


@pytest.mark.asyncio
async def test_workspace_quote_lookup_uses_one_query(db_session):
    owner, order, quote = await _seed_quote_context(db_session)
    query_count = 0

    def _count_query(*_args):
        nonlocal query_count
        query_count += 1

    sync_engine = db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _count_query)
    try:
        response = await get_quote_by_repair_order(
            repair_order_id=order.id,
            db=db_session,
            current_user=owner,
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", _count_query)

    assert response is not None
    assert response.id == quote.id
    assert query_count == 1
