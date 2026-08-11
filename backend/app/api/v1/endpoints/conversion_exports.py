from __future__ import annotations

import csv
import hashlib
import io
import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user, get_db, user_has_permission
from app.db.models.conversion_api_key import ConversionApiKey
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.conversion_export_audit_service import record_conversion_audit
from app.services.paid_invoice_webhook_service import CONVERSION_EVENT_TYPES, attribution, enqueue_conversion_event, service_lines

router = APIRouter()


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _require_conversion_access(user: User) -> UUID:
    if not user.tenant_id or user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN) or not user_has_permission(user, "conversion_exports"):
        raise HTTPException(status_code=403, detail="Shop owner or conversion-export permission required")
    return user.tenant_id


async def conversion_api_key(x_api_key: str = Header(..., alias="X-API-Key", max_length=255), db: AsyncSession = Depends(get_db)) -> ConversionApiKey:
    key = (await db.execute(select(ConversionApiKey).where(ConversionApiKey.key_hash == _hash_key(x_api_key), ConversionApiKey.revoked_at.is_(None)))).scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=401, detail="Invalid or revoked conversion API key")
    return key


async def conversion_api_tenant(key: ConversionApiKey = Depends(conversion_api_key), db: AsyncSession = Depends(get_db)) -> Tenant:
    tenant = await db.get(Tenant, key.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=401, detail="Shop is inactive")
    key.last_used_at = datetime.now(timezone.utc)
    return tenant


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class ApiKeyCreated(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    api_key: str
    created_at: datetime


@router.post("/api-keys", response_model=ApiKeyCreated)
async def create_api_key(body: ApiKeyCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    tenant_id = _require_conversion_access(user)
    raw = f"dbce_{secrets.token_urlsafe(32)}"
    record = ConversionApiKey(tenant_id=tenant_id, name=body.name.strip(), key_prefix=raw[:12], key_hash=_hash_key(raw))
    db.add(record)
    await db.flush()
    record_conversion_audit(db, tenant_id=tenant_id, actor_user_id=user.id, action="api_key.created", target_type="conversion_api_key", target_id=record.id, metadata={"key_prefix": record.key_prefix})
    await db.commit(); await db.refresh(record)
    return ApiKeyCreated(id=record.id, name=record.name, key_prefix=record.key_prefix, api_key=raw, created_at=record.created_at)


@router.get("/api-keys")
async def list_api_keys(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    tenant_id = _require_conversion_access(user)
    rows = (await db.execute(select(ConversionApiKey).where(ConversionApiKey.tenant_id == tenant_id).order_by(ConversionApiKey.created_at.desc()))).scalars().all()
    record_conversion_audit(db, tenant_id=tenant_id, actor_user_id=user.id, action="api_key.listed", target_type="tenant", target_id=tenant_id, metadata={"result_count": len(rows)})
    await db.commit()
    return [{"id": row.id, "name": row.name, "key_prefix": row.key_prefix, "created_at": row.created_at, "last_used_at": row.last_used_at, "revoked_at": row.revoked_at} for row in rows]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(key_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    tenant_id = _require_conversion_access(user)
    key = await db.get(ConversionApiKey, key_id)
    if not key or key.tenant_id != tenant_id: raise HTTPException(status_code=404, detail="API key not found")
    key.revoked_at = datetime.now(timezone.utc)
    record_conversion_audit(db, tenant_id=tenant_id, actor_user_id=user.id, action="api_key.revoked", target_type="conversion_api_key", target_id=key.id, metadata={"key_prefix": key.key_prefix})
    await db.commit(); return Response(status_code=204)


def _export_item(invoice: Invoice, order: RepairOrder, customer: Customer) -> dict:
    return {
        "repair_order_id": order.order_number, "invoice_id": str(invoice.id),
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "total_amount": float(Decimal(invoice.total_amount)), "currency": "USD",
        "service_lines": service_lines(invoice),
        "customer": {"phone": customer.phone, "email": customer.email},
        "attribution": attribution(order),
    }


@router.get("/paid-repair-orders")
async def export_paid_repair_orders(
    paid_from: datetime = Query(...), paid_to: datetime = Query(...), payment_status: str = Query("paid"),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), format: str = Query("json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db), tenant: Tenant = Depends(conversion_api_tenant), api_key: ConversionApiKey = Depends(conversion_api_key),
):
    if paid_to < paid_from: raise HTTPException(status_code=422, detail="paid_to must be after paid_from")
    if payment_status != "paid": raise HTTPException(status_code=422, detail="Only paid repair orders are exportable")
    filters = [Invoice.tenant_id == tenant.id, Invoice.status == InvoiceStatus.PAID, Invoice.paid_at >= paid_from, Invoice.paid_at <= paid_to, Invoice.total_amount > 0, RepairOrder.deleted_at.is_(None)]
    total = (await db.execute(select(func.count(Invoice.id)).join(RepairOrder).where(*filters))).scalar_one()
    rows = (await db.execute(select(Invoice, RepairOrder, Customer).join(RepairOrder, Invoice.repair_order_id == RepairOrder.id).join(Customer, RepairOrder.customer_id == Customer.id).where(*filters).order_by(Invoice.paid_at, Invoice.id).offset(skip).limit(limit))).all()
    items = [_export_item(*row) for row in rows]
    record_conversion_audit(
        db, tenant_id=tenant.id, actor_api_key_id=api_key.id, action="paid_repair_orders.exported",
        target_type="tenant", target_id=tenant.id,
        metadata={"format": format, "paid_from": paid_from.isoformat(), "paid_to": paid_to.isoformat(), "skip": skip, "limit": limit, "result_count": len(items)},
    )
    await db.commit()
    if format == "csv":
        output = io.StringIO(); fields = ["repair_order_id", "invoice_id", "paid_at", "total_amount", "currency", "service_lines", "customer_phone", "customer_email", "attribution"]
        writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
        for item in items: writer.writerow({**{k: item[k] for k in fields[:5]}, "service_lines": json.dumps(item["service_lines"]), "customer_phone": item["customer"]["phone"], "customer_email": item["customer"]["email"], "attribution": json.dumps(item["attribution"])})
        return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=paid-repair-orders.csv"})
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/deliveries")
async def delivery_history(skip: int = 0, limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    tenant_id = _require_conversion_access(user)
    rows = (await db.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id == tenant_id, ProviderOutboxEvent.event_type.in_(CONVERSION_EVENT_TYPES)).order_by(ProviderOutboxEvent.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    record_conversion_audit(db, tenant_id=tenant_id, actor_user_id=user.id, action="delivery_history.viewed", target_type="tenant", target_id=tenant_id, metadata={"skip": skip, "limit": limit, "result_count": len(rows)})
    await db.commit()
    return [{"event_id": row.id, "event_type": row.event_type, "status": row.status, "created_at": row.created_at, "last_attempt_at": row.last_attempt_at, "completed_at": row.completed_at, "response_code": row.last_response_code, "retry_count": row.attempt_count, "last_error": row.last_error} for row in rows]


@router.post("/deliveries/{event_id}/replay", status_code=202)
async def replay_delivery(event_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    tenant_id = _require_conversion_access(user); event = await db.get(ProviderOutboxEvent, event_id)
    if not event or event.tenant_id != tenant_id or event.event_type not in CONVERSION_EVENT_TYPES: raise HTTPException(status_code=404, detail="Delivery not found")
    if (event.payload or {}).get("pii_redacted_at"):
        raise HTTPException(status_code=410, detail="Delivery payload expired under the conversion PII retention policy")
    if event.status != ProviderOutboxStatus.DEAD.value: raise HTTPException(status_code=409, detail="Only failed deliveries can be replayed")
    event.status, event.available_at, event.completed_at, event.last_error = ProviderOutboxStatus.PENDING.value, datetime.now(timezone.utc), None, None
    event.attempt_count = 0
    record_conversion_audit(db, tenant_id=tenant_id, actor_user_id=user.id, action="delivery.replayed", target_type="provider_outbox", target_id=event.id, metadata={"event_type": event.event_type})
    await db.commit(); return {"event_id": event.id, "status": event.status}


class CorrectionRequest(BaseModel):
    event_type: Literal["repair_order.payment_refunded", "repair_order.payment_voided", "repair_order.payment_adjusted"]
    total_amount: Decimal = Field(max_digits=10, decimal_places=2)


@router.post("/invoices/{invoice_id}/corrections", status_code=202)
async def create_correction(invoice_id: UUID, body: CorrectionRequest, idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=255), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    tenant_id = _require_conversion_access(user)
    if body.total_amount == 0:
        raise HTTPException(status_code=422, detail="Correction amount must be non-zero")
    if body.event_type in {"repair_order.payment_refunded", "repair_order.payment_voided"} and body.total_amount > 0:
        raise HTTPException(status_code=422, detail="Refund and void correction amounts must be negative")
    # Serialize every correction against the authoritative invoice row. This
    # makes different idempotency keys obey the same cumulative reversal limit.
    invoice = (await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.repair_order).selectinload(RepairOrder.customer))
        .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
        .with_for_update()
    )).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    order = invoice.repair_order
    if invoice.status != InvoiceStatus.PAID or invoice.paid_at is None or order.status.value != "paid":
        raise HTTPException(status_code=409, detail="Corrections require an authoritatively paid invoice")
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Shop not found")
    stable_key = f"correction:{idempotency_key}"
    existing = (await db.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.tenant_id == tenant_id, ProviderOutboxEvent.idempotency_key == stable_key))).scalar_one_or_none()
    if existing:
        existing_amount = Decimal(str(existing.payload.get("total_amount", "0")))
        if existing.aggregate_id != invoice_id or existing.event_type != body.event_type or existing_amount != body.total_amount:
            raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different correction")
        record_conversion_audit(db, tenant_id=tenant_id, actor_user_id=user.id, action="correction.idempotent_replay", target_type="provider_outbox", target_id=existing.id, metadata={"invoice_id": str(invoice_id), "event_type": body.event_type})
        await db.commit()
        return {"event_id": existing.id, "event_type": existing.event_type}

    paid_total = Decimal((await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.invoice_id == invoice.id,
            Payment.tenant_id == tenant_id,
            Payment.status == PaymentStatus.COMPLETED,
            Payment.amount > 0,
        )
    )).scalar_one()).quantize(Decimal("0.01"))
    authoritative_paid = min(paid_total, Decimal(invoice.total_amount)).quantize(Decimal("0.01"))
    if authoritative_paid <= 0:
        raise HTTPException(status_code=409, detail="Invoice has no completed payment to correct")

    prior = (await db.execute(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.tenant_id == tenant_id,
        ProviderOutboxEvent.aggregate_type == "invoice",
        ProviderOutboxEvent.aggregate_id == invoice.id,
        ProviderOutboxEvent.event_type.in_(CONVERSION_EVENT_TYPES - {"repair_order.paid"}),
    ))).scalars().all()
    prior_amounts = [(row.event_type, Decimal(str(row.payload.get("total_amount", "0")))) for row in prior]
    if any(event_type == "repair_order.payment_voided" for event_type, _amount in prior_amounts):
        raise HTTPException(status_code=409, detail="A voided payment cannot receive another correction")
    if body.event_type == "repair_order.payment_voided":
        if prior_amounts:
            raise HTTPException(status_code=409, detail="Void is exclusive and cannot follow another correction")
        if body.total_amount != -authoritative_paid:
            raise HTTPException(status_code=422, detail="Void correction amount must reverse the authoritative paid amount")

    prior_reversal = sum((-amount for event_type, amount in prior_amounts if event_type in {"repair_order.payment_refunded", "repair_order.payment_voided"} and amount < 0), Decimal("0"))
    next_reversal = prior_reversal + (-body.total_amount if body.event_type == "repair_order.payment_refunded" else Decimal("0"))
    if next_reversal > authoritative_paid:
        raise HTTPException(status_code=422, detail="Cumulative refunds exceed the authoritative paid amount")

    recognized_after = authoritative_paid + sum((amount for _event_type, amount in prior_amounts), Decimal("0")) + body.total_amount
    if recognized_after < 0 or recognized_after > authoritative_paid:
        raise HTTPException(status_code=422, detail="Adjustment would move recognized payment outside the paid range")

    event = await enqueue_conversion_event(db, tenant=tenant, invoice=invoice, order=order, customer=order.customer, event_type=body.event_type, idempotency_key=stable_key, total_amount=body.total_amount)
    if not event: raise HTTPException(status_code=409, detail="Conversion webhook is not enabled")
    record_conversion_audit(db, tenant_id=tenant_id, actor_user_id=user.id, action="correction.created", target_type="provider_outbox", target_id=event.id, metadata={"invoice_id": str(invoice.id), "event_type": body.event_type, "amount": str(body.total_amount), "authoritative_paid": str(authoritative_paid)})
    await db.commit(); return {"event_id": event.id, "event_type": event.event_type}
