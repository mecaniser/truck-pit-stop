from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.customer_receivables import render_statement_pdf
from app.api.v1.endpoints import customer_receivables as account_endpoints
from app.core.dependencies import get_current_active_user
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import CustomerCreditEntry, InvoiceSettlement, PaymentOverpayment
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.services.customer_receivables import (
    _credit_remaining, account_snapshot, bucket_for, credit_effect, decode_cursor, encode_cursor, trusted_settlement,
)
from app.services import customer_receivables as account_service
from app.services.native_record_classification import policy_digest
from app.core.config import settings
import json


def test_bucket_edges_and_cursor_scope():
    today = date(2026, 10, 17)
    assert bucket_for(None, today) == "undated_due"
    assert bucket_for(today + timedelta(days=1), today) == "current"
    for days, expected in ((0, "current"), (1, "days_1_30"), (30, "days_1_30"),
                           (31, "days_31_60"), (60, "days_31_60"), (61, "days_61_90"),
                           (90, "days_61_90"), (91, "days_90_plus")):
        assert bucket_for(today - timedelta(days=days), today) == expected
    tenant_id, customer_id = uuid4(), uuid4()
    row = {"occurred_at": "2026-10-17T12:00:00Z", "source_date": None, "kind": "invoice", "id": str(uuid4())}
    cursor = encode_cursor(tenant_id, customer_id, "native", row)
    assert decode_cursor(cursor, tenant_id, customer_id, "native") == (row["occurred_at"], row["kind"], row["id"])
    with pytest.raises(Exception) as wrong_customer:
        decode_cursor(cursor, tenant_id, uuid4(), "native")
    assert wrong_customer.value.status_code == 422
    with pytest.raises(Exception) as tampered:
        decode_cursor(cursor[:-1] + ("A" if cursor[-1] != "A" else "B"), tenant_id, customer_id, "native")
    assert tampered.value.status_code == 422


def test_trusted_settlement_requires_exact_principal_and_no_paid_baseline():
    tenant_id, customer_id, invoice_id = uuid4(), uuid4(), uuid4()
    invoice = Invoice(id=invoice_id, tenant_id=tenant_id, repair_order_id=uuid4(),
                      invoice_number="INV-TRUST", status=InvoiceStatus.PAID,
                      subtotal=Decimal("100.00"), total_amount=Decimal("100.00"))
    settlement = InvoiceSettlement(id=uuid4(), tenant_id=tenant_id, customer_id=customer_id,
                                   invoice_id=invoice_id, principal_total=Decimal("100.00"),
                                   confirmed_principal=Decimal("40.00"),
                                   legacy_reconciliation_status="reconciled", currency="USD")
    assert trusted_settlement(invoice, settlement, customer_id=customer_id, bad_baseline=False)
    settlement.deleted_at = datetime.now(timezone.utc)
    assert not trusted_settlement(invoice, settlement, customer_id=customer_id, bad_baseline=False)
    settlement.deleted_at = None
    assert not trusted_settlement(invoice, settlement, customer_id=customer_id, bad_baseline=True)
    settlement.legacy_reconciliation_status = "legacy_paid_snapshot"
    assert not trusted_settlement(invoice, settlement, customer_id=customer_id, bad_baseline=False)
    settlement.legacy_reconciliation_status = "native"
    settlement.principal_total = Decimal("99.99")
    assert not trusted_settlement(invoice, settlement, customer_id=customer_id, bad_baseline=False)
    settlement.principal_total = Decimal("100.00")
    settlement.customer_id = uuid4()
    assert not trusted_settlement(invoice, settlement, customer_id=customer_id, bad_baseline=False)


