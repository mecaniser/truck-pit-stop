from __future__ import annotations

from datetime import datetime, timezone
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

from app.api.v1.endpoints import invoice_access, payments
from app.core.dependencies import get_current_active_user, get_db
from app.core.rate_limit import limiter
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.user import User, UserRole


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakePaymentsSession:
    def __init__(self, invoice: Invoice):
        self.invoice = invoice
        self.committed = False

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is Invoice:
            return _ScalarResult(self.invoice)
        raise AssertionError(f"Unexpected query entity: {entity}")

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        return None


class _FakeInvoiceAccessSession:
    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        return None


def _build_context():
    tenant_id = uuid4()
    customer_id = uuid4()
    order_id = uuid4()
    invoice_id = uuid4()
    user_id = uuid4()
    vehicle_id = uuid4()

    customer = Customer(
        id=customer_id,
        tenant_id=tenant_id,
        first_name="Alex",
        last_name="Driver",
        email="alex@example.com",
    )
    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number="RO-9001",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("100.00"),
        total_cost=Decimal("100.00"),
    )
    invoice = Invoice(
        id=invoice_id,
        tenant_id=tenant_id,
        repair_order_id=order_id,
        invoice_number="INV-9001",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("100.00"),
        shop_supplies_amount=Decimal("0.00"),
        service_fee_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
    )
    user = User(
        id=user_id,
        email="alex@example.com",
        hashed_password="hashed-password",
        first_name="Alex",
        last_name="Driver",
        role=UserRole.CUSTOMER,
        tenant_id=tenant_id,
        customer_id=customer_id,
        is_active=True,
        is_verified=True,
    )

    order.customer = customer
    invoice.repair_order = order
    return invoice, order, customer, user


@pytest.mark.asyncio
async def test_customer_submit_zelle_broadcasts_repair_order_update(monkeypatch):
    invoice, order, _customer, user = _build_context()
    fake_db = _FakePaymentsSession(invoice=invoice)
    broadcast_calls: list[dict] = []
    alert_calls: list[dict] = []

    async def _override_get_db():
        yield fake_db

    async def _override_current_user():
        return user

    async def _capture_broadcast(**kwargs):
        broadcast_calls.append(kwargs)

    async def _capture_alert(**kwargs):
        alert_calls.append(kwargs)

    monkeypatch.setattr(payments, "broadcast_repair_order_update", _capture_broadcast)
    monkeypatch.setattr(payments, "send_pending_zelle_submission_alert", _capture_alert)

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
            json={
                "invoice_id": str(invoice.id),
                "sender_email": "zelle.sender@example.com",
                "sender_phone": "(414) 555-1111",
                "notes": "sent from app",
            },
        )

    assert response.status_code == 200
    assert response.json()["pending_zelle_confirmation"] is True
    assert fake_db.committed is True
    assert invoice.zelle_pending_submitted_at is not None
    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["tenant_id"] == str(invoice.tenant_id)
    assert broadcast_calls[0]["customer_id"] == str(order.customer_id)
    assert broadcast_calls[0]["order_id"] == str(order.id)
    assert broadcast_calls[0]["status"] == order.status.value
    assert len(alert_calls) == 1
    assert alert_calls[0]["invoice_number"] == invoice.invoice_number
    assert alert_calls[0]["source_label"] == "customer portal"


