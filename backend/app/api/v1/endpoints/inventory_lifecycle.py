"""DB-045 immutable Activity, lifecycle, and bounded manual counter-sale APIs."""
from __future__ import annotations

import base64
import csv
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.inventory_lifecycle import (
    CounterSale,
    CounterSaleLine,
    CounterSalePaymentAttempt,
    CounterSaleReturn,
    CounterSaleReturnLine,
    PartActivityEvent,
)
from app.db.models.parts_operations import CoreObligation, PurchaseReceiptLine, VendorReturn, VendorReturnLine
from app.db.models.user import User
from app.services.counter_sale_receipt import generate_counter_sale_receipt_pdf
from app.services.counter_sale_service import (
    cancel_draft,
    complete_manual_checkout,
    complete_manual_return,
    create_or_replace_draft,
    money,
    now_utc,
    require_counter_sales_enabled,
    serialize_return,
    serialize_sale,
    tenant_sale,
)
from app.services.part_activity_service import (
    cursor_condition,
    decode_cursor,
    encode_cursor,
    escape_csv_text,
    normalized_filter_fingerprint,
    serialize_activity,
)
from app.services.parts_operations_service import (
    begin_idempotency,
    canonical_fingerprint,
    complete_idempotency,
    find_idempotent_response,
    require_parts_operations_enabled,
    require_parts_role,
    validate_idempotency_key,
)


router = APIRouter()
ACTIVITY_CATEGORIES = frozenset({"catalog", "stock", "repairs", "purchasing", "returns", "sales"})
SALE_STATUSES = frozenset({"draft", "completed", "partially_returned", "returned", "cancelled"})
MANUAL_TENDER = Literal["cash", "check", "ach", "zelle", "external_terminal", "fleet_reference", "other"]


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
    tender: MANUAL_TENDER
    manual_reference: str | None = Field(default=None, max_length=255)


class CancelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
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


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not found")


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(status_code=422, detail="Dates must include a timezone")
    return value.astimezone(timezone.utc)


def _sale_cursor(created_at: datetime, sale_id: UUID, *, fingerprint: str) -> str:
    created_at_utc = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at.astimezone(timezone.utc)
    payload = json.dumps({
        "v": 1,
        "created_at": created_at_utc.isoformat(),
        "id": str(sale_id),
        "fp": fingerprint,
    }, separators=(",", ":")).encode()
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
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user: User,
    family: str,
    route: str,
    key: str | None,
    payload: dict[str, Any],
):
    valid = validate_idempotency_key(key)
    fingerprint = canonical_fingerprint(route=route, principal_id=user.id, payload=payload)
    existing = await find_idempotent_response(
        db,
        tenant_id=tenant_id,
        family=family,
        key=valid,
        fingerprint=fingerprint,
    )
    if existing and existing.completed_at is not None:
        return json.loads(existing.response_body or "{}"), existing, True
    if existing:
        raise HTTPException(status_code=409, detail="Request is already in progress")
    record = begin_idempotency(tenant_id=tenant_id, family=family, key=valid, fingerprint=fingerprint)
    db.add(record)
    return None, record, False


async def _activity_tenant(db: AsyncSession, user: User) -> UUID:
    tenant_id = await require_parts_operations_enabled(db, user)
    require_parts_role(user, mutate=False)
    return tenant_id


