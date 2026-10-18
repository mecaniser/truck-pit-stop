from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.services.receivable_attestation_fingerprint import (
    REQUIRED_RELATIONS, _row_payload, fingerprint_source_bundle,
)


def _source():
    tenant_id, customer_id, order_id, invoice_id = (uuid4() for _ in range(4))
    customer = Customer(id=customer_id, tenant_id=tenant_id, first_name="A")
    order = RepairOrder(id=order_id, tenant_id=tenant_id, customer_id=customer_id,
                        status=RepairOrderStatus.INVOICED)
    invoice = Invoice(id=invoice_id, tenant_id=tenant_id, repair_order_id=order_id,
                      billed_customer_id=customer_id, status=InvoiceStatus.PAID,
                      subtotal=Decimal("100.00"), total_amount=Decimal("100.00"))
    payments = [Payment(id=uuid4(), tenant_id=tenant_id, invoice_id=invoice_id,
                        amount=Decimal("25.00"), method=PaymentMethod.CASH,
                        status=PaymentStatus.COMPLETED),
                Payment(id=uuid4(), tenant_id=tenant_id, invoice_id=invoice_id,
                        amount=Decimal("75.00"), method=PaymentMethod.ZELLE,
                        status=PaymentStatus.COMPLETED)]
    rows = {kind: [] for kind in REQUIRED_RELATIONS}
    rows["payments"] = payments
    return tenant_id, invoice, order, customer, rows


def test_receivable_fingerprint_is_stable_and_tracks_tombstones_and_source_drift():
    tenant_id, invoice, order, customer, rows = _source()
    args = dict(tenant_id=tenant_id, invoice=invoice, order=order, customer=customer)
    first = fingerprint_source_bundle(**args, linked_rows=rows)
    rows["payments"].reverse()
    assert fingerprint_source_bundle(**args, linked_rows=rows) == first
    rows["payments"][0].deleted_at = datetime(2026, 10, 18, tzinfo=timezone.utc)
    assert fingerprint_source_bundle(**args, linked_rows=rows) != first
    rows["payments"][0].deleted_at = None
    rows["payments"][0].amount = Decimal("76.00")
    assert fingerprint_source_bundle(**args, linked_rows=rows) != first


def test_provider_reference_is_digested_and_changes_fingerprint():
    tenant_id, invoice, order, customer, rows = _source()
    payment = rows["payments"][0]
    payment.stripe_charge_id = "private-provider-charge"
    assert "private-provider-charge" not in str(_row_payload(payment))
    first = fingerprint_source_bundle(tenant_id=tenant_id, invoice=invoice, order=order,
                                      customer=customer, linked_rows=rows)
    payment.stripe_charge_id = "different-provider-charge"
    assert fingerprint_source_bundle(tenant_id=tenant_id, invoice=invoice, order=order,
                                     customer=customer, linked_rows=rows) != first


def test_receivable_fingerprint_requires_complete_tenant_scoped_relation_map():
    tenant_id, invoice, order, customer, rows = _source()
    args = dict(tenant_id=tenant_id, invoice=invoice, order=order, customer=customer)
    with pytest.raises(ValueError, match="relation map incomplete"):
        fingerprint_source_bundle(**args, linked_rows={"payments": rows["payments"]})
    rows["payments"][0].tenant_id = uuid4()
    with pytest.raises(ValueError, match="tenant mismatch"):
        fingerprint_source_bundle(**args, linked_rows=rows)
    rows["payments"][0].tenant_id = tenant_id
    invoice.billed_customer_id = uuid4()
    with pytest.raises(ValueError, match="bill-to mismatch"):
        fingerprint_source_bundle(**args, linked_rows=rows)


def test_receivable_fingerprint_tracks_insert_status_due_and_rejects_bad_rows(monkeypatch):
    tenant_id, invoice, order, customer, rows = _source()
    args = dict(tenant_id=tenant_id, invoice=invoice, order=order, customer=customer)
    first = fingerprint_source_bundle(**args, linked_rows=rows)
    invoice.status = InvoiceStatus.OVERDUE
    assert fingerprint_source_bundle(**args, linked_rows=rows) != first
    invoice.status = InvoiceStatus.PAID
    invoice.due_date = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert fingerprint_source_bundle(**args, linked_rows=rows) != first
    invoice.due_date = None
    rows["payments"].append(Payment(id=uuid4(), tenant_id=tenant_id, invoice_id=invoice.id,
                                    amount=Decimal("1.00"), method=PaymentMethod.CASH,
                                    status=PaymentStatus.COMPLETED))
    assert fingerprint_source_bundle(**args, linked_rows=rows) != first
    rows["payments"].append(rows["payments"][0])
    with pytest.raises(ValueError, match="duplicated"):
        fingerprint_source_bundle(**args, linked_rows=rows)
    rows["payments"].pop()
    monkeypatch.setattr("app.services.receivable_attestation_fingerprint.MAX_SOURCE_ROWS_PER_KIND", 2)
    with pytest.raises(ValueError, match="safe read limit"):
        fingerprint_source_bundle(**args, linked_rows=rows)


def test_receivable_fingerprint_rejects_unsupported_json_value():
    tenant_id, invoice, order, customer, rows = _source()
    invoice.line_items_snapshot = {"unexpected": {1, 2}}
    with pytest.raises(TypeError, match="Unsupported attestation source value"):
        fingerprint_source_bundle(tenant_id=tenant_id, invoice=invoice, order=order,
                                  customer=customer, linked_rows=rows)