@pytest.mark.asyncio
async def test_guest_submit_zelle_broadcasts_repair_order_update(monkeypatch):
    invoice, order, customer, _user = _build_context()
    fake_db = _FakeInvoiceAccessSession()
    broadcast_calls: list[dict] = []
    alert_calls: list[dict] = []
    payload = {
        "invoice_id": str(invoice.id),
        "customer_id": str(customer.id),
        "tenant_id": str(invoice.tenant_id),
    }

    async def _override_get_db():
        yield fake_db

    async def _fake_get_payload(_token: str):
        return payload

    async def _fake_load_context(_db, _invoice_id: str):
        return invoice, order, customer, None

    async def _capture_broadcast(**kwargs):
        broadcast_calls.append(kwargs)

    async def _capture_alert(**kwargs):
        alert_calls.append(kwargs)

    monkeypatch.setattr(invoice_access, "_get_active_invoice_payload_or_400", _fake_get_payload)
    monkeypatch.setattr(invoice_access, "_load_invoice_context", _fake_load_context)
    monkeypatch.setattr(invoice_access, "broadcast_repair_order_update", _capture_broadcast)
    monkeypatch.setattr(invoice_access, "send_pending_zelle_submission_alert", _capture_alert)

    app = FastAPI()
    limiter.reset()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(invoice_access.router, prefix="/api/v1/invoice-access")
    app.dependency_overrides[get_db] = _override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/invoice-access/submit-zelle",
            json={
                "token": "test-token",
                "sender_email": "guest.sender@example.com",
                "sender_phone": "(262) 555-2222",
                "notes": "guest flow",
            },
        )

    assert response.status_code == 200
    assert response.json()["pending_zelle_confirmation"] is True
    assert fake_db.committed is True
    assert invoice.zelle_pending_submitted_at is not None
    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["tenant_id"] == str(invoice.tenant_id)
    assert broadcast_calls[0]["customer_id"] == str(order.customer_id)
    assert broadcast_calls[0]["order_id"] == str(order.id)
    assert broadcast_calls[0]["status"] == order.status.value
    assert len(alert_calls) == 1
    assert alert_calls[0]["invoice_number"] == invoice.invoice_number
    assert alert_calls[0]["source_label"] == "guest invoice link"


@pytest.mark.asyncio
async def test_customer_resubmit_pending_zelle_does_not_send_staff_alert(monkeypatch):
    invoice, _order, _customer, user = _build_context()
    invoice.zelle_pending_submitted_at = datetime.now(timezone.utc)
    fake_db = _FakePaymentsSession(invoice=invoice)
    alert_calls: list[dict] = []

    async def _override_get_db():
        yield fake_db

    async def _override_current_user():
        return user

    async def _capture_alert(**kwargs):
        alert_calls.append(kwargs)

    async def _noop_broadcast(**_kwargs):
        return None

    monkeypatch.setattr(payments, "broadcast_repair_order_update", _noop_broadcast)
    monkeypatch.setattr(payments, "send_pending_zelle_submission_alert", _capture_alert)

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
            json={
                "invoice_id": str(invoice.id),
                "sender_email": "repeat.sender@example.com",
            },
        )

    assert response.status_code == 200
    assert response.json()["pending_zelle_confirmation"] is True
    assert len(alert_calls) == 0


@pytest.mark.asyncio
async def test_guest_resubmit_pending_zelle_does_not_send_staff_alert(monkeypatch):
    invoice, order, customer, _user = _build_context()
    invoice.zelle_pending_submitted_at = datetime.now(timezone.utc)
    fake_db = _FakeInvoiceAccessSession()
    alert_calls: list[dict] = []
    payload = {
        "invoice_id": str(invoice.id),
        "customer_id": str(customer.id),
        "tenant_id": str(invoice.tenant_id),
    }

    async def _override_get_db():
        yield fake_db

    async def _fake_get_payload(_token: str):
        return payload

    async def _fake_load_context(_db, _invoice_id: str):
        return invoice, order, customer, None

    async def _capture_alert(**kwargs):
        alert_calls.append(kwargs)

    async def _noop_broadcast(**_kwargs):
        return None

    monkeypatch.setattr(invoice_access, "_get_active_invoice_payload_or_400", _fake_get_payload)
    monkeypatch.setattr(invoice_access, "_load_invoice_context", _fake_load_context)
    monkeypatch.setattr(invoice_access, "broadcast_repair_order_update", _noop_broadcast)
    monkeypatch.setattr(invoice_access, "send_pending_zelle_submission_alert", _capture_alert)

    app = FastAPI()
    limiter.reset()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(invoice_access.router, prefix="/api/v1/invoice-access")
    app.dependency_overrides[get_db] = _override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/invoice-access/submit-zelle",
            json={
                "token": "test-token",
                "sender_email": "repeat.guest@example.com",
            },
        )

    assert response.status_code == 200
    assert response.json()["pending_zelle_confirmation"] is True
    assert len(alert_calls) == 0
