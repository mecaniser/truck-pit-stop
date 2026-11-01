import base64
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import select

from app.api.v1.endpoints import historical_invoice_reviews as reviews
from app.db.models.customer import Customer
from app.db.models.historical_invoice_export import HistoricalInvoiceEvidence, HistoricalInvoiceMapping, HistoricalInvoiceDecision
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.notification import Notification, NotificationStatus, NotificationType
from app.db.models.user import User, UserRole
from app.services import historical_invoice_proof as proof_service
from app.services.historical_invoice_identity import guard_mapped_customer_name
from test_db094_fleet_invoice_exports import _seed


async def seed(db, *, replacement=False, duplicate=True, portal=True):
    owner, target, invoice, _ = await _seed(db, f"proof-{uuid4().hex}")
    invoice.billed_customer_id = None
    invoice.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    target.email = f"target-{uuid4().hex}@example.com"
    reviewer = User(tenant_id=owner.tenant_id, email=f"reviewer-{uuid4().hex}@example.com",
        hashed_password="x", first_name="Reviewer", last_name="Test", role=UserRole.GARAGE_ADMIN,
        is_active=True, is_verified=True)
    other = Customer(tenant_id=owner.tenant_id, first_name=target.first_name, last_name=target.last_name,
        email=f"different-{uuid4().hex}@example.com") if duplicate else None
    db.add(reviewer)
    if other: db.add(other)
    order = invoice.repair_order
    predecessor = None
    observed = invoice.invoice_number
    if replacement:
        order.source = "easy_truck_shop_import"
        predecessor = Invoice(id=uuid4(), tenant_id=owner.tenant_id, repair_order_id=order.id,
            invoice_number=f"ETSINV-OLD-{uuid4().hex}", source="easy_truck_shop_import",
            status=InvoiceStatus.CANCELLED, subtotal=100, tax_amount=0, discount_amount=0,
            total_amount=100, created_at=invoice.created_at - timedelta(days=1),
            voided_at=invoice.created_at - timedelta(minutes=1))
        db.add(predecessor); await db.flush()
        invoice.supersedes_invoice_id = predecessor.id
        invoice.invoice_number = f"ETSINV-{uuid4().hex[:10]}"
        observed = f"INV-{str(owner.tenant_id).split('-')[0].upper()}-000013"
    link = f'https://www.dieselbridge.com/portal/invoices/{invoice.id}' if portal else 'https://www.dieselbridge.com/invoice/expired-opaque-token'
    notification = Notification(id=uuid4(), tenant_id=owner.tenant_id, type=NotificationType.EMAIL,
        status=NotificationStatus.SENT, recipient_email=target.email,
        subject=f"Invoice {observed}", body=f'<p>Invoice {observed} — Bill to ELIS Fleet</p><a href="{link}">View invoice</a>',
        template_name="invoice_created", external_id=f"provider-{uuid4()}",
        created_at=invoice.created_at + timedelta(seconds=5), sent_at=invoice.created_at + timedelta(seconds=10))
    db.add(notification); await db.commit()
    return owner, reviewer, target, other, invoice, notification, observed, predecessor


async def record(db, owner, invoice, notification, *, document=None, original_customer_id=None):
    content = proof_service.canonical(proof_service.snapshot(notification)).encode() if document is None else document
    return await reviews.record_evidence(invoice.id, reviews.EvidenceRequest(
        source_type="billing_correspondence", source_reference=f"sent-notification:{notification.id}",
        source_content_type="application/json", source_document_base64=base64.b64encode(content).decode(),
        captured_at=datetime.now(timezone.utc), original_bill_to_name="ELIS Fleet",
        original_customer_id=original_customer_id,
    ), Response(), db=db, user=owner)


def request(evidence, target, invoice, notification, observed, **changes):
    values = dict(source_sha256=evidence["source_sha256"], observed_invoice_number=observed,
        observed_bill_to_name="ELIS Fleet", target_customer_id=target.id,
        verification_note="Independently inspected original sent invoice correspondence",
        identity_proof=dict(kind="sent_notification", notification_id=notification.id,
            observed_invoice_id=invoice.id, observed_repair_order_id=invoice.repair_order_id,
            observed_recipient_email=target.email, original_correspondence_attested=True))
    values.update(changes)
    return reviews.VerifyRequest(**values)


