from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import repair_orders
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.schemas.repair_order import RepairOrderUpdate


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [RepairOrderStatus.INVOICED, RepairOrderStatus.PAID])
async def test_attribution_is_immutable_after_invoice_finalization(db_session, state):
    tenant = Tenant(name="Attribution Lock", slug=f"lock-{uuid4().hex}")
    user = User(
        tenant=tenant, email=f"owner-{uuid4().hex}@example.com", hashed_password="x",
        first_name="Owner", last_name="One", role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    customer = Customer(tenant=tenant, first_name="Test", last_name="Customer", email=f"customer-{uuid4().hex}@example.com")
    order = RepairOrder(
        tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"RO-{uuid4().hex}",
        status=state, utm_campaign="original",
    )
    db_session.add_all([tenant, user, customer, order])
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await repair_orders.update_repair_order(
            order.id, RepairOrderUpdate(utm_campaign="rewritten"), db=db_session, current_user=user,
        )
    assert exc.value.status_code == 409
    assert order.utm_campaign == "original"


@pytest.mark.asyncio
async def test_attribution_update_cannot_cross_tenant(db_session):
    tenant_a = Tenant(name="A", slug=f"a-{uuid4().hex}")
    tenant_b = Tenant(name="B", slug=f"b-{uuid4().hex}")
    user_b = User(
        tenant=tenant_b, email=f"owner-{uuid4().hex}@example.com", hashed_password="x",
        first_name="Owner", last_name="B", role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    customer = Customer(tenant=tenant_a, first_name="Test", last_name="Customer", email=f"customer-{uuid4().hex}@example.com")
    order = RepairOrder(
        tenant=tenant_a, customer=customer, vehicle_id=uuid4(), order_number=f"RO-{uuid4().hex}",
        status=RepairOrderStatus.DRAFT,
    )
    db_session.add_all([tenant_a, tenant_b, user_b, customer, order])
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await repair_orders.update_repair_order(
            order.id, RepairOrderUpdate(utm_campaign="stolen"), db=db_session, current_user=user_b,
        )
    assert exc.value.status_code == 403
