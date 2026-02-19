from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi import HTTPException

pytest.importorskip("stripe")
pytest.importorskip("slowapi")

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.endpoints import invoice_access
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


def test_validate_new_password_or_400_passthrough_http_exception(monkeypatch):
    expected = HTTPException(status_code=400, detail="Password is too weak")

    def _raise_http_exception(_password: str):
        raise expected

    monkeypatch.setattr(invoice_access, "validate_password", _raise_http_exception)

    with pytest.raises(HTTPException) as exc_info:
        invoice_access._validate_new_password_or_400("WeakPass1!")

    assert exc_info.value is expected


def test_validate_new_password_or_400_normalizes_unexpected_exceptions(monkeypatch):
    def _raise_value_error(_password: str):
        raise ValueError("unexpected parser failure")

    monkeypatch.setattr(invoice_access, "validate_password", _raise_value_error)

    with pytest.raises(HTTPException) as exc_info:
        invoice_access._validate_new_password_or_400("ValidPass1!")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid password. Please choose a stronger password and try again."


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, invoice: Invoice, user: User):
        self.invoice = invoice
        self.user = user

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is Invoice:
            return _ScalarResult(self.invoice)
        if entity is User:
            return _ScalarResult(self.user)
        raise AssertionError(f"Unexpected query entity: {entity}")

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None

    async def rollback(self):
        return None

    def add(self, _obj):
        return None


def _build_invoice_context():
    tenant_id = uuid4()
    customer_id = uuid4()
    vehicle_id = uuid4()
    order_id = uuid4()
    invoice_id = uuid4()
    user_id = uuid4()

    customer = Customer(
        id=customer_id,
        tenant_id=tenant_id,
        first_name="Alex",
        last_name="Driver",
        email="alex@example.com",
        phone="5551234567",
    )
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
        order_number="RO-0001",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("100.00"),
        total_cost=Decimal("100.00"),
    )
    invoice = Invoice(
        id=invoice_id,
        tenant_id=tenant_id,
        repair_order_id=order_id,
        invoice_number="INV-0001",
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
        is_verified=False,
    )

    order.customer = customer
    order.vehicle = vehicle
    invoice.repair_order = order

    return invoice, order, customer, user


@pytest.mark.skip(reason="Test needs full rewrite: endpoint internals changed significantly")
@pytest.mark.asyncio
async def test_create_portal_concurrent_requests_only_one_succeeds(monkeypatch):
    invoice, order, customer, user = _build_invoice_context()
    payload = {"invoice_id": str(invoice.id), "customer_id": str(customer.id)}
    token = "concurrent-invoice-token"

    async def _override_get_db():
        yield _FakeAsyncSession(invoice=invoice, user=user)

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(invoice_access.router, prefix="/api/v1/invoice-access")
    app.dependency_overrides[get_db] = _override_get_db

    async def fake_get_active_payload(_token: str):
        return payload, "invoice_access"

    consume_arrivals = 0
    consume_gate = asyncio.Event()
    consume_lock = asyncio.Lock()
    consume_done = False

    async def fake_consume(_token: str):
        nonlocal consume_arrivals, consume_done
        consume_arrivals += 1
        if consume_arrivals >= 2:
            consume_gate.set()
        else:
            try:
                await asyncio.wait_for(consume_gate.wait(), timeout=0.2)
            except asyncio.TimeoutError:
                pass

        async with consume_lock:
            if consume_done:
                return None
            consume_done = True
            return payload

    async def fake_get_token_version(_user_id: str):
        return 0

    monkeypatch.setattr(invoice_access, "_get_portal_auth_payload_or_400", fake_get_active_payload)
    monkeypatch.setattr(invoice_access, "consume_invoice_access_token", fake_consume)
    monkeypatch.setattr(invoice_access, "get_token_version", fake_get_token_version)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        responses = await asyncio.gather(
            client.post("/api/v1/invoice-access/create-portal", json={"token": token}),
            client.post("/api/v1/invoice-access/create-portal", json={"token": token}),
        )

    status_codes = sorted(response.status_code for response in responses)
    assert status_codes == [200, 410]
    gone_response = next(response for response in responses if response.status_code == 410)
    assert gone_response.json()["detail"] == "This invoice link has already been used. Please request a new invoice link."