def approval(evidence, target):
    return reviews.DecisionRequest(action="approve", expected_version=0, idempotency_key=str(uuid4()),
        reason="Reviewed original correspondence identifies the legal bill-to",
        evidence_id=evidence["evidence_id"], target_customer_id=target.id, legal_continuity_attested=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", [False, True])
async def test_duplicate_name_recipient_proof_is_independent_and_does_not_itself_grant_access(db_session, replacement):
    owner, reviewer, target, other, invoice, notification, observed, predecessor = await seed(db_session, replacement=replacement)
    evidence = await record(db_session, owner, invoice, notification)
    body = request(evidence, target, invoice, notification, observed)
    with pytest.raises(HTTPException) as error:
        await reviews.verify_evidence(invoice.id, evidence["evidence_id"], body, Response(), db=db_session, user=owner)
    assert error.value.status_code == 403
    verified = await reviews.verify_evidence(invoice.id, evidence["evidence_id"], body, Response(), db=db_session, user=reviewer)
    assert verified["verified_target_customer_id"] == target.id
    assert (await db_session.execute(select(HistoricalInvoiceMapping))).scalars().all() == []
    frozen = await db_session.get(HistoricalInvoiceEvidence, evidence["evidence_id"])
    assert frozen.identity_proof and frozen.identity_proof_sha256
    decision = approval(evidence, target)
    result = await reviews.decide(invoice.id, decision, Response(), db=db_session, user=owner)
    replay = await reviews.decide(invoice.id, decision, Response(), db=db_session, user=owner)
    assert replay == result
    audit = await db_session.get(HistoricalInvoiceDecision, result["decision_id"])
    assert audit.evidence_identity_proof_sha256 == frozen.identity_proof_sha256
    assert invoice.billed_customer_id is None
    assert invoice.source is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["wrong_recipient", "shared_email", "cross_tenant", "resend", "late", "forged_snapshot", "original_customer", "unattested"])
async def test_correspondence_proof_rejects_ambiguous_or_forged_sources(db_session, change):
    owner, reviewer, target, other, invoice, notification, observed, _ = await seed(db_session)
    original_id = None
    document = None
    if change == "wrong_recipient": notification.recipient_email = other.email
    if change == "shared_email": other.email = target.email
    if change == "cross_tenant": notification.tenant_id = uuid4()
    if change == "resend": notification.template_name = "invoice_resend"
    if change == "late":
        notification.sent_at = invoice.created_at + timedelta(days=2)
    if change == "forged_snapshot":
        source = proof_service.snapshot(notification); source["body"] += " forged"
        document = proof_service.canonical(source).encode()
    if change == "original_customer": original_id = other.id
    await db_session.commit()
    evidence = await record(db_session, owner, invoice, notification, document=document, original_customer_id=original_id)
    body = request(evidence, target, invoice, notification, observed)
    if change == "unattested": body.identity_proof.original_correspondence_attested = False
    with pytest.raises(HTTPException) as error:
        await reviews.verify_evidence(invoice.id, evidence["evidence_id"], body, Response(), db=db_session, user=reviewer)
    assert error.value.status_code in (422, 404)
    stored = await db_session.get(HistoricalInvoiceEvidence, evidence["evidence_id"])
    assert stored.verified_at is None and stored.identity_proof is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["email", "name", "number", "source", "duplicate_email"])
