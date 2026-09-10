from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.tenant import Tenant
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
    invoice = Invoice(
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
    invoice.tenant = Tenant(id=tenant_id, name="Acme Diesel Repair")
    return invoice


def test_customer_match_rejects_same_company_with_different_email() -> None:
    connection = _connection()
    customer = _customer(connection.tenant_id)
    candidate = {
        "Id": "99",
        "DisplayName": "Sergio Trucking",
        "CompanyName": "Sergio Trucking",
        "PrimaryEmailAddr": {"Address": "other-owner@example.com"},
    }

    assert accounting._qbo_customer_matches(
        customer,
        candidate,
        tenant_name="Truck Pit Stop",
    ) is False


@pytest.mark.asyncio
async def test_invoice_and_payment_sync_are_idempotent_and_linked(monkeypatch):
    connection = _connection()
    customer = _customer(connection.tenant_id)
    invoice = _invoice(connection.tenant_id)
    calls = []

    async def fake_query(_connection, statement):
        if "from Customer where Id" in statement:
            return [{"Id": "41", "DisplayName": "Sergio Trucking · DB-" + str(customer.id)[:8]}]
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
    invoice_body = next(kwargs["json"] for _method, resource, kwargs in calls if resource == "invoice")
    expected_memo = "Acme Diesel Repair invoice INV-QBO-1001"
    assert invoice_body["PrivateNote"] == expected_memo
    assert invoice_body["CustomerMemo"] == {"value": expected_memo}
    assert invoice_body["Line"][0]["Description"] == expected_memo
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
    assert payment_body["PrivateNote"] == (
        "Acme Diesel Repair invoice INV-QBO-1001 payment PAY-QBO-1001; "
        "Intuit charge charge-123"
    )
    assert payment.quickbooks_reconciled_at is not None

    # Stored provider IDs make worker/webhook retries local no-ops.
    call_count = len(calls)
    assert await accounting.sync_invoice(connection, invoice, customer) == "501"
    assert await accounting.sync_payment(connection, payment, invoice, customer) == "601"
    assert len(calls) == call_count


@pytest.mark.asyncio
async def test_customer_sync_replaces_stale_cross_realm_id(monkeypatch):
    connection = _connection()
    customer = _customer(connection.tenant_id)
    customer.quickbooks_customer_id = "76"
    expected_name = "Sergio Trucking"
    queries = []

    async def fake_query(_connection, statement):
        queries.append(statement)
        if "where Id = '76'" in statement:
            return []
        if "where DisplayName" in statement:
            return []
        raise AssertionError(statement)

    async def fake_request(_connection, method, resource, **kwargs):
        assert method == "POST"
        assert resource == "customer"
        assert kwargs["json"]["DisplayName"] == expected_name
        assert "Notes" not in kwargs["json"]
        assert kwargs["params"] == {"requestid": f"customer-{customer.id}"[:50]}
        return {"Customer": {"Id": "30", "DisplayName": expected_name}}

    monkeypatch.setattr(accounting, "_query", fake_query)
    monkeypatch.setattr(accounting, "_request", fake_request)

    assert await accounting.ensure_customer(connection, customer) == "30"
    assert customer.quickbooks_customer_id == "30"
    assert "where Id = '76'" in queries[0]


@pytest.mark.asyncio
async def test_customer_sync_rejects_cross_realm_id_collision(monkeypatch):
    connection = _connection()
    customer = _customer(connection.tenant_id)
    customer.quickbooks_customer_id = "12"
    expected_name = f"Sergio Trucking · DB-{str(customer.id)[:8]}"

    async def fake_query(_connection, statement):
        if "where Id = '12'" in statement:
            return [{"Id": "12", "DisplayName": "Unrelated sandbox customer"}]
        if "where DisplayName" in statement:
            return [{"Id": "29", "DisplayName": expected_name}]
        raise AssertionError(statement)

    monkeypatch.setattr(accounting, "_query", fake_query)

    assert await accounting.ensure_customer(connection, customer) == "29"
    assert customer.quickbooks_customer_id == "29"


@pytest.mark.asyncio
async def test_customer_sync_replaces_legacy_platform_suffix(monkeypatch):
    connection = _connection()
    customer = _customer(connection.tenant_id)
    legacy_name = f"Sergio Trucking · DB-{str(customer.id)[:8]}"
    calls = []

    async def fake_query(_connection, statement):
        if "where Id = '41'" in statement:
            return [{
                "Id": "41",
                "SyncToken": "3",
                "DisplayName": legacy_name,
                "Notes": f"DieselBridge customer {customer.id}",
            }]
        if "where DisplayName = 'Sergio Trucking'" in statement:
            return []
        raise AssertionError(statement)

    async def fake_request(_connection, method, resource, **kwargs):
        calls.append((method, resource, kwargs))
        return {"Customer": {"Id": "41", "DisplayName": "Sergio Trucking"}}

    monkeypatch.setattr(accounting, "_query", fake_query)
    monkeypatch.setattr(accounting, "_request", fake_request)

    assert await accounting.ensure_customer(
        connection,
        customer,
        tenant_name="Truck Pit Stop",
    ) == "41"
    assert calls == [(
        "POST",
        "customer",
        {
            "params": {
                "operation": "update",
                "requestid": f"customer-name-{customer.id}"[:50],
            },
            "json": {
                "Id": "41",
                "SyncToken": "3",
                "sparse": True,
                "DisplayName": "Sergio Trucking",
                "Notes": "",
            },
        },
    )]


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
        assert kwargs["params"]["entities"] == (
            "Customer,Invoice,Payment,RefundReceipt"
        )
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


@pytest.mark.asyncio
async def test_qbp_settlement_window_queries_deposits_and_purchases_together(
    monkeypatch,
) -> None:
    connection = _connection()
    statements: list[str] = []

    async def fake_query(_connection, statement):
        statements.append(statement)
        if "from Deposit" in statement:
            return [{"Id": "deposit-1"}]
        if "from Purchase" in statement:
            return [{"Id": "fee-1"}]
        raise AssertionError(statement)

    monkeypatch.setattr(accounting, "_query", fake_query)
    result = await accounting.qbp_settlement_window(
        connection,
        date_from=date(2026, 8, 28),
        date_to=date(2026, 9, 3),
    )

    assert result == {
        "Deposit": [{"Id": "deposit-1"}],
        "Purchase": [{"Id": "fee-1"}],
    }
    assert statements == [
        "select * from Deposit where TxnDate >= '2026-08-28' "
        "and TxnDate <= '2026-09-03' startposition 1 maxresults 1000",
        "select * from Purchase where TxnDate >= '2026-08-28' "
        "and TxnDate <= '2026-09-03' startposition 1 maxresults 1000",
    ]