def test_credit_only_direct_origin_children_reduce_available_balance():
    tenant_id, customer_id, overpayment_id, issue_id, application_id = (uuid4() for _ in range(5))
    overpayment = PaymentOverpayment(id=overpayment_id, tenant_id=tenant_id, customer_id=customer_id,
                                     state="credited", consented_at=datetime.now(timezone.utc))
    issue = CustomerCreditEntry(id=issue_id, tenant_id=tenant_id, customer_id=customer_id,
                                entry_type="issued", amount=Decimal("20.00"),
                                origin_overpayment_id=overpayment_id, consent_channel="phone")
    applied = CustomerCreditEntry(id=application_id, tenant_id=tenant_id, customer_id=customer_id,
                                  entry_type="applied", amount=Decimal("7.00"), source_entry_id=issue_id)
    reversal = CustomerCreditEntry(id=uuid4(), tenant_id=tenant_id, customer_id=customer_id,
                                   entry_type="reversed", amount=Decimal("7.00"), source_entry_id=application_id)
    assert _credit_remaining([issue, applied, reversal], {overpayment_id: overpayment}) == Decimal("13.00")
    by_id = {entry.id: entry for entry in (issue, applied, reversal)}
    assert credit_effect(issue, by_id, {overpayment_id: overpayment}) == "increase"
    assert credit_effect(applied, by_id, {overpayment_id: overpayment}) == "decrease"
    assert credit_effect(reversal, by_id, {overpayment_id: overpayment}) == "audit"
    overpayment.state = "refund_required"
    assert _credit_remaining([issue, applied, reversal], {overpayment_id: overpayment}) == Decimal("0.00")
    assert credit_effect(issue, by_id, {overpayment_id: overpayment}) == "audit"
    assert credit_effect(applied, by_id, {overpayment_id: overpayment}) == "audit"


def test_statement_identifies_entries_and_discloses_truncation(monkeypatch):
    original_canvas = account_endpoints.canvas.Canvas

    def uncompressed_canvas(*args, **kwargs):
        kwargs["pageCompression"] = 0
        return original_canvas(*args, **kwargs)

    monkeypatch.setattr(account_endpoints.canvas, "Canvas", uncompressed_canvas)
    row = {"id": str(uuid4()), "kind": "payment", "source_owner": "native",
           "occurred_at": "2026-10-17T12:00:00Z", "source_date": None,
           "invoice_id": str(uuid4()), "invoice_number": "INV-ACCOUNT-1",
           "amount": "5.00", "remaining_principal": None, "credit_action": None}
    snapshot = {"customer": {"name": "A <script> customer"}, "generated_at": "2026-10-17T12:00:00Z",
                "as_of_date": "2026-10-17", "native": {"collectible": "0.00", "collectible_complete": True,
                "unverified_invoice_count": 0, "current": "0.00",
                "days_1_30": "0.00", "days_31_60": "0.00", "days_61_90": "0.00",
                "days_90_plus": "0.00", "undated_due": "0.00", "unapplied_credit": "0.00",
                "review_required_count": 0}, "ets_history": {"review_required_count": 0},
                "transactions": [row] * 201}
    pdf = render_statement_pdf(snapshot)
    assert pdf.startswith(b"%PDF-")
    assert row["id"].encode() in pdf and b"INV-ACCOUNT-1" in pdf
    assert b"1 activity rows omitted" in pdf
    assert len(pdf) < account_endpoints.PDF_BYTES_CAP
    snapshot["native"]["collectible_complete"] = False
    snapshot["native"]["unverified_invoice_count"] = 1
    incomplete_pdf = render_statement_pdf(snapshot)
    assert b"Native balance incomplete" in incomplete_pdf
    assert b"Verified native subtotal only" in incomplete_pdf
    snapshot["native"]["reviewed_attestation_count"] = 1
    snapshot["transactions"][0] = {**row, "reconciliation_basis": "reviewed_attestation"}
    reviewed_pdf = render_statement_pdf(snapshot)
    assert b"time-limited" in reviewed_pdf.lower()
    assert b"Reviewed historical receivable; not a native settlement" in reviewed_pdf


