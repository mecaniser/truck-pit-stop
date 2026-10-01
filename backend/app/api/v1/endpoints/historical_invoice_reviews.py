"""Shop-owner review of the original bill-to on legacy invoices."""

import base64
import binascii
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.db.models.customer import Customer
from app.db.models.historical_invoice_export import (
    FleetInvoiceScopeEvent, HistoricalInvoiceDecision, HistoricalInvoiceEvidence,
    HistoricalInvoiceMapping,
)
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.user import User, UserRole

router = APIRouter()


def _owner(user: User) -> UUID:
    if user.role != UserRole.GARAGE_OWNER or not user.tenant_id:
        raise HTTPException(status_code=403, detail="Shop owner required")
    return user.tenant_id


def _staff(user: User) -> UUID:
    if user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN) or not user.tenant_id:
        raise HTTPException(status_code=403, detail="Shop staff required")
    return user.tenant_id


async def _eligible_invoice(db: AsyncSession, tenant_id: UUID, invoice_id: UUID) -> Invoice:
    row = (await db.execute(select(Invoice, RepairOrder).join(
        RepairOrder, Invoice.repair_order_id == RepairOrder.id,
    ).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id,
            RepairOrder.tenant_id == tenant_id))).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice, _ = row
    if (invoice.deleted_at is not None or invoice.is_internal
            or invoice.status == InvoiceStatus.DRAFT):
        raise HTTPException(status_code=422, detail="Invoice is not eligible for historical export")
    if invoice.billed_customer_id is not None:
        raise HTTPException(status_code=409, detail="Invoice has a native bill-to snapshot")
    return invoice


class EvidenceRequest(BaseModel):
    source_type: Literal["original_invoice", "original_receipt", "preserved_source_record", "billing_correspondence"]
    source_reference: str = Field(min_length=8, max_length=500)
    source_content_type: Literal["application/pdf", "message/rfc822", "application/json"]
    source_document_base64: str = Field(min_length=20, max_length=14_000_000)
    captured_at: datetime
    original_bill_to_name: str = Field(min_length=2, max_length=255)
    original_customer_id: UUID | None = None
    merge_lineage_reference: str | None = Field(default=None, max_length=500)


@router.post("/historical-invoices/{invoice_id}/evidence", status_code=201)
async def record_evidence(invoice_id: UUID, body: EvidenceRequest, response: Response,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_active_user)):
    tenant_id = _staff(user)
    invoice = await _eligible_invoice(db, tenant_id, invoice_id)
    if (body.captured_at.tzinfo is None or body.captured_at > datetime.now(timezone.utc)
            or not body.source_reference.strip() or not body.original_bill_to_name.strip()):
        raise HTTPException(status_code=422, detail="Invalid source evidence")
    if body.original_customer_id:
        original = await db.get(Customer, body.original_customer_id)
        if original and original.tenant_id != tenant_id:
            raise HTTPException(status_code=422, detail="Original customer belongs to another shop")
        if not original and not body.merge_lineage_reference:
            raise HTTPException(status_code=422, detail="Deleted customer needs merge-lineage evidence")
    try:
        document = base64.b64decode(body.source_document_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=422, detail="Invalid source document") from None
    if not 32 <= len(document) <= 10_000_000:
        raise HTTPException(status_code=422, detail="Source document size outside limit")
    if (body.source_content_type == "application/pdf" and not document.startswith(b"%PDF-")
            or body.source_content_type == "message/rfc822" and b"\n" not in document[:1024]
            or body.source_content_type == "application/json" and not document.lstrip().startswith(b"{")):
        raise HTTPException(status_code=422, detail="Source document does not match content type")
    if (body.source_type in ("original_invoice", "original_receipt")
            and body.source_content_type != "application/pdf"):
        raise HTTPException(status_code=422, detail="Original invoice or receipt must be PDF")
    # Store the actual source bytes, compute the hash server-side, and require a
    # different staff reviewer to inspect them before any owner approval.
    evidence = HistoricalInvoiceEvidence(
        tenant_id=tenant_id, invoice_id=invoice.id, repair_order_id=invoice.repair_order_id,
        source_type=body.source_type, source_reference=body.source_reference.strip(),
        source_sha256=hashlib.sha256(document).hexdigest(), source_document=document,
        source_content_type=body.source_content_type, captured_at=body.captured_at,
        original_bill_to_name=body.original_bill_to_name.strip(),
        original_customer_id=body.original_customer_id,
        merge_lineage_reference=body.merge_lineage_reference,
        recorded_by_user_id=user.id,
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)
    response.headers["Cache-Control"] = "no-store"
    return {"evidence_id": evidence.id, "invoice_id": invoice.id,
            "source_type": evidence.source_type, "source_sha256": evidence.source_sha256}