def _activity_filters(
    inventory_id: UUID | None,
    category: str | None,
    event_types: list[str],
    actor_id: UUID | None,
    source_type: str | None,
    source_id: UUID | None,
    search: str | None,
    from_at: datetime | None,
    to: datetime | None,
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
        "category": category,
        "event_type": sorted(set(event_types)),
        "actor_id": str(actor_id) if actor_id else None,
        "source_type": source_type,
        "source_id": str(source_id) if source_id else None,
        "search": search.casefold() if search else None,
        "from": from_at.isoformat() if from_at else None,
        "to": to.isoformat() if to else None,
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
    inventory_id: UUID | None = None,
    category: str | None = None,
    event_type: list[str] = Query(default=[]),
    actor_id: UUID | None = None,
    source_type: str | None = None,
    source_id: UUID | None = None,
    search: str | None = None,
    from_at: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant_id = await _activity_tenant(db, user)
    if inventory_id and not await db.scalar(select(Inventory.id).where(
        Inventory.id == inventory_id,
        Inventory.tenant_id == tenant_id,
        Inventory.deleted_at.is_(None),
    )):
        raise _not_found()
    filters = _activity_filters(inventory_id, category, event_type, actor_id, source_type, source_id, search, from_at, to)
    fingerprint = normalized_filter_fingerprint(filters)
    stmt = _activity_statement(tenant_id, filters)
    if cursor:
        occurred_at, event_id = decode_cursor(cursor, fingerprint=fingerprint)
        stmt = stmt.where(cursor_condition(occurred_at, event_id))
    rows = list((await db.execute(stmt.order_by(
        PartActivityEvent.occurred_at.desc(),
        PartActivityEvent.id.desc(),
    ).limit(limit + 1))).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [serialize_activity(row) for row in rows],
        "next_cursor": encode_cursor(
            occurred_at=rows[-1].occurred_at,
            event_id=rows[-1].id,
            fingerprint=fingerprint,
        ) if has_more and rows else None,
    }


@router.get("/activity-events/export.csv")
async def export_activity_events(
    inventory_id: UUID | None = None,
    category: str | None = None,
    event_type: list[str] = Query(default=[]),
    actor_id: UUID | None = None,
    source_type: str | None = None,
    source_id: UUID | None = None,
    search: str | None = None,
    from_at: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant_id = await _activity_tenant(db, user)
    filters = _activity_filters(inventory_id, category, event_type, actor_id, source_type, source_id, search, from_at, to)
    rows = list((await db.execute(_activity_statement(tenant_id, filters).order_by(
        PartActivityEvent.occurred_at.desc(),
        PartActivityEvent.id.desc(),
    ).limit(50001))).scalars().all())
    if len(rows) > 50000:
        raise HTTPException(status_code=413, detail="Activity export exceeds 50,000 rows; narrow the filters")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["occurred_at", "part_sku", "part_name", "category", "event_type", "actor", "reason", "note", "before", "after", "physical_on_hand", "held_for_checkout", "available_to_sell", "delta", "wac", "list_price", "charged_price", "tax", "fee", "tender", "payment_status", "source_type", "source_number", "source_link", "origin", "correlation_id"])
    for row in rows:
        value = serialize_activity(row)
        stock = row.stock_snapshot or {}
        monetary = row.money_snapshot or {}
        payment = row.payment_snapshot or {}
        source = value["source"]
        writer.writerow([escape_csv_text(item) for item in (
            row.occurred_at.isoformat(), row.part_sku_snapshot, row.part_name_snapshot,
            row.category, row.event_type, row.actor_name_snapshot, row.reason_code,
            row.note, json.dumps(row.before_values or {}, sort_keys=True),
            json.dumps(row.after_values or {}, sort_keys=True), stock.get("physical_on_hand"),
            stock.get("held_for_checkout"), stock.get("available_to_sell"), stock.get("delta"),
            monetary.get("wac_after"), monetary.get("list_price"), monetary.get("charged_price"),
            monetary.get("tax"), monetary.get("service_fee"), payment.get("tender"),
            payment.get("state"), row.source_type, row.source_number_snapshot,
            source["href"], row.origin, row.correlation_id,
        )])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=part-activity.csv"})


@router.get("/parts/{inventory_id}/lifecycle-summary")
async def part_lifecycle_summary(
    inventory_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant_id = await _activity_tenant(db, user)
    item = (await db.execute(select(Inventory).where(
        Inventory.id == inventory_id,
        Inventory.tenant_id == tenant_id,
        Inventory.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if item is None:
        raise _not_found()
    usage_rows = (await db.execute(select(PartsUsage.quantity, PartsUsage.repair_order_id, PartsUsage.created_at).where(
        PartsUsage.tenant_id == tenant_id,
        PartsUsage.inventory_id == inventory_id,
        PartsUsage.deleted_at.is_(None),
    ))).all()
    receipt_rows = (await db.execute(select(PurchaseReceiptLine.quantity, PurchaseReceiptLine.purchase_receipt_id).where(
        PurchaseReceiptLine.tenant_id == tenant_id,
        PurchaseReceiptLine.inventory_id == inventory_id,
    ))).all()
    vendor_rows = (await db.execute(select(VendorReturnLine.quantity).join(
        VendorReturn,
        VendorReturn.id == VendorReturnLine.vendor_return_id,
    ).where(
        VendorReturnLine.tenant_id == tenant_id,
        VendorReturnLine.inventory_id == inventory_id,
        VendorReturnLine.deleted_at.is_(None),
        VendorReturn.status.in_(("shipped", "credited")),
    ))).all()
    core_count = int(await db.scalar(select(func.count(CoreObligation.id)).where(
        CoreObligation.tenant_id == tenant_id,
        CoreObligation.inventory_id == inventory_id,
        CoreObligation.deleted_at.is_(None),
        CoreObligation.status.in_(("expected", "on_hand")),
    )) or 0)
    sale_rows = (await db.execute(select(CounterSaleLine, CounterSale).join(
        CounterSale,
        CounterSale.id == CounterSaleLine.sale_id,
    ).where(
        CounterSaleLine.tenant_id == tenant_id,
        CounterSaleLine.inventory_id == inventory_id,
        CounterSaleLine.deleted_at.is_(None),
        CounterSale.status.in_(("completed", "partially_returned", "returned")),
    ))).all()
    returned_rows = (await db.execute(select(CounterSaleReturnLine, CounterSaleReturn).join(
        CounterSaleReturn,
        CounterSaleReturn.id == CounterSaleReturnLine.return_id,
    ).join(CounterSaleLine, CounterSaleLine.id == CounterSaleReturnLine.sale_line_id).where(
        CounterSaleReturnLine.tenant_id == tenant_id,
        CounterSaleLine.inventory_id == inventory_id,
        CounterSaleReturn.state == "completed",
    ))).all()
    sold_qty = sum(line.quantity for line, _sale in sale_rows)
    returned_qty = sum(line.quantity for line, _return in returned_rows)
    gross = sum((Decimal(line.item_subtotal) for line, _sale in sale_rows), Decimal("0"))
    discounts = sum((Decimal(line.discount_total) for line, _sale in sale_rows), Decimal("0"))
    refunds = sum((Decimal(line.item_amount) for line, _return in returned_rows), Decimal("0"))
    event_count = int(await db.scalar(select(func.count(PartActivityEvent.id)).where(
        PartActivityEvent.tenant_id == tenant_id,
        PartActivityEvent.inventory_id == inventory_id,
    )) or 0)
    last_event = await db.scalar(select(func.max(PartActivityEvent.occurred_at)).where(
        PartActivityEvent.tenant_id == tenant_id,
        PartActivityEvent.inventory_id == inventory_id,
    ))
    return {
        "inventory_id": str(item.id),
        "as_of": now_utc().isoformat(),
        "repairs": {
            "units_used": str(sum((Decimal(row.quantity) for row in usage_rows), Decimal("0"))),
            "repair_order_count": len({row.repair_order_id for row in usage_rows}),
            "last_used_at": max((row.created_at for row in usage_rows), default=None),
        },
        "purchasing": {
            "units_received": sum(int(row.quantity) for row in receipt_rows),
            "receipt_count": len({row.purchase_receipt_id for row in receipt_rows}),
            "units_returned_to_vendor": sum(int(row.quantity) for row in vendor_rows),
            "open_core_obligations": core_count,
        },
        "sales": {
            "units_sold": sold_qty,
            "units_returned": returned_qty,
            "net_units": sold_qty - returned_qty,
            "gross_item_revenue": str(money(gross)),
            "discounts": str(money(discounts)),
            "refunds": str(money(refunds)),
            "net_item_revenue": str(money(gross - refunds)),
            "last_sold_at": max((sale.completed_at for _line, sale in sale_rows if sale.completed_at), default=None),
        },
        "activity": {"event_count": event_count, "last_event_at": last_event},
    }


@router.get("/counter-sales")
async def list_counter_sales(
    sale_status: str | None = Query(default=None, alias="status"),
    customer_id: UUID | None = None,
    text: str | None = None,
    from_at: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    if sale_status and sale_status not in SALE_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid sale status")
    normalized_text = " ".join((text or "").split()) or None
    normalized_from, normalized_to = _utc(from_at), _utc(to)
    filters = {
        "status": sale_status,
        "customer_id": str(customer_id) if customer_id else None,
        "text": normalized_text,
        "from": normalized_from.isoformat() if normalized_from else None,
        "to": normalized_to.isoformat() if normalized_to else None,
    }
    fingerprint = normalized_filter_fingerprint(filters)
    stmt = select(CounterSale).where(
        CounterSale.tenant_id == tenant.id,
        CounterSale.deleted_at.is_(None),
    )
    if sale_status:
        stmt = stmt.where(CounterSale.status == sale_status)
    if customer_id:
        stmt = stmt.where(CounterSale.customer_id == customer_id)
    if normalized_text:
        pattern = f"%{normalized_text}%"
        stmt = stmt.where(or_(
            CounterSale.sale_number.ilike(pattern),
            CounterSale.buyer_name_snapshot.ilike(pattern),
            CounterSale.buyer_email_snapshot.ilike(pattern),
        ))
    if normalized_from:
        stmt = stmt.where(CounterSale.created_at >= normalized_from)
    if normalized_to:
        stmt = stmt.where(CounterSale.created_at < normalized_to)
    if cursor:
        created_at, sale_id = _decode_sale_cursor(cursor, fingerprint=fingerprint)
        stmt = stmt.where(or_(
            CounterSale.created_at < created_at,
            (CounterSale.created_at == created_at) & (CounterSale.id < sale_id),
        ))
    rows = list((await db.execute(stmt.order_by(
        CounterSale.created_at.desc(),
        CounterSale.id.desc(),
    ).limit(limit + 1))).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for row in rows:
        line_count = int(await db.scalar(select(func.count(CounterSaleLine.id)).where(
            CounterSaleLine.tenant_id == tenant.id,
            CounterSaleLine.sale_id == row.id,
            CounterSaleLine.deleted_at.is_(None),
        )) or 0)
        tender = await db.scalar(select(CounterSalePaymentAttempt.tender).where(
            CounterSalePaymentAttempt.tenant_id == tenant.id,
            CounterSalePaymentAttempt.sale_id == row.id,
        ).order_by(CounterSalePaymentAttempt.created_at.desc()).limit(1))
        items.append({
            "id": str(row.id),
            "sale_number": row.sale_number,
            "status": row.status,
            "buyer_name": row.buyer_name_snapshot,
            "buyer_email": row.buyer_email_snapshot,
            "total_amount": str(money(row.total)),
            "line_count": line_count,
            "tender": tender,
            "created_at": row.created_at.isoformat(),
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        })
    return {
        "items": items,
        "next_cursor": _sale_cursor(rows[-1].created_at, rows[-1].id, fingerprint=fingerprint) if has_more and rows else None,
    }


@router.post("/counter-sales", status_code=201)
async def create_counter_sale(
    body: SaleDraftInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    payload = body.model_dump(mode="json")
    replay, record, replayed = await _mutation(
        db,
        tenant_id=tenant.id,
        user=user,
        family="counter_sale_create",
        route="POST:/counter-sales",
        key=idempotency_key,
        payload=payload,
    )
    if replayed:
        return replay
    sale, _lines = await create_or_replace_draft(
        db,
        tenant=tenant,
        actor=user,
        sale=None,
        customer_id=body.customer_id,
        buyer_name=body.buyer_name,
        buyer_email=str(body.buyer_email) if body.buyer_email else None,
        buyer_phone=body.buyer_phone,
        line_inputs=[line.model_dump() for line in body.lines],
    )
    await db.flush()
    await db.refresh(sale)
    response = await serialize_sale(db, sale, user)
    complete_idempotency(record, status_code=201, body=response)
    await db.commit()
    return response


@router.get("/counter-sales/{sale_id}")
async def get_counter_sale(
    sale_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    return await serialize_sale(db, await tenant_sale(db, tenant.id, sale_id), user)


@router.patch("/counter-sales/{sale_id}")
async def update_counter_sale(
    sale_id: UUID,
    body: SalePatchInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    sale = await tenant_sale(db, tenant.id, sale_id, lock=True)
    if sale.version != body.expected_version:
        raise HTTPException(status_code=409, detail="Counter sale version conflict")
    replay, record, replayed = await _mutation(
        db,
        tenant_id=tenant.id,
        user=user,
        family="counter_sale_update",
        route=f"PATCH:/counter-sales/{sale_id}",
        key=idempotency_key,
        payload=body.model_dump(mode="json"),
    )
    if replayed:
        return replay
    sale, _lines = await create_or_replace_draft(
        db,
        tenant=tenant,
        actor=user,
        sale=sale,
        customer_id=body.customer_id,
        buyer_name=body.buyer_name,
        buyer_email=str(body.buyer_email) if body.buyer_email else None,
        buyer_phone=body.buyer_phone,
        line_inputs=[line.model_dump() for line in body.lines],
    )
    await db.flush()
    await db.refresh(sale)
    response = await serialize_sale(db, sale, user)
    complete_idempotency(record, status_code=200, body=response)
    await db.commit()
    return response


@router.post("/counter-sales/{sale_id}/checkout")
async def checkout_counter_sale(
    sale_id: UUID,
    body: CheckoutInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, tenders = await require_counter_sales_enabled(db, user)
    if body.tender not in tenders:
        raise HTTPException(status_code=422, detail="Unsupported manual tender")
    replay, record, replayed = await _mutation(
        db,
        tenant_id=tenant.id,
        user=user,
        family="counter_sale_checkout",
        route=f"POST:/counter-sales/{sale_id}/checkout",
        key=idempotency_key,
        payload=body.model_dump(mode="json"),
    )
    if replayed:
        return replay
    sale = await complete_manual_checkout(
        db,
        tenant=tenant,
        sale_id=sale_id,
        actor=user,
        expected_version=body.expected_version,
        tender=body.tender,
        idempotency_key=record.idempotency_key,
        manual_reference=body.manual_reference,
    )
    await db.flush()
    await db.refresh(sale)
    response = await serialize_sale(db, sale, user)
    complete_idempotency(record, status_code=200, body=response)
    await db.commit()
    return response


@router.post("/counter-sales/{sale_id}/cancel")
async def cancel_counter_sale(
    sale_id: UUID,
    body: CancelInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    replay, record, replayed = await _mutation(
        db,
        tenant_id=tenant.id,
        user=user,
        family="counter_sale_cancel",
        route=f"POST:/counter-sales/{sale_id}/cancel",
        key=idempotency_key,
        payload=body.model_dump(mode="json"),
    )
    if replayed:
        return replay
    sale = await cancel_draft(
        db,
        tenant=tenant,
        sale_id=sale_id,
        actor=user,
        expected_version=body.expected_version,
        reason=body.reason,
    )
    await db.flush()
    await db.refresh(sale)
    response = await serialize_sale(db, sale, user)
    complete_idempotency(record, status_code=200, body=response)
    await db.commit()
    return response


@router.get("/counter-sales/{sale_id}/returns")
async def list_counter_sale_returns(
    sale_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    await tenant_sale(db, tenant.id, sale_id)
    rows = list((await db.execute(select(CounterSaleReturn).where(
        CounterSaleReturn.tenant_id == tenant.id,
        CounterSaleReturn.sale_id == sale_id,
        CounterSaleReturn.deleted_at.is_(None),
    ).order_by(CounterSaleReturn.created_at.desc()))).scalars().all())
    return [await serialize_return(db, row) for row in rows]


@router.post("/counter-sales/{sale_id}/returns", status_code=201)
async def create_counter_sale_return(
    sale_id: UUID,
    body: ReturnInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    replay, record, replayed = await _mutation(
        db,
        tenant_id=tenant.id,
        user=user,
        family="counter_sale_return",
        route=f"POST:/counter-sales/{sale_id}/returns",
        key=idempotency_key,
        payload=body.model_dump(mode="json"),
    )
    if replayed:
        return replay
    _sale, return_row = await complete_manual_return(
        db,
        tenant=tenant,
        sale_id=sale_id,
        actor=user,
        expected_version=body.expected_version,
        line_inputs=[line.model_dump() for line in body.lines],
        manual_reference=body.manual_refund_reference,
    )
    await db.flush()
    await db.refresh(return_row)
    response = await serialize_return(db, return_row)
    complete_idempotency(record, status_code=201, body=response)
    await db.commit()
    return response


@router.get("/counter-sales/{sale_id}/returns/{return_id}")
async def get_counter_sale_return(
    sale_id: UUID,
    return_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    row = (await db.execute(select(CounterSaleReturn).where(
        CounterSaleReturn.id == return_id,
        CounterSaleReturn.sale_id == sale_id,
        CounterSaleReturn.tenant_id == tenant.id,
        CounterSaleReturn.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if row is None:
        raise _not_found()
    return await serialize_return(db, row)


@router.get("/counter-sales/{sale_id}/receipt.pdf")
async def counter_sale_receipt_pdf(
    sale_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    tenant, _tenders = await require_counter_sales_enabled(db, user)
    sale = await tenant_sale(db, tenant.id, sale_id)
    if sale.status not in {"completed", "partially_returned", "returned"} or not sale.receipt_snapshot:
        raise HTTPException(status_code=409, detail="Receipt is not available")
    returns = list((await db.execute(select(CounterSaleReturn).where(
        CounterSaleReturn.tenant_id == tenant.id,
        CounterSaleReturn.sale_id == sale.id,
        CounterSaleReturn.state == "completed",
    ))).scalars().all())
    pdf = generate_counter_sale_receipt_pdf(tenant=tenant, snapshot=sale.receipt_snapshot, returns=returns)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{sale.sale_number}.pdf"'},
    )
