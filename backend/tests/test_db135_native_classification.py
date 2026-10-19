"""Synthetic read-only projection checks; no production/provider calls."""
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import CustomerCreditEntry, InvoiceSettlement, PaymentOverpayment
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.customer_receivables import account_snapshot, classified_credit_families
from app.services.native_record_classification import load_native_record_policy, policy_digest


def manifest(entries):
    payload = {"version": 1, "review_reference": "synthetic-review", "review_snapshot_sha256": "b" * 64,
               "entries": sorted(entries, key=lambda entry: (entry["tenant_id"], entry["invoice_id"]))}
    payload["policy_sha256"] = policy_digest(payload)
    return payload


def entry(invoice, order, customer_id, classification="real"):
    return {"tenant_id": str(invoice.tenant_id), "invoice_id": str(invoice.id),
            "repair_order_id": str(order.id), "invoice_number": invoice.invoice_number,
            "billed_customer_id": str(invoice.billed_customer_id) if invoice.billed_customer_id else None,
            "resolved_customer_id": str(customer_id), "classification": classification}


def test_policy_strict_integrity_exact_identity_and_tenant_scope():
    tenant, customer = uuid4(), uuid4()
    order = SimpleNamespace(id=uuid4(), tenant_id=tenant)
    invoice = SimpleNamespace(id=uuid4(), tenant_id=tenant, repair_order_id=order.id,
                              invoice_number="SYNTHETIC", billed_customer_id=None)
    payload = manifest([entry(invoice, order, customer)])
    policy = load_native_record_policy(json.dumps(payload))
    assert policy.available
    assert policy.classify(invoice, order, customer, tenant_id=tenant) == "real"
    assert policy.classify(invoice, order, uuid4(), tenant_id=tenant) == "unknown"
    assert policy.classify(invoice, order, customer, tenant_id=uuid4()) == "unknown"
    invoice.invoice_number = "RENAMED"
    assert policy.classify(invoice, order, customer, tenant_id=tenant) == "unknown"
    payload["entries"][0]["classification"] = "test"
    assert not load_native_record_policy(json.dumps(payload)).available


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(version=True),
    lambda p: p.update(extra="forbidden"),
    lambda p: p["entries"][0].update(extra="forbidden"),
    lambda p: p["entries"].append(dict(p["entries"][0])),
    lambda p: p["entries"][0].update(tenant_id="INVALID"),
    lambda p: p["entries"][0].update(classification="paid"),
    lambda p: p.update(review_reference="\nprivate"),
])
def test_malformed_policy_fails_closed_even_with_recomputed_digest(mutate):
    order = SimpleNamespace(id=uuid4(), tenant_id=uuid4())
    invoice = SimpleNamespace(id=uuid4(), tenant_id=order.tenant_id, repair_order_id=order.id,
                              invoice_number="SYNTHETIC", billed_customer_id=None)
    payload = manifest([entry(invoice, order, uuid4())])
    mutate(payload)
    payload["policy_sha256"] = policy_digest(payload)
    assert not load_native_record_policy(json.dumps(payload)).available


def test_missing_duplicate_and_oversized_policy_fail_closed():
    for raw in ("", "{}", '{"version":1,"version":1}', " " * 65537, '{"version":NaN}'):
        assert not load_native_record_policy(raw).available


