from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

pytest.importorskip("stripe")
pytest.importorskip("aiosqlite")

from app.api.v1.endpoints import payments
from app.core.dependencies import get_current_active_user, get_db
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, invoice: Invoice, customer: Customer, conflict_customer: Customer):
        self.invoice = invoice
        self.customer = customer
        self.conflict_customer = conflict_customer
        self.execute_calls = 0
        self.added: list[object] = []
        self.committed = False

    async def execute(self, statement):
        self.execute_calls += 1
        entity = statement.column_descriptions[0].get("entity")
        if self.execute_calls == 1:
            assert entity is Invoice
            return _ScalarResult(self.invoice)
        if self.execute_calls == 2:
            assert entity is Tenant
            return _ScalarResult(None)
        if self.execute_calls == 3:
            assert entity is Customer
            return _ScalarResult(self.customer)
        if self.execute_calls == 4:
            assert entity is Customer
            return _ScalarResult(self.conflict_customer)
        raise AssertionError(f"Unexpected query call #{self.execute_calls} for entity {entity}")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        return None


def _build_context():
    tenant_id = uuid4()
    customer_id = uuid4()
    conflict_customer_id = uuid4()
    order_id = uuid4()
    invoice_id = uuid4()
    user_id = uuid4()
    vehicle_id = uuid4()

    walkin_customer = Customer(
        id=customer_id,
        tenant_id=tenant_id,
        first_name="Walk-in",
        last_name="Customer",
        email="walkin+15551234567@placeholder.dieselbridge.network",
        phone="15551234567",
        source="walk_in",
    )
    conflict_customer = Customer(
        id=conflict_customer_id,
        tenant_id=tenant_id,
        first_name="Existing",
        last_name="Conflict",
        email="conflict@example.com",
        phone="18005550199",
    )
    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number="RO-1001",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("125.00"),
        total_cost=Decimal("125.00"),
    )
    invoice = Invoice(
        id=invoice_id,
        tenant_id=tenant_id,
        repair_order_id=order_id,
        invoice_number="INV-1001",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("125.00"),
        shop_supplies_amount=Decimal("0.00"),
        service_fee_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("125.00"),
    )
    user = User(
        id=user_id,
        email="admin@example.com",
        hashed_password="hashed-password",
        first_name="Garage",
        last_name="Admin",
        role=UserRole.GARAGE_ADMIN,
        tenant_id=tenant_id,
        is_active=True,
        is_verified=True,
    )

    invoice.repair_order = order

    return invoice, order, walkin_customer, conflict_customer, user


@pytest.mark.asyncio
async def test_record_manual_payment_returns_warning_when_sender_email_conflicts(monkeypatch):
    invoice, order, walkin_customer, conflict_customer, user = _build_context()
    fake_db = _FakeAsyncSession(
        invoice=invoice,
        customer=walkin_customer,
        conflict_customer=conflict_customer,
    )

    async def _override_get_db():
        yield fake_db

    async def _override_current_user():
        return user

    async def _fake_allocate_next_payment_number(_db, _tenant_id):
        return "PMT-0001"

    async def _noop_async(**_kwargs):
        return None

    monkeypatch.setattr(payments, "allocate_next_payment_number", _fake_allocate_next_payment_number)
    monkeypatch.setattr(payments, "broadcast_payment_received", _noop_async)
    monkeypatch.setattr(payments, "broadcast_repair_order_update", _noop_async)
    monkeypatch.setattr(payments, "send_invoice_payment_confirmation_email", _noop_async)
    monkeypatch.setattr(payments, "record_payment", lambda **_kwargs: None)

    app = FastAPI()
    app.include_router(payments.router, prefix="/api/v1/payments")
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_active_user] = _override_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/payments/record-manual",
            json={
                "invoice_id": str(invoice.id),
                "method": "zelle",
                "zelle_sender_email": "conflict@example.com",
                "zelle_sender_phone": "+1 (414) 555-0909",
                "update_customer_from_sender": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["warning"] == (
        "Sender email was not applied because it already belongs to another customer in this garage."
    )

    # Email remains unchanged on conflict, but other enrichment still applies.
    assert walkin_customer.email == "walkin+15551234567@placeholder.dieselbridge.network"
    assert walkin_customer.phone == "14145550909"
    assert walkin_customer.source == "zelle"

    assert invoice.status == InvoiceStatus.PAID
    assert order.status == RepairOrderStatus.PAID
    assert fake_db.committed is True
    assert fake_db.execute_calls == 4
    assert len([obj for obj in fake_db.added if isinstance(obj, Payment)]) == 1
    payment = next(obj for obj in fake_db.added if isinstance(obj, Payment))
    assert payment.method == PaymentMethod.ZELLE
