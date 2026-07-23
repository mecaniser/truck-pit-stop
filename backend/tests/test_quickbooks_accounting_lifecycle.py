from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.services import quickbooks_accounting_service as accounting


def _connection() -> QuickBooksConnection:
    return QuickBooksConnection(
        tenant_id=uuid4(),
        realm_id="123456789",
        status="connected",
        encrypted_access_token="unused-by-mocked-request",
    )


def _customer(tenant_id) -> Customer:
    return Customer(
        id=uuid4(),
        tenant_id=tenant_id,
        first_name="Sergio",
        last_name="Driver",
        company_name="Sergio Trucking",
        email="sergio@example.com",
        quickbooks_customer_id="41",
    )


def _invoice(tenant_id) -> Invoice:
    return Invoice(
        id=uuid4(),
        tenant_id=tenant_id,
        repair_order_id=uuid4(),
        invoice_number="INV-QBO-1001",
        status=InvoiceStatus.SENT,
        is_internal=False,
        subtotal=Decimal("100.00"),
        total_amount=Decimal("108.00"),
        tax_amount=Decimal("8.00"),
        discount_amount=Decimal("0.00"),
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_invoice_and_payment_sync_are_idempotent_and_linked(monkeypatch):
    connection = _connection()
    customer = _customer(connection.tenant_id)
    invoice = _invoice(connection.tenant_id)
    calls = []

    async def fake_query(_connection, statement):
        if "from Invoice" in statement or "from Payment" in statement:
            return []
        if "from Item" in statement:
            return [{"Id": "17"}]
        raise AssertionError(statement)

    async def fake_request(_connection, method, resource, **kwargs):
        calls.append((method, resource, kwargs))
        if resource == "invoice":
            return {"Invoice": {"Id": "501"}}
        if resource == "payment":
            return {"Payment": {"Id": "601"}}
        raise AssertionError(resource)

    monkeypatch.setattr(accounting, "_query", fake_query)
    monkeypatch.setattr(accounting, "_request", fake_request)

    assert await accounting.sync_invoice(connection, invoice, customer) == "501"
    payment = Payment(
        id=uuid4(),
        tenant_id=connection.tenant_id,
        invoice_id=invoice.id,
        payment_number="PAY-QBO-1001",
        amount=invoice.total_amount,
        method=PaymentMethod.QUICKBOOKS,
        status=PaymentStatus.COMPLETED,
        quickbooks_charge_id="charge-123",
    )
    assert await accounting.sync_payment(connection, payment, invoice, customer) == "601"

    payment_body = next(kwargs["json"] for _method, resource, kwargs in calls if resource == "payment")
    assert payment_body["Line"][0]["LinkedTxn"] == [{"TxnId": "501", "TxnType": "Invoice"}]
    assert payment.quickbooks_reconciled_at is not None

    # Stored provider IDs make worker/webhook retries local no-ops.
    call_count = len(calls)
    assert await accounting.sync_invoice(connection, invoice, customer) == "501"
    assert await accounting.sync_payment(connection, payment, invoice, customer) == "601"
    assert len(calls) == call_count


@pytest.mark.asyncio
async def test_cancelled_invoice_is_voided_in_qbo(monkeypatch):
    connection = _connection()
    customer = _customer(connection.tenant_id)
    invoice = _invoice(connection.tenant_id)
    invoice.status = InvoiceStatus.CANCELLED
    invoice.quickbooks_invoice_id = "501"
    calls = []

    async def fake_request(_connection, method, resource, **kwargs):
        calls.append((method, resource, kwargs))
        if method == "GET":
            return {"Invoice": {"Id": "501", "SyncToken": "3"}}
        return {"Invoice": {"Id": "501"}}

    monkeypatch.setattr(accounting, "_request", fake_request)

    assert await accounting.sync_invoice(connection, invoice, customer) == "501"
    assert calls[-1][2]["params"]["operation"] == "void"
    assert calls[-1][2]["json"] == {"Id": "501", "SyncToken": "3"}
    assert invoice.quickbooks_sync_status == "voided"


@pytest.mark.asyncio
async def test_change_data_capture_flattens_supported_entities(monkeypatch):
    connection = _connection()

    async def fake_request(_connection, method, resource, **kwargs):
        assert method == "GET"
        assert resource == "cdc"
        assert kwargs["params"]["entities"] == "Customer,Invoice,Payment,RefundReceipt,Deposit"
        return {
            "CDCResponse": [{
                "QueryResponse": {
                    "Invoice": [{"Id": "501"}],
                    "Payment": [{"Id": "601"}],
                },
            }],
        }

    monkeypatch.setattr(accounting, "_request", fake_request)
    changes = await accounting.change_data_capture(
        connection,
        changed_since=datetime(2026, 7, 22, tzinfo=timezone.utc),
    )
    assert changes == {
        "Invoice": [{"Id": "501"}],
        "Payment": [{"Id": "601"}],
    }