@router.get("/historical-invoices/{invoice_id}/evidence/{evidence_id}/document")
async def evidence_document(invoice_id: UUID, evidence_id: UUID,
                            db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_active_user)):
    tenant_id = _staff(user)
    evidence = (await db.execute(select(HistoricalInvoiceEvidence).where(
        HistoricalInvoiceEvidence.id == evidence_id,
        HistoricalInvoiceEvidence.invoice_id == invoice_id,
        HistoricalInvoiceEvidence.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return Response(evidence.source_document, media_type=evidence.source_content_type,
                    headers={"Cache-Control": "no-store", "Content-Disposition": "attachment"})


class VerifyRequest(BaseModel):
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_invoice_number: str = Field(min_length=1, max_length=50)
    observed_bill_to_name: str = Field(min_length=2, max_length=255)
    target_customer_id: UUID
    verification_note: str = Field(min_length=12, max_length=2000)


@router.post("/historical-invoices/{invoice_id}/evidence/{evidence_id}/verify")
async def verify_evidence(invoice_id: UUID, evidence_id: UUID, body: VerifyRequest,
                          response: Response, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_active_user)):
    tenant_id = _staff(user)
    invoice = await _eligible_invoice(db, tenant_id, invoice_id)
    evidence = (await db.execute(select(HistoricalInvoiceEvidence).where(
        HistoricalInvoiceEvidence.id == evidence_id,
        HistoricalInvoiceEvidence.invoice_id == invoice_id,
        HistoricalInvoiceEvidence.tenant_id == tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if evidence.verified_at is not None:
        raise HTTPException(status_code=409, detail="Evidence already verified")
    if evidence.recorded_by_user_id == user.id:
        raise HTTPException(status_code=403, detail="Another staff member must verify source evidence")
    if (body.source_sha256 != evidence.source_sha256
            or body.observed_invoice_number.strip() != invoice.invoice_number
            or body.observed_bill_to_name.strip().casefold() != evidence.original_bill_to_name.casefold()):
        raise HTTPException(status_code=422, detail="Source identity does not match invoice or evidence")
    target = await db.get(Customer, body.target_customer_id)
    if not target or target.tenant_id != tenant_id or target.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Target customer not found")
    target_names = {f"{target.first_name} {target.last_name}".strip().casefold()}
    if target.company_name:
        target_names.add(target.company_name.strip().casefold())
    if evidence.original_bill_to_name.casefold() not in target_names:
        raise HTTPException(status_code=422, detail="Target legal name differs from source")
    # A name is not a unique legal identity. Hold ambiguous shops until a
    # separately verified identity/lineage proof can distinguish the accounts.
    customers = (await db.execute(select(Customer).where(
        Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None),
    ))).scalars().all()
    observed_name = evidence.original_bill_to_name.casefold()
    for other in customers:
        if other.id == target.id:
            continue
        other_names = {f"{other.first_name} {other.last_name}".strip().casefold()}
        if other.company_name:
            other_names.add(other.company_name.strip().casefold())
        if observed_name in other_names:
            raise HTTPException(status_code=422, detail="Ambiguous bill-to name needs additional identity proof")
    evidence.verified_at = datetime.now(timezone.utc)
    evidence.verified_by_user_id = user.id
    evidence.verified_target_customer_id = target.id
    evidence.verified_target_legal_name = observed_name
    evidence.verification_note = body.verification_note.strip()
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"evidence_id": evidence.id, "verified_at": evidence.verified_at,
            "verified_by_user_id": evidence.verified_by_user_id,
            "verified_target_customer_id": evidence.verified_target_customer_id}


class DecisionRequest(BaseModel):
    action: Literal["approve", "revoke", "reject"]
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=8, max_length=2000)
    evidence_id: UUID | None = None
    target_customer_id: UUID | None = None
    legal_continuity_attested: bool = False


@router.get("/historical-invoices")
async def list_candidates(response: Response, limit: int = Query(100, ge=1, le=100),
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_active_user)):
    tenant_id = _owner(user)
    rows = (await db.execute(select(Invoice, HistoricalInvoiceMapping).join(
        RepairOrder, Invoice.repair_order_id == RepairOrder.id,
    ).outerjoin(HistoricalInvoiceMapping,
                HistoricalInvoiceMapping.invoice_id == Invoice.id).where(
        Invoice.tenant_id == tenant_id, RepairOrder.tenant_id == tenant_id,
        Invoice.billed_customer_id.is_(None), Invoice.deleted_at.is_(None),
        Invoice.is_internal.is_(False), Invoice.status != InvoiceStatus.DRAFT,
    ).order_by(Invoice.created_at.desc(), Invoice.id).limit(limit))).all()
    response.headers["Cache-Control"] = "no-store"
    return [{"invoice_id": inv.id, "invoice_number": inv.invoice_number,
             "repair_order_id": inv.repair_order_id, "invoice_date": inv.created_at,
             "status": inv.status.value, "mapping_version": mapping.version if mapping else 0,
             "target_customer_id": mapping.target_customer_id if mapping else None}
            for inv, mapping in rows]


@router.post("/historical-invoices/{invoice_id}/decisions")
async def decide(invoice_id: UUID, body: DecisionRequest, response: Response,
                 db: AsyncSession = Depends(get_db),
                 user: User = Depends(get_current_active_user)):
    tenant_id = _owner(user)
    invoice = await _eligible_invoice(db, tenant_id, invoice_id)
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(mode="json"),
                                            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # Invoice lock serializes first approval, before a mapping row exists.
    await db.execute(select(Invoice.id).where(Invoice.id == invoice_id).with_for_update())
    prior = (await db.execute(select(HistoricalInvoiceDecision).where(
        HistoricalInvoiceDecision.tenant_id == tenant_id,
        HistoricalInvoiceDecision.invoice_id == invoice_id,
        HistoricalInvoiceDecision.idempotency_key == body.idempotency_key,
    ))).scalar_one_or_none()
    if prior:
        if prior.request_sha256 != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key reused for another decision")
        response.headers["Cache-Control"] = "no-store"
        return {"invoice_id": invoice_id, "version": prior.version,
                "target_customer_id": prior.new_customer_id, "decision_id": prior.id}
    mapping = (await db.execute(select(HistoricalInvoiceMapping).where(
        HistoricalInvoiceMapping.tenant_id == tenant_id,
        HistoricalInvoiceMapping.invoice_id == invoice_id,
    ).with_for_update())).scalar_one_or_none()
    version = mapping.version if mapping else 0
    if body.expected_version != version:
        raise HTTPException(status_code=409, detail="Historical mapping version changed")
    old_target = mapping.target_customer_id if mapping else None
    evidence = None
    target = None
    if body.action == "approve":
        if not body.legal_continuity_attested or not body.evidence_id or not body.target_customer_id:
            raise HTTPException(status_code=422, detail="Evidence, target, and legal-continuity attestation required")
        evidence = (await db.execute(select(HistoricalInvoiceEvidence).where(
            HistoricalInvoiceEvidence.id == body.evidence_id,
            HistoricalInvoiceEvidence.tenant_id == tenant_id,
            HistoricalInvoiceEvidence.invoice_id == invoice_id,
            HistoricalInvoiceEvidence.repair_order_id == invoice.repair_order_id,
        ))).scalar_one_or_none()
        if not evidence:
            raise HTTPException(status_code=422, detail="Evidence does not belong to invoice")
        if evidence.verified_at is None:
            raise HTTPException(status_code=422, detail="Source evidence requires independent verification")
        target = (await db.execute(select(Customer).where(
            Customer.id == body.target_customer_id,
        ).with_for_update())).scalar_one_or_none()
        if not target or target.tenant_id != tenant_id or target.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Target customer not found")
        if evidence.verified_target_customer_id != body.target_customer_id:
            raise HTTPException(status_code=422, detail="Target was not verified against source")
        current_names = {f"{target.first_name} {target.last_name}".strip().casefold()}
        if target.company_name:
            current_names.add(target.company_name.strip().casefold())
        if evidence.verified_target_legal_name not in current_names:
            raise HTTPException(status_code=409, detail="Target identity changed since verification")
        candidates = (await db.execute(select(Customer).where(
            Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None),
        ))).scalars().all()
        for other in candidates:
            if other.id == target.id:
                continue
            other_names = {f"{other.first_name} {other.last_name}".strip().casefold()}
            if other.company_name:
                other_names.add(other.company_name.strip().casefold())
            if evidence.verified_target_legal_name in other_names:
                raise HTTPException(status_code=409, detail="Bill-to name became ambiguous after verification")
    elif body.action == "revoke" and old_target is None:
        raise HTTPException(status_code=409, detail="No active mapping to revoke")
    elif body.action == "reject" and old_target is not None:
        raise HTTPException(status_code=409, detail="Revoke the active mapping instead")
    new_target = target.id if target else None
    now = datetime.now(timezone.utc)
    if not mapping:
        mapping = HistoricalInvoiceMapping(tenant_id=tenant_id, invoice_id=invoice_id)
        db.add(mapping)
    mapping.target_customer_id = new_target
    mapping.evidence_id = evidence.id if evidence else mapping.evidence_id
    mapping.version = version + 1
    mapping.updated_at = now
    decision = HistoricalInvoiceDecision(
        tenant_id=tenant_id, invoice_id=invoice_id, evidence_id=evidence.id if evidence else mapping.evidence_id,
        evidence_sha256=evidence.source_sha256 if evidence else None,
        original_bill_to_name=evidence.original_bill_to_name if evidence else None,
        actor_user_id=user.id, old_customer_id=old_target, new_customer_id=new_target,
        action=body.action, reason=body.reason.strip(), version=mapping.version,
        idempotency_key=body.idempotency_key, request_sha256=fingerprint,
    )
    db.add(decision)
    await db.flush()
    if old_target and old_target != new_target:
        db.add(FleetInvoiceScopeEvent(
            tenant_id=tenant_id, invoice_id=invoice_id, customer_id=old_target,
            decision_id=decision.id, kind="access_removed", effective_at=now,
        ))
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"invoice_id": invoice_id, "version": mapping.version,
            "target_customer_id": new_target, "decision_id": decision.id}
