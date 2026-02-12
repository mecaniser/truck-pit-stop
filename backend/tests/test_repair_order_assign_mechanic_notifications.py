from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

# Twilio client is initialized at import time in app.services.twilio_service.
# Provide placeholder credentials for test imports.
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import repair_orders
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, order: RepairOrder, mechanic: User):
        self.order = order
        self.mechanic = mechanic
        self.execute_calls = 0
        self.commit_count = 0

    async def execute(self, statement):
        self.execute_calls += 1
        entity = statement.column_descriptions[0].get("entity")
        if self.execute_calls == 1:
            assert entity is RepairOrder
            return _ScalarResult(self.order)
        if self.execute_calls == 2:
            assert entity is User
            return _ScalarResult(self.mechanic)
        raise AssertionError(f"Unexpected query call #{self.execute_calls} for entity {entity}")

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _obj):
        return None


def _build_context(mechanic_phone: str | None):
    tenant_id = uuid4()
    customer_id = uuid4()
    vehicle_id = uuid4()
    order_id = uuid4()
    mechanic_id = uuid4()
    manager_id = uuid4()

    now = datetime.now(timezone.utc)
    vehicle = Vehicle(
        id=vehicle_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        make="Freightliner",
        model="Cascadia",
        year=2022,
    )

    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        vehicle=vehicle,
        order_number="RO-2001",
        status=RepairOrderStatus.APPROVED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("150.00"),
        total_cost=Decimal("150.00"),
        created_at=now,
        updated_at=now,
    )

    mechanic = User(
        id=mechanic_id,
        tenant_id=tenant_id,
        role=UserRole.MECHANIC,
        email="mechanic@example.com",
        hashed_password="hashed-password",
        first_name="Mike",
        last_name="Tech",
        phone=mechanic_phone,
        is_active=True,
        is_verified=True,
    )

    manager = User(
        id=manager_id,
        tenant_id=tenant_id,
        role=UserRole.GARAGE_ADMIN,
        email="manager@example.com",
        hashed_password="hashed-password",
        first_name="Shop",
        last_name="Manager",
        is_active=True,
        is_verified=True,
    )

    return order, mechanic, manager


@pytest.mark.asyncio
async def test_assign_mechanic_sends_sms_when_mechanic_has_phone(monkeypatch):
    order, mechanic, manager = _build_context(mechanic_phone="14145550123")
    fake_db = _FakeAsyncSession(order=order, mechanic=mechanic)

    email_calls: list[dict] = []
    sms_calls: list[dict] = []
    broadcast_calls: list[dict] = []

    async def _capture_email(**kwargs):
        email_calls.append(kwargs)
        return None

    async def _capture_sms(**kwargs):
        sms_calls.append(kwargs)
        return None

    async def _capture_broadcast(**kwargs):
        broadcast_calls.append(kwargs)

    monkeypatch.setattr(repair_orders, "send_email", _capture_email)
    monkeypatch.setattr(repair_orders, "send_sms", _capture_sms)
    monkeypatch.setattr(repair_orders, "broadcast_repair_order_update", _capture_broadcast)

    response = await repair_orders.assign_mechanic(
        order_id=order.id,
        body=repair_orders.AssignMechanicRequest(mechanic_id=mechanic.id),
        db=fake_db,
        current_user=manager,
    )

    assert response.status == RepairOrderStatus.ASSIGNED
    assert response.assigned_mechanic_id == mechanic.id
    assert fake_db.commit_count == 1

    assert len(email_calls) == 1
    assert email_calls[0]["to"] == mechanic.email

    assert len(sms_calls) == 1
    assert sms_calls[0]["to"] == mechanic.phone
    assert sms_calls[0]["template_name"] == "job_assigned_sms"
    assert "/mechanic" in sms_calls[0]["body"]
    assert "Portal:" in sms_calls[0]["body"]

    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["status"] == RepairOrderStatus.ASSIGNED.value


@pytest.mark.asyncio
async def test_assign_mechanic_skips_sms_when_no_mechanic_phone(monkeypatch):
    order, mechanic, manager = _build_context(mechanic_phone=None)
    fake_db = _FakeAsyncSession(order=order, mechanic=mechanic)

    sms_calls: list[dict] = []

    async def _capture_email(**_kwargs):
        return None

    async def _capture_sms(**kwargs):
        sms_calls.append(kwargs)
        return None

    async def _noop_broadcast(**_kwargs):
        return None

    monkeypatch.setattr(repair_orders, "send_email", _capture_email)
    monkeypatch.setattr(repair_orders, "send_sms", _capture_sms)
    monkeypatch.setattr(repair_orders, "broadcast_repair_order_update", _noop_broadcast)

    response = await repair_orders.assign_mechanic(
        order_id=order.id,
        body=repair_orders.AssignMechanicRequest(mechanic_id=mechanic.id),
        db=fake_db,
        current_user=manager,
    )

    assert response.status == RepairOrderStatus.ASSIGNED
    assert len(sms_calls) == 0