@pytest.mark.asyncio
async def test_account_api_denies_receptionist_and_ungranted_admin_then_pages(client, monkeypatch):
    from app.main import app

    tenant_id, customer_id = uuid4(), uuid4()
    native_id, ets_id = uuid4(), uuid4()
    principal = SimpleNamespace(role=UserRole.RECEPTIONIST, tenant_id=tenant_id, permissions={})
    extra_rows = []

    async def fake_user():
        return principal

    async def fake_snapshot(_tenant_id, _customer_id):
        assert _tenant_id == tenant_id and _customer_id == customer_id
        return {
            "as_of_date": "2026-10-17", "generated_at": "2026-10-17T12:00:00+00:00",
            "currency": "USD", "customer": {"id": str(customer_id), "name": "Customer"},
            "native": {"collectible": "0.00", "collectible_complete": True,
                       "unverified_invoice_count": 0, "current": "0.00", "days_1_30": "0.00",
                       "days_31_60": "0.00", "days_61_90": "0.00", "days_90_plus": "0.00",
                       "undated_due": "0.00", "unapplied_credit": "0.00", "review_required_count": 0},
            "ets_history": {"observed_open_balance": None, "balance_basis": "unavailable",
                            "review_required_count": 0, "collectible": False},
            "transactions": extra_rows + [{"id": str(native_id), "source_owner": "native", "kind": "invoice",
                              "occurred_at": "2026-10-17T12:00:00+00:00", "source_date": None,
                              "amount": "10.00", "remaining_principal": "10.00"},
                             {"id": str(ets_id), "source_owner": "ets_history", "kind": "invoice",
                              "occurred_at": None, "source_date": "2025-01-05",
                              "amount": "20.00", "remaining_principal": None}],
        }

    app.dependency_overrides[get_current_active_user] = fake_user
    monkeypatch.setattr(account_endpoints, "_snapshot", fake_snapshot)
    path = f"/api/v1/customers/{customer_id}/account"
    assert (await client.get(path)).status_code == 403
    assert (await client.get(f"{path}/statement.pdf")).status_code == 403
    principal.role = UserRole.GARAGE_ADMIN
    assert (await client.get(path)).status_code == 403
    principal.permissions = {"payments": True}
    assert (await client.get(path, params={"source_filter": "invalid"})).status_code == 422
    first_response = await client.get(path, params={"limit": 1})
    assert set(part.strip() for part in first_response.headers["cache-control"].split(",")) == {"private", "no-store"}
    first = first_response.json()
    assert len(first["transactions"]) == 1 and first["next_cursor"]
    extra_rows.append({"id": str(uuid4()), "source_owner": "native", "kind": "payment",
                       "occurred_at": "2026-10-18T12:00:00+00:00", "source_date": None,
                       "amount": "1.00", "remaining_principal": None})
    second = (await client.get(path, params={"limit": 1, "cursor": first["next_cursor"]})).json()
    assert len(second["transactions"]) == 1 and second["next_cursor"] is None
    assert second["transactions"][0]["source_owner"] == "ets_history"
    assert (await client.get(path.replace(str(customer_id), str(uuid4())),
                             params={"cursor": first["next_cursor"]})).status_code == 422
    assert (await client.get(f"{path}/statement.pdf")).headers["content-type"] == "application/pdf"


