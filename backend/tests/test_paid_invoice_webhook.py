from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.paid_invoice_webhook_crypto import encrypt_paid_invoice_webhook_secret
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.services.paid_invoice_webhook_service import (
    PAID_INVOICE_WEBHOOK_EVENT,
    _deliver,
    enqueue_paid_invoice_webhook,
    process_due_paid_invoice_webhooks,
)
from app.services.provider_outbox_service import ProviderDeliveryError
from app.core.webhook_destination import ResolvedWebhookDestination


@pytest.mark.asyncio
async def test_paid_invoice_event_contains_revenue_contact_lines_and_lead_id(_db_engine, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant = Tenant(name="Attribution Garage", slug=f"attribution-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url="https://example.test/hook")
        tenant.paid_invoice_webhook_secret_encrypted = encrypt_paid_invoice_webhook_secret("webhook-test-secret")
        customer = Customer(tenant=tenant, first_name="Ava", last_name="Driver", email="ava@example.com", phone="+15555550123")
        order = RepairOrder(tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"TPS-{uuid4().hex}", status=RepairOrderStatus.PAID, lead_source_channel="google_ads", external_lead_id="lead-abc", callrail_call_id="callrail-abc", google_click_id="gclid-123", utm_campaign="roadside")
        invoice = Invoice(tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.PAID, subtotal=Decimal("100"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("100"), paid_at=datetime.now(timezone.utc), line_items_snapshot={"labor": [{"description": "Brake repair", "hours": "1.0", "total_cost": "100.00"}], "parts": []})
        db.add_all([tenant, customer, order, invoice])
        await db.flush()
        event = await enqueue_paid_invoice_webhook(db, tenant=tenant, invoice=invoice, order=order, customer=customer)
        await db.commit()

    assert event.event_type == PAID_INVOICE_WEBHOOK_EVENT
    assert event.payload["repair_order_id"] == order.order_number
    assert event.payload["total_amount"] == 100.0
    assert event.payload["currency"] == "USD"
    assert event.payload["customer"] == {"phone": "+15555550123", "email": "ava@example.com"}
    assert event.payload["attribution"]["callrail_call_id"] == "callrail-abc"
    assert event.payload["attribution"]["gclid"] == "gclid-123"
    assert event.payload["service_lines"] == [{"name": "Brake repair", "quantity": 1.0, "amount": 100.0}]


@pytest.mark.asyncio
async def test_paid_invoice_event_is_signed(monkeypatch):
    sent = {}
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())

    async def allow_destination(url, **_kwargs):
        return ResolvedWebhookDestination(url, "example.test", "example.test", ("93.184.216.34",))

    class Response:
        status_code = 202
        headers = {"X-Request-Id": "receiver-123"}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def request(self, method, url, *, content, headers, extensions):
            sent.update(method=method, url=url, content=content, headers=headers, extensions=extensions)
            return Response()

    client_options = {}

    def client_factory(**kwargs):
        client_options.update(kwargs)
        return Client()

    monkeypatch.setattr("app.services.paid_invoice_webhook_service.resolve_webhook_destination", allow_destination)
    monkeypatch.setattr("app.services.paid_invoice_webhook_service.httpx.AsyncClient", client_factory)
    tenant = Tenant(name="Webhook Garage", slug=f"webhook-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url="https://example.test/hook")
    tenant.paid_invoice_webhook_secret_encrypted = encrypt_paid_invoice_webhook_secret("webhook-test-secret")
    from app.db.models.provider_outbox import ProviderOutboxEvent
    event = ProviderOutboxEvent(tenant_id=uuid4(), event_type=PAID_INVOICE_WEBHOOK_EVENT, aggregate_type="invoice", aggregate_id=uuid4(), payload={"event_type": PAID_INVOICE_WEBHOOK_EVENT}, idempotency_key="paid-invoice:test")

    assert await _deliver(tenant, event) == ("receiver-123", 202)
    assert sent["headers"]["X-DieselBridge-Event"] == PAID_INVOICE_WEBHOOK_EVENT
    assert sent["headers"]["X-DieselBridge-Timestamp"].isdigit()
    assert sent["headers"]["Host"] == "example.test"
    assert sent["extensions"]["sni_hostname"] == "example.test"
    assert sent["url"].host == "93.184.216.34"
    assert sent["headers"]["X-DieselBridge-Signature"].startswith("sha256=")
    assert sent["headers"]["Idempotency-Key"] == "paid-invoice:test"
    assert client_options["follow_redirects"] is False
    assert client_options["trust_env"] is False


@pytest.mark.asyncio
async def test_unpaid_zero_and_deleted_orders_do_not_emit(_db_engine, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant = Tenant(name="Guard Garage", slug=f"guard-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url="https://example.test/hook", paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("webhook-test-secret"))
        customer = Customer(tenant=tenant, first_name="A", last_name="B", email="a@example.com")
        order = RepairOrder(tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"TPS-{uuid4().hex}", status=RepairOrderStatus.INVOICED)
        invoice = Invoice(tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.SENT, subtotal=Decimal("0"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("0"))
        db.add_all([tenant, customer, order, invoice]); await db.flush()
        assert await enqueue_paid_invoice_webhook(db, tenant=tenant, invoice=invoice, order=order, customer=customer) is None


@pytest.mark.asyncio
async def test_repeated_delivery_failure_disables_shop_webhook(_db_engine, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("app.core.config.settings.PROVIDER_OUTBOX_MAX_ATTEMPTS", 1)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant = Tenant(name="Fail Garage", slug=f"fail-{uuid4().hex}", email="owner@example.com", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url="https://example.test/hook", paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("webhook-test-secret"))
        customer = Customer(tenant=tenant, first_name="A", last_name="B", email="a@example.com")
        order = RepairOrder(tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"TPS-{uuid4().hex}", status=RepairOrderStatus.PAID)
        invoice = Invoice(tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.PAID, subtotal=Decimal("10"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("10"), paid_at=datetime.now(timezone.utc))
        db.add_all([tenant, customer, order, invoice]); await db.flush()
        await enqueue_paid_invoice_webhook(db, tenant=tenant, invoice=invoice, order=order, customer=customer); await db.commit(); tenant_id = tenant.id

    async def fail(_tenant, _event):
        raise ProviderDeliveryError("receiver unavailable", retryable=True)
    monkeypatch.setattr("app.services.paid_invoice_webhook_service._deliver", fail)
    result = await process_due_paid_invoice_webhooks(session_factory=factory)
    assert result["dead"] == 1
    async with factory() as db:
        tenant = await db.get(Tenant, tenant_id)
        assert tenant.paid_invoice_webhook_enabled is False


@pytest.mark.asyncio
async def test_conversion_delivery_retries_with_backoff(_db_engine, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("app.core.config.settings.PROVIDER_OUTBOX_MAX_ATTEMPTS", 3)
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant = Tenant(name="Retry Garage", slug=f"retry-{uuid4().hex}", paid_invoice_webhook_enabled=True, paid_invoice_webhook_url="https://example.test/hook", paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("webhook-test-secret"))
        customer = Customer(tenant=tenant, first_name="A", last_name="B", email="a@example.com")
        order = RepairOrder(tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"TPS-{uuid4().hex}", status=RepairOrderStatus.PAID)
        invoice = Invoice(tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.PAID, subtotal=Decimal("10"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("10"), paid_at=datetime.now(timezone.utc))
        db.add_all([tenant, customer, order, invoice]); await db.flush()
        event = await enqueue_paid_invoice_webhook(db, tenant=tenant, invoice=invoice, order=order, customer=customer); await db.commit(); event_id = event.id
    async def fail(_tenant, _event): raise ProviderDeliveryError("temporary", retryable=True)
    monkeypatch.setattr("app.services.paid_invoice_webhook_service._deliver", fail)
    result = await process_due_paid_invoice_webhooks(session_factory=factory)
    assert result["retried"] == 1
    async with factory() as db:
        event = await db.get(ProviderOutboxEvent, event_id)
        assert event.status == "pending"
        assert event.attempt_count == 1
        assert event.available_at > event.last_attempt_at


@pytest.mark.asyncio
async def test_private_destination_is_a_nonretryable_delivery_failure(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    tenant = Tenant(
        name="Private Target", slug=f"private-{uuid4().hex}", paid_invoice_webhook_enabled=True,
        paid_invoice_webhook_url="https://127.0.0.1/conversions",
        paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("webhook-test-secret"),
    )
    event = ProviderOutboxEvent(
        tenant_id=uuid4(), event_type=PAID_INVOICE_WEBHOOK_EVENT, aggregate_type="invoice",
        aggregate_id=uuid4(), payload={}, idempotency_key="paid-invoice:private",
    )
    with pytest.raises(ProviderDeliveryError) as exc:
        await _deliver(tenant, event)
    assert exc.value.retryable is False
    assert "public" in str(exc.value)


@pytest.mark.asyncio
async def test_cross_tenant_resources_cannot_enter_conversion_outbox(_db_engine, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    async with factory() as db:
        tenant = Tenant(
            name="Right Shop", slug=f"right-{uuid4().hex}", paid_invoice_webhook_enabled=True,
            paid_invoice_webhook_url="https://hooks.example.com/conversions",
            paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("webhook-test-secret"),
        )
        other = Tenant(name="Other Shop", slug=f"other-{uuid4().hex}")
        customer = Customer(tenant=other, first_name="A", last_name="B", email="a@example.com")
        order = RepairOrder(
            tenant=other, customer=customer, vehicle_id=uuid4(), order_number=f"RO-{uuid4().hex}",
            status=RepairOrderStatus.PAID,
        )
        invoice = Invoice(
            tenant=other, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.PAID,
            subtotal=Decimal("10"), tax_amount=Decimal("0"), discount_amount=Decimal("0"),
            total_amount=Decimal("10"), paid_at=datetime.now(timezone.utc),
        )
        db.add_all([tenant, other, customer, order, invoice])
        await db.flush()
        with pytest.raises(ValueError, match="same shop"):
            await enqueue_paid_invoice_webhook(db, tenant=tenant, invoice=invoice, order=order, customer=customer)


@pytest.mark.asyncio
async def test_webhook_redirect_is_rejected_without_following(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.PAID_INVOICE_WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode())

    async def allow_destination(url, **_kwargs):
        return ResolvedWebhookDestination(url, "hooks.example.com", "hooks.example.com", ("93.184.216.34",))

    class Response:
        status_code = 302
        headers = {"Location": "https://127.0.0.1/internal"}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def request(self, *_args, **_kwargs): return Response()

    monkeypatch.setattr("app.services.paid_invoice_webhook_service.resolve_webhook_destination", allow_destination)
    monkeypatch.setattr("app.services.paid_invoice_webhook_service.httpx.AsyncClient", lambda **_kwargs: Client())
    tenant = Tenant(
        name="Redirect Target", slug=f"redirect-{uuid4().hex}", paid_invoice_webhook_enabled=True,
        paid_invoice_webhook_url="https://hooks.example.com/conversions",
        paid_invoice_webhook_secret_encrypted=encrypt_paid_invoice_webhook_secret("webhook-test-secret"),
    )
    event = ProviderOutboxEvent(
        tenant_id=uuid4(), event_type=PAID_INVOICE_WEBHOOK_EVENT, aggregate_type="invoice",
        aggregate_id=uuid4(), payload={}, idempotency_key="paid-invoice:redirect",
    )
    with pytest.raises(ProviderDeliveryError) as exc:
        await _deliver(tenant, event)
    assert exc.value.retryable is False
    assert "redirect" in str(exc.value).lower()
