from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import quickbooks
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.quickbooks_payments_service import QuickBooksRefund


@pytest.mark.asyncio
async def test_quickbooks_refund_enqueues_negative_conversion(db_session, monkeypatch):
    tenant = Tenant(
        name="Refund Garage", slug=f"refund-{uuid4().hex}", paid_invoice_webhook_enabled=True,
        paid_invoice_webhook_url="https://hooks.example.com/conversions",
        paid_invoice_webhook_secret_encrypted="encrypted",
    )
    owner = User(
        tenant=tenant, email=f"owner-{uuid4().hex}@example.com", hashed_password="x", first_name="Owner",
        last_name="One", role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    customer = Customer(tenant=tenant, first_name="Test", last_name="Customer", email="refund@example.com")
    order = RepairOrder(
        tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"RO-{uuid4().hex}",
        status=RepairOrderStatus.PAID,
    )
    invoice = Invoice(
        tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.PAID,
        subtotal=Decimal("100"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("100"),
    )
    payment = Payment(
        tenant=tenant, invoice=invoice, payment_number=f"PAY-{uuid4().hex}", amount=Decimal("100"),
        method=PaymentMethod.QUICKBOOKS, status=PaymentStatus.COMPLETED,
        quickbooks_charge_id="charge-refund", quickbooks_charge_status="CAPTURED",
    )
    db_session.add_all([tenant, owner, customer, order, invoice, payment])
    await db_session.commit()

    async def connection(*_args, **_kwargs):
        return object()

    async def noop(*_args, **_kwargs):
        return None

    async def refund(**_kwargs):
        return QuickBooksRefund(id="refund-1", status="SUCCEEDED", amount=Decimal("25"), raw={})

    monkeypatch.setattr(quickbooks, "_get_connection", connection)
    monkeypatch.setattr(quickbooks, "_refresh_connection_if_needed", noop)
    monkeypatch.setattr(quickbooks, "refund_charge", refund)
    monkeypatch.setattr(quickbooks, "create_refund_receipt", noop)

    response = await quickbooks.refund_quickbooks_payment(
        payment.id,
        quickbooks.QuickBooksRefundRequest(amount=Decimal("25"), reason="Customer adjustment"),
        db=db_session,
        current_user=owner,
    )
    assert response.status == "SUCCEEDED"
    event = (await db_session.execute(select(ProviderOutboxEvent))).scalar_one()
    assert event.event_type == "repair_order.payment_refunded"
    assert event.payload["total_amount"] == -25.0
    assert invoice.status == InvoiceStatus.SENT
    assert order.status == RepairOrderStatus.INVOICED
