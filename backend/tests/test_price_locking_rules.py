from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import os

import pytest
from sqlalchemy import select

# Twilio client is initialized at import time in app.services.twilio_service.
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import quotes as quotes_endpoint
from app.db.models.customer import Customer
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.service import Service
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.price_build_service import PriceBuildLockedError, PriceBuildService


async def _seed_quote_context(db_session):
    tenant = Tenant(
        id=uuid4(),
        name="Lock Test Garage",
        slug=f"lock-test-{uuid4().hex[:8]}",
        labor_rate=Decimal("100.00"),
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Taylor",
        last_name="Fleet",
        email=f"taylor-{uuid4().hex[:8]}@example.com",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Kenworth",
        model="T680",
        year=2022,
        vin="1XKAD49X35J654321",
    )
    staff_user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"staff-{uuid4().hex[:8]}@example.com",
        hashed_password="hashed-password",
        first_name="Shop",
        last_name="Admin",
        role=UserRole.GARAGE_ADMIN,
        is_active=True,
        is_verified=True,
    )
    order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.QUOTED,
        description="Brake repair",
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    service = Service(
        id=uuid4(),
        tenant_id=tenant.id,
        name="Brake Inspection",
        duration_minutes=60,
        base_price=Decimal("120.00"),
        is_active=True,
        requires_vehicle=True,
    )
    quote = Quote(
        id=uuid4(),
        tenant_id=tenant.id,
        repair_order_id=order.id,
        quote_number=f"Q-{uuid4().hex[:8]}",
        total_amount=Decimal("120.00"),
        notes=None,
        expires_at=None,
        is_approved=False,
        is_declined=False,
        sent_to_customer=False,
        sent_at=None,
    )
    db_session.add_all([tenant, customer, vehicle, staff_user, order, service, quote])
    await db_session.commit()
    return staff_user, order, service, quote


@pytest.mark.asyncio
async def test_locked_order_rejects_price_build_edits(db_session):
    _, order, service, _ = await _seed_quote_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.lock_order_pricing(db_session, loaded.id, reason="quote_sent")
    locked = await svc.load_order(db_session, order.id)

    with pytest.raises(PriceBuildLockedError):
        await svc.add_flat_service_line(db_session, locked, service.id, quantity=1)


@pytest.mark.asyncio
async def test_quote_send_locks_order_pricing(db_session, monkeypatch):
    staff_user, order, service, quote = await _seed_quote_context(db_session)

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)

    async def _noop_email(**_kwargs):
        return None

    async def _noop_sms(*_args, **_kwargs):
        return None

    async def _noop_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(quotes_endpoint, "send_email", _noop_email)
    monkeypatch.setattr(quotes_endpoint, "send_sms", _noop_sms)
    monkeypatch.setattr(quotes_endpoint, "broadcast_quote_event", _noop_broadcast)
    monkeypatch.setattr(quotes_endpoint, "broadcast_repair_order_update", _noop_broadcast)

    response = await quotes_endpoint.send_quote_to_customer(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    assert response.sent_to_customer is True
    assert response.sent_at is not None

    refreshed_order = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    assert refreshed_order.pricing_locked_at is not None
    assert refreshed_order.pricing_lock_reason == "quote_sent"
