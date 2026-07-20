from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.api.v1.endpoints import invoice_access, quotes
from app.db.models.invoice import InvoiceStatus
from app.db.models.repair_order import RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, *, tenant: Tenant | None, user: object | None):
        self._tenant = tenant
        self._user = user

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is Tenant:
            return _ScalarResult(self._tenant)
        if entity is User:
            return _ScalarResult(self._user)
        raise AssertionError(f"Unexpected query entity: {entity}")


def _fake_request() -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": ("testclient", 50000),
    })


@pytest.mark.asyncio
async def test_quote_token_response_includes_shop_branding(monkeypatch):
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Truck Pit Stop",
        slug="truck-pit-stop",
        logo_url="https://cdn.example.com/tenant-logo.png",
        phone="7045550199",
        email="service@truckpitstop.example",
    )
    customer = SimpleNamespace(id=uuid4(), first_name="Alex")
    vehicle = SimpleNamespace(year=2022, make="Freightliner", model="Cascadia", vin="1234567890VIN")
    quote = SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id,
        repair_order_id=uuid4(),
        quote_number="QUO-0001",
        total_amount=Decimal("125.00"),
        notes=None,
        expires_at=None,
        is_approved=False,
        is_declined=False,
        decline_notes=None,
        sent_to_customer=True,
        sent_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    order = SimpleNamespace(
        id=quote.repair_order_id,
        tenant_id=tenant_id,
        customer_id=customer.id,
        order_number="RO-0001",
        description="Brake service",
        status=RepairOrderStatus.QUOTED,
        internal_notes='{"selected_services":[{"name":"Brake Service","base_price":"95.00"}]}',
        total_labor_cost=Decimal("95.00"),
        total_parts_cost=Decimal("30.00"),
        labor_discount_amount=Decimal("10.00"),
        order_discount_amount=Decimal("5.00"),
        total_cost=Decimal("110.00"),
        customer=customer,
        vehicle=vehicle,
        parts_usage=[],
    )

    async def _fake_load_quote_context(_db, _token: str, *, include_parts: bool = False):
        assert include_parts is True
        return quote, order

    monkeypatch.setattr(quotes, "_load_quote_context_by_token_or_400", _fake_load_quote_context)

    response = await quotes.get_quote_by_token(
        request=_fake_request(),
        token="quote-token",
        db=_FakeAsyncSession(tenant=tenant, user=object()),
    )

    assert response.shop_name == "Truck Pit Stop"
    assert response.shop_logo_url == "https://cdn.example.com/tenant-logo.png"
    assert response.shop_phone == "7045550199"
    assert response.shop_email == "service@truckpitstop.example"
    assert response.labor_discount_amount == Decimal("10.00")
    assert response.order_discount_amount == Decimal("5.00")


@pytest.mark.asyncio
async def test_invoice_access_resolve_includes_shop_branding(monkeypatch):
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Truck Pit Stop",
        slug="truck-pit-stop",
        logo_url="https://cdn.example.com/tenant-logo.png",
    )
    customer = SimpleNamespace(id=uuid4(), first_name="Alex", last_name="Driver")
    vehicle = SimpleNamespace(year=2022, make="Freightliner", model="Cascadia", unit_number=None)
    order = SimpleNamespace(id=uuid4(), tenant_id=tenant_id, order_number="RO-0001")
    invoice = SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id,
        total_amount=Decimal("125.00"),
        subtotal=Decimal("100.00"),
        shop_supplies_amount=Decimal("10.00"),
        service_fee_amount=Decimal("5.00"),
        tax_amount=Decimal("10.00"),
        discount_amount=Decimal("0.00"),
        invoice_number="INV-0001",
        status=InvoiceStatus.SENT,
        due_date=None,
        paid_at=None,
        pending_zelle_confirmation=False,
    )
    payload = {
        "invoice_id": str(invoice.id),
        "repair_order_id": str(order.id),
        "customer_id": str(customer.id),
    }

    async def _fake_get_active_payload(_token: str):
        return payload

    async def _fake_load_invoice_context(_db, _invoice_id: str):
        return invoice, order, customer, vehicle

    monkeypatch.setattr(invoice_access, "_get_active_invoice_payload_or_400", _fake_get_active_payload)
    monkeypatch.setattr(invoice_access, "_load_invoice_context", _fake_load_invoice_context)
    monkeypatch.setattr(invoice_access, "_validate_invoice_link_subject", lambda *_args, **_kwargs: None)

    response = await invoice_access.resolve_invoice_link(
        request=_fake_request(),
        body=invoice_access.TokenRequest(token="invoice-token"),
        db=_FakeAsyncSession(tenant=tenant, user=object()),
    )

    assert response.shop_name == "Truck Pit Stop"
    assert response.shop_logo_url == "https://cdn.example.com/tenant-logo.png"
