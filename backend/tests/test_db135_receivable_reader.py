from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.services.receivable_attestation_fingerprint import FINGERPRINT_VERSION, REQUIRED_RELATIONS, fingerprint_source_bundle
from app.services.receivable_attestation_reader import compute_manifest_digest, verify_receivable_head
from app.services.receivable_attestation_source import ReceivableSourceBundle


NOW = datetime(2026, 10, 18, 10, tzinfo=timezone.utc)


def _case(status=InvoiceStatus.OVERDUE):
    tenant, customer_id, order_id, invoice_id = (uuid4() for _ in range(4))
    customer = Customer(id=customer_id, tenant_id=tenant, first_name="A")
    order = RepairOrder(id=order_id, tenant_id=tenant, customer_id=customer_id,
                        status=RepairOrderStatus.INVOICED)
    invoice = Invoice(id=invoice_id, tenant_id=tenant, repair_order_id=order_id,
                      billed_customer_id=customer_id, status=status, is_internal=False,
                      subtotal=Decimal("100.00"), shop_supplies_amount=Decimal("0.00"),
                      service_fee_amount=Decimal("0.00"), tax_amount=Decimal("0.00"),
                      total_amount=Decimal("100.00"))
    rows = {kind: [] for kind in REQUIRED_RELATIONS}
    if status == InvoiceStatus.PAID:
        rows["payments"].append(Payment(id=uuid4(), tenant_id=tenant, invoice_id=invoice_id,
                                        amount=Decimal("100.00"), status=PaymentStatus.COMPLETED,
                                        method=PaymentMethod.CASH))
    fingerprint = fingerprint_source_bundle(tenant_id=tenant, invoice=invoice,
                                            order=order, customer=customer, linked_rows=rows)
    bundle = ReceivableSourceBundle(invoice, order, customer, rows, fingerprint)
    decision = "verified_paid_tender" if status == InvoiceStatus.PAID else "verified_open"
    confirmed = 10000 if status == InvoiceStatus.PAID else 0
    reviewer, executor, run_id, approval_id = (uuid4() for _ in range(4))
    reviewed, applied, expiry = NOW - timedelta(hours=2), NOW - timedelta(hours=1), NOW + timedelta(days=2)
    approval = SimpleNamespace(id=approval_id, tenant_id=tenant, invoice_id=invoice_id,
        repair_order_id=order_id, customer_id=customer_id, run_id=run_id, version=1,
        supersedes_id=None, decision=decision, currency="USD", principal_total_cents=10000,
        confirmed_principal_cents=confirmed, source_fingerprint=bundle.fingerprint,
        fingerprint_version=FINGERPRINT_VERSION, evidence_digest="b" * 64,
        manifest_digest="c" * 64, reviewer_user_id=reviewer, executor_user_id=executor,
        reviewed_at=reviewed, applied_at=applied, valid_until=expiry, audit_reference="DB135-local")
    entry = dict(repair_order_id=str(order_id), customer_id=str(customer_id), decision=decision,
        principal_total_cents="10000", confirmed_principal_cents=str(confirmed),
        source_fingerprint=bundle.fingerprint, evidence_digest="b" * 64,
        fingerprint_version=FINGERPRINT_VERSION, version="1", supersedes_id="",
        reviewed_at=reviewed.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        valid_until=expiry.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), audit_reference="DB135-local")
    run = SimpleNamespace(id=run_id, tenant_id=tenant, state="applied", manifest_digest="c" * 64,
        fingerprint_version=FINGERPRINT_VERSION, reviewer_user_id=reviewer,
        executor_user_id=executor, authorization_reference="test-only",
        invoice_ids=[str(invoice_id)], approved_entries={str(invoice_id): entry},
        expected_insert_count=1)
    run.manifest_digest = compute_manifest_digest(tenant_id=tenant, invoice_ids=run.invoice_ids,
        approved_entries=run.approved_entries, fingerprint_version=run.fingerprint_version,
        reviewer_user_id=reviewer, executor_user_id=executor,
        authorization_reference=run.authorization_reference, expected_insert_count=1)
    approval.manifest_digest = run.manifest_digest
    return bundle, approval, run