@pytest.mark.asyncio
async def test_account_separates_native_ets_and_orphan_bill_to_without_double_count(db_session, monkeypatch):
    tenant_id, customer_id, other_id = uuid4(), uuid4(), uuid4()
    tenant = Tenant(id=tenant_id, name="Account Garage", slug=f"account-{uuid4().hex[:8]}", timezone="UTC")
    customer = Customer(id=customer_id, tenant_id=tenant_id, first_name="A", last_name="Customer",
                        email=f"a-{uuid4().hex[:8]}@example.test")
    other = Customer(id=other_id, tenant_id=tenant_id, first_name="B", last_name="Customer",
                     email=f"b-{uuid4().hex[:8]}@example.test")
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant_id, customer_id=customer_id, make="Volvo", model="VNR")
    db_session.add_all([tenant, customer, other, vehicle])
    await db_session.flush()
    orders = [RepairOrder(id=uuid4(), tenant_id=tenant_id, customer_id=customer_id,
                          vehicle_id=vehicle.id, order_number=f"RO-{uuid4().hex[:8]}",
                          status=RepairOrderStatus.INVOICED) for _ in range(6)]
    db_session.add_all(orders)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    orders[5].deleted_at = now
    native = Invoice(id=uuid4(), tenant_id=tenant_id, repair_order_id=orders[0].id,
                     billed_customer_id=None, invoice_number=f"INV-{uuid4().hex[:8]}",
                     status=InvoiceStatus.SENT, subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
                     due_date=now - timedelta(days=31))
    imported = Invoice(id=uuid4(), tenant_id=tenant_id, repair_order_id=orders[1].id,
                       billed_customer_id=customer_id, invoice_number=f"INV-{uuid4().hex[:8]}",
                       status=InvoiceStatus.PAID, subtotal=Decimal("500.00"), total_amount=Decimal("500.00"),
                       source="easy_truck_shop_import", ets_invoiced_at=date(2025, 1, 5))
    orphan = Invoice(id=uuid4(), tenant_id=tenant_id, repair_order_id=orders[2].id,
                     billed_customer_id=uuid4(), invoice_number=f"INV-{uuid4().hex[:8]}",
                     status=InvoiceStatus.SENT, subtotal=Decimal("900.00"), total_amount=Decimal("900.00"))
    reassigned = Invoice(id=uuid4(), tenant_id=tenant_id, repair_order_id=orders[3].id,
                         billed_customer_id=other_id, invoice_number=f"INV-{uuid4().hex[:8]}",
                         status=InvoiceStatus.SENT, subtotal=Decimal("300.00"), total_amount=Decimal("300.00"))
    missing_settlement = Invoice(id=uuid4(), tenant_id=tenant_id, repair_order_id=orders[4].id,
                                 billed_customer_id=customer_id, invoice_number=f"INV-{uuid4().hex[:8]}",
                                 status=InvoiceStatus.OVERDUE, subtotal=Decimal("200.00"),
                                 total_amount=Decimal("200.00"), due_date=now - timedelta(days=91))
    deleted_order_invoice = Invoice(id=uuid4(), tenant_id=tenant_id, repair_order_id=orders[5].id,
                                    billed_customer_id=customer_id, invoice_number=f"INV-{uuid4().hex[:8]}",
                                    status=InvoiceStatus.OVERDUE, subtotal=Decimal("400.00"),
                                    total_amount=Decimal("400.00"), due_date=now - timedelta(days=91))
    db_session.add_all([native, imported, orphan, reassigned, missing_settlement, deleted_order_invoice])
    await db_session.flush()
    native_settlement = InvoiceSettlement(id=uuid4(), tenant_id=tenant_id, invoice_id=native.id,
                                          customer_id=customer_id, principal_total=Decimal("100.00"),
                                          confirmed_principal=Decimal("25.00"), legacy_reconciliation_status="native")
    db_session.add(native_settlement)
    db_session.add(InvoiceSettlement(id=uuid4(), tenant_id=tenant_id, invoice_id=deleted_order_invoice.id,
                                     customer_id=customer_id, principal_total=Decimal("400.00"),
                                     confirmed_principal=Decimal("0.00"), legacy_reconciliation_status="native"))
    db_session.add(Payment(id=uuid4(), tenant_id=tenant_id, invoice_id=native.id,
                           payment_number=f"PAY-{uuid4().hex[:8]}", amount=Decimal("25.00"),
                           method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED))
    orphan_payment = Payment(id=uuid4(), tenant_id=tenant_id, invoice_id=orphan.id,
                             payment_number=f"PAY-{uuid4().hex[:8]}", amount=Decimal("900.00"),
                             method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED)
    db_session.add(orphan_payment)
    pending_payment = Payment(id=uuid4(), tenant_id=tenant_id, invoice_id=native.id,
                              payment_number=f"PAY-{uuid4().hex[:8]}", amount=Decimal("70.00"),
                              method=PaymentMethod.ZELLE, status=PaymentStatus.PENDING)
    db_session.add(pending_payment)
    mixed_history_payment = Payment(id=uuid4(), tenant_id=tenant_id, invoice_id=imported.id,
                                    payment_number=f"PAY-{uuid4().hex[:8]}", amount=Decimal("10.00"),
                                    method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED)
    db_session.add(mixed_history_payment)
    await db_session.flush()

    with monkeypatch.context() as bound:
        bound.setattr(account_service, "MAX_ACCOUNT_INVOICES", 1)
        with pytest.raises(HTTPException) as oversized:
            await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
        assert oversized.value.status_code == 413
    policy = {"version": 1, "review_reference": "synthetic-test-review",
              "review_snapshot_sha256": "a" * 64, "entries": sorted([
                  {"tenant_id": str(tenant_id), "invoice_id": str(item.id),
                   "invoice_number": item.invoice_number, "repair_order_id": str(item.repair_order_id),
                   "billed_customer_id": str(item.billed_customer_id) if item.billed_customer_id else None,
                   "resolved_customer_id": str(other_id if item is reassigned else customer_id),
                   "classification": "real"}
                  for item in (native, imported, orphan, reassigned, missing_settlement, deleted_order_invoice)
              ], key=lambda x: (x["tenant_id"], x["invoice_id"]))}
    policy["policy_sha256"] = policy_digest(policy)
    monkeypatch.setattr(settings, "DB135_NATIVE_RECORD_POLICY_JSON", json.dumps(policy))
    snapshot = await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    tenant.timezone = "Invalid/Shop_Timezone"
    await db_session.flush()
    with pytest.raises(HTTPException) as invalid_timezone:
        await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    assert invalid_timezone.value.status_code == 503
    tenant.timezone = "UTC"
    await db_session.flush()
    with pytest.raises(HTTPException) as hidden:
        await account_snapshot(db_session, tenant_id=uuid4(), customer_id=customer_id)
    assert hidden.value.status_code == 404
    assert snapshot["native"]["collectible"] == "75.00"
    assert snapshot["native"]["collectible_complete"] is False
    assert snapshot["native"]["unverified_invoice_count"] == 3
    assert snapshot["native"]["days_31_60"] == "75.00"
    assert snapshot["native"]["days_90_plus"] == "0.00"
    assert snapshot["native"]["review_required_count"] == 4
    assert snapshot["ets_history"]["observed_open_balance"] is None
    assert snapshot["ets_history"]["collectible"] is False
    assert snapshot["ets_history"]["review_required_count"] == 1
    assert not any(row["invoice_id"] == str(reassigned.id) for row in snapshot["transactions"])
    orphan_row = next(row for row in snapshot["transactions"] if row["invoice_id"] == str(orphan.id))
    assert orphan_row["source_owner"] == "review_required"
    missing_row = next(row for row in snapshot["transactions"] if row["invoice_id"] == str(missing_settlement.id))
    assert missing_row["source_owner"] == "review_required" and missing_row["remaining_principal"] is None
    deleted_row = next(row for row in snapshot["transactions"] if row["invoice_id"] == str(deleted_order_invoice.id))
    assert deleted_row["source_owner"] == "review_required" and deleted_row["review_reason"] == "Repair order was deleted"
    assert deleted_row["amount"] is None and deleted_row["remaining_principal"] is None
    assert orphan_row["amount"] is None and orphan_row["drilldown_route"] is None
    assert all(row["id"] != str(orphan_payment.id) for row in snapshot["transactions"])
    pending_row = next(row for row in snapshot["transactions"] if row["id"] == str(pending_payment.id))
    assert pending_row["source_owner"] == "review_required" and pending_row["payment_status"] == "pending"
    assert next(row for row in snapshot["transactions"] if row["id"] == str(mixed_history_payment.id))["source_owner"] == "review_required"
    imported_row = next(row for row in snapshot["transactions"] if row["id"] == str(imported.id))
    assert imported_row["source_date"] == "2025-01-05"
    assert imported_row["source_owner"] == "ets_history"
    assert any(row["drilldown_route"] == f"/dashboard/repair-orders?selected={orders[0].id}"
               for row in snapshot["transactions"])
    pdf = render_statement_pdf(snapshot)
    assert pdf.startswith(b"%PDF-") and len(pdf) < 2_000_000
    native_settlement.deleted_at = now
    await db_session.flush()
    tombstoned_snapshot = await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    assert tombstoned_snapshot["native"]["collectible"] == "0.00"
    assert tombstoned_snapshot["native"]["collectible_complete"] is False
    assert tombstoned_snapshot["native"]["unverified_invoice_count"] == 4
    native_row = next(row for row in tombstoned_snapshot["transactions"] if row["id"] == str(native.id))
    assert native_row["source_owner"] == "review_required"
    assert native_row["remaining_principal"] is None