async def test_approval_rechecks_pinned_identity_and_context(db_session, change):
    owner, reviewer, target, other, invoice, notification, observed, _ = await seed(db_session)
    evidence = await record(db_session, owner, invoice, notification)
    await reviews.verify_evidence(invoice.id, evidence["evidence_id"], request(evidence, target, invoice, notification, observed), Response(), db=db_session, user=reviewer)
    if change == "email": target.email = f"new-{uuid4()}@example.com"
    if change == "name": target.last_name = "Changed"
    if change == "number": invoice.invoice_number += "-changed"
    if change == "source": notification.body += " altered"
    if change == "duplicate_email": other.email = target.email
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await reviews.decide(invoice.id, approval(evidence, target), Response(), db=db_session, user=owner)
    assert error.value.status_code == 409
    assert (await db_session.execute(select(HistoricalInvoiceMapping))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing", "nonvoided", "wrong_ro", "cross_tenant", "native_predecessor", "self", "imported_invoice", "opaque_alias"])
async def test_native_imported_order_exception_is_tightly_bounded(db_session, change):
    owner, reviewer, target, other, invoice, notification, observed, predecessor = await seed(db_session, replacement=True, portal=change != "opaque_alias")
    if change == "missing": invoice.supersedes_invoice_id = uuid4()
    if change == "nonvoided": predecessor.voided_at = None
    if change == "wrong_ro": predecessor.repair_order_id = uuid4()
    if change == "cross_tenant": predecessor.tenant_id = uuid4()
    if change == "native_predecessor": predecessor.source = None
    if change == "self": invoice.supersedes_invoice_id = invoice.id
    if change == "imported_invoice": invoice.source = "easy_truck_shop_import"
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        evidence = await record(db_session, owner, invoice, notification)
        await reviews.verify_evidence(invoice.id, evidence["evidence_id"], request(evidence, target, invoice, notification, observed), Response(), db=db_session, user=reviewer)
    assert error.value.status_code in (409, 422)


@pytest.mark.asyncio
async def test_replacement_requires_proof_even_with_unique_name_and_can_revoke_after_drift(db_session):
    owner, reviewer, target, other, invoice, notification, observed, predecessor = await seed(db_session, replacement=True, duplicate=False)
    evidence = await record(db_session, owner, invoice, notification)
    no_proof = request(evidence, target, invoice, notification, invoice.invoice_number, identity_proof=None)
    with pytest.raises(HTTPException) as error:
        await reviews.verify_evidence(invoice.id, evidence["evidence_id"], no_proof, Response(), db=db_session, user=reviewer)
    assert error.value.status_code == 422
    await reviews.verify_evidence(invoice.id, evidence["evidence_id"], request(evidence, target, invoice, notification, observed), Response(), db=db_session, user=reviewer)
    await reviews.decide(invoice.id, approval(evidence, target), Response(), db=db_session, user=owner)
    with pytest.raises(HTTPException) as error:
        await guard_mapped_customer_name(db_session, target, {"email": "changed@example.com"})
    assert error.value.status_code == 409
    invoice.status = InvoiceStatus.CANCELLED
    predecessor.voided_at = None
    await db_session.commit()
    result = await reviews.decide(invoice.id, reviews.DecisionRequest(action="revoke", expected_version=1,
        idempotency_key=str(uuid4()), reason="Source context changed; revoke old grant"), Response(), db=db_session, user=owner)
    assert result["target_customer_id"] is None and result["version"] == 2


@pytest.mark.asyncio
async def test_http_nested_proof_and_auth_boundaries(client, db_session):
    from app.core.security import create_access_token
    from app.api.v1.endpoints import fleet_invoice_exports as exports

    owner, reviewer, target, _, invoice, notification, observed, _ = await seed(db_session)
    evidence = await record(db_session, owner, invoice, notification)
    data = request(evidence, target, invoice, notification, observed).model_dump(mode="json")
    url = f'/api/v1/fleet-invoice-exports/historical-invoices/{invoice.id}/evidence/{evidence["evidence_id"]}/verify'
    assert (await client.post(url, json=data)).status_code in (401, 403)
    key = await exports.create_key(exports.KeyRequest(customer_id=target.id, name="synthetic review deny"), Response(), db=db_session, user=owner)
    assert (await client.post(url, json=data, headers={"X-API-Key": key["api_key"]})).status_code in (401, 403)
    headers = {"Authorization": f'Bearer {create_access_token({"sub": str(reviewer.id)})}'}
    bad = {**data, "identity_proof": {**data["identity_proof"], "untrusted_extra": "x"}}
    assert (await client.post(url, json=bad, headers=headers)).status_code == 422
    reviewer.role = UserRole.MECHANIC
    await db_session.commit()
    assert (await client.post(url, json=data, headers=headers)).status_code == 403
    reviewer.role = UserRole.GARAGE_ADMIN
    await db_session.commit()
    result = await client.post(url, json=data, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["verified_target_customer_id"] == str(target.id)
    assert not (await db_session.execute(select(HistoricalInvoiceMapping))).scalars().all()
