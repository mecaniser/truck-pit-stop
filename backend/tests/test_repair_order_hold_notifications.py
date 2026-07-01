from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

# Twilio client is initialized at import time in app.services.twilio_service.
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import repair_orders
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.user import User, UserRole


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, order: RepairOrder):
        self.order = order
        self.commit_count = 0

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        assert entity is RepairOrder
        return _ScalarResult(self.order)

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _obj):
        return None


def _build_order_and_mechanic(*, on_hold: bool) -> tuple[RepairOrder, User]:
    tenant_id = uuid4()
    customer_id = uuid4()
    vehicle_id = uuid4()
    order_id = uuid4()
    mechanic_id = uuid4()
    now = datetime.now(timezone.utc)

    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number="RO-HOLD-1001",
        status=RepairOrderStatus.IN_PROGRESS,
        is_internal=False,
        is_warranty_repair=False,
        is_pm=False,
        assigned_mechanic_id=mechanic_id,
        hold_reason="waiting_for_parts" if on_hold else None,
        held_at=now if on_hold else None,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("120.00"),
        total_cost=Decimal("120.00"),
        created_at=now,
        updated_at=now,
    )

    mechanic = User(
        id=mechanic_id,
        tenant_id=tenant_id,
        role=UserRole.MECHANIC,
        email="tech@example.com",
        hashed_password="hashed",
        first_name="Test",
        last_name="Mechanic",
        is_active=True,
        is_verified=True,
    )

    return order, mechanic


@pytest.mark.asyncio
async def test_hold_repair_order_broadcast_is_staff_only(monkeypatch):
    order, mechanic = _build_order_and_mechanic(on_hold=False)
    fake_db = _FakeAsyncSession(order)
    broadcast_calls: list[dict] = []

    async def _capture_broadcast(**kwargs):
        broadcast_calls.append(kwargs)

    async def _noop_timer(**_kwargs):
        return None

    async def _no_active_session(*_args, **_kwargs):
        return None

    monkeypatch.setattr(repair_orders, "broadcast_repair_order_update", _capture_broadcast)
    monkeypatch.setattr(repair_orders, "broadcast_mechanic_timer_update", _noop_timer)
    monkeypatch.setattr(repair_orders, "get_active_session", _no_active_session)

    response = await repair_orders.hold_repair_order(
        order_id=order.id,
        body=repair_orders.HoldRequest(reason="waiting_for_parts"),
        db=fake_db,
        current_user=mechanic,
    )

    assert response.hold_reason == "waiting_for_parts"
    assert fake_db.commit_count == 1
    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["send_to_customer"] is False


@pytest.mark.asyncio
async def test_resume_repair_order_broadcast_is_staff_only(monkeypatch):
    order, mechanic = _build_order_and_mechanic(on_hold=True)
    fake_db = _FakeAsyncSession(order)
    broadcast_calls: list[dict] = []

    async def _capture_broadcast(**kwargs):
        broadcast_calls.append(kwargs)

    async def _noop_timer(**_kwargs):
        return None

    async def _fake_fetch_tenant_and_mechanic(*_args, **_kwargs):
        return object(), object()

    async def _fake_start_session(*_args, **_kwargs):
        return None, False, None, None

    monkeypatch.setattr(repair_orders, "broadcast_repair_order_update", _capture_broadcast)
    monkeypatch.setattr(repair_orders, "broadcast_mechanic_timer_update", _noop_timer)
    monkeypatch.setattr(repair_orders, "fetch_tenant_and_mechanic", _fake_fetch_tenant_and_mechanic)
    monkeypatch.setattr(repair_orders, "start_session", _fake_start_session)

    response = await repair_orders.resume_repair_order(
        order_id=order.id,
        db=fake_db,
        current_user=mechanic,
    )

    assert response.hold_reason is None
    assert fake_db.commit_count == 1
    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["send_to_customer"] is False
