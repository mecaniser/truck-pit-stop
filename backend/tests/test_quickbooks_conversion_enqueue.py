from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.services import quickbooks_payment_finalization as finalization
from app.services.quickbooks_payments_service import QuickBooksCharge


@pytest.mark.asyncio
async def test_quickbooks_finalization_enqueues_paid_conversion(db_session, monkeypatch):
    tenant = Tenant(
        name="QuickBooks Conversion", slug=f"qb-conversion-{uuid4().hex}",
        paid_invoice_webhook_enabled=True,
        paid_invoice_webhook_url="https://hooks.example.com/conversions",
        paid_invoice_webhook_secret_encrypted="encrypted",
    )
    customer = Customer(tenant=tenant, first_name="Quick", last_name="Books", email="qb@example.com")
    order = RepairOrder(
        tenant=tenant, customer=customer, vehicle_id=uuid4(), order_number=f"RO-{uuid4().hex}",
        status=RepairOrderStatus.INVOICED,
    )
    invoice = Invoice(
        tenant=tenant, repair_order=order, invoice_number=f"INV-{uuid4().hex}", status=InvoiceStatus.SENT,
        subtotal=Decimal("85"), tax_amount=Decimal("0"), discount_amount=Decimal("0"), total_amount=Decimal("85"),
    )
    db_session.add_all([tenant, customer, order, invoice])
    await db_session.commit()

    async def noop(**_kwargs):
        return None

    monkeypatch.setattr(finalization, "broadcast_payment_received", noop)
    monkeypatch.setattr(finalization, "broadcast_repair_order_update", noop)
    monkeypatch.setattr(finalization, "send_invoice_payment_confirmation_email", noop)
    monkeypatch.setattr(finalization, "record_payment", lambda **_kwargs: None)

    await finalization.finalize_quickbooks_invoice_payment(
        db=db_session,
        invoice=invoice,
        order=order,
        customer=customer,
        tenant=tenant,
        vehicle=None,
        charge=QuickBooksCharge(id="charge-1", status="CAPTURED", amount=Decimal("85"), raw={}),
        idempotency_key="qb-conversion-1",
    )
    event = (await db_session.execute(select(ProviderOutboxEvent))).scalar_one()
    assert event.event_type == "repair_order.paid"
    assert event.aggregate_id == invoice.id
    assert event.payload["total_amount"] == 85.0