@pytest.mark.asyncio
async def test_real_test_unknown_and_order_ets_projection_leave_financial_rows_unchanged(db_session, monkeypatch):
    tenant_id, customer_id = uuid4(), uuid4()
    tenant = Tenant(id=tenant_id, name="Classification fixture", slug=f"class-{uuid4().hex[:8]}", timezone="UTC")
    customer = Customer(id=customer_id, tenant_id=tenant_id, first_name="Synthetic", last_name="Customer",
                        email=f"class-{uuid4().hex[:8]}@example.test")
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant_id, customer_id=customer_id, make="Volvo", model="VNR")
    db_session.add_all([tenant, customer, vehicle])
    await db_session.flush()
    invoices, orders, settlements = [], [], []
    for index in range(6):
        order = RepairOrder(id=uuid4(), tenant_id=tenant_id, customer_id=customer_id, vehicle_id=vehicle.id,
                            order_number=f"SYN-RO-{uuid4().hex[:8]}", status=RepairOrderStatus.INVOICED,
                            source="easy_truck_shop_import" if index == 3 else None)
        db_session.add(order)
        await db_session.flush()
        invoice = Invoice(id=uuid4(), tenant_id=tenant_id, repair_order_id=order.id,
                          billed_customer_id=customer_id, invoice_number=f"SYN-INV-{uuid4().hex[:8]}",
                          status=InvoiceStatus.DRAFT if index == 4 else InvoiceStatus.OVERDUE,
                          is_internal=index == 5, subtotal=Decimal("100.00"), total_amount=Decimal("100.00"))
        db_session.add(invoice)
        await db_session.flush()
        settlement = InvoiceSettlement(id=uuid4(), tenant_id=tenant_id, customer_id=customer_id,
                                       invoice_id=invoice.id, principal_total=Decimal("100.00"),
                                       confirmed_principal=Decimal("25.00"), currency="USD",
                                       legacy_reconciliation_status="native")
        db_session.add(settlement)
        db_session.add(Payment(id=uuid4(), tenant_id=tenant_id, invoice_id=invoice.id,
                               payment_number=f"SYN-PAY-{uuid4().hex[:8]}", amount=Decimal("25.00"),
                               method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED))
        invoices.append(invoice)
        orders.append(order)
        settlements.append(settlement)
    await db_session.flush()
    raw = json.dumps(manifest([entry(invoices[index], orders[index], customer_id, choice)
                               for index, choice in ((0, "real"), (1, "test"), (3, "real"))]))
    monkeypatch.setattr(settings, "DB135_NATIVE_RECORD_POLICY_JSON", raw)
    snapshot = await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    assert snapshot["native"]["collectible"] == "75.00"
    assert snapshot["native"]["excluded_test_invoice_count"] == 1
    assert snapshot["native"]["unclassified_invoice_count"] == 1
    assert snapshot["native"]["collectible_complete"] is False
    assert not any(row["invoice_id"] == str(invoices[1].id) for row in snapshot["transactions"])
    unknown = [row for row in snapshot["transactions"] if row["invoice_id"] == str(invoices[2].id)]
    assert len(unknown) == 1 and unknown[0]["amount"] is None and unknown[0]["drilldown_route"] is None
    imported = [row for row in snapshot["transactions"] if row["invoice_id"] == str(invoices[3].id)]
    assert next(row for row in imported if row["kind"] == "invoice")["source_owner"] == "ets_history"
    assert all(row["remaining_principal"] is None for row in imported)
    assert not db_session.dirty and not db_session.new and not db_session.deleted
    assert [settlement.confirmed_principal for settlement in settlements] == [Decimal("25.00")] * 6
    # A test-origin credit applied to a Real invoice invalidates the whole
    # settlement projection; it must never become a partially invented balance.
    origin_id, issue_id = uuid4(), uuid4()
    db_session.add(PaymentOverpayment(id=origin_id, tenant_id=tenant_id, customer_id=customer_id,
        invoice_id=invoices[1].id, settlement_id=settlements[1].id, source_attempt_id=uuid4(),
        amount=Decimal("10.00"), state="credited", consented_at=datetime.now(timezone.utc)))
    for identity, action, source, target, origin in (
        (issue_id, "issued", None, None, origin_id),
        (uuid4(), "applied", issue_id, invoices[0].id, None),
    ):
        db_session.add(CustomerCreditEntry(id=identity, tenant_id=tenant_id, customer_id=customer_id,
            entry_type=action, amount=Decimal("10.00"), source_entry_id=source, target_invoice_id=target,
            origin_overpayment_id=origin, consent_channel="phone", actor_name_snapshot="Synthetic",
            idempotency_key=f"synthetic-{identity}", request_hash="a" * 64))
    await db_session.flush()
    contaminated = await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    assert contaminated["native"]["collectible"] == "0.00"
    assert contaminated["native"]["quarantined_credit_count"] == 1
    assert contaminated["native"]["unapplied_credit"] == "0.00"
    assert not any(row["kind"] in {"credit", "refund"} for row in contaminated["transactions"])
    assert not db_session.dirty and not db_session.new and not db_session.deleted
    assert [settlement.confirmed_principal for settlement in settlements] == [Decimal("25.00")] * 6
    monkeypatch.setattr(settings, "DB135_NATIVE_RECORD_POLICY_JSON", "")
    unavailable = await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    assert unavailable["native"]["collectible"] == "0.00"
    assert unavailable["native"]["classification_policy_available"] is False
    assert unavailable["native"]["collectible_complete"] is False


