"""Fleet board + truck detail: status derivation, KPI stats, detail aggregation."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4
import os

import pytest

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import fleet
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.internal_fleet import ensure_internal_fleet_customer


async def _seed(db):
    tenant = Tenant(id=uuid4(), name="Board Garage", slug=f"bg-{uuid4().hex[:8]}", labor_rate=Decimal("100.00"))
    db.add(tenant)
    await db.commit()
    fc = await ensure_internal_fleet_customer(db, tenant.id)
    await db.commit()
    user = User(id=uuid4(), tenant_id=tenant.id, email=f"fm-{uuid4().hex[:8]}@x.com",
                hashed_password="x", first_name="Fleet", last_name="Mgr",
                role=UserRole.FLEET_MANAGER, is_active=True, is_verified=True)
    db.add(user)
    await db.commit()
    return tenant, fc, user


def _vehicle(tenant_id, fc_id, **kw):
    base = dict(id=uuid4(), tenant_id=tenant_id, customer_id=fc_id, make="Volvo", model="VNL",
                year=2021, mileage=100000, pm_interval_miles=25000)
    base.update(kw)
    return Vehicle(**base)


def _ro(tenant_id, fc_id, vehicle_id, status, **kw):
    base = dict(id=uuid4(), tenant_id=tenant_id, customer_id=fc_id, vehicle_id=vehicle_id,
                order_number=f"RO-{uuid4().hex[:8]}", status=status, is_internal=True,
                total_parts_cost=Decimal("0"), total_labor_cost=Decimal("0"), total_cost=Decimal("0"))
    base.update(kw)
    return RepairOrder(**base)


@pytest.mark.asyncio
async def test_board_status_derivation(db_session):
    tenant, fc, user = await _seed(db_session)
    # active: PM far out, no open RO
    v_active = _vehicle(tenant.id, fc.id, unit_number="A", mileage=100000, next_pm_miles=120000)
    # pm: overdue
    v_pm = _vehicle(tenant.id, fc.id, unit_number="P", mileage=100000, next_pm_miles=99500)
    # shop: open internal RO
    v_shop = _vehicle(tenant.id, fc.id, unit_number="S", mileage=100000, next_pm_miles=120000)
    # parts: open RO on hold for parts
    v_parts = _vehicle(tenant.id, fc.id, unit_number="R", mileage=100000, next_pm_miles=120000)
    db_session.add_all([v_active, v_pm, v_shop, v_parts])
    await db_session.commit()
    db_session.add(_ro(tenant.id, fc.id, v_shop.id, RepairOrderStatus.IN_PROGRESS))
    db_session.add(_ro(tenant.id, fc.id, v_parts.id, RepairOrderStatus.IN_PROGRESS, hold_reason="awaiting_parts"))
    await db_session.commit()

    board = await fleet.fleet_board(db=db_session, current_user=user)
    by_unit = {t.unit_number: t for t in board.trucks}
    assert by_unit["A"].status == "active"
    assert by_unit["P"].status == "pm"
    assert by_unit["S"].status == "shop"
    assert by_unit["R"].status == "parts"
    # work order surfaced for shop truck
    assert by_unit["S"].work_order is not None
    assert by_unit["S"].work_order.status == "In progress"
    assert by_unit["R"].work_order.status == "Awaiting parts"


@pytest.mark.asyncio
async def test_board_stats(db_session):
    tenant, fc, user = await _seed(db_session)
    v1 = _vehicle(tenant.id, fc.id, unit_number="1", next_pm_miles=120000)
    v2 = _vehicle(tenant.id, fc.id, unit_number="2", next_pm_miles=99000)  # overdue -> pm
    db_session.add_all([v1, v2])
    await db_session.commit()
    db_session.add(_ro(tenant.id, fc.id, v1.id, RepairOrderStatus.IN_PROGRESS))
    await db_session.commit()

    board = await fleet.fleet_board(db=db_session, current_user=user)
    assert board.stats.total == 2
    assert board.stats.shop == 1
    assert board.stats.pm == 1
    assert board.stats.open_wo == 1


@pytest.mark.asyncio
async def test_truck_detail_history_and_spend(db_session):
    tenant, fc, user = await _seed(db_session)
    v = _vehicle(tenant.id, fc.id, unit_number="H", mileage=200000, next_pm_miles=210000,
                 driver_name="Marcus Reed", driver_phone="+17045551234")
    db_session.add(v)
    await db_session.commit()
    # two completed internal ROs (one PM, one repair) + one open
    db_session.add(_ro(tenant.id, fc.id, v.id, RepairOrderStatus.COMPLETED, is_pm=True,
                       total_cost=Decimal("500.00"), mileage_out=180000, description="PM service A"))
    db_session.add(_ro(tenant.id, fc.id, v.id, RepairOrderStatus.COMPLETED, is_pm=False,
                       total_cost=Decimal("1200.00"), mileage_out=190000, description="Brake job"))
    db_session.add(_ro(tenant.id, fc.id, v.id, RepairOrderStatus.IN_PROGRESS, description="Open"))
    await db_session.commit()

    detail = await fleet.truck_detail(vehicle_id=v.id, db=db_session, current_user=user)
    assert detail.driver_phone == "+17045551234"
    assert detail.lifetime_spend == 1700.0
    kinds = sorted(h.kind for h in detail.history)
    assert kinds == ["PM", "Repair"]
    assert detail.truck.work_order is not None  # the open one


@pytest.mark.asyncio
async def test_schedule_pm_and_new_work_order(db_session):
    tenant, fc, user = await _seed(db_session)
    v = _vehicle(tenant.id, fc.id, unit_number="W", next_pm_miles=120000)
    db_session.add(v)
    await db_session.commit()

    res = await fleet.schedule_pm(vehicle_id=v.id, db=db_session, current_user=user)
    assert res.work_order is not None
    # the spawned RO is an internal PM order
    ros = (await db_session.execute(
        __import__("sqlalchemy").select(RepairOrder).where(RepairOrder.vehicle_id == v.id)
    )).scalars().all()
    assert len(ros) == 1 and ros[0].is_internal and ros[0].is_pm

    res2 = await fleet.new_work_order(vehicle_id=v.id, db=db_session, current_user=user)
    assert res2.work_order is not None
