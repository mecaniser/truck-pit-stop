"""DB-045 Activity, lifecycle, counter-sale, receipt, and provider APIs."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_db
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.inventory_lifecycle import (
    CounterSale, CounterSaleLine, CounterSalePaymentAttempt,
    CounterSaleProviderEvent, CounterSaleRefund, CounterSaleReturn,
    CounterSaleReturnLine, PartActivityEvent,
)
from app.db.models.parts_operations import (
    CoreObligation, PurchaseReceipt, PurchaseReceiptLine, VendorReturn,
    VendorReturnLine,
)
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.services.counter_sale_receipt import generate_counter_sale_receipt_pdf
from app.services.counter_sale_service import (
    MANAGER_ROLES, MANUAL_TENDERS, create_or_replace_draft,
    create_return_claim, finalize_checkout_failure, finalize_checkout_success,
    finalize_refund_failure, finalize_refund_success, money, now_utc, require_counter_sale_role,
    require_counter_sales_enabled, sale_lines, serialize_sale, tenant_sale,
    prepare_checkout,
)
from app.services.part_activity_service import (
    cursor_condition, decode_cursor, encode_cursor, escape_csv_text,
    normalized_filter_fingerprint, serialize_activity,
)
from app.services.parts_operations_service import (
    begin_idempotency, canonical_fingerprint, complete_idempotency,
    find_idempotent_response, require_parts_operations_enabled,
    require_parts_role, validate_idempotency_key,
)
from app.services.quickbooks_payments_service import (
    QuickBooksPaymentError, create_charge, get_charge, is_successful_charge,
    refund_charge,
)


router = APIRouter()
webhook_router = APIRouter()

ACTIVITY_CATEGORIES = frozenset({"catalog", "stock", "repairs", "purchasing", "returns", "sales"})
SALE_STATUSES = frozenset({"draft", "awaiting_payment", "completed", "partially_returned", "returned", "cancelled"})


class SaleLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inventory_id: UUID
    quantity: int = Field(ge=1, le=999)
    charged_unit_price: Decimal | None = Field(default=None, gt=0)
    price_override_reason: str | None = Field(default=None, max_length=500)


class SaleDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: UUID | None = None
    buyer_name: str | None = Field(default=None, max_length=255)
    buyer_email: EmailStr | None = None
    buyer_phone: str | None = Field(default=None, max_length=40)
    lines: list[SaleLineInput] = Field(min_length=1, max_length=100)


class SalePatchInput(SaleDraftInput):
    expected_version: int = Field(ge=1)


class CheckoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    tender: Literal["stripe", "quickbooks_payments", "cash", "check", "ach", "zelle", "external_terminal", "fleet_reference", "other"]
    payment_token: str | None = Field(default=None, max_length=2048)
    manual_reference: str | None = Field(default=None, max_length=255)
    receipt_email: EmailStr | None = None

    @field_validator("payment_token")
    @classmethod
    def _token_nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("payment_token cannot be blank")
        return value


class CancelInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class ReturnLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sale_line_id: UUID
    quantity: int = Field(ge=1, le=999)
    reason: str = Field(min_length=3, max_length=500)
    disposition: Literal["restock", "damaged"]


class ReturnInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    lines: list[ReturnLineInput] = Field(min_length=1, max_length=100)
    manual_refund_reference: str | None = Field(default=None, max_length=255)


class ReceiptEmailInput(BaseModel):
    email: EmailStr


class RetryRefundInput(BaseModel):
    expected_version: int = Field(ge=1)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not found")


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(status_code=422, detail="Dates must include a timezone")
    return value.astimezone(timezone.utc)


def _sale_cursor(created_at: datetime, sale_id: UUID, *, fingerprint: str) -> str:
    created_at_utc = (
        created_at.replace(tzinfo=timezone.utc)
        if created_at.tzinfo is None
        else created_at.astimezone(timezone.utc)
    )
    payload = json.dumps(
        {"v": 1, "created_at": created_at_utc.isoformat(), "id": str(sale_id), "fp": fingerprint},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_sale_cursor(value: str, *, fingerprint: str) -> tuple[datetime, UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode())
        if payload.get("v") != 1 or payload.get("fp") != fingerprint:
            raise ValueError
        return datetime.fromisoformat(payload["created_at"]), UUID(payload["id"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid counter-sale cursor") from exc


async def _mutation(
    db: AsyncSession, *, tenant_id: UUID, user: User, family: str,
    route: str, key: str | None, payload: dict[str, Any],
    allow_incomplete_resume: bool = False,
):
    valid = validate_idempotency_key(key)
    fingerprint = canonical_fingerprint(route=route, principal_id=user.id, payload=payload)
    existing = await find_idempotent_response(
        db, tenant_id=tenant_id, family=family, key=valid,
        fingerprint=fingerprint,
        allow_incomplete_resume=allow_incomplete_resume,
    )
    if existing:
        if existing.completed_at is None:
            return None, existing, False
        return json.loads(existing.response_body or "{}"), existing, True
    record = begin_idempotency(tenant_id=tenant_id, family=family, key=valid, fingerprint=fingerprint)
    db.add(record)
    return None, record, False


async def _activity_tenant(db: AsyncSession, user: User) -> UUID:
    tenant_id = await require_parts_operations_enabled(db, user)
    require_parts_role(user, mutate=False)
    return tenant_id


def _activity_filters(
    inventory_id: UUID | None, category: str | None, event_types: list[str],
    actor_id: UUID | None, source_type: str | None, source_id: UUID | None,
    search: str | None, from_at: datetime | None, to: datetime | None,
) -> dict[str, Any]:
    if category is not None and category not in ACTIVITY_CATEGORIES:
        raise HTTPException(status_code=422, detail="Invalid Activity category")
    if source_id and not source_type:
        raise HTTPException(status_code=422, detail="source_id requires source_type")
    if search is not None:
        search = " ".join(search.split())
        if not 2 <= len(search) <= 200:
            raise HTTPException(status_code=422, detail="Invalid Activity search")
    from_at, to = _utc(from_at), _utc(to)
    if from_at and to and from_at >= to:
        raise HTTPException(status_code=422, detail="Invalid Activity date range")
    return {
        "inventory_id": str(inventory_id) if inventory_id else None,
        "category": category, "event_type": sorted(set(event_types)),
        "actor_id": str(actor_id) if actor_id else None,
        "source_type": source_type, "source_id": str(source_id) if source_id else None,
        "search": search.casefold() if search else None,
        "from": from_at.isoformat() if from_at else None, "to": to.isoformat() if to else None,
    }


def _activity_statement(tenant_id: UUID, filters: dict[str, Any]):
    stmt = select(PartActivityEvent).where(PartActivityEvent.tenant_id == tenant_id)
    if filters["inventory_id"]:
        stmt = stmt.where(PartActivityEvent.inventory_id == UUID(filters["inventory_id"]))
    if filters["category"]:
        stmt = stmt.where(PartActivityEvent.category == filters["category"])
    if filters["event_type"]:
        stmt = stmt.where(PartActivityEvent.event_type.in_(filters["event_type"]))
    if filters["actor_id"]:
        stmt = stmt.where(PartActivityEvent.actor_id == UUID(filters["actor_id"]))
    if filters["source_type"]:
        stmt = stmt.where(PartActivityEvent.source_type == filters["source_type"])
    if filters["source_id"]:
        stmt = stmt.where(PartActivityEvent.source_id == UUID(filters["source_id"]))
    if filters["search"]:
        pattern = f"%{filters['search']}%"
        stmt = stmt.where(or_(
            func.lower(PartActivityEvent.actor_name_snapshot).like(pattern),
            func.lower(PartActivityEvent.reason_code).like(pattern),
            func.lower(PartActivityEvent.note).like(pattern),
            func.lower(PartActivityEvent.source_number_snapshot).like(pattern),
            func.lower(PartActivityEvent.part_sku_snapshot).like(pattern),
            func.lower(PartActivityEvent.part_name_snapshot).like(pattern),
        ))
    if filters["from"]:
        stmt = stmt.where(PartActivityEvent.occurred_at >= datetime.fromisoformat(filters["from"]))
    if filters["to"]:
        stmt = stmt.where(PartActivityEvent.occurred_at < datetime.fromisoformat(filters["to"]))
    return stmt


@router.get("/activity-events")
async def list_activity_events(
    inventory_id: UUID | None = None, category: str | None = None,
    event_type: list[str] = Query(default=[]), actor_id: UUID | None = None,
    source_type: str | None = None, source_id: UUID | None = None,
    search: str | None = None, from_at: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None, cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user),
):
    tenant_id = await _activity_tenant(db, user)
    if inventory_id and not await db.scalar(select(Inventory.id).where(
        Inventory.id == inventory_id, Inventory.tenant_id == tenant_id,
        Inventory.deleted_at.is_(None),
    )):
        raise _not_found()
    filters = _activity_filters(inventory_id, category, event_type, actor_id, source_type, source_id, search, from_at, to)
    fingerprint = normalized_filter_fingerprint(filters)
    stmt = _activity_statement(tenant_id, filters)
    if cursor:
        occurred_at, event_id = decode_cursor(cursor, fingerprint=fingerprint)
        stmt = stmt.where(cursor_condition(occurred_at, event_id))
    rows = list((await db.execute(stmt.order_by(PartActivityEvent.occurred_at.desc(), PartActivityEvent.id.desc()).limit(limit + 1))).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(occurred_at=rows[-1].occurred_at, event_id=rows[-1].id, fingerprint=fingerprint) if has_more and rows else None
    items = [serialize_activity(row) for row in rows]
    return {"items": items, "next_cursor": next_cursor}


@router.get("/activity-events/export.csv")
async def export_activity_events(
    inventory_id: UUID | None = None, category: str | None = None,
    event_type: list[str] = Query(default=[]), actor_id: UUID | None = None,
    source_type: str | None = None, source_id: UUID | None = None,
    search: str | None = None, from_at: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user),
):
    tenant_id = await _activity_tenant(db, user)
    filters = _activity_filters(inventory_id, category, event_type, actor_id, source_type, source_id, search, from_at, to)
    stmt = _activity_statement(tenant_id, filters)
    rows = list((await db.execute(stmt.order_by(PartActivityEvent.occurred_at.desc(), PartActivityEvent.id.desc()).limit(50001))).scalars().all())
    if len(rows) > 50000:
        raise HTTPException(status_code=413, detail="Activity export exceeds 50,000 rows; narrow the filters")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["occurred_at", "part_sku", "part_name", "category", "event_type", "actor", "reason", "note", "before", "after", "physical_on_hand", "held_for_checkout", "available_to_sell", "delta", "wac", "list_price", "charged_price", "tax", "fee", "tender", "payment_status", "source_type", "source_number", "source_link", "origin", "correlation_id"])
    for row in rows:
        value = serialize_activity(row)
        stock, monetary, payment, source = row.stock_snapshot or {}, row.money_snapshot or {}, row.payment_snapshot or {}, value["source"]
        writer.writerow([escape_csv_text(item) for item in (
            row.occurred_at.isoformat(), row.part_sku_snapshot,
            row.part_name_snapshot, row.category, row.event_type,
            row.actor_name_snapshot, row.reason_code, row.note,
            json.dumps(row.before_values or {}, sort_keys=True), json.dumps(row.after_values or {}, sort_keys=True),
            stock.get("physical_on_hand"), stock.get("held_for_checkout"), stock.get("available_to_sell"), stock.get("delta"),
            monetary.get("wac_after"), monetary.get("list_price"), monetary.get("charged_price"), monetary.get("tax"), monetary.get("service_fee"),
            payment.get("tender"), payment.get("state"), row.source_type, row.source_number_snapshot,
            source["href"], row.origin, row.correlation_id,
        )])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=part-activity.csv"})


@router.get("/parts/{inventory_id}/lifecycle-summary")
async def part_lifecycle_summary(
    inventory_id: UUID, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant_id = await _activity_tenant(db, user)
    item = (await db.execute(select(Inventory).where(
        Inventory.id == inventory_id, Inventory.tenant_id == tenant_id,
        Inventory.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if item is None:
        raise _not_found()
    usage_rows = (await db.execute(select(PartsUsage.quantity, PartsUsage.repair_order_id, PartsUsage.created_at).where(
        PartsUsage.tenant_id == tenant_id, PartsUsage.inventory_id == inventory_id,
        PartsUsage.deleted_at.is_(None),
    ))).all()
    receipt_rows = (await db.execute(select(PurchaseReceiptLine.quantity, PurchaseReceiptLine.purchase_receipt_id).where(
        PurchaseReceiptLine.tenant_id == tenant_id, PurchaseReceiptLine.inventory_id == inventory_id,
    ))).all()
    vendor_rows = (await db.execute(select(VendorReturnLine.quantity).join(
        VendorReturn, VendorReturn.id == VendorReturnLine.vendor_return_id
    ).where(
        VendorReturnLine.tenant_id == tenant_id, VendorReturnLine.inventory_id == inventory_id,
        VendorReturnLine.deleted_at.is_(None), VendorReturn.status.in_(("shipped", "credited")),
    ))).all()
    core_count = int(await db.scalar(select(func.count(CoreObligation.id)).where(
        CoreObligation.tenant_id == tenant_id, CoreObligation.inventory_id == inventory_id,
        CoreObligation.deleted_at.is_(None), CoreObligation.status.in_(("expected", "on_hand")),
    )) or 0)
    sale_rows = (await db.execute(select(CounterSaleLine, CounterSale).join(
        CounterSale, CounterSale.id == CounterSaleLine.sale_id
    ).where(
        CounterSaleLine.tenant_id == tenant_id, CounterSaleLine.inventory_id == inventory_id,
        CounterSaleLine.deleted_at.is_(None), CounterSale.status.in_(("completed", "partially_returned", "returned")),
    ))).all()
    returned_rows = (await db.execute(select(CounterSaleReturnLine, CounterSaleReturn).join(
        CounterSaleReturn, CounterSaleReturn.id == CounterSaleReturnLine.return_id
    ).join(CounterSaleLine, CounterSaleLine.id == CounterSaleReturnLine.sale_line_id).where(
        CounterSaleReturnLine.tenant_id == tenant_id, CounterSaleLine.inventory_id == inventory_id,
        CounterSaleReturn.state == "completed",
    ))).all()
    sold_qty = sum(line.quantity for line, _sale in sale_rows)
    returned_qty = sum(line.quantity for line, _return in returned_rows)
    gross = sum((Decimal(line.item_subtotal) for line, _sale in sale_rows), Decimal("0"))
    discounts = sum((Decimal(line.discount_total) for line, _sale in sale_rows), Decimal("0"))
    refunds = sum((Decimal(line.item_amount) for line, _return in returned_rows), Decimal("0"))
    event_count = int(await db.scalar(select(func.count(PartActivityEvent.id)).where(
        PartActivityEvent.tenant_id == tenant_id, PartActivityEvent.inventory_id == inventory_id,
    )) or 0)
    last_event = await db.scalar(select(func.max(PartActivityEvent.occurred_at)).where(
        PartActivityEvent.tenant_id == tenant_id, PartActivityEvent.inventory_id == inventory_id,
    ))
    return {
        "inventory_id": str(item.id), "as_of": now_utc().isoformat(),
        "repairs": {"units_used": str(sum((Decimal(row.quantity) for row in usage_rows), Decimal("0"))), "repair_order_count": len({row.repair_order_id for row in usage_rows}), "last_used_at": max((row.created_at for row in usage_rows), default=None)},
        "purchasing": {"units_received": sum(int(row.quantity) for row in receipt_rows), "receipt_count": len({row.purchase_receipt_id for row in receipt_rows}), "units_returned_to_vendor": sum(int(row.quantity) for row in vendor_rows), "open_core_obligations": core_count},
        "sales": {"units_sold": sold_qty, "units_returned": returned_qty, "net_units": sold_qty - returned_qty, "gross_item_revenue": str(money(gross)), "discounts": str(money(discounts)), "refunds": str(money(refunds)), "net_item_revenue": str(money(gross - refunds)), "last_sold_at": max((sale.completed_at for _line, sale in sale_rows if sale.completed_at), default=None)},
        "activity": {"event_count": event_count, "last_event_at": last_event},
    }


@router.get("/counter-sales")
async def list_counter_sales(
    sale_status: str | None = Query(default=None, alias="status"), customer_id: UUID | None = None,
    text: str | None = None,
    search: str | None = Query(default=None, deprecated=True),
    from_at: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None, cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100), db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    if sale_status and sale_status not in SALE_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid sale status")
    normalized_text = " ".join((text or search or "").split()) or None
    if text and search and " ".join(text.split()) != " ".join(search.split()):
        raise HTTPException(status_code=422, detail="Use one counter-sale text filter")
    normalized_from = _utc(from_at)
    normalized_to = _utc(to)
    filter_fingerprint = normalized_filter_fingerprint({
        "status": sale_status,
        "customer_id": str(customer_id) if customer_id else None,
        "text": normalized_text,
        "from": normalized_from.isoformat() if normalized_from else None,
        "to": normalized_to.isoformat() if normalized_to else None,
    })
    stmt = select(CounterSale).where(CounterSale.tenant_id == tenant.id, CounterSale.deleted_at.is_(None))
    if sale_status:
        stmt = stmt.where(CounterSale.status == sale_status)
    if customer_id:
        stmt = stmt.where(CounterSale.customer_id == customer_id)
    if normalized_text:
        pattern = f"%{normalized_text}%"
        stmt = stmt.where(or_(CounterSale.sale_number.ilike(pattern), CounterSale.buyer_name_snapshot.ilike(pattern), CounterSale.buyer_email_snapshot.ilike(pattern)))
    if normalized_from:
        stmt = stmt.where(CounterSale.created_at >= normalized_from)
    if normalized_to:
        stmt = stmt.where(CounterSale.created_at < normalized_to)
    if cursor:
        created_at, sale_id = _decode_sale_cursor(cursor, fingerprint=filter_fingerprint)
        stmt = stmt.where(or_(CounterSale.created_at < created_at, (CounterSale.created_at == created_at) & (CounterSale.id < sale_id)))
    rows = list((await db.execute(stmt.order_by(CounterSale.created_at.desc(), CounterSale.id.desc()).limit(limit + 1))).scalars().all())
    has_more, rows = len(rows) > limit, rows[:limit]
    values = []
    for row in rows:
        line_count = int(await db.scalar(select(func.count(CounterSaleLine.id)).where(CounterSaleLine.sale_id == row.id, CounterSaleLine.deleted_at.is_(None))) or 0)
        tender = await db.scalar(select(CounterSalePaymentAttempt.tender).where(CounterSalePaymentAttempt.sale_id == row.id).order_by(CounterSalePaymentAttempt.created_at.desc()).limit(1))
        values.append({"id": str(row.id), "sale_number": row.sale_number, "status": row.status, "buyer_name": row.buyer_name_snapshot, "buyer_email": row.buyer_email_snapshot, "total_amount": str(row.total), "line_count": line_count, "tender": tender, "created_at": row.created_at.isoformat(), "completed_at": row.completed_at.isoformat() if row.completed_at else None})
    return {
        "items": values,
        "next_cursor": _sale_cursor(
            rows[-1].created_at, rows[-1].id, fingerprint=filter_fingerprint,
        ) if has_more and rows else None,
    }


@router.post("/counter-sales", status_code=201)
async def create_counter_sale(
    body: SaleDraftInput, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    payload = body.model_dump(mode="json")
    replay, record, replayed = await _mutation(db, tenant_id=tenant.id, user=user, family="counter_sale_create", route="POST:/counter-sales", key=idempotency_key, payload=payload)
    if replayed:
        return replay
    sale, _lines = await create_or_replace_draft(db, tenant=tenant, actor=user, sale=None, customer_id=body.customer_id, buyer_name=body.buyer_name, buyer_email=str(body.buyer_email) if body.buyer_email else None, buyer_phone=body.buyer_phone, line_inputs=[line.model_dump() for line in body.lines])
    response = await serialize_sale(db, sale, user)
    complete_idempotency(record, status_code=201, body=response)
    await db.commit()
    return response


@router.get("/counter-sales/{sale_id}")
async def get_counter_sale(sale_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    return await serialize_sale(db, await tenant_sale(db, tenant.id, sale_id), user)


@router.patch("/counter-sales/{sale_id}")
async def update_counter_sale(
    sale_id: UUID, body: SalePatchInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    sale = await tenant_sale(db, tenant.id, sale_id, lock=True)
    if sale.version != body.expected_version:
        raise HTTPException(status_code=409, detail="Counter sale version conflict")
    payload = body.model_dump(mode="json")
    replay, record, replayed = await _mutation(db, tenant_id=tenant.id, user=user, family="counter_sale_update", route=f"PATCH:/counter-sales/{sale_id}", key=idempotency_key, payload=payload)
    if replayed:
        return replay
    sale, _lines = await create_or_replace_draft(db, tenant=tenant, actor=user, sale=sale, customer_id=body.customer_id, buyer_name=body.buyer_name, buyer_email=str(body.buyer_email) if body.buyer_email else None, buyer_phone=body.buyer_phone, line_inputs=[line.model_dump() for line in body.lines])
    response = await serialize_sale(db, sale, user)
    complete_idempotency(record, status_code=200, body=response)
    await db.commit()
    return response


async def _connection(db: AsyncSession, tenant_id: UUID) -> QuickBooksConnection:
    row = (await db.execute(select(QuickBooksConnection).where(
        QuickBooksConnection.tenant_id == tenant_id,
        QuickBooksConnection.deleted_at.is_(None), QuickBooksConnection.status == "connected",
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=424, detail="Payment provider is not configured")
    return row


@router.post("/counter-sales/{sale_id}/checkout")
async def checkout_counter_sale(
    sale_id: UUID, body: CheckoutInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user),
):
    tenant, tenders = await require_counter_sales_enabled(db, user)
    if body.tender not in tenders:
        raise HTTPException(status_code=424, detail="Payment provider is not configured")
    if body.tender == "quickbooks_payments" and not body.payment_token:
        raise HTTPException(status_code=422, detail="QuickBooks payment token is required")
    if body.tender != "quickbooks_payments" and body.payment_token is not None:
        raise HTTPException(status_code=422, detail="payment_token is accepted only for QuickBooks Payments")
    payload = body.model_dump(mode="json", exclude={"payment_token"})
    payload["payment_token_digest"] = (
        hashlib.sha256(body.payment_token.encode()).hexdigest()
        if body.payment_token is not None else None
    )
    replay, record, replayed = await _mutation(
        db, tenant_id=tenant.id, user=user, family="counter_sale_checkout",
        route=f"POST:/counter-sales/{sale_id}/checkout",
        key=idempotency_key, payload=payload, allow_incomplete_resume=True,
    )
    if replayed:
        return Response(
            content=json.dumps(replay, default=str), media_type="application/json",
            status_code=record.status_code or 200,
        )
    attempt = (await db.execute(select(CounterSalePaymentAttempt).where(
        CounterSalePaymentAttempt.tenant_id == tenant.id,
        CounterSalePaymentAttempt.sale_id == sale_id,
        CounterSalePaymentAttempt.idempotency_key == record.idempotency_key,
    ).order_by(CounterSalePaymentAttempt.created_at.desc()).limit(1))).scalar_one_or_none()
    if attempt is None:
        sale, _lines, attempt = await prepare_checkout(
            db, tenant=tenant, sale_id=sale_id, actor=user,
            expected_version=body.expected_version, tender=body.tender,
            idempotency_key=record.idempotency_key,
            manual_reference=body.manual_reference,
            receipt_email=str(body.receipt_email) if body.receipt_email else None,
        )
        await db.commit()
    else:
        sale = await tenant_sale(db, tenant.id, sale_id)
        if attempt.tender != body.tender:
            raise HTTPException(status_code=409, detail="Idempotency key conflict")
        if attempt.state in {"succeeded", "failed", "compensated"}:
            response = await serialize_sale(db, sale, user)
            payment = {
                "attempt_id": str(attempt.id), "tender": body.tender,
                "state": attempt.state, "client_secret": None,
                "stripe_account_id": tenant.stripe_account_id if body.tender == "stripe" else None,
                "reconcile_url": f"/api/v1/parts-operations/counter-sales/{sale.id}/payment-attempts/{attempt.id}/reconcile",
            }
            status_code = 402 if attempt.state == "failed" else 200
            terminal = {"sale": response, "payment": payment}
            complete_idempotency(record, status_code=status_code, body=terminal)
            await db.commit()
            return Response(
                content=json.dumps(terminal, default=str),
                media_type="application/json", status_code=status_code,
            )
    client_secret: str | None = None
    provider_object_id: str | None = None
    if body.tender in MANUAL_TENDERS:
        sale = await finalize_checkout_success(db, tenant_id=tenant.id, sale_id=sale.id, attempt_id=attempt.id, provider_amount=attempt.amount, currency="USD", provider_status="completed", provider_object_id=attempt.provider_reference, actor=user)
        await db.commit()
    elif body.tender == "stripe":
        try:
            if attempt.provider_intent_id:
                intent = stripe.PaymentIntent.retrieve(
                    attempt.provider_intent_id,
                    stripe_account=tenant.stripe_account_id,
                )
            else:
                intent = stripe.PaymentIntent.create(
                    amount=int(Decimal(attempt.amount) * 100), currency="usd",
                    metadata={"counter_sale_id": str(sale.id), "tenant_id": str(tenant.id), "attempt_id": str(attempt.id)},
                    automatic_payment_methods={"enabled": True},
                    idempotency_key=attempt.provider_request_id,
                    stripe_account=tenant.stripe_account_id,
                )
            attempt = await db.get(CounterSalePaymentAttempt, attempt.id)
            attempt.provider_intent_id = intent.id
            attempt.provider_status = intent.status
            client_secret = intent.client_secret
            if intent.status == "succeeded":
                sale = await finalize_checkout_success(
                    db, tenant_id=tenant.id, sale_id=sale.id,
                    attempt_id=attempt.id,
                    provider_amount=Decimal(intent.amount_received) / Decimal(100),
                    currency=str(intent.currency).upper(),
                    provider_status=intent.status,
                    provider_object_id=intent.id, actor=user,
                )
            # A new Elements PaymentIntent normally starts in
            # requires_payment_method. That is the client-confirmation state,
            # not a definitive payment failure: keep the stock hold and return
            # its client_secret. Definitive failures arrive through the signed
            # payment_intent.payment_failed webhook; cancellation is terminal.
            elif intent.status == "canceled":
                sale = await finalize_checkout_failure(
                    db, tenant_id=tenant.id, sale_id=sale.id,
                    attempt_id=attempt.id, failure_code=intent.status, actor=user,
                )
            await db.commit()
        except stripe.error.StripeError as exc:
            # Creation failure before a provider object exists is definitive;
            # network/indeterminate failures preserve the hold for reconciliation.
            if getattr(exc, "code", None) in {"card_declined", "payment_intent_authentication_failure"}:
                await finalize_checkout_failure(db, tenant_id=tenant.id, sale_id=sale.id, attempt_id=attempt.id, failure_code=str(exc.code), actor=user)
                await db.commit()
                raise HTTPException(status_code=402, detail="Payment was declined")
            raise HTTPException(status_code=503, detail="Payment state is indeterminate; reconcile before retrying")
    else:
        connection = await _connection(db, tenant.id)
        charge = None
        last_error: QuickBooksPaymentError | None = None
        # One bounded in-request recovery reuses the exact Intuit Request-Id
        # while the opaque browser token is still only in memory. It does not
        # persist or log that token, and provider idempotency prevents a second
        # financial charge after an ambiguous first response.
        for _ in range(2):
            try:
                charge = await create_charge(
                    connection=connection, token=body.payment_token or "",
                    amount=Decimal(attempt.amount),
                    description=f"Counter sale {sale.sale_number}",
                    request_id=attempt.provider_request_id or str(attempt.id),
                )
                break
            except QuickBooksPaymentError as exc:
                last_error = exc
        if charge is None:
            raise HTTPException(status_code=503, detail="Payment state is indeterminate; reconcile before retrying") from last_error
        attempt = await db.get(CounterSalePaymentAttempt, attempt.id)
        attempt.provider_charge_id = charge.id
        attempt.provider_status = charge.status
        if is_successful_charge(charge):
            sale = await finalize_checkout_success(db, tenant_id=tenant.id, sale_id=sale.id, attempt_id=attempt.id, provider_amount=charge.amount, currency="USD", provider_status=charge.status, provider_object_id=charge.id, actor=user)
            await db.commit()
        else:
            await finalize_checkout_failure(db, tenant_id=tenant.id, sale_id=sale.id, attempt_id=attempt.id, failure_code=charge.status, actor=user)
            await db.commit()
            raise HTTPException(status_code=402, detail="Payment was declined")
    response = await serialize_sale(db, await tenant_sale(db, tenant.id, sale.id), user)
    payment = {"attempt_id": str(attempt.id), "tender": body.tender, "state": "pending" if response["status"] == "awaiting_payment" else "succeeded", "client_secret": client_secret if body.tender == "stripe" else None, "stripe_account_id": tenant.stripe_account_id if body.tender == "stripe" else None, "reconcile_url": f"/api/v1/parts-operations/counter-sales/{sale.id}/payment-attempts/{attempt.id}/reconcile"}
    status_code = 202 if response["status"] == "awaiting_payment" else 200
    response_body = {"sale": response, "payment": payment}
    stored_response = json.loads(json.dumps(response_body, default=str))
    stored_response["payment"]["client_secret"] = None
    complete_idempotency(record, status_code=status_code, body=stored_response)
    await db.commit()
    return Response(
        content=json.dumps(response_body, default=str),
        media_type="application/json", status_code=status_code,
    )


@router.post("/counter-sales/{sale_id}/payment-attempts/{attempt_id}/reconcile")
async def reconcile_counter_sale_payment(
    sale_id: UUID, attempt_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    replay, record, replayed = await _mutation(
        db, tenant_id=tenant.id, user=user, family="counter_sale_payment_reconcile",
        route=f"POST:/counter-sales/{sale_id}/payment-attempts/{attempt_id}/reconcile",
        key=idempotency_key, payload={},
    )
    if replayed:
        return Response(
            content=json.dumps(replay, default=str), media_type="application/json",
            status_code=record.status_code or 200,
        )
    sale = await tenant_sale(db, tenant.id, sale_id)
    attempt = (await db.execute(select(CounterSalePaymentAttempt).where(
        CounterSalePaymentAttempt.id == attempt_id, CounterSalePaymentAttempt.tenant_id == tenant.id,
        CounterSalePaymentAttempt.sale_id == sale.id,
    ))).scalar_one_or_none()
    if attempt is None:
        raise _not_found()
    if attempt.state in {"succeeded", "failed", "compensated"}:
        response = await serialize_sale(db, sale, user)
        complete_idempotency(record, status_code=200, body=response)
        await db.commit()
        return response
    if attempt.tender == "stripe":
        try:
            intent = stripe.PaymentIntent.retrieve(attempt.provider_intent_id, stripe_account=tenant.stripe_account_id)
        except stripe.error.StripeError as exc:
            raise HTTPException(status_code=503, detail="Payment state is indeterminate; reconcile later") from exc
        if intent.status == "succeeded":
            sale = await finalize_checkout_success(db, tenant_id=tenant.id, sale_id=sale.id, attempt_id=attempt.id, provider_amount=Decimal(intent.amount_received) / Decimal(100), currency=str(intent.currency).upper(), provider_status=intent.status, provider_object_id=intent.id, actor=user)
        elif intent.status == "canceled":
            sale = await finalize_checkout_failure(db, tenant_id=tenant.id, sale_id=sale.id, attempt_id=attempt.id, failure_code=intent.status, actor=user)
        else:
            response = await serialize_sale(db, sale, user)
            complete_idempotency(record, status_code=202, body=response)
            await db.commit()
            return Response(content=json.dumps(response, default=str), media_type="application/json", status_code=202)
    elif attempt.tender == "quickbooks_payments":
        try:
            charge = await get_charge(connection=await _connection(db, tenant.id), charge_id=attempt.provider_charge_id or "")
        except QuickBooksPaymentError as exc:
            raise HTTPException(status_code=503, detail="Payment state is indeterminate; reconcile later") from exc
        if is_successful_charge(charge):
            sale = await finalize_checkout_success(db, tenant_id=tenant.id, sale_id=sale.id, attempt_id=attempt.id, provider_amount=charge.amount, currency="USD", provider_status=charge.status, provider_object_id=charge.id, actor=user)
        elif charge.status in {"DECLINED", "FAILED", "CANCELLED"}:
            sale = await finalize_checkout_failure(db, tenant_id=tenant.id, sale_id=sale.id, attempt_id=attempt.id, failure_code=charge.status, actor=user)
        else:
            response = await serialize_sale(db, sale, user)
            complete_idempotency(record, status_code=202, body=response)
            await db.commit()
            return Response(content=json.dumps(response, default=str), media_type="application/json", status_code=202)
    await db.commit()
    response = await serialize_sale(db, sale, user)
    complete_idempotency(record, status_code=200, body=response)
    await db.commit()
    return response


@router.post("/counter-sales/{sale_id}/cancel")
async def cancel_counter_sale(
    sale_id: UUID, body: CancelInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    require_counter_sale_role(user, manager=True)
    replay, record, replayed = await _mutation(
        db, tenant_id=tenant.id, user=user, family="counter_sale_cancel",
        route=f"POST:/counter-sales/{sale_id}/cancel", key=idempotency_key,
        payload=body.model_dump(mode="json"),
    )
    if replayed:
        return replay
    sale = await tenant_sale(db, tenant.id, sale_id, lock=True)
    if sale.status != "draft" or sale.version != body.expected_version:
        raise HTTPException(status_code=409, detail="Counter sale version or state conflict")
    sale.status = "cancelled"
    sale.version += 1
    sale.cancelled_at = now_utc()
    sale.cancelled_by_user_id = user.id
    for line in await sale_lines(db, tenant.id, sale.id):
        from app.services.part_activity_service import append_part_activity
        await append_part_activity(db, tenant_id=tenant.id, inventory_id=line.inventory_id, category="sales", event_type="counter_sale.cancelled", idempotency_key=f"counter_sale:{sale.id}:line:{line.id}:cancelled:v1", actor=user, correlation_id=sale.id, source_type="counter_sale", source_id=sale.id, source_number=sale.sale_number, before={"status": "draft"}, after={"status": "cancelled"}, reason_code="manager_cancel", note=body.reason)
    response = await serialize_sale(db, sale, user)
    complete_idempotency(record, status_code=200, body=response)
    await db.commit()
    return response


async def _serialize_return(db: AsyncSession, row: CounterSaleReturn) -> dict[str, Any]:
    lines = list((await db.execute(select(CounterSaleReturnLine).where(CounterSaleReturnLine.return_id == row.id))).scalars().all())
    refund = (await db.execute(select(CounterSaleRefund).where(CounterSaleRefund.return_id == row.id))).scalar_one_or_none()
    return {"id": str(row.id), "sale_id": str(row.sale_id), "version": row.version, "state": row.state, "item_amount": str(row.item_amount), "tax_amount": str(row.tax_amount), "fee_amount": str(row.fee_amount), "refund_amount": str(row.refund_amount), "reason": row.reason, "lines": [{"id": str(line.id), "sale_line_id": str(line.sale_line_id), "quantity": line.quantity, "reason": line.reason, "disposition": line.disposition, "item_amount": str(line.item_amount), "tax_amount": str(line.tax_amount), "fee_amount": str(line.fee_amount)} for line in lines], "refund": None if refund is None else {"id": str(refund.id), "tender": refund.tender, "state": refund.state, "amount": str(refund.amount), "failure_code": refund.safe_failure_code}, "created_at": row.created_at.isoformat(), "completed_at": row.completed_at.isoformat() if row.completed_at else None}


@router.get("/counter-sales/{sale_id}/returns")
async def list_counter_sale_returns(sale_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    tenant, _ = await require_counter_sales_enabled(db, user)
    await tenant_sale(db, tenant.id, sale_id)
    rows = list((await db.execute(select(CounterSaleReturn).where(CounterSaleReturn.tenant_id == tenant.id, CounterSaleReturn.sale_id == sale_id).order_by(CounterSaleReturn.created_at.desc()))).scalars().all())
    return [await _serialize_return(db, row) for row in rows]


async def _execute_refund(
    db: AsyncSession, tenant: Tenant, return_row: CounterSaleReturn,
    refund: CounterSaleRefund, user: User,
) -> tuple[Literal["succeeded", "pending", "failed"], str | None]:
    attempt = await db.get(CounterSalePaymentAttempt, refund.payment_attempt_id)
    if attempt is None:
        raise HTTPException(status_code=409, detail="Original payment attempt is unavailable")
    if refund.tender in MANUAL_TENDERS:
        await finalize_refund_success(db, tenant_id=tenant.id, return_id=return_row.id, provider_refund_id=refund.provider_reference, actor=user)
        return "succeeded", refund.provider_reference
    try:
        if refund.tender == "stripe":
            result = stripe.Refund.create(payment_intent=attempt.provider_intent_id, amount=int(Decimal(refund.amount) * 100), idempotency_key=f"db045-refund-{refund.id}-attempt-{refund.attempt_count}", stripe_account=tenant.stripe_account_id)
            provider_id = result.id
            provider_status = str(result.status).lower()
            succeeded = provider_status == "succeeded"
            pending = provider_status in {"pending", "requires_action"}
        else:
            result = await refund_charge(connection=await _connection(db, tenant.id), charge_id=attempt.provider_charge_id or "", amount=Decimal(refund.amount), description=f"Counter sale return {return_row.id}", request_id=f"db045-refund-{refund.id}-attempt-{refund.attempt_count}")
            provider_id = result.id
            provider_status = str(result.status).upper()
            succeeded = provider_status in {"SUCCEEDED", "COMPLETED", "CAPTURED"}
            pending = provider_status in {"PENDING", "PROCESSING", "AUTHORIZED"}
    except (stripe.error.StripeError, QuickBooksPaymentError) as exc:
        # A provider exception can be an ambiguous timeout after provider
        # acceptance. Keep the durable claim pending and reconcile by the same
        # provider idempotency/request ID; never retry blindly or restock.
        refund.state = "pending"
        refund.safe_failure_code = "provider_indeterminate"
        return_row.state = "pending_refund"
        return "pending", None
    if succeeded:
        await finalize_refund_success(db, tenant_id=tenant.id, return_id=return_row.id, provider_refund_id=provider_id, actor=user)
        return "succeeded", provider_id
    refund.provider_refund_id = provider_id
    if pending:
        refund.state = "pending"
        refund.safe_failure_code = None
        return_row.state = "pending_refund"
        return "pending", provider_id
    await finalize_refund_failure(
        db, tenant_id=tenant.id, return_id=return_row.id,
        failure_code="provider_failed", actor=user,
    )
    return "failed", provider_id


@router.post("/counter-sales/{sale_id}/returns", status_code=201)
async def create_counter_sale_return(
    sale_id: UUID, body: ReturnInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user),
):
    tenant, _ = await require_counter_sales_enabled(db, user)
    replay, record, replayed = await _mutation(
        db, tenant_id=tenant.id, user=user, family="counter_sale_return",
        route=f"POST:/counter-sales/{sale_id}/returns", key=idempotency_key,
        payload=body.model_dump(mode="json"),
    )
    if replayed:
        return Response(
            content=json.dumps(replay, default=str), media_type="application/json",
            status_code=record.status_code or 200,
        )
    sale, return_row, refund, _lines = await create_return_claim(
        db, tenant=tenant, sale_id=sale_id, actor=user,
        expected_version=body.expected_version,
        line_inputs=[line.model_dump() for line in body.lines],
        idempotency_key=record.idempotency_key,
        manual_reference=body.manual_refund_reference,
    )
    await db.commit()
    refund_result, _provider_id = await _execute_refund(db, tenant, return_row, refund, user)
    await db.commit()
    value = await _serialize_return(db, return_row)
    status_code = 200 if refund_result == "succeeded" else 202
    complete_idempotency(record, status_code=status_code, body=value)
    await db.commit()
    return Response(
        content=json.dumps(value, default=str), media_type="application/json",
        status_code=status_code,
    )


@router.get("/counter-sales/{sale_id}/returns/{return_id}")
async def get_counter_sale_return(sale_id: UUID, return_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    tenant, _ = await require_counter_sales_enabled(db, user)
    row = (await db.execute(select(CounterSaleReturn).where(CounterSaleReturn.id == return_id, CounterSaleReturn.sale_id == sale_id, CounterSaleReturn.tenant_id == tenant.id))).scalar_one_or_none()
    if row is None:
        raise _not_found()
    return await _serialize_return(db, row)


@router.post("/counter-sales/{sale_id}/returns/{return_id}/retry-refund")
async def retry_counter_sale_refund(
    sale_id: UUID, return_id: UUID,
    body: RetryRefundInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user),
):
    tenant, _ = await require_counter_sales_enabled(db, user)
    require_counter_sale_role(user, manager=True)
    replay, record, replayed = await _mutation(
        db, tenant_id=tenant.id, user=user, family="counter_sale_refund_retry",
        route=f"POST:/counter-sales/{sale_id}/returns/{return_id}/retry-refund",
        key=idempotency_key, payload=body.model_dump(mode="json"),
    )
    if replayed:
        return Response(
            content=json.dumps(replay, default=str), media_type="application/json",
            status_code=record.status_code or 200,
        )
    row = (await db.execute(select(CounterSaleReturn).where(CounterSaleReturn.id == return_id, CounterSaleReturn.sale_id == sale_id, CounterSaleReturn.tenant_id == tenant.id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise _not_found()
    if row.state != "refund_failed" or row.version != body.expected_version:
        raise HTTPException(status_code=409, detail="Refund is not retryable")
    refund = (await db.execute(select(CounterSaleRefund).where(CounterSaleRefund.return_id == row.id, CounterSaleRefund.tenant_id == tenant.id).with_for_update())).scalar_one()
    refund.state = "pending"
    refund.attempt_count += 1
    row.state = "pending_refund"
    row.version += 1
    await db.commit()
    refund_result, _provider_id = await _execute_refund(db, tenant, row, refund, user)
    await db.commit()
    response = await _serialize_return(db, row)
    status_code = 200 if refund_result == "succeeded" else 202
    complete_idempotency(record, status_code=status_code, body=response)
    await db.commit()
    return Response(
        content=json.dumps(response, default=str),
        media_type="application/json",
        status_code=status_code,
    )


@router.get("/counter-sales/{sale_id}/receipt.pdf")
async def counter_sale_receipt_pdf(sale_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    tenant, _ = await require_counter_sales_enabled(db, user)
    sale = await tenant_sale(db, tenant.id, sale_id)
    if sale.status not in {"completed", "partially_returned", "returned"} or not sale.receipt_snapshot:
        raise HTTPException(status_code=409, detail="Receipt is not available")
    returns = list((await db.execute(select(CounterSaleReturn).where(CounterSaleReturn.sale_id == sale.id, CounterSaleReturn.state == "completed"))).scalars().all())
    pdf = generate_counter_sale_receipt_pdf(tenant=tenant, snapshot=sale.receipt_snapshot, returns=returns)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{sale.sale_number}.pdf"'})


@router.post("/counter-sales/{sale_id}/receipt/email", status_code=202)
async def email_counter_sale_receipt(
    sale_id: UUID, body: ReceiptEmailInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user),
):
    tenant, _ = await require_counter_sales_enabled(db, user)
    replay, record, replayed = await _mutation(
        db, tenant_id=tenant.id, user=user, family="counter_sale_receipt_email",
        route=f"POST:/counter-sales/{sale_id}/receipt/email",
        key=idempotency_key, payload=body.model_dump(mode="json"),
    )
    if replayed:
        return replay
    sale = await tenant_sale(db, tenant.id, sale_id)
    if not sale.receipt_snapshot:
        raise HTTPException(status_code=409, detail="Receipt is not available")
    sale.receipt_email_to = str(body.email)
    existing = await db.scalar(select(ProviderOutboxEvent.id).where(ProviderOutboxEvent.tenant_id == tenant.id, ProviderOutboxEvent.event_type == "counter_sale.receipt.email.v1", ProviderOutboxEvent.idempotency_key == record.idempotency_key))
    if not existing:
        db.add(ProviderOutboxEvent(tenant_id=tenant.id, event_type="counter_sale.receipt.email.v1", aggregate_type="counter_sale", aggregate_id=sale.id, payload={"sale_id": str(sale.id), "payload_version": 1}, idempotency_key=record.idempotency_key, status=ProviderOutboxStatus.PENDING.value, available_at=now_utc()))
    response = {"queued": True, "sale_id": str(sale.id)}
    complete_idempotency(record, status_code=202, body=response)
    await db.commit()
    return response


@webhook_router.post("/counter-sales")
async def stripe_counter_sale_webhook(request: Request, stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"), db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    secret = settings.STRIPE_CONNECT_WEBHOOK_SECRET or settings.STRIPE_WEBHOOK_SECRET
    if not secret or not stripe_signature:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc
    event_id = str(event.id)
    existing = await db.scalar(select(CounterSaleProviderEvent.id).where(CounterSaleProviderEvent.provider == "stripe", CounterSaleProviderEvent.external_event_id == event_id))
    if existing:
        return {"received": True}
    obj = event.data.object
    metadata = dict(getattr(obj, "metadata", {}) or {})
    try:
        sale_id, tenant_id, attempt_id = UUID(metadata["counter_sale_id"]), UUID(metadata["tenant_id"]), UUID(metadata["attempt_id"])
    except Exception:
        return {"received": True}
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id, Tenant.stripe_account_id == getattr(event, "account", None), Tenant.deleted_at.is_(None)))).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=400, detail="Invalid connected account")
    delivery = CounterSaleProviderEvent(tenant_id=tenant_id, provider="stripe", external_event_id=event_id, event_type=str(event.type), safe_payload_hash=hashlib.sha256(payload).hexdigest(), processing_state="received")
    db.add(delivery)
    if event.type in {"payment_intent.succeeded"}:
        await finalize_checkout_success(db, tenant_id=tenant_id, sale_id=sale_id, attempt_id=attempt_id, provider_amount=Decimal(obj.amount_received) / Decimal(100), currency=str(obj.currency).upper(), provider_status=str(obj.status), provider_object_id=str(obj.id), actor=None)
    elif event.type in {"payment_intent.payment_failed", "payment_intent.canceled"}:
        await finalize_checkout_failure(db, tenant_id=tenant_id, sale_id=sale_id, attempt_id=attempt_id, failure_code=str(event.type).rsplit(".", 1)[-1], actor=None)
    delivery.processing_state = "processed"
    delivery.processed_at = now_utc()
    await db.commit()
    return {"received": True}
