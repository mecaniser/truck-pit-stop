import base64
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Response
from sqlalchemy import select
from reportlab.pdfgen import canvas

from app.api.v1.endpoints import fleet_invoice_exports as exports
from app.api.v1.endpoints import historical_invoice_reviews as reviews
from app.api.v1.endpoints.auth import _resolve_or_create_customer
from app.db.models.customer import Customer
from app.db.models.historical_invoice_export import HistoricalInvoiceDecision, HistoricalInvoiceMapping
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.user import User, UserRole
from test_db094_fleet_invoice_exports import _seed


def _window():
    now = datetime.now(timezone.utc)
    return {"updated_since": (now - timedelta(days=1)).isoformat(),
            "updated_before": now.isoformat()}


def _evidence(invoice_number, *, lineage=None):
    output = BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawString(60, 700, f"Original invoice {invoice_number}")
    pdf.drawString(60, 680, "Bill to ELIS Fleet")
    pdf.save()
    return reviews.EvidenceRequest(
        source_type="original_invoice", source_reference="archive:2024/original-invoice-1",
        source_content_type="application/pdf",
        source_document_base64=base64.b64encode(output.getvalue()).decode(),
        captured_at=datetime.now(timezone.utc), original_bill_to_name="ELIS Fleet",
        merge_lineage_reference=lineage,
    )


async def _record_and_verify(db, owner, invoice, target_customer, *, lineage=None):
    reviewer = User(tenant_id=owner.tenant_id, email=f"reviewer-{uuid4().hex}@example.com",
                    hashed_password="x", first_name="Reviewer", last_name="Test",
                    role=UserRole.GARAGE_ADMIN, is_active=True, is_verified=True)
    db.add(reviewer)
    await db.commit()
    evidence = await reviews.record_evidence(invoice.id, _evidence(invoice.invoice_number,
                                                                    lineage=lineage), Response(),
                                             db=db, user=owner)
    verify = reviews.VerifyRequest(
        source_sha256=evidence["source_sha256"], observed_invoice_number=invoice.invoice_number,
        observed_bill_to_name="ELIS Fleet", target_customer_id=target_customer.id,
        verification_note="Inspected the stored original invoice PDF",
    )
    with pytest.raises(Exception) as error:
        await reviews.verify_evidence(invoice.id, evidence["evidence_id"], verify,
                                      Response(), db=db, user=owner)
    assert error.value.status_code == 403
    verified = await reviews.verify_evidence(invoice.id, evidence["evidence_id"], verify,
                                             Response(), db=db, user=reviewer)
    assert verified["verified_by_user_id"] == reviewer.id
    return evidence


def _decision(action, version, evidence_id=None, target_id=None, key=None):
    return reviews.DecisionRequest(
        action=action, expected_version=version, idempotency_key=key or str(uuid4()),
        reason="Original invoice reviewed against customer billing record",
        evidence_id=evidence_id, target_customer_id=target_id,
        legal_continuity_attested=action == "approve",
    )