def test_test_credit_origin_quarantines_real_target_and_transitive_origin():
    tenant, customer, test_invoice, real_invoice, next_invoice = (uuid4() for _ in range(5))
    origin1, origin2 = uuid4(), uuid4()
    issue1 = CustomerCreditEntry(id=uuid4(), tenant_id=tenant, customer_id=customer, entry_type="issued",
                                origin_overpayment_id=origin1, amount=Decimal("10"), consent_channel="phone")
    apply1 = CustomerCreditEntry(id=uuid4(), tenant_id=tenant, customer_id=customer, entry_type="applied",
                                source_entry_id=issue1.id, target_invoice_id=real_invoice, amount=Decimal("5"))
    issue2 = CustomerCreditEntry(id=uuid4(), tenant_id=tenant, customer_id=customer, entry_type="issued",
                                origin_overpayment_id=origin2, amount=Decimal("10"), consent_channel="phone")
    apply2 = CustomerCreditEntry(id=uuid4(), tenant_id=tenant, customer_id=customer, entry_type="applied",
                                source_entry_id=issue2.id, target_invoice_id=next_invoice, amount=Decimal("5"))
    overpayments = {identity: PaymentOverpayment(id=identity, tenant_id=tenant, customer_id=customer,
                    invoice_id=invoice, state="credited", consented_at=datetime.now(timezone.utc))
                    for identity, invoice in ((origin1, test_invoice), (origin2, real_invoice))}
    kept, held, count = classified_credit_families([issue1, apply1, issue2, apply2], overpayments,
        classifications={test_invoice: "test", real_invoice: "real", next_invoice: "real"},
        trusted_invoice_ids={real_invoice, next_invoice},
        account_invoice_ids={test_invoice, real_invoice, next_invoice}, customer_id=customer, tenant_id=tenant)
    assert kept == [] and held == {real_invoice, next_invoice} and count == 2


def test_cross_customer_and_missing_credit_parent_never_leak():
    tenant, customer, invoice = uuid4(), uuid4(), uuid4()
    edge = CustomerCreditEntry(id=uuid4(), tenant_id=tenant, customer_id=uuid4(), entry_type="applied",
                              source_entry_id=uuid4(), target_invoice_id=invoice, amount=Decimal("5"))
    kept, held, count = classified_credit_families([edge], {}, classifications={invoice: "real"},
        trusted_invoice_ids={invoice}, account_invoice_ids={invoice}, customer_id=customer, tenant_id=tenant)
    assert kept == [] and held == {invoice} and count == 1


def test_fully_real_credit_family_survives_and_all_test_family_disappears():
    tenant, customer, invoice, origin_id = uuid4(), uuid4(), uuid4(), uuid4()
    issue = CustomerCreditEntry(id=uuid4(), tenant_id=tenant, customer_id=customer, entry_type="issued",
                               origin_overpayment_id=origin_id, amount=Decimal("10"), consent_channel="phone")
    refund = CustomerCreditEntry(id=uuid4(), tenant_id=tenant, customer_id=customer, entry_type="refunded",
                                source_entry_id=issue.id, amount=Decimal("5"))
    origins = {origin_id: PaymentOverpayment(id=origin_id, tenant_id=tenant, customer_id=customer,
                  invoice_id=invoice, state="credited", consented_at=datetime.now(timezone.utc))}
    for choice, expected in (("real", [issue, refund]), ("test", [])):
        kept, held, count = classified_credit_families([issue, refund], origins,
            classifications={invoice: choice}, trusted_invoice_ids={invoice}, account_invoice_ids={invoice},
            customer_id=customer, tenant_id=tenant)
        assert kept == expected and held == set() and count == 0
