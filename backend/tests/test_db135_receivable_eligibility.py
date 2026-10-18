from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import CustomerCreditEntry, InvoiceSettlement
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.services.receivable_attestation_eligibility import triage_receivable_source
from app.services.receivable_attestation_fingerprint import REQUIRED_RELATIONS
from app.services.receivable_attestation_source import ReceivableSourceBundle


def _bundle(status=InvoiceStatus.OVERDUE):
    tenant_id, customer_id, order_id, invoice_id = (uuid4() for _ in range(4))
    customer = Customer(id=customer_id, tenant_id=tenant_id, first_name="A")
    order = RepairOrder(id=order_id, tenant_id=tenant_id, customer_id=customer_id,
                        status=RepairOrderStatus.INVOICED)
    invoice = Invoice(id=invoice_id, tenant_id=tenant_id, repair_order_id=order_id,
                      billed_customer_id=customer_id, status=status, is_internal=False,
                      subtotal=Decimal("100.00"),
                      shop_supplies_amount=Decimal("0.00"), service_fee_amount=Decimal("0.00"),
                      tax_amount=Decimal("0.00"), total_amount=Decimal("100.00"))
    rows = {kind: [] for kind in REQUIRED_RELATIONS}
    return ReceivableSourceBundle(invoice, order, customer, rows, "a" * 64)


def _payment(bundle, amount, *, status=PaymentStatus.COMPLETED):
    return Payment(id=uuid4(), tenant_id=bundle.invoice.tenant_id, invoice_id=bundle.invoice.id,
                   amount=Decimal(amount), method=PaymentMethod.CASH, status=status)


def test_open_candidate_always_requires_operator_review():
    bundle = _bundle()
    result = triage_receivable_source(bundle)
    assert result.review_path == "open_operator_review"
    assert result.hold_reasons == () and result.principal == Decimal("100.00")
    assert result.completed_payment_total == Decimal("0.00")
    assert result.source_fingerprint == bundle.fingerprint
    bundle.linked_rows["payments"].append(_payment(bundle, "1.00"))
    held = triage_receivable_source(bundle)
    assert held.review_path is None and "open_invoice_has_payment_evidence" in held.hold_reasons


def test_internal_order_or_fleet_customer_blocks_external_invoice_review():
    bundle = _bundle()
    assert bundle.invoice.is_internal is False
    bundle.order.is_internal = True
    assert "internal_source_conflict" in triage_receivable_source(bundle).hold_reasons
    assert triage_receivable_source(bundle).review_path is None
    bundle.order.is_internal = False
    bundle.customer.is_internal_fleet = True
    held = triage_receivable_source(bundle)
    assert held.review_path is None and "internal_source_conflict" in held.hold_reasons


def test_paid_candidate_needs_full_receipt_review_and_holds_overage_shortfall():
    bundle = _bundle(InvoiceStatus.PAID)
    bundle.linked_rows["payments"].append(_payment(bundle, "100.00"))
    assert triage_receivable_source(bundle).review_path == "paid_receipt_review"
    bundle.linked_rows["payments"][0].amount = Decimal("101.00")
    assert "paid_tender_overage" in triage_receivable_source(bundle).hold_reasons
    bundle.linked_rows["payments"][0].amount = Decimal("99.00")
    assert "paid_tender_shortfall" in triage_receivable_source(bundle).hold_reasons
    bundle.linked_rows["payments"][0].amount = Decimal("100.00")
    bundle.linked_rows["payments"][0].deleted_at = datetime.now(timezone.utc)
    assert "financial_source_tombstoned" in triage_receivable_source(bundle).hold_reasons


def test_ets_settlement_and_conflicting_credit_never_become_candidates():
    bundle = _bundle()
    bundle.invoice.source = "easy_truck_shop_import"
    assert "ets_owned_history" in triage_receivable_source(bundle).hold_reasons
    bundle.invoice.source = None
    bundle.linked_rows["settlements"].append(InvoiceSettlement(
        id=uuid4(), tenant_id=bundle.invoice.tenant_id, invoice_id=bundle.invoice.id,
        customer_id=bundle.customer.id, principal_total=Decimal("100.00"),
        confirmed_principal=Decimal("0.00"), legacy_reconciliation_status="native"))
    assert "settlement_exists" in triage_receivable_source(bundle).hold_reasons
    bundle.linked_rows["settlements"].clear()
    bundle.linked_rows["customer_credits"].append(CustomerCreditEntry(
        id=uuid4(), tenant_id=bundle.invoice.tenant_id, customer_id=uuid4(),
        target_invoice_id=bundle.invoice.id, entry_type="applied", amount=Decimal("5.00")))
    held = triage_receivable_source(bundle)
    assert held.review_path is None
    assert "credit_customer_conflict" in held.hold_reasons
