"""Owner price-builder: bulk Stock/List parts pricing + labor/order dollar discounts."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import repair_orders as ro
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor, LaborLineType
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import PartsPricingModeRequest, DiscountUpdate


async def _seed_order(db):
    t = Tenant(id=uuid4(), name="P", slug=f"p-{uuid4().hex[:6]}", labor_rate=Decimal("100"))
    db.add(t)
    await db.commit()
    cust = Customer(id=uuid4(), tenant_id=t.id, first_name="A", last_name="B", email=f"c{uuid4().hex[:6]}@x.com")
    owner = User(id=uuid4(), tenant_id=t.id, email=f"o{uuid4().hex[:6]}@x.com", hashed_password="x",
                 first_name="O", last_name="W", role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True)
    veh = Vehicle(id=uuid4(), tenant_id=t.id, customer_id=cust.id, make="V", model="N")
    inv = Inventory(id=uuid4(), tenant_id=t.id, sku="P1", name="Pump", stock_quantity=5,
                    cost=Decimal("40.00"), selling_price=Decimal("100.00"))
    db.add_all([cust, owner, veh, inv])
    await db.commit()
    order = RepairOrder(id=uuid4(), tenant_id=t.id, customer_id=cust.id, vehicle_id=veh.id,
                        order_number=f"RO-{uuid4().hex[:6]}", status=RepairOrderStatus.QUOTED)
    db.add(order)
    await db.commit()
    db.add(PartsUsage(id=uuid4(), tenant_id=t.id, repair_order_id=order.id, inventory_id=inv.id, quantity=2,
                      unit_cost=Decimal("40.00"), unit_price=Decimal("100.00"), list_price=Decimal("100.00"),
                      total_price=Decimal("200.00")))
    db.add(Labor(id=uuid4(), tenant_id=t.id, repair_order_id=order.id, description="Labor", hours=Decimal("2"),
                 hourly_rate=Decimal("100"), total_cost=Decimal("200.00"), line_type=LaborLineType.MANUAL))
    await db.commit()
    await ro._recompute_repair_order_totals(db, order.id)
    return t, owner, order


@pytest.mark.asyncio
async def test_stock_and_list_pricing_modes(db_session):
    _, owner, order = await _seed_order(db_session)
    stock = await ro.set_parts_pricing_mode(order_id=order.id, body=PartsPricingModeRequest(mode="stock"),
                                             db=db_session, current_user=owner)
    assert stock.parts_total == Decimal("80.00")   # 40 cost * 2
    assert stock.total_cost == Decimal("280.00")    # 80 parts + 200 labor
    lst = await ro.set_parts_pricing_mode(order_id=order.id, body=PartsPricingModeRequest(mode="list"),
                                          db=db_session, current_user=owner)
    assert lst.parts_total == Decimal("200.00")     # back to list
    assert lst.total_cost == Decimal("400.00")


@pytest.mark.asyncio
async def test_pricing_mode_rejects_bad_value(db_session):
    _, owner, order = await _seed_order(db_session)
    with pytest.raises(HTTPException) as exc:
        await ro.set_parts_pricing_mode(order_id=order.id, body=PartsPricingModeRequest(mode="wholesale"),
                                        db=db_session, current_user=owner)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_labor_and_order_discounts(db_session):
    _, owner, order = await _seed_order(db_session)
    res = await ro.update_repair_order_discounts(
        order_id=order.id, body=DiscountUpdate(labor_discount_amount=Decimal("50"), order_discount_amount=Decimal("30")),
        db=db_session, current_user=owner)
    # parts 200 + (labor 200 - 50) - 30 = 320
    assert res.labor_discount_amount == Decimal("50.00")
    assert res.order_discount_amount == Decimal("30.00")
    assert res.total_cost == Decimal("320.00")
    # labor_total still reports gross
    assert res.labor_total == Decimal("200.00")


@pytest.mark.asyncio
async def test_discount_caps_enforced(db_session):
    _, owner, order = await _seed_order(db_session)
    with pytest.raises(HTTPException) as exc:  # labor discount > labor total
        await ro.update_repair_order_discounts(order_id=order.id, body=DiscountUpdate(labor_discount_amount=Decimal("500")),
                                               db=db_session, current_user=owner)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:  # order discount > subtotal (400)
        await ro.update_repair_order_discounts(order_id=order.id, body=DiscountUpdate(order_discount_amount=Decimal("9999")),
                                               db=db_session, current_user=owner)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_discount_survives_parts_recompute(db_session):
    """A labor discount must persist when parts are re-priced (totals recompute)."""
    _, owner, order = await _seed_order(db_session)
    await ro.update_repair_order_discounts(order_id=order.id, body=DiscountUpdate(labor_discount_amount=Decimal("50")),
                                           db=db_session, current_user=owner)
    stock = await ro.set_parts_pricing_mode(order_id=order.id, body=PartsPricingModeRequest(mode="stock"),
                                            db=db_session, current_user=owner)
    # 80 parts + (200 labor - 50) = 230, discount preserved
    assert stock.labor_discount_amount == Decimal("50.00")
    assert stock.total_cost == Decimal("230.00")
