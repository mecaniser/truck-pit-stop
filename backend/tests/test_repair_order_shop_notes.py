"""The shop's note is its own column, and the customer never receives it.

`internal_notes` reads like the place to put a note, but it is a JSON envelope:
`get_selected_services_total` parses `selected_services` out of it to price the
invoice, and quotes, mechanic time tracking and the customer portal parse it
too. Prose written there is not merely invisible — it makes the services
unparseable and the order's labour total silently becomes zero. These tests pin
both halves: that shop_notes round-trips as plain text, and that writing it
leaves the pricing envelope alone.
"""
from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import repair_orders
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import RepairOrderUpdate
from app.services.pricing import get_selected_services_total

# base_price is the key the pricer sums; duration_minutes is what the update
# endpoint re-derives estimated_labor_minutes from.
SERVICES = json.dumps({"selected_services": [{"name": "Brake pads", "base_price": 215.0, "duration_minutes": 90}]})


async def _seed(db, *, role: UserRole = UserRole.GARAGE_OWNER):
    suffix = uuid4().hex[:8]
    tenant = Tenant(id=uuid4(), name="Note shop", slug=f"notes-{suffix}", is_active=True)
    customer = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Pat", last_name="Driver",
        email=f"pat-{suffix}@example.test",
    )
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, make="Volvo", model="VNL")
    user = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{suffix}@example.test",
        hashed_password="x", first_name="Owner", last_name="One", role=role,
        is_active=True, is_verified=True, customer_id=customer.id if role == UserRole.CUSTOMER else None,
    )
    order = RepairOrder(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        order_number=f"RO-{suffix}", status=RepairOrderStatus.IN_PROGRESS, is_internal=False,
        internal_notes=SERVICES,
        total_parts_cost=Decimal("0.00"), total_labor_cost=Decimal("0.00"), total_cost=Decimal("0.00"),
    )
    db.add_all([tenant, customer, vehicle, user, order])
    await db.commit()
    return tenant, user, order


@pytest.mark.asyncio
async def test_a_shop_note_round_trips_as_plain_text(db_session):
    _, user, order = await _seed(db_session)

    result = await repair_orders.update_repair_order(
        order_id=order.id,
        order_data=RepairOrderUpdate(shop_notes="Torque checked. Second pass at next PM."),
        db=db_session, current_user=user,
    )

    assert result.shop_notes == "Torque checked. Second pass at next PM."
    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    assert stored.shop_notes == "Torque checked. Second pass at next PM."


@pytest.mark.asyncio
async def test_writing_a_shop_note_leaves_the_pricing_envelope_intact(db_session):
    """The regression this column exists to prevent.

    Had the note gone into internal_notes, the services would stop parsing and
    the order's labour total would fall to zero without an error anywhere.
    """
    _, user, order = await _seed(db_session)
    assert get_selected_services_total(order.internal_notes) == Decimal("215.0")

    await repair_orders.update_repair_order(
        order_id=order.id,
        order_data=RepairOrderUpdate(shop_notes="Customer called twice about the noise."),
        db=db_session, current_user=user,
    )

    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    assert json.loads(stored.internal_notes)["selected_services"][0]["name"] == "Brake pads"
    assert get_selected_services_total(stored.internal_notes) == Decimal("215.0")


@pytest.mark.asyncio
async def test_a_customer_never_receives_the_shop_note(db_session):
    """Unconditionally — not merely while financials are unpublished."""
    _, owner, order = await _seed(db_session)
    await repair_orders.update_repair_order(
        order_id=order.id,
        order_data=RepairOrderUpdate(shop_notes="Do not tell the customer we reused the old core."),
        db=db_session, current_user=owner,
    )

    customer_user = User(
        id=uuid4(), tenant_id=order.tenant_id, email=f"cust-{uuid4().hex[:8]}@example.test",
        hashed_password="x", first_name="Pat", last_name="Driver", role=UserRole.CUSTOMER,
        is_active=True, is_verified=True, customer_id=order.customer_id,
    )
    db_session.add(customer_user)
    await db_session.commit()

    detail = await repair_orders.get_repair_order(
        order_id=order.id, db=db_session, current_user=customer_user,
    )
    payload = detail if isinstance(detail, dict) else detail.model_dump()
    assert payload.get("shop_notes") is None
