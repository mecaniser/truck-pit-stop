from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.receivable_attestation import InvoiceReceivableAttestation, InvoiceReceivableAttestationRun
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.customer_receivables import account_snapshot
from app.services.native_record_classification import policy_digest
from app.core.config import settings
import json
from app.services.receivable_attestation_fingerprint import FINGERPRINT_VERSION
from app.services.receivable_attestation_reader import compute_manifest_digest
from app.services.receivable_attestation_source import load_receivable_source


@pytest.mark.asyncio
async def test_account_uses_only_current_source_matching_reviewed_head(db_session, monkeypatch):
    async def local_fixture_transaction(_db, *, read_only):
        assert read_only

    monkeypatch.setattr("app.services.receivable_attestation_source._verify_transaction",
                        local_fixture_transaction)
    # SQLite discards timezone offsets; PostgreSQL preserves them. Adapt only
    # this synthetic fixture's timestamp decoding, never production behavior.
    def sqlite_utc(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def sqlite_stamp(value):
        return sqlite_utc(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    monkeypatch.setattr("app.services.receivable_attestation_reader._utc", sqlite_utc)
    monkeypatch.setattr("app.services.receivable_attestation_reader._stamp", sqlite_stamp)
    tenant_id, customer_id, vehicle_id, order_id, invoice_id = (uuid4() for _ in range(5))
    tenant = Tenant(id=tenant_id, name="Attestation Garage", slug=f"attest-{uuid4().hex[:8]}", timezone="UTC")
    customer = Customer(id=customer_id, tenant_id=tenant_id, first_name="A", last_name="Customer",
                        email=f"attest-{uuid4().hex[:8]}@example.test")
    vehicle = Vehicle(id=vehicle_id, tenant_id=tenant_id, customer_id=customer_id,
                      make="Volvo", model="VNR")
    db_session.add_all([tenant, customer, vehicle])
    await db_session.flush()
    order = RepairOrder(id=order_id, tenant_id=tenant_id, customer_id=customer_id,
                        vehicle_id=vehicle_id, order_number=f"RO-{uuid4().hex[:8]}",
                        status=RepairOrderStatus.INVOICED)
    db_session.add(order)
    await db_session.flush()
    invoice = Invoice(id=invoice_id, tenant_id=tenant_id, repair_order_id=order_id,
                      billed_customer_id=customer_id, invoice_number=f"INV-{uuid4().hex[:8]}",
                      status=InvoiceStatus.OVERDUE, subtotal=Decimal("100.00"),
                      total_amount=Decimal("100.00"), due_date=datetime.now(timezone.utc) - timedelta(days=91))
    db_session.add(invoice)
    await db_session.flush()
    source = await load_receivable_source(db_session, tenant_id=tenant_id, invoice_id=invoice_id)
    reviewer, executor, run_id = uuid4(), uuid4(), uuid4()
    reviewed = datetime.now(timezone.utc) - timedelta(hours=1)
    applied = reviewed + timedelta(minutes=1)
    expiry = reviewed + timedelta(days=3)
    entry = {
        "repair_order_id": str(order_id), "customer_id": str(customer_id),
        "decision": "verified_open", "principal_total_cents": "10000",
        "confirmed_principal_cents": "0", "source_fingerprint": source.fingerprint,
        "evidence_digest": "b" * 64, "fingerprint_version": FINGERPRINT_VERSION,
        "version": "1", "supersedes_id": "",
        "reviewed_at": reviewed.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "valid_until": expiry.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "audit_reference": "DB135-local-fixture",
    }
    entries = {str(invoice_id): entry}
    digest = compute_manifest_digest(tenant_id=tenant_id, invoice_ids=[str(invoice_id)],
        approved_entries=entries, fingerprint_version=FINGERPRINT_VERSION,
        reviewer_user_id=reviewer, executor_user_id=executor,
        authorization_reference="synthetic-only", expected_insert_count=1)
    db_session.add(InvoiceReceivableAttestationRun(
        id=run_id, tenant_id=tenant_id, manifest_digest=digest,
        invoice_ids=[str(invoice_id)], approved_entries=entries,
        fingerprint_version=FINGERPRINT_VERSION, expected_insert_count=1,
        authorization_reference="synthetic-only", reviewer_user_id=reviewer,
        executor_user_id=executor, state="applied", created_at=applied))
    db_session.add(InvoiceReceivableAttestation(
        id=uuid4(), tenant_id=tenant_id, invoice_id=invoice_id,
        repair_order_id=order_id, customer_id=customer_id, run_id=run_id,
        version=1, supersedes_id=None, decision="verified_open", currency="USD",
        principal_total_cents=10000, confirmed_principal_cents=0,
        source_fingerprint=source.fingerprint, fingerprint_version=FINGERPRINT_VERSION,
        evidence_digest="b" * 64, manifest_digest=digest,
        reviewer_user_id=reviewer, executor_user_id=executor,
        reviewed_at=reviewed, applied_at=applied, valid_until=expiry,
        audit_reference="DB135-local-fixture", created_at=applied))
    await db_session.flush()
    policy = {"version": 1, "review_reference": "synthetic-test-review",
              "review_snapshot_sha256": "a" * 64, "entries": [{
                  "tenant_id": str(tenant_id), "invoice_id": str(invoice.id),
                  "invoice_number": invoice.invoice_number, "repair_order_id": str(order_id),
                  "billed_customer_id": str(customer_id), "resolved_customer_id": str(customer_id),
                  "classification": "real"}]}
    policy["policy_sha256"] = policy_digest(policy)
    monkeypatch.setattr(settings, "DB135_NATIVE_RECORD_POLICY_JSON", json.dumps(policy))
    snapshot = await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    assert snapshot["native"]["collectible"] == "100.00"
    assert snapshot["native"]["collectible_complete"] is True
    assert snapshot["native"]["reviewed_attestation_count"] == 1
    row = next(item for item in snapshot["transactions"] if item["id"] == str(invoice_id))
    assert row["reconciliation_basis"] == "reviewed_attestation"
    with monkeypatch.context() as bound:
        bound.setattr("app.services.receivable_attestation_reader.MAX_ACCOUNT_ATTESTED_INVOICES", 0)
        with pytest.raises(HTTPException) as over_bound:
            await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
        assert over_bound.value.status_code == 413

    invoice.due_date += timedelta(days=1)
    await db_session.flush()
    drifted = await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    assert drifted["native"]["collectible"] == "0.00"
    assert drifted["native"]["collectible_complete"] is False
    invoice.due_date -= timedelta(days=1)
    await db_session.flush()
    settlement = InvoiceSettlement(id=uuid4(), tenant_id=tenant_id, invoice_id=invoice_id,
        customer_id=customer_id, principal_total=Decimal("100.00"),
        confirmed_principal=Decimal("0.00"), legacy_reconciliation_status="legacy_paid_snapshot")
    db_session.add(settlement)
    await db_session.flush()
    later_settlement = await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    assert later_settlement["native"]["collectible"] == "0.00"
    assert later_settlement["native"]["collectible_complete"] is False
    settlement.legacy_reconciliation_status = "native"
    order.is_internal = True
    await db_session.flush()
    internal_order = await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    assert internal_order["native"]["collectible"] == "0.00"
    assert internal_order["native"]["collectible_complete"] is False
    order.is_internal = False
    customer.is_internal_fleet = True
    await db_session.flush()
    internal_customer = await account_snapshot(db_session, tenant_id=tenant_id, customer_id=customer_id)
    assert internal_customer["native"]["collectible"] == "0.00"
    assert internal_customer["native"]["collectible_complete"] is False
