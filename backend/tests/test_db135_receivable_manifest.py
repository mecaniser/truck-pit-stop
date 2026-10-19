from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.services.receivable_attestation_fingerprint import REQUIRED_RELATIONS, fingerprint_source_bundle
from app.services.receivable_attestation_manifest import ReviewedDecision, build_reviewed_write_set
from app.services.receivable_attestation_reader import compute_manifest_digest
from app.services.receivable_attestation_source import ReceivableSourceBundle


def bundle(status=InvoiceStatus.OVERDUE):
    tenant, customer_id, order_id, invoice_id = (uuid4() for _ in range(4))
    customer = Customer(id=customer_id, tenant_id=tenant, first_name="Synthetic")
    order = RepairOrder(id=order_id, tenant_id=tenant, customer_id=customer_id,
                        status=RepairOrderStatus.INVOICED)
    invoice = Invoice(id=invoice_id, tenant_id=tenant, repair_order_id=order_id,
                      billed_customer_id=customer_id, status=status,
                      subtotal=Decimal("100.00"), total_amount=Decimal("100.00"))
    rows = {kind: [] for kind in REQUIRED_RELATIONS}
    fingerprint = fingerprint_source_bundle(tenant_id=tenant, invoice=invoice,
        order=order, customer=customer, linked_rows=rows)
    return ReceivableSourceBundle(invoice, order, customer, rows, fingerprint)


def decision(source, *, now=None, status="verified_open"):
    now = now or datetime.now(timezone.utc)
    return ReviewedDecision(invoice_id=source.invoice.id, decision=status,
        source_fingerprint=source.fingerprint, evidence_digest="b" * 64,
        audit_reference="private-synthetic-review", reviewed_at=now - timedelta(hours=1),
        valid_until=now + timedelta(days=2))


def build(source, item, *, now=None, reviewer=None, executor=None):
    return build_reviewed_write_set(tenant_id=source.invoice.tenant_id,
        decisions=[item], bundles={source.invoice.id: source},
        reviewer_user_id=reviewer or uuid4(), executor_user_id=executor or uuid4(),
        authorization_reference="local-synthetic-only", now=now or datetime.now(timezone.utc))


def test_explicit_open_review_produces_exact_canonical_candidate():
    source = bundle()
    now, reviewer, executor = datetime.now(timezone.utc), uuid4(), uuid4()
    result = build(source, decision(source, now=now), now=now, reviewer=reviewer, executor=executor)
    assert result.invoice_ids == [str(source.invoice.id)]
    entry = result.approved_entries[str(source.invoice.id)]
    assert entry["decision"] == "verified_open"
    assert entry["principal_total_cents"] == "10000"
    assert entry["confirmed_principal_cents"] == "0"
    assert result.manifest_digest == compute_manifest_digest(
        tenant_id=source.invoice.tenant_id, invoice_ids=result.invoice_ids,
        approved_entries=result.approved_entries, fingerprint_version=entry["fingerprint_version"],
        reviewer_user_id=reviewer, executor_user_id=executor,
        authorization_reference="local-synthetic-only", expected_insert_count=1)


def test_paid_requires_explicit_full_receipt_decision_and_no_overage():
    source = bundle(InvoiceStatus.PAID)
    source.linked_rows["payments"].append(Payment(
        id=uuid4(), tenant_id=source.invoice.tenant_id, invoice_id=source.invoice.id,
        amount=Decimal("100.00"), method=PaymentMethod.CASH,
        status=PaymentStatus.COMPLETED))
    source = replace(source, fingerprint=fingerprint_source_bundle(
        tenant_id=source.invoice.tenant_id, invoice=source.invoice,
        order=source.order, customer=source.customer, linked_rows=source.linked_rows))
    with pytest.raises(ValueError, match="eligible"):
        build(source, decision(source))
    result = build(source, decision(source, status="verified_paid_tender"))
    assert result.approved_entries[str(source.invoice.id)]["confirmed_principal_cents"] == "10000"
    source.linked_rows["payments"][0].amount = Decimal("101.00")
    with pytest.raises(ValueError, match="fingerprint changed"):
        build(source, decision(source, status="verified_paid_tender"))


def test_scope_evidence_expiry_and_internal_source_fail_closed():
    source = bundle()
    item = decision(source)
    with pytest.raises(ValueError, match="actors"):
        actor = uuid4()
        build(source, item, reviewer=actor, executor=actor)
    with pytest.raises(ValueError, match="actors"):
        build(source, item, reviewer="not-a-uuid")
    for bad_version in (1.0, True):
        with pytest.raises(ValueError, match="version or predecessor"):
            build(source, replace(item, version=bad_version))
    for bad_predecessor in ("not-a-uuid", 123):
        with pytest.raises(ValueError, match="version or predecessor"):
            build(source, replace(item, version=2, supersedes_id=bad_predecessor))
    with pytest.raises(ValueError, match="evidence"):
        build(source, replace(item, evidence_digest="not-a-digest"))
    with pytest.raises(ValueError, match="validity"):
        build(source, replace(item, valid_until=item.reviewed_at + timedelta(days=8)))
    with pytest.raises(ValueError, match="source fingerprint changed"):
        build(source, replace(item, source_fingerprint="a" * 64))
    source.order.is_internal = True
    refreshed = replace(source, fingerprint=fingerprint_source_bundle(
        tenant_id=source.invoice.tenant_id, invoice=source.invoice,
        order=source.order, customer=source.customer, linked_rows=source.linked_rows))
    with pytest.raises(ValueError, match="eligible"):
        build(refreshed, decision(refreshed))
