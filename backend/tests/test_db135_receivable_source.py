from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import CustomerCreditEntry
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.receivable_attestation_source import load_receivable_source
from app.services import receivable_attestation_source as source_service


@pytest.mark.asyncio
async def test_source_loader_is_complete_tenant_scoped_and_tombstone_aware(db_session, monkeypatch):
    tenant_id, customer_id, invoice_id, order_id = (uuid4() for _ in range(4))
    other_tenant_id = uuid4()
    tenant = Tenant(id=tenant_id, name="Source Garage", slug=f"source-{uuid4().hex[:8]}", timezone="UTC")
    other_tenant = Tenant(id=other_tenant_id, name="Other Garage", slug=f"other-{uuid4().hex[:8]}", timezone="UTC")
    customer = Customer(id=customer_id, tenant_id=tenant_id, first_name="A", last_name="Customer",
                        email=f"source-{uuid4().hex[:8]}@example.test")
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant_id, customer_id=customer_id, make="Volvo", model="VNR")
    db_session.add_all([tenant, other_tenant, customer, vehicle])
    await db_session.flush()
    order = RepairOrder(id=order_id, tenant_id=tenant_id, customer_id=customer_id,
                        vehicle_id=vehicle.id, order_number=f"RO-{uuid4().hex[:8]}",
                        status=RepairOrderStatus.INVOICED)
    db_session.add(order)
    await db_session.flush()
    invoice = Invoice(id=invoice_id, tenant_id=tenant_id, repair_order_id=order_id,
                      billed_customer_id=customer_id, invoice_number=f"INV-{uuid4().hex[:8]}",
                      status=InvoiceStatus.OVERDUE, subtotal=Decimal("100.00"),
                      total_amount=Decimal("100.00"))
    db_session.add(invoice)
    await db_session.flush()

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        await load_receivable_source(db_session, tenant_id=tenant_id, invoice_id=invoice_id)
    async def disposable_test_transaction(_db, *, read_only):
        assert read_only is True
    monkeypatch.setattr(source_service, "_verify_transaction", disposable_test_transaction)
    with pytest.raises(HTTPException) as wrong_tenant:
        await load_receivable_source(db_session, tenant_id=other_tenant_id, invoice_id=invoice_id)
    assert wrong_tenant.value.status_code == 404

    initial = await load_receivable_source(db_session, tenant_id=tenant_id, invoice_id=invoice_id)
    assert initial.linked_rows["payments"] == []
    payment = Payment(id=uuid4(), tenant_id=tenant_id, invoice_id=invoice_id,
                      payment_number=f"PAY-{uuid4().hex[:8]}", amount=Decimal("20.00"),
                      method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED)
    db_session.add(payment)
    await db_session.flush()
    inserted = await load_receivable_source(db_session, tenant_id=tenant_id, invoice_id=invoice_id)
    assert len(inserted.linked_rows["payments"]) == 1
    assert inserted.fingerprint != initial.fingerprint

    payment.deleted_at = datetime(2026, 10, 18, tzinfo=timezone.utc)
    await db_session.flush()
    tombstoned = await load_receivable_source(db_session, tenant_id=tenant_id, invoice_id=invoice_id)
    assert tombstoned.linked_rows["payments"][0].deleted_at is not None
    assert tombstoned.fingerprint != inserted.fingerprint

    invoice.due_date = datetime(2026, 10, 1, tzinfo=timezone.utc)
    await db_session.flush()
    due_drift = await load_receivable_source(db_session, tenant_id=tenant_id, invoice_id=invoice_id)
    assert due_drift.fingerprint != tombstoned.fingerprint

    # A misattributed same-tenant credit targeting this invoice is evidence,
    # even though it belongs to a different customer account.
    other_customer = Customer(id=uuid4(), tenant_id=tenant_id, first_name="B", last_name="Customer",
                              email=f"other-{uuid4().hex[:8]}@example.test")
    db_session.add(other_customer)
    await db_session.flush()
    conflicting_credit = CustomerCreditEntry(id=uuid4(), tenant_id=tenant_id, customer_id=other_customer.id,
                                             target_invoice_id=invoice_id, entry_type="applied",
                                             amount=Decimal("5.00"), actor_name_snapshot="Test",
                                             idempotency_key=f"test-{uuid4().hex}", request_hash="a" * 64)
    db_session.add(conflicting_credit)
    await db_session.flush()
    conflict = await load_receivable_source(db_session, tenant_id=tenant_id, invoice_id=invoice_id)
    assert any(row.id == conflicting_credit.id for row in conflict.linked_rows["customer_credits"])
    assert conflict.fingerprint != due_drift.fingerprint

    second_payment = Payment(id=uuid4(), tenant_id=tenant_id, invoice_id=invoice_id,
                             payment_number=f"PAY-{uuid4().hex[:8]}", amount=Decimal("5.00"),
                             method=PaymentMethod.ZELLE, status=PaymentStatus.COMPLETED)
    db_session.add(second_payment)
    await db_session.flush()
    monkeypatch.setattr("app.services.receivable_attestation_source.MAX_SOURCE_ROWS_PER_KIND", 1)
    with pytest.raises(HTTPException) as oversized:
        await load_receivable_source(db_session, tenant_id=tenant_id, invoice_id=invoice_id)
    assert oversized.value.status_code == 413