def test_current_open_and_paid_heads_only_support_full_invoice_decisions():
    for status, confirmed in ((InvoiceStatus.OVERDUE, Decimal("0")),
                              (InvoiceStatus.PAID, Decimal("100"))):
        bundle, approval, run = _case(status)
        verified = verify_receivable_head(bundle, [approval], run, now=NOW)
        assert verified and verified.basis == "reviewed_attestation"
        assert verified.principal == Decimal("100.00") and verified.confirmed == confirmed


def test_reader_rejects_source_drift_settlement_and_expiry_without_old_head_fallback():
    bundle, approval, run = _case()
    bundle.linked_rows["settlements"].append(object())
    assert verify_receivable_head(bundle, [approval], run, now=NOW) is None
    bundle.linked_rows["settlements"].clear()
    bundle = ReceivableSourceBundle(bundle.invoice, bundle.order, bundle.customer,
                                    bundle.linked_rows, "d" * 64)
    assert verify_receivable_head(bundle, [approval], run, now=NOW) is None
    bundle, approval, run = _case()
    later = SimpleNamespace(**vars(approval))
    later.id = uuid4()
    later.version = 2
    later.supersedes_id = approval.id
    later.valid_until = NOW - timedelta(seconds=1)
    assert verify_receivable_head(bundle, [approval, later], run, now=NOW) is None
    approval.valid_until = NOW - timedelta(seconds=1)
    assert verify_receivable_head(bundle, [approval], run, now=NOW) is None


def test_reader_rejects_lineage_manifest_amount_and_review_conflicts():
    bundle, approval, run = _case()
    approval.customer_id = uuid4()
    assert verify_receivable_head(bundle, [approval], run, now=NOW) is None
    bundle, approval, run = _case()
    run.approved_entries[str(bundle.invoice.id)]["source_fingerprint"] = "e" * 64
    assert verify_receivable_head(bundle, [approval], run, now=NOW) is None
    bundle, approval, run = _case()
    approval.confirmed_principal_cents = 1
    assert verify_receivable_head(bundle, [approval], run, now=NOW) is None
    bundle, approval, run = _case()
    approval.reviewer_user_id = approval.executor_user_id
    assert verify_receivable_head(bundle, [approval], run, now=NOW) is None


def test_reader_rejects_arbitrary_digest_and_malformed_manifest():
    bundle, approval, run = _case()
    run.manifest_digest = approval.manifest_digest = "c" * 64
    assert verify_receivable_head(bundle, [approval], run, now=NOW) is None
    for malformed in (None, [], {"extra": {}}, {}):
        bundle, approval, run = _case()
        run.approved_entries = malformed
        assert verify_receivable_head(bundle, [approval], run, now=NOW) is None
    bundle, approval, run = _case()
    run.invoice_ids = ["not-a-uuid"]
    assert verify_receivable_head(bundle, [approval], run, now=NOW) is None


def test_reader_rechecks_bundle_lineage_and_fingerprint_after_load():
    for changed in ("order_tenant", "customer_tenant", "order_link", "bill_to", "status"):
        bundle, approval, run = _case()
        if changed == "order_tenant":
            bundle.order.tenant_id = uuid4()
        elif changed == "customer_tenant":
            bundle.customer.tenant_id = uuid4()
        elif changed == "order_link":
            bundle.invoice.repair_order_id = uuid4()
        elif changed == "bill_to":
            bundle.invoice.billed_customer_id = uuid4()
        else:
            bundle.invoice.status = InvoiceStatus.CANCELLED
        assert verify_receivable_head(bundle, [approval], run, now=NOW) is None
