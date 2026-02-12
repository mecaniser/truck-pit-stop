from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

pytest.importorskip("stripe")
pytest.importorskip("slowapi")
pytest.importorskip("aiosqlite")

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.endpoints import payments
from app.core.dependencies import get_current_active_user, get_db
from app.core.rate_limit import limiter
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.user import User, UserRole


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, invoice: Invoice):
        self.invoice = invoice

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is Invoice:
            return _ScalarResult(self.invoice)
        raise AssertionError(f"Unexpected query entity: {entity}")

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


def _build_context():
    tenant_id = uuid4()
    customer_id = uuid4()
    order_id = uuid4()
    invoice_id = uuid4()
    user_id = uuid4()
    vehicle_id = uuid4()

    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number="RO-7001",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("90.00"),
        total_cost=Decimal("90.00"),
    )
    invoice = Invoice(
        id=invoice_id,
        tenant_id=tenant_id,
        repair_order_id=order_id,
        invoice_number="INV-7001",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("90.00"),
        shop_supplies_amount=Decimal("0.00"),
        service_fee_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("90.00"),
    )
    invoice.repair_order = order

    user = User(
        id=user_id,
        email="rate.limit.customer@example.com",
        hashed_password="hashed-password",
        first_name="Rate",
        last_name="Limited",
        role=UserRole.CUSTOMER,
        tenant_id=tenant_id,
        customer_id=customer_id,
        is_active=True,
        is_verified=True,
    )
    return invoice, user


@pytest.mark.asyncio
async def test_submit_customer_zelle_allows_normal_single_request(monkeypatch):
    invoice, user = _build_context()
    fake_db = _FakeAsyncSession(invoice)

    async def _override_get_db():
        yield fake_db

    async def _override_current_user():
        return user

    async def _noop_async(**_kwargs):
        return None

    monkeypatch.setattr(payments, "broadcast_repair_order_update", _noop_async)
    monkeypatch.setattr(payments, "send_pending_zelle_submission_alert", _noop_async)

    app = FastAPI()
    limiter.reset()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(payments.router, prefix="/api/v1/payments")
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_active_user] = _override_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/payments/submit-zelle",
            json={"invoice_id": str(invoice.id)},
        )

    assert response.status_code == 200
    assert response.json()["pending_zelle_confirmation"] is True


@pytest.mark.asyncio
async def test_submit_customer_zelle_rate_limits_burst_requests(monkeypatch):
    invoice, user = _build_context()
    fake_db = _FakeAsyncSession(invoice)

    async def _override_get_db():
        yield fake_db

    async def _override_current_user():
        return user

    async def _noop_async(**_kwargs):
        return None

    monkeypatch.setattr(payments, "broadcast_repair_order_update", _noop_async)
    monkeypatch.setattr(payments, "send_pending_zelle_submission_alert", _noop_async)

    app = FastAPI()
    limiter.reset()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(payments.router, prefix="/api/v1/payments")
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_active_user] = _override_current_user

    statuses: list[int] = []
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for _ in range(6):
            response = await client.post(
                "/api/v1/payments/submit-zelle",
                json={"invoice_id": str(invoice.id)},
            )
            statuses.append(response.status_code)

    assert any(code == 200 for code in statuses)
    assert any(code == 429 for code in statuses)
