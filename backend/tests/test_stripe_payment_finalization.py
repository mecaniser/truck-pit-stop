from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.endpoints import stripe_webhooks
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.services import stripe_payment_finalization as svc


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FinalizeSession:
    def __init__(self, existing_payment: Payment | None = None):
        self.existing_payment = existing_payment
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshes: list[object] = []
        self.payment_queries = 0

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is Payment:
            self.payment_queries += 1
            return _ScalarResult(self.existing_payment)
        raise AssertionError(f"Unexpected query entity: {entity}")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        self.refreshes.append(obj)


class _WebhookSession:
    def __init__(self, invoice: Invoice, tenant: Tenant):
        self.invoice = invoice
        self.tenant = tenant
        self.execute_calls = 0

    async def execute(self, statement):
        self.execute_calls += 1
        entity = statement.column_descriptions[0].get("entity")
        if self.execute_calls == 1:
            assert entity is Invoice
            return _ScalarResult(self.invoice)
        if self.execute_calls == 2:
            assert entity is Tenant
            return _ScalarResult(self.tenant)
        raise AssertionError(f"Unexpected query call #{self.execute_calls} for entity {entity}")


def _entities():
    tenant_id = uuid4()
    customer_id = uuid4()
    order_id = uuid4()
    invoice_id = uuid4()
    vehicle_id = uuid4()

    tenant = Tenant(id=tenant_id, name="Stripe Flow Garage", slug="stripe-flow-garage")
    customer = Customer(
        id=customer_id,
        tenant_id=tenant_id,
        first_name="Card",
        last_name="Customer",
        email="card@example.com",
    )
    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number="RO-STRIPE",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("100.00"),
        total_cost=Decimal("100.00"),
    )
    invoice = Invoice(
        id=invoice_id,
        tenant_id=tenant_id,
        repair_order_id=order_id,
        invoice_number="INV-STRIPE",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("100.00"),
        shop_supplies_amount=Decimal("0.00"),
        service_fee_amount=Decimal("3.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("103.00"),
    )
    invoice.repair_order = order
    order.customer = customer
    return tenant, customer, order, invoice


@pytest.mark.asyncio
async def test_finalize_stripe_invoice_payment_creates_payment_and_marks_paid(monkeypatch):
    tenant, customer, order, invoice = _entities()
    tenant.paid_invoice_webhook_enabled = True
    tenant.paid_invoice_webhook_url = "https://example.test/conversions"
    tenant.paid_invoice_webhook_secret_encrypted = "encrypted-test-secret"
    fake_db = _FinalizeSession()
    broadcasts: list[tuple[str, dict]] = []
    emails: list[dict] = []

    async def _payment_number(_db, _tenant_id):
        return "PAY-TEST-000001"

    async def _broadcast_payment(**kwargs):
        broadcasts.append(("payment", kwargs))

    async def _broadcast_order(**kwargs):
        broadcasts.append(("order", kwargs))

    async def _send_email(**kwargs):
        emails.append(kwargs)

    monkeypatch.setattr(svc, "allocate_next_payment_number", _payment_number)
    monkeypatch.setattr(svc, "broadcast_payment_received", _broadcast_payment)
    monkeypatch.setattr(svc, "broadcast_repair_order_update", _broadcast_order)
    monkeypatch.setattr(svc, "send_invoice_payment_confirmation_email", _send_email)
    monkeypatch.setattr(svc, "record_payment", lambda **_kwargs: None)

    result = await svc.finalize_stripe_invoice_payment(
        db=fake_db,
        invoice=invoice,
        order=order,
        customer=customer,
        tenant=tenant,
        vehicle=None,
        payment_intent={
            "id": "pi_succeeded",
            "metadata": {
                "invoice_id": str(invoice.id),
                "stripe_connected_account_id": "acct_123",
                "platform_fee_percent": "1.500",
                "platform_fee_amount_cents": "155",
            },
            "latest_charge": "ch_123",
        },
        payment_note="Payment made by test.",
    )

    assert result.created is True
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.paid_at is not None
    assert order.status == RepairOrderStatus.PAID
    assert fake_db.commits == 1
    payment = next(obj for obj in fake_db.added if isinstance(obj, Payment))
    assert payment.payment_number == "PAY-TEST-000001"
    assert payment.method == PaymentMethod.STRIPE
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.stripe_payment_intent_id == "pi_succeeded"
    assert payment.stripe_charge_id == "ch_123"
    assert payment.stripe_connected_account_id == "acct_123"
    assert payment.stripe_platform_fee_percent == Decimal("1.500")
    assert payment.stripe_platform_fee_amount == Decimal("1.55")
    assert len(broadcasts) == 2
    assert len(emails) == 1
    events = [obj for obj in fake_db.added if isinstance(obj, ProviderOutboxEvent)]
    assert len(events) == 1
    assert events[0].event_type == "repair_order.paid"
    assert events[0].payload["repair_order_id"] == "RO-STRIPE"


@pytest.mark.asyncio
async def test_finalize_stripe_invoice_payment_is_idempotent_for_existing_intent(monkeypatch):
    tenant, customer, order, invoice = _entities()
    tenant.paid_invoice_webhook_enabled = True
    tenant.paid_invoice_webhook_url = "https://example.test/conversions"
    tenant.paid_invoice_webhook_secret_encrypted = "encrypted-test-secret"
    invoice.status = InvoiceStatus.PAID
    existing = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        payment_number="PAY-TEST-000001",
        amount=invoice.total_amount,
        method=PaymentMethod.STRIPE,
        status=PaymentStatus.COMPLETED,
        stripe_payment_intent_id="pi_succeeded",
    )
    fake_db = _FinalizeSession(existing_payment=existing)
    monkeypatch.setattr(svc, "record_payment", lambda **_kwargs: None)

    result = await svc.finalize_stripe_invoice_payment(
        db=fake_db,
        invoice=invoice,
        order=order,
        customer=customer,
        tenant=tenant,
        vehicle=None,
        payment_intent={"id": "pi_succeeded", "metadata": {"invoice_id": str(invoice.id)}},
        payment_note="Payment made by test.",
    )

    assert result.created is False
    assert result.payment is existing
    assert fake_db.added == []
    assert fake_db.commits == 0


@pytest.mark.asyncio
async def test_payment_succeeded_webhook_invokes_local_finalization(monkeypatch):
    tenant, customer, order, invoice = _entities()
    fake_db = _WebhookSession(invoice=invoice, tenant=tenant)
    captured = {}

    async def _finalize(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(created=True)

    monkeypatch.setattr(stripe_webhooks, "finalize_stripe_invoice_payment", _finalize)

    await stripe_webhooks._handle_payment_succeeded(
        fake_db,
        {
            "id": "pi_webhook",
            "metadata": {"invoice_id": str(invoice.id)},
        },
    )

    assert fake_db.execute_calls == 2
    assert captured["invoice"] is invoice
    assert captured["order"] is order
    assert captured["customer"] is customer
    assert captured["tenant"] is tenant
    assert captured["payment_intent"]["id"] == "pi_webhook"
    assert captured["allow_already_paid_without_payment"] is True