@pytest.mark.asyncio
async def test_reviewed_legacy_invoice_and_revocation_event(client, db_session):
    owner, customer, invoice, _ = await _seed(db_session, f"history-{uuid4().hex}")
    invoice.billed_customer_id = None
    await db_session.commit()
    key = await exports.create_key(exports.KeyRequest(customer_id=customer.id, name="ELIS"),
                                   Response(), db=db_session, user=owner)
    url = "/api/v1/fleet-invoice-exports/invoices"
    headers = {"X-API-Key": key["api_key"]}
    initial = await client.get(url, headers=headers, params=_window())
    assert initial.status_code == 200 and initial.json()["items"] == []
    assert (await client.get(f"{url}/{invoice.id}/pdf", headers=headers)).status_code == 404

    evidence = await _record_and_verify(db_session, owner, invoice, customer)
    approval = _decision("approve", 0, evidence["evidence_id"], customer.id)
    approved = await reviews.decide(invoice.id, approval, Response(), db=db_session, user=owner)
    assert approved["version"] == 1
    assert (await reviews.decide(invoice.id, approval, Response(), db=db_session,
                                 user=owner))["decision_id"] == approved["decision_id"]
    result = await client.get(url, headers=headers, params=_window())
    assert [item["invoice_id"] for item in result.json()["items"]] == [str(invoice.id)]
    assert (await client.get(f"{url}/{invoice.id}/pdf", headers=headers)).status_code == 200

    await reviews.decide(invoice.id, _decision("revoke", 1), Response(), db=db_session, user=owner)
    revocation = (await db_session.execute(select(HistoricalInvoiceDecision).where(
        HistoricalInvoiceDecision.invoice_id == invoice.id,
        HistoricalInvoiceDecision.action == "revoke",
    ))).scalar_one()
    assert revocation.evidence_sha256 == evidence["source_sha256"]
    result = await client.get(url, headers=headers, params={**_window(), "limit": 1})
    assert result.status_code == 200
    assert result.json()["items"][0]["event_type"] == "access_removed"
    assert result.json()["items"][0]["invoice_id"] == str(invoice.id)
    assert (await client.get(f"{url}/{invoice.id}/pdf", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_review_rejects_wrong_tenant_and_stale_or_unattested_decisions(db_session):
    owner, customer, invoice, _ = await _seed(db_session, f"review-{uuid4().hex}")
    other_owner, other_customer, other_invoice, _ = await _seed(db_session, f"other-{uuid4().hex}")
    invoice.billed_customer_id = None
    other_invoice.billed_customer_id = None
    await db_session.commit()
    with pytest.raises(Exception) as error:
        await reviews.record_evidence(other_invoice.id, _evidence(other_invoice.invoice_number), Response(),
                                      db=db_session, user=owner)
    assert error.value.status_code == 404
    evidence = await _record_and_verify(db_session, owner, invoice, customer)
    with pytest.raises(Exception) as error:
        await reviews.decide(invoice.id, _decision("approve", 0, evidence["evidence_id"],
                                                  other_customer.id), Response(), db=db_session,
                             user=owner)
    assert error.value.status_code == 404
    with pytest.raises(Exception) as error:
        await reviews.decide(invoice.id, reviews.DecisionRequest(
            action="approve", expected_version=0, idempotency_key=str(uuid4()),
            reason="Invoice source was reviewed", evidence_id=evidence["evidence_id"],
            target_customer_id=customer.id, legal_continuity_attested=False,
        ), Response(), db=db_session, user=owner)
    assert error.value.status_code == 422
    await reviews.decide(invoice.id, _decision("approve", 0, evidence["evidence_id"], customer.id),
                         Response(), db=db_session, user=owner)
    with pytest.raises(Exception) as error:
        await reviews.decide(invoice.id, _decision("revoke", 0), Response(), db=db_session,
                             user=owner)
    assert error.value.status_code == 409
    mapping = (await db_session.execute(select(HistoricalInvoiceMapping).where(
        HistoricalInvoiceMapping.invoice_id == invoice.id))).scalar_one()
    assert mapping.target_customer_id == customer.id and mapping.version == 1


@pytest.mark.asyncio
async def test_unrelated_same_name_customer_cannot_be_verified(client, db_session):
    owner, customer, invoice, _ = await _seed(db_session, f"retarget-{uuid4().hex}")
    invoice.billed_customer_id = None
    successor = Customer(tenant_id=owner.tenant_id, first_name="ELIS", last_name="Fleet",
                         email=f"successor-{uuid4().hex}@example.com")
    db_session.add(successor)
    await db_session.commit()
    old_key = await exports.create_key(exports.KeyRequest(customer_id=customer.id, name="Old"),
                                       Response(), db=db_session, user=owner)
    new_key = await exports.create_key(exports.KeyRequest(customer_id=successor.id, name="New"),
                                       Response(), db=db_session, user=owner)
    reviewer = User(tenant_id=owner.tenant_id, email=f"reviewer-{uuid4().hex}@example.com",
                    hashed_password="x", first_name="Reviewer", last_name="Test",
                    role=UserRole.GARAGE_ADMIN, is_active=True, is_verified=True)
    db_session.add(reviewer)
    await db_session.commit()
    evidence = await reviews.record_evidence(invoice.id, _evidence(invoice.invoice_number,
                                                                   lineage="Unverified claim"),
                                             Response(), db=db_session, user=owner)
    for target in (customer, successor):
        with pytest.raises(Exception) as error:
            await reviews.verify_evidence(invoice.id, evidence["evidence_id"],
                reviews.VerifyRequest(source_sha256=evidence["source_sha256"],
                                      observed_invoice_number=invoice.invoice_number,
                                      observed_bill_to_name="ELIS Fleet", target_customer_id=target.id,
                                      verification_note="Inspected original invoice and target"),
                Response(), db=db_session, user=reviewer)
        assert error.value.status_code == 422
    with pytest.raises(Exception) as error:
        await reviews.decide(invoice.id, _decision("approve", 0, evidence["evidence_id"], customer.id),
                             Response(), db=db_session, user=owner)
    assert error.value.status_code == 422
    old = await client.get("/api/v1/fleet-invoice-exports/invoices", params=_window(),
                           headers={"X-API-Key": old_key["api_key"]})
    new = await client.get("/api/v1/fleet-invoice-exports/invoices", params=_window(),
                           headers={"X-API-Key": new_key["api_key"]})
    assert old.json()["items"] == []
    assert new.json()["items"] == []


@pytest.mark.asyncio
async def test_mixed_cursor_and_key_rotation_replay(client, db_session):
    owner, customer, legacy, vehicle = await _seed(db_session, f"replay-{uuid4().hex}")
    legacy.billed_customer_id = None
    order = RepairOrder(tenant_id=owner.tenant_id, customer_id=customer.id,
                        vehicle_id=vehicle.id, order_number=f"RO-{uuid4().hex}")
    native = Invoice(tenant_id=owner.tenant_id, repair_order=order,
                     billed_customer_id=customer.id, invoice_number=f"INV-{uuid4().hex}",
                     status=InvoiceStatus.SENT, subtotal=0, tax_amount=0,
                     discount_amount=0, total_amount=0)
    db_session.add_all([order, native])
    await db_session.commit()
    old_key = await exports.create_key(exports.KeyRequest(customer_id=customer.id, name="Old"),
                                       Response(), db=db_session, user=owner)
    evidence = await _record_and_verify(db_session, owner, legacy, customer)
    await reviews.decide(legacy.id, _decision("approve", 0, evidence["evidence_id"], customer.id),
                         Response(), db=db_session, user=owner)
    await reviews.decide(legacy.id, _decision("revoke", 1), Response(), db=db_session,
                         user=owner)
    url = "/api/v1/fleet-invoice-exports/invoices"
    params = {**_window(), "limit": 1}
    headers = {"X-API-Key": old_key["api_key"]}
    first = await client.get(url, params=params, headers=headers)
    assert first.status_code == 200 and first.json()["next_cursor"]
    second = await client.get(url, params={**params, "cursor": first.json()["next_cursor"]},
                              headers=headers)
    assert second.status_code == 200 and second.json()["next_cursor"] is None
    items = first.json()["items"] + second.json()["items"]
    assert {item["invoice_id"] for item in items} == {str(native.id), str(legacy.id)}
    assert [item.get("event_type", "invoice") for item in items].count("access_removed") == 1
    await exports.revoke_key(old_key["id"], db=db_session, user=owner)
    new_key = await exports.create_key(exports.KeyRequest(customer_id=customer.id, name="Rotated"),
                                       Response(), db=db_session, user=owner)
    replay = await client.get(url, params=_window(), headers={"X-API-Key": new_key["api_key"]})
    assert replay.status_code == 200
    assert any(item.get("event_type") == "access_removed" and item["invoice_id"] == str(legacy.id)
               for item in replay.json()["items"])


@pytest.mark.asyncio
async def test_target_name_change_invalidates_prior_verification(db_session):
    owner, customer, invoice, _ = await _seed(db_session, f"rename-{uuid4().hex}")
    invoice.billed_customer_id = None
    await db_session.commit()
    evidence = await _record_and_verify(db_session, owner, invoice, customer)
    customer.last_name = "Renamed"
    await db_session.commit()
    with pytest.raises(Exception) as error:
        await reviews.decide(invoice.id, _decision("approve", 0, evidence["evidence_id"], customer.id),
                             Response(), db=db_session, user=owner)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_portal_claim_cannot_rename_mapped_bill_to(db_session):
    owner, customer, invoice, _ = await _seed(db_session, f"claim-{uuid4().hex}")
    invoice.billed_customer_id = None
    customer.email = f"fleet-{uuid4().hex}@placeholder.invalid"
    customer.phone = "5551230000"
    await db_session.commit()
    evidence = await _record_and_verify(db_session, owner, invoice, customer)
    await reviews.decide(invoice.id, _decision("approve", 0, evidence["evidence_id"], customer.id),
                         Response(), db=db_session, user=owner)
    with pytest.raises(Exception) as error:
        await _resolve_or_create_customer(db_session, SimpleNamespace(
            email=f"new-{uuid4().hex}@example.com", first_name="Other", last_name="Fleet",
        ), "5551230000", owner.tenant_id)
    assert error.value.status_code == 409
