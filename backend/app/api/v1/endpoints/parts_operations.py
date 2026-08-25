"""DB-038 tenant-safe purchasing, immutable activity, returns, and core custody."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from math import ceil
from typing import Literal, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.parts_operations import (
    CoreObligation, InventoryCategory, InventoryMovement, InventorySupplierSource, PurchaseOrder,
    PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine, VendorReturn,
    VendorReturnLine,
)
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.supplier import Supplier
from app.db.models.user import User
from app.db.models.vehicle import Vehicle
from app.services.parts_operations_service import (
    apply_inventory_movement, begin_idempotency, canonical_fingerprint,
    complete_idempotency, decimal_money, find_idempotent_response,
    normalize_name, receipt_wac, require_parts_operations_enabled,
    require_parts_role, validate_idempotency_key,
)

router = APIRouter()

DemandState = Literal["open", "covered", "unlinked"]
POStatusFilter = Literal["draft", "submitted", "partially_received", "received", "cancelled"]
ReturnKindFilter = Literal["stock", "core"]
ReturnStatusFilter = Literal["draft", "submitted", "shipped", "credited", "cancelled"]
CoreStatusFilter = Literal["expected", "on_hand", "returned", "waived"]
PartView = Literal["active", "archived", "all"]
PartAttention = Literal["needs_reorder", "out_of_stock", "incoming"]
PartSort = Literal["catalog", "name", "available", "location", "cost", "reorder"]
PartDirection = Literal["asc", "desc"]

DEMAND_STATES = frozenset({"open", "covered", "unlinked"})
PO_STATUSES = frozenset({"draft", "submitted", "partially_received", "received", "cancelled"})
RETURN_KINDS = frozenset({"stock", "core"})
RETURN_STATUSES = frozenset({"draft", "submitted", "shipped", "credited", "cancelled"})
CORE_STATUSES = frozenset({"expected", "on_hand", "returned", "waived"})
MOVEMENT_TYPES = frozenset({
    "migration_opening_balance", "legacy_inventory_opening", "manual_adjustment",
    "legacy_direct_receipt", "repair_reservation", "repair_release", "po_receipt",
    "core_recovery", "vendor_return", "core_return", "vendor_return_reversal",
    "core_return_reversal",
})
SOURCE_TYPES = frozenset({
    "legacy_inventory_create", "legacy_inventory_preload", "legacy_inventory_update",
    "legacy_inventory_receive", "repair_order", "purchase_receipt", "core_obligation",
    "vendor_return",
})
EDITABLE_REPAIR_STATUSES = frozenset({
    RepairOrderStatus.DRAFT, RepairOrderStatus.QUOTED, RepairOrderStatus.DECLINED,
    RepairOrderStatus.APPROVED, RepairOrderStatus.ASSIGNED, RepairOrderStatus.ACKNOWLEDGED,
    RepairOrderStatus.IN_PROGRESS, RepairOrderStatus.PENDING_REVIEW,
})
PART_VIEWS = frozenset({"active", "archived", "all"})
PART_ATTENTION = frozenset({"needs_reorder", "out_of_stock", "incoming"})
PART_SORTS = frozenset({"catalog", "name", "available", "location", "cost", "reorder"})
PART_DIRECTIONS = frozenset({"asc", "desc"})
PART_DEFAULT_DIRECTIONS = {
    "catalog": "asc",
    "name": "asc",
    "available": "asc",
    "location": "asc",
    "cost": "desc",
    "reorder": "desc",
}


class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)


class POLineInput(BaseModel):
    inventory_id: UUID
    ordered_quantity: int = Field(ge=1, le=999)
    unit_cost: Decimal = Field(gt=0, le=Decimal("999999.99"))


class POCreate(BaseModel):
    po_number: str = Field(min_length=1, max_length=100)
    supplier_id: UUID
    expected_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    lines: list[POLineInput] = Field(min_length=1, max_length=100)


class POUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    expected_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    lines: Optional[list[POLineInput]] = Field(default=None, min_length=1, max_length=100)


class SupplierSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: UUID
    supplier_part_number: Optional[str] = Field(default=None, max_length=150)
    is_preferred: bool = False
    minimum_order_quantity: int = Field(default=1, ge=1, le=999)
    pack_quantity: int = Field(default=1, ge=1, le=999)
    lead_time_days: Optional[int] = Field(default=None, ge=0, le=365)
    is_active: bool = True


class SupplierSourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_updated_at: datetime
    supplier_part_number: Optional[str] = Field(default=None, max_length=150)
    is_preferred: Optional[bool] = None
    minimum_order_quantity: Optional[int] = Field(default=None, ge=1, le=999)
    pack_quantity: Optional[int] = Field(default=None, ge=1, le=999)
    lead_time_days: Optional[int] = Field(default=None, ge=0, le=365)
    is_active: Optional[bool] = None


class SupplierSourceDelete(BaseModel):
    expected_updated_at: datetime


class BatchPOLineInput(POLineInput):
    source_id: UUID


class BatchPOGroupInput(BaseModel):
    supplier_id: UUID
    lines: list[BatchPOLineInput] = Field(min_length=1, max_length=100)


class POBatchCreate(BaseModel):
    groups: list[BatchPOGroupInput] = Field(min_length=1, max_length=25)
    notes: Optional[str] = Field(default=None, max_length=2000)


class VersionCommand(BaseModel):
    expected_version: int = Field(ge=1)
    reason: Optional[str] = Field(default=None, min_length=1, max_length=2000)


class ReceiptLineInput(BaseModel):
    purchase_order_line_id: UUID
    quantity: int = Field(ge=1, le=999)
    unit_cost: Decimal = Field(gt=0, le=Decimal("999999.99"))


class ReceiptCreate(BaseModel):
    expected_version: int = Field(ge=1)
    received_at: datetime
    supplier_reference: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=2000)
    lines: list[ReceiptLineInput] = Field(min_length=1, max_length=100)


class ReturnLineInput(BaseModel):
    purchase_receipt_line_id: Optional[UUID] = None
    core_obligation_id: Optional[UUID] = None
    quantity: int = Field(ge=1, le=999)
    expected_credit: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("999999.99"))


class ReturnCreate(BaseModel):
    kind: Literal["stock", "core"]
    supplier_id: UUID
    reason: str = Field(min_length=1, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=2000)
    lines: list[ReturnLineInput] = Field(min_length=1, max_length=100)


class ReturnUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    notes: Optional[str] = Field(default=None, max_length=2000)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_collection(skip: int, limit: int) -> None:
    if skip < 0 or not 1 <= limit <= 100:
        raise _unprocessable("Invalid pagination")


def _validate_choice(value: str | None, allowed: frozenset[str], name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise _unprocessable(f"Invalid {name}")
    return normalized


def _validate_text_filter(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 255:
        raise _unprocessable(f"Invalid {name}")
    return normalized.casefold()


def _collection(items: list[dict], *, total: int, skip: int, limit: int, paginated: bool):
    if not paginated:
        return items
    return {"items": items, "total": total, "skip": skip, "limit": limit,
            "has_more": skip + len(items) < total}


def _page(items: list[dict], *, skip: int, limit: int, paginated: bool):
    return _collection(items[skip:skip + limit], total=len(items), skip=skip, limit=limit, paginated=paginated)


def _supplier_summary(row: Supplier | None) -> dict | None:
    return None if row is None else {"id": str(row.id), "name": row.name, "normalized_name": row.normalized_name}


def _inventory_summary(row: Inventory | None) -> dict | None:
    return None if row is None else {"id": str(row.id), "sku": row.sku, "name": row.name, "unit_type": row.unit_type}


def _supplier_source_summary(row: InventorySupplierSource, supplier: Supplier | None) -> dict:
    return {
        "source_id": str(row.id),
        "supplier_id": str(row.supplier_id),
        "supplier_name": supplier.name if supplier else None,
        "supplier_part_number": row.supplier_part_number,
        "is_preferred": bool(row.is_preferred),
        "minimum_order_quantity": int(row.minimum_order_quantity),
        "pack_quantity": int(row.pack_quantity),
        "last_unit_cost": str(row.last_unit_cost) if row.last_unit_cost is not None else None,
        "lead_time_days": row.lead_time_days,
        "is_active": bool(row.is_active),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _part_metric_expressions(tenant_id: UUID):
    shortage_packages = (
        func.ceil(PartsUsage.quantity)
        - func.coalesce(PartsUsage.stock_reserved_packages, 0)
    )
    shortage = (
        select(func.coalesce(func.sum(case((shortage_packages > 0, shortage_packages), else_=0)), 0))
        .select_from(PartsUsage)
        .join(RepairOrder, RepairOrder.id == PartsUsage.repair_order_id)
        .where(
            PartsUsage.tenant_id == tenant_id,
            PartsUsage.inventory_id == Inventory.id,
            PartsUsage.deleted_at.is_(None),
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.deleted_at.is_(None),
            RepairOrder.pricing_locked_at.is_(None),
            RepairOrder.status.in_(EDITABLE_REPAIR_STATUSES),
        )
        .correlate(Inventory)
        .scalar_subquery()
    )
    po_remaining = PurchaseOrderLine.ordered_quantity - PurchaseOrderLine.received_quantity
    po_incoming = (
        select(func.coalesce(func.sum(case((po_remaining > 0, po_remaining), else_=0)), 0))
        .select_from(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(
            PurchaseOrderLine.tenant_id == tenant_id,
            PurchaseOrderLine.inventory_id == Inventory.id,
            PurchaseOrderLine.deleted_at.is_(None),
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.deleted_at.is_(None),
            PurchaseOrder.status.in_(("submitted", "partially_received")),
        )
        .correlate(Inventory)
        .scalar_subquery()
    )
    available = func.coalesce(Inventory.stock_quantity, 0)
    reorder_level = func.coalesce(Inventory.reorder_level, 0)
    shelf_need = case((reorder_level > available, reorder_level - available), else_=0)
    incoming = func.coalesce(Inventory.on_order_quantity, 0) + po_incoming
    gross_need = shortage + shelf_need
    recommended = case((gross_need > incoming, gross_need - incoming), else_=0)
    return shortage, incoming, recommended


def _actionable_recommendation(recommended):
    return case(
        (Inventory.ets_retired_at.is_not(None), 0),
        (Inventory.is_placeholder.is_(True), 0),
        else_=recommended,
    )


def _part_ordering(sort_by: str, direction: str, recommended):
    name = func.lower(Inventory.name)
    sku = func.lower(Inventory.sku)
    stable = (name.asc(), sku.asc(), Inventory.id.asc())
    actionable_reorder = _actionable_recommendation(recommended)

    if sort_by == "catalog":
        primary = sku
        fallback = (name.asc(), Inventory.id.asc())
    elif sort_by == "name":
        primary = name
        fallback = (sku.asc(), Inventory.id.asc())
    elif sort_by == "available":
        primary = func.coalesce(Inventory.stock_quantity, 0)
        fallback = stable
    elif sort_by == "location":
        normalized_location = func.lower(func.trim(func.coalesce(Inventory.location, "")))
        location_is_unset = case((func.length(normalized_location) == 0, 1), else_=0)
        primary_order = normalized_location.desc() if direction == "desc" else normalized_location.asc()
        return (location_is_unset.asc(), primary_order, *stable)
    elif sort_by == "cost":
        primary = Inventory.cost
        fallback = stable
    else:
        primary = actionable_reorder
        fallback = stable

    primary_order = primary.desc() if direction == "desc" else primary.asc()
    return (primary_order, *fallback)


async def _part_projection_rows(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    items: list[Inventory],
) -> list[dict]:
    item_ids = {item.id for item in items}

    source_rows = list((await db.execute(
        select(InventorySupplierSource)
        .join(Supplier, Supplier.id == InventorySupplierSource.supplier_id)
        .where(
            InventorySupplierSource.tenant_id == tenant_id,
            InventorySupplierSource.inventory_id.in_(item_ids),
            InventorySupplierSource.deleted_at.is_(None),
            Supplier.tenant_id == tenant_id,
            Supplier.deleted_at.is_(None),
            Supplier.is_active.is_(True),
        )
        .order_by(
            InventorySupplierSource.inventory_id,
            InventorySupplierSource.is_preferred.desc(),
            InventorySupplierSource.id,
        )
    )).scalars().all()) if item_ids else []
    source_supplier_ids = {source.supplier_id for source in source_rows}
    suppliers = {row.id: row for row in (await db.execute(select(Supplier).where(
        Supplier.tenant_id == tenant_id,
        Supplier.id.in_(source_supplier_ids),
        Supplier.deleted_at.is_(None),
    ))).scalars().all()} if source_supplier_ids else {}
    sources_by_item: dict[UUID, list[InventorySupplierSource]] = {item_id: [] for item_id in item_ids}
    for source in source_rows:
        if source.inventory_id in sources_by_item:
            sources_by_item[source.inventory_id].append(source)

    shortage_totals: dict[UUID, int] = {item_id: 0 for item_id in item_ids}
    shortage_sources: dict[UUID, list[dict]] = {item_id: [] for item_id in item_ids}
    if item_ids:
        usages = (await db.execute(
            select(PartsUsage, RepairOrder, Vehicle)
            .join(RepairOrder, RepairOrder.id == PartsUsage.repair_order_id)
            .join(Vehicle, Vehicle.id == RepairOrder.vehicle_id)
            .where(
                PartsUsage.tenant_id == tenant_id,
                PartsUsage.inventory_id.in_(item_ids),
                PartsUsage.deleted_at.is_(None),
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.deleted_at.is_(None),
                RepairOrder.pricing_locked_at.is_(None),
                RepairOrder.status.in_(EDITABLE_REPAIR_STATUSES),
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
            )
        )).all()
        for usage, order, vehicle in usages:
            packages = max(0, ceil(Decimal(usage.quantity)) - int(usage.stock_reserved_packages or 0))
            if not packages:
                continue
            shortage_totals[usage.inventory_id] += packages
            vehicle_display = " ".join(str(value) for value in (vehicle.year, vehicle.make, vehicle.model) if value)
            shortage_sources[usage.inventory_id].append({
                "type": "repair_order",
                "repair_order_id": str(order.id),
                "order_number": order.order_number,
                "status": order.status.value if hasattr(order.status, "value") else str(order.status),
                "vehicle_id": str(vehicle.id),
                "vehicle_display": vehicle_display,
                "unit_number": vehicle.unit_number,
                "parts_usage_id": str(usage.id),
                "packages": packages,
            })

    incoming_totals: dict[UUID, int] = {item_id: 0 for item_id in item_ids}
    incoming_sources: dict[UUID, list[dict]] = {item_id: [] for item_id in item_ids}
    if item_ids:
        supply_rows = (await db.execute(
            select(PurchaseOrderLine, PurchaseOrder)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .where(
                PurchaseOrderLine.tenant_id == tenant_id,
                PurchaseOrderLine.inventory_id.in_(item_ids),
                PurchaseOrderLine.deleted_at.is_(None),
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.deleted_at.is_(None),
                PurchaseOrder.status.in_(("submitted", "partially_received")),
            )
        )).all()
        for line, po in supply_rows:
            remaining = max(0, int(line.ordered_quantity) - int(line.received_quantity))
            if not remaining:
                continue
            incoming_totals[line.inventory_id] += remaining
            incoming_sources[line.inventory_id].append({
                "type": "purchase_order",
                "purchase_order_id": str(po.id),
                "po_number": po.po_number,
                "purchase_order_line_id": str(line.id),
                "packages": remaining,
                "expected_at": po.expected_at.isoformat() if po.expected_at else None,
            })

    values: list[dict] = []
    for item in items:
        source_rows_for_item = sources_by_item[item.id]
        preferred = next((source for source in source_rows_for_item if source.is_preferred and source.is_active), None)
        if preferred is None and item.preferred_supplier_id:
            preferred = next((source for source in source_rows_for_item if source.supplier_id == item.preferred_supplier_id and source.is_active), None)
        available = int(item.stock_quantity or 0)
        needed = shortage_totals[item.id]
        reorder = int(item.reorder_level or 0)
        incoming = incoming_totals[item.id] + int(item.on_order_quantity or 0)
        recommended = max(needed + max(reorder - available, 0) - incoming, 0)
        if item.is_placeholder or item.ets_retired_at is not None:
            recommended = 0
        values.append({
            "id": str(item.id),
            "sku": item.sku,
            "name": item.name,
            "description": item.description,
            "image_url": item.image_url,
            "unit_type": item.unit_type,
            "location": item.location,
            "available_packages": available,
            "needed_for_open_repairs": needed,
            "reorder_level": reorder,
            "incoming_packages": incoming,
            "recommended_order_packages": recommended,
            "average_unit_cost": str(decimal_money(item.cost or 0)),
            "is_archived": item.ets_retired_at is not None,
            "is_placeholder": bool(item.is_placeholder),
            "preferred_source": _supplier_source_summary(preferred, suppliers.get(preferred.supplier_id)) if preferred else None,
            "supplier_sources": [_supplier_source_summary(source, suppliers.get(source.supplier_id)) for source in source_rows_for_item if source.is_active],
            "repair_sources": shortage_sources[item.id],
            "incoming_sources": incoming_sources[item.id],
        })
    return values


async def _supplier_source(
    db: AsyncSession,
    tenant_id: UUID,
    inventory_id: UUID,
    source_id: UUID,
    *,
    locked: bool = False,
) -> InventorySupplierSource:
    stmt = select(InventorySupplierSource).where(
        InventorySupplierSource.id == source_id,
        InventorySupplierSource.inventory_id == inventory_id,
        InventorySupplierSource.tenant_id == tenant_id,
        InventorySupplierSource.deleted_at.is_(None),
    )
    if locked:
        stmt = stmt.with_for_update()
    value = (await db.execute(stmt)).scalar_one_or_none()
    if value is None:
        raise _not_found()
    return value


async def _apply_preferred_source(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    item: Inventory,
    source: InventorySupplierSource,
    is_preferred: bool,
) -> None:
    if is_preferred:
        existing = list((await db.execute(select(InventorySupplierSource).where(
            InventorySupplierSource.tenant_id == tenant_id,
            InventorySupplierSource.inventory_id == item.id,
            InventorySupplierSource.id != source.id,
            InventorySupplierSource.deleted_at.is_(None),
            InventorySupplierSource.is_preferred.is_(True),
        ).with_for_update())).scalars().all())
        for row in existing:
            row.is_preferred = False
        # Apply demotions before the promotion so partial unique indexes never
        # observe two live preferred sources in the same statement batch.
        if existing:
            await db.flush()
        source.is_preferred = True
        item.preferred_supplier_id = source.supplier_id
    else:
        source.is_preferred = False
        if item.preferred_supplier_id == source.supplier_id:
            item.preferred_supplier_id = None


async def _next_po_number(db: AsyncSession, tenant_id: UUID) -> str:
    prefix = f"PO-{_utc_now().strftime('%Y%m%d')}-"
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"db038:po-number:{tenant_id}"))))
    values = list((await db.execute(select(PurchaseOrder.po_number).where(
        PurchaseOrder.tenant_id == tenant_id,
        PurchaseOrder.po_number.like(f"{prefix}%"),
    ))).scalars().all())
    sequence = 1
    for value in values:
        try:
            sequence = max(sequence, int(value.rsplit("-", 1)[1]) + 1)
        except (ValueError, IndexError):
            continue
    return f"{prefix}{sequence:04d}"


async def _tenant_supplier(db: AsyncSession, tenant_id: UUID, supplier_id: UUID | None) -> Supplier | None:
    if supplier_id is None:
        return None
    row = (await db.execute(select(Supplier).where(
        Supplier.id == supplier_id, Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if row is None:
        raise _not_found()
    return row


async def _tenant_inventory(db: AsyncSession, tenant_id: UUID, inventory_id: UUID | None) -> Inventory | None:
    if inventory_id is None:
        return None
    row = (await db.execute(select(Inventory).where(
        Inventory.id == inventory_id, Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if row is None:
        raise _not_found()
    return row


def _serialize_movement(row: InventoryMovement, inventory: Inventory | None = None, source: dict | None = None) -> dict:
    return {"id": str(row.id), "inventory_id": str(row.inventory_id), "bucket": row.bucket,
            "movement_type": row.movement_type, "quantity_delta": row.quantity_delta,
            "balance_before": row.balance_before, "balance_after": row.balance_after,
            "wac_before": str(row.wac_before) if row.wac_before is not None else None,
            "wac_after": str(row.wac_after) if row.wac_after is not None else None,
            "source_type": row.source_type, "source_id": str(row.source_id) if row.source_id else None,
            "destination_type": row.destination_type,
            "destination_id": str(row.destination_id) if row.destination_id else None,
            "occurred_at": row.occurred_at.isoformat(),
            "inventory": _inventory_summary(inventory), "source": source}


def _serialize_po(po: PurchaseOrder, lines: list[PurchaseOrderLine]) -> dict:
    return {"id": str(po.id), "po_number": po.po_number, "supplier_id": str(po.supplier_id),
            "status": po.status, "version": po.version, "expected_at": po.expected_at.isoformat() if po.expected_at else None,
            "notes": po.notes, "lines": [{"id": str(line.id), "inventory_id": str(line.inventory_id),
            "supplier_source_id": str(line.supplier_source_id) if line.supplier_source_id else None,
            "supplier_part_number": line.supplier_part_number_snapshot,
            "sku": line.sku_snapshot, "description": line.description_snapshot, "unit_type": line.unit_type_snapshot,
            "unit_cost": str(line.unit_cost_snapshot), "ordered_quantity": line.ordered_quantity,
            "received_quantity": line.received_quantity} for line in lines]}


async def _tenant(db: AsyncSession, user: User, *, mutate: bool) -> UUID:
    tenant_id = await require_parts_operations_enabled(db, user)
    require_parts_role(user, mutate=mutate)
    return tenant_id


async def _po(db: AsyncSession, tenant_id: UUID, po_id: UUID, *, locked: bool = False) -> PurchaseOrder:
    stmt = select(PurchaseOrder).where(PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.deleted_at.is_(None))
    if locked:
        stmt = stmt.with_for_update()
    value = (await db.execute(stmt)).scalar_one_or_none()
    if value is None:
        raise _not_found()
    return value


async def _po_lines(db: AsyncSession, tenant_id: UUID, po_id: UUID, *, locked: bool = False) -> list[PurchaseOrderLine]:
    stmt = select(PurchaseOrderLine).where(PurchaseOrderLine.tenant_id == tenant_id, PurchaseOrderLine.purchase_order_id == po_id, PurchaseOrderLine.deleted_at.is_(None)).order_by(PurchaseOrderLine.id)
    if locked:
        stmt = stmt.with_for_update()
    return list((await db.execute(stmt)).scalars().all())


async def _start_mutation(
    db: AsyncSession, *, tenant_id: UUID, user: User, family: str,
    route: str, idempotency_key: str | None, payload: dict,
):
    """Return a replay response or a transaction-bound durable record."""
    key = validate_idempotency_key(idempotency_key)
    fingerprint = canonical_fingerprint(route=route, principal_id=user.id, payload=payload)
    replay = await find_idempotent_response(
        db, tenant_id=tenant_id, family=family, key=key, fingerprint=fingerprint,
    )
    if replay is not None:
        return Response(
            content=replay.response_body, status_code=replay.status_code,
            media_type="application/json", headers={"Idempotency-Replayed": "true"},
        ), None
    record = begin_idempotency(
        tenant_id=tenant_id, family=family, key=key, fingerprint=fingerprint,
    )
    db.add(record)
    return None, record


def _complete_mutation(record, body: dict, *, status_code: int = 200) -> dict:
    complete_idempotency(record, status_code=status_code, body=body)
    return body


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False)
    _, _, recommended = _part_metric_expressions(tenant_id)
    needs_reorder = (await db.execute(select(func.count(Inventory.id)).where(
        Inventory.tenant_id == tenant_id,
        Inventory.deleted_at.is_(None),
        Inventory.ets_retired_at.is_(None),
        Inventory.is_placeholder.is_(False),
        recommended > 0,
    ))).scalar() or 0
    open_pos = (await db.execute(select(func.count(PurchaseOrder.id)).where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.deleted_at.is_(None), PurchaseOrder.status.in_(("draft", "submitted", "partially_received"))))).scalar() or 0
    return {
        "needs_reorder_count": needs_reorder,
        "low_stock_count": needs_reorder,
        "open_purchase_order_count": open_pos,
    }


@router.get("/parts")
async def list_parts(
    view: PartView = "active",
    attention: Optional[PartAttention] = None,
    supplier_id: Optional[UUID] = None,
    search: Optional[str] = None,
    sort_by: PartSort = Query(default="catalog", alias="sort"),
    direction: Optional[PartDirection] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    paginated: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=False)
    _validate_collection(skip, limit)
    view_filter = _validate_choice(view, PART_VIEWS, "view") or "active"
    attention_filter = _validate_choice(attention, PART_ATTENTION, "attention")
    sort_filter = _validate_choice(sort_by, PART_SORTS, "sort") or "catalog"
    direction_filter = _validate_choice(direction, PART_DIRECTIONS, "direction")
    direction_filter = direction_filter or PART_DEFAULT_DIRECTIONS[sort_filter]
    supplier_filter = await _tenant_supplier(db, tenant_id, supplier_id)
    search_filter = _validate_text_filter(search, "search")
    _, incoming, recommended = _part_metric_expressions(tenant_id)
    query = select(Inventory).where(
        Inventory.tenant_id == tenant_id,
        Inventory.deleted_at.is_(None),
    )
    if view_filter == "active":
        query = query.where(Inventory.ets_retired_at.is_(None))
    elif view_filter == "archived":
        query = query.where(Inventory.ets_retired_at.is_not(None))
    if attention_filter == "needs_reorder":
        query = query.where(
            Inventory.ets_retired_at.is_(None),
            Inventory.is_placeholder.is_(False),
            recommended > 0,
        )
    elif attention_filter == "out_of_stock":
        query = query.where(func.coalesce(Inventory.stock_quantity, 0) == 0)
    elif attention_filter == "incoming":
        query = query.where(incoming > 0)
    if supplier_filter is not None:
        query = query.where(exists(
            select(1).select_from(InventorySupplierSource).where(
                InventorySupplierSource.tenant_id == tenant_id,
                InventorySupplierSource.inventory_id == Inventory.id,
                InventorySupplierSource.supplier_id == supplier_filter.id,
                InventorySupplierSource.deleted_at.is_(None),
                InventorySupplierSource.is_active.is_(True),
            )
        ))
    if search_filter:
        search_pattern = f"%{search_filter}%"
        source_match = exists(
            select(1)
            .select_from(InventorySupplierSource)
            .join(Supplier, Supplier.id == InventorySupplierSource.supplier_id)
            .where(
                InventorySupplierSource.tenant_id == tenant_id,
                InventorySupplierSource.inventory_id == Inventory.id,
                InventorySupplierSource.deleted_at.is_(None),
                InventorySupplierSource.is_active.is_(True),
                Supplier.tenant_id == tenant_id,
                Supplier.deleted_at.is_(None),
                Supplier.is_active.is_(True),
                or_(
                    Supplier.name.ilike(search_pattern),
                    InventorySupplierSource.supplier_part_number.ilike(search_pattern),
                ),
            )
        )
        query = query.where(or_(
            Inventory.sku.ilike(search_pattern),
            Inventory.name.ilike(search_pattern),
            Inventory.location.ilike(search_pattern),
            source_match,
        ))

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int((await db.execute(count_query)).scalar_one())
    query = query.order_by(*_part_ordering(sort_filter, direction_filter, recommended))
    if paginated:
        query = query.offset(skip).limit(limit)
    items = list((await db.execute(query)).scalars().all())
    values = await _part_projection_rows(db, tenant_id, items=items)
    return _collection(values, total=total, skip=skip, limit=limit, paginated=paginated)


@router.get("/parts/{inventory_id}")
async def get_part_detail(
    inventory_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=False)
    item = await _tenant_inventory(db, tenant_id, inventory_id)
    value = next((row for row in await _part_projection_rows(db, tenant_id, items=[item]) if row["id"] == str(inventory_id)), None)
    if value is None:
        raise _not_found()

    receipt_rows = (await db.execute(
        select(PurchaseReceiptLine, PurchaseReceipt, PurchaseOrder)
        .join(PurchaseReceipt, PurchaseReceipt.id == PurchaseReceiptLine.purchase_receipt_id)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseReceipt.purchase_order_id)
        .where(
            PurchaseReceiptLine.tenant_id == tenant_id,
            PurchaseReceiptLine.inventory_id == inventory_id,
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.deleted_at.is_(None),
        )
        .order_by(PurchaseReceipt.received_at.desc(), PurchaseReceiptLine.id.desc())
        .limit(5)
    )).all()
    movement_rows = list((await db.execute(select(InventoryMovement).where(
        InventoryMovement.tenant_id == tenant_id,
        InventoryMovement.inventory_id == inventory_id,
    ).order_by(InventoryMovement.occurred_at.desc(), InventoryMovement.id.desc()).limit(20))).scalars().all())
    open_po_rows = (await db.execute(
        select(PurchaseOrderLine, PurchaseOrder, Supplier)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .where(
            PurchaseOrderLine.tenant_id == tenant_id,
            PurchaseOrderLine.inventory_id == inventory_id,
            PurchaseOrderLine.deleted_at.is_(None),
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.deleted_at.is_(None),
            PurchaseOrder.status.in_(("draft", "submitted", "partially_received")),
            Supplier.tenant_id == tenant_id,
            Supplier.deleted_at.is_(None),
        )
        .order_by(PurchaseOrder.created_at.desc(), PurchaseOrderLine.id.desc())
    )).all()
    value["recent_receipts"] = [{
        "receipt_id": str(receipt.id),
        "receipt_number": receipt.receipt_number,
        "purchase_order_id": str(po.id),
        "po_number": po.po_number,
        "supplier_id": str(po.supplier_id),
        "quantity": int(line.quantity),
        "unit_cost": str(line.unit_cost),
        "received_at": receipt.received_at.isoformat(),
    } for line, receipt, po in receipt_rows]
    value["open_purchase_order_lines"] = [{
        "purchase_order_id": str(po.id),
        "po_number": po.po_number,
        "status": po.status,
        "supplier_id": str(supplier.id),
        "supplier_name": supplier.name,
        "purchase_order_line_id": str(line.id),
        "supplier_source_id": str(line.supplier_source_id) if line.supplier_source_id else None,
        "supplier_part_number": line.supplier_part_number_snapshot,
        "ordered_quantity": int(line.ordered_quantity),
        "received_quantity": int(line.received_quantity),
        "remaining_quantity": max(0, int(line.ordered_quantity) - int(line.received_quantity)),
        "unit_cost": str(line.unit_cost_snapshot),
        "expected_at": po.expected_at.isoformat() if po.expected_at else None,
    } for line, po, supplier in open_po_rows]
    value["recent_movements"] = [_serialize_movement(row) for row in movement_rows]
    return value


@router.post("/parts/{inventory_id}/supplier-sources", status_code=status.HTTP_201_CREATED)
async def create_supplier_source(
    inventory_id: UUID,
    body: SupplierSourceCreate,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(
        db,
        tenant_id=tenant_id,
        user=current_user,
        family="supplier_source_create",
        route=f"POST:/parts/{inventory_id}/supplier-sources",
        idempotency_key=idempotency_key,
        payload=body.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    item = (await db.execute(select(Inventory).where(
        Inventory.id == inventory_id,
        Inventory.tenant_id == tenant_id,
        Inventory.deleted_at.is_(None),
    ).with_for_update())).scalar_one_or_none()
    supplier = (await db.execute(select(Supplier).where(
        Supplier.id == body.supplier_id,
        Supplier.tenant_id == tenant_id,
        Supplier.deleted_at.is_(None),
        Supplier.is_active.is_(True),
    ))).scalar_one_or_none()
    if item is None or supplier is None:
        raise _not_found()
    if item.ets_retired_at is not None:
        raise HTTPException(status_code=409, detail="Archived parts are read-only")
    duplicate = (await db.execute(select(InventorySupplierSource.id).where(
        InventorySupplierSource.tenant_id == tenant_id,
        InventorySupplierSource.inventory_id == item.id,
        InventorySupplierSource.supplier_id == supplier.id,
        InventorySupplierSource.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Supplier source already exists")
    source = InventorySupplierSource(
        tenant_id=tenant_id,
        inventory_id=item.id,
        supplier_id=supplier.id,
        supplier_part_number=body.supplier_part_number,
        minimum_order_quantity=body.minimum_order_quantity,
        pack_quantity=body.pack_quantity,
        lead_time_days=body.lead_time_days,
        is_active=body.is_active,
    )
    db.add(source)
    await db.flush()
    await _apply_preferred_source(
        db,
        tenant_id=tenant_id,
        item=item,
        source=source,
        is_preferred=body.is_preferred,
    )
    await db.flush()
    await db.refresh(source, attribute_names=["updated_at"])
    output = _complete_mutation(
        record,
        _supplier_source_summary(source, supplier),
        status_code=201,
    )
    await db.commit()
    return output


@router.patch("/parts/{inventory_id}/supplier-sources/{source_id}")
async def update_supplier_source(
    inventory_id: UUID,
    source_id: UUID,
    body: SupplierSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=True)
    item = (await db.execute(select(Inventory).where(
        Inventory.id == inventory_id,
        Inventory.tenant_id == tenant_id,
        Inventory.deleted_at.is_(None),
    ).with_for_update())).scalar_one_or_none()
    if item is None:
        raise _not_found()
    if item.ets_retired_at is not None:
        raise HTTPException(status_code=409, detail="Archived parts are read-only")
    source = await _supplier_source(db, tenant_id, inventory_id, source_id, locked=True)
    if source.updated_at != body.expected_updated_at:
        raise HTTPException(status_code=409, detail="Supplier source changed")
    fields = body.model_fields_set
    if "supplier_part_number" in fields:
        source.supplier_part_number = body.supplier_part_number
    if body.minimum_order_quantity is not None:
        source.minimum_order_quantity = body.minimum_order_quantity
    if body.pack_quantity is not None:
        source.pack_quantity = body.pack_quantity
    if "lead_time_days" in fields:
        source.lead_time_days = body.lead_time_days
    if body.is_active is not None:
        source.is_active = body.is_active
    desired_preferred = source.is_preferred if body.is_preferred is None else body.is_preferred
    if not source.is_active:
        desired_preferred = False
    await _apply_preferred_source(
        db,
        tenant_id=tenant_id,
        item=item,
        source=source,
        is_preferred=desired_preferred,
    )
    await db.flush()
    await db.refresh(source, attribute_names=["updated_at"])
    supplier = await _tenant_supplier(db, tenant_id, source.supplier_id)
    output = _supplier_source_summary(source, supplier)
    await db.commit()
    return output


@router.delete("/parts/{inventory_id}/supplier-sources/{source_id}")
async def delete_supplier_source(
    inventory_id: UUID,
    source_id: UUID,
    body: SupplierSourceDelete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=True)
    item = (await db.execute(select(Inventory).where(
        Inventory.id == inventory_id,
        Inventory.tenant_id == tenant_id,
        Inventory.deleted_at.is_(None),
    ).with_for_update())).scalar_one_or_none()
    if item is None:
        raise _not_found()
    if item.ets_retired_at is not None:
        raise HTTPException(status_code=409, detail="Archived parts are read-only")
    source = await _supplier_source(db, tenant_id, inventory_id, source_id, locked=True)
    if source.updated_at != body.expected_updated_at:
        raise HTTPException(status_code=409, detail="Supplier source changed")
    if source.is_preferred and item.preferred_supplier_id == source.supplier_id:
        item.preferred_supplier_id = None
    source.is_preferred = False
    source.is_active = False
    source.deleted_at = _utc_now()
    await db.commit()
    return {"deleted": True, "source_id": str(source.id)}


@router.get("/suppliers/{supplier_id}/purchasing")
async def get_supplier_purchasing(
    supplier_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=False)
    supplier = await _tenant_supplier(db, tenant_id, supplier_id)
    if supplier is None:
        raise _not_found()
    sources = list((await db.execute(select(InventorySupplierSource).where(
        InventorySupplierSource.tenant_id == tenant_id,
        InventorySupplierSource.supplier_id == supplier.id,
        InventorySupplierSource.deleted_at.is_(None),
        InventorySupplierSource.is_active.is_(True),
    ))).scalars().all())
    open_orders = list((await db.execute(select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == tenant_id,
        PurchaseOrder.supplier_id == supplier.id,
        PurchaseOrder.deleted_at.is_(None),
        PurchaseOrder.status.in_(("draft", "submitted", "partially_received")),
    ))).scalars().all())
    order_ids = {order.id for order in open_orders}
    open_lines = list((await db.execute(select(PurchaseOrderLine).where(
        PurchaseOrderLine.tenant_id == tenant_id,
        PurchaseOrderLine.purchase_order_id.in_(order_ids),
        PurchaseOrderLine.deleted_at.is_(None),
    ))).scalars().all()) if order_ids else []
    receipt_rows = (await db.execute(
        select(PurchaseReceipt, PurchaseOrder)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseReceipt.purchase_order_id)
        .where(
            PurchaseReceipt.tenant_id == tenant_id,
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.supplier_id == supplier.id,
            PurchaseOrder.deleted_at.is_(None),
        )
        .order_by(PurchaseReceipt.received_at.desc(), PurchaseReceipt.id.desc())
    )).all()
    completion_receipts: dict[UUID, tuple[PurchaseReceipt, PurchaseOrder]] = {}
    for receipt, po in receipt_rows:
        if po.status != "received" or po.expected_at is None:
            continue
        current = completion_receipts.get(po.id)
        if current is None or receipt.received_at > current[0].received_at:
            completion_receipts[po.id] = (receipt, po)
    on_time_count = sum(
        1 for receipt, po in completion_receipts.values()
        if receipt.received_at <= po.expected_at
    )
    timed_order_count = len(completion_receipts)
    return {
        **_supplier_summary(supplier),
        "payment_terms": supplier.payment_terms,
        "default_lead_time_days": supplier.default_lead_time_days,
        "minimum_order_amount": str(supplier.minimum_order_amount) if supplier.minimum_order_amount is not None else None,
        "purchasing_notes": supplier.purchasing_notes,
        "active_part_source_count": len(sources),
        "open_purchase_order_count": len(open_orders),
        "open_purchase_order_value": str(decimal_money(sum(
            (Decimal(line.unit_cost_snapshot) * (int(line.ordered_quantity) - int(line.received_quantity)) for line in open_lines),
            Decimal("0"),
        ))),
        "last_receipt_at": receipt_rows[0][0].received_at.isoformat() if receipt_rows else None,
        "on_time_order_count": on_time_count,
        "timed_order_count": timed_order_count,
        "on_time_rate": (
            str(decimal_money(Decimal(on_time_count) * 100 / Decimal(timed_order_count)))
            if timed_order_count else None
        ),
    }


@router.get("/activity")
async def activity(
    inventory_id: Optional[UUID] = None, source_type: Optional[str] = None,
    movement_type: Optional[str] = None,
    from_at: Optional[datetime] = Query(default=None, alias="from"),
    to: Optional[datetime] = None, skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100), paginated: bool = Query(default=False),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=False)
    _validate_collection(skip, limit)
    inventory = await _tenant_inventory(db, tenant_id, inventory_id)
    source_filter = _validate_choice(source_type, SOURCE_TYPES, "source_type")
    movement_filter = _validate_choice(movement_type, MOVEMENT_TYPES, "movement_type")
    if (from_at and from_at.tzinfo is None) or (to and to.tzinfo is None) or (from_at and to and from_at > to):
        raise _unprocessable("Invalid date range")
    stmt = select(InventoryMovement).where(InventoryMovement.tenant_id == tenant_id)
    if inventory is not None:
        stmt = stmt.where(InventoryMovement.inventory_id == inventory.id)
    if source_filter is not None:
        stmt = stmt.where(InventoryMovement.source_type == source_filter)
    if movement_filter is not None:
        stmt = stmt.where(InventoryMovement.movement_type == movement_filter)
    if from_at is not None:
        stmt = stmt.where(InventoryMovement.occurred_at >= from_at)
    if to is not None:
        stmt = stmt.where(InventoryMovement.occurred_at <= to)
    rows = list((await db.execute(stmt.order_by(InventoryMovement.occurred_at.desc(), InventoryMovement.id.desc()))).scalars().all())
    inventory_ids = {row.inventory_id for row in rows}
    inventories = {row.id: row for row in (await db.execute(select(Inventory).where(
        Inventory.tenant_id == tenant_id, Inventory.id.in_(inventory_ids), Inventory.deleted_at.is_(None),
    ))).scalars().all()} if inventory_ids else {}
    source_summaries: dict[tuple[str, UUID], dict] = {}
    repair_ids = {row.source_id for row in rows if row.source_type == "repair_order" and row.source_id}
    if repair_ids:
        orders = (await db.execute(select(RepairOrder).where(
            RepairOrder.tenant_id == tenant_id, RepairOrder.id.in_(repair_ids), RepairOrder.deleted_at.is_(None),
        ))).scalars().all()
        source_summaries.update({("repair_order", order.id): {"type": "repair_order", "id": str(order.id), "order_number": order.order_number} for order in orders})
    return_ids = {row.source_id for row in rows if row.source_type == "vendor_return" and row.source_id}
    if return_ids:
        returns = (await db.execute(select(VendorReturn).where(
            VendorReturn.tenant_id == tenant_id, VendorReturn.id.in_(return_ids), VendorReturn.deleted_at.is_(None),
        ))).scalars().all()
        source_summaries.update({("vendor_return", row.id): {"type": "vendor_return", "id": str(row.id), "return_number": row.return_number} for row in returns})
    receipt_ids = {row.source_id for row in rows if row.source_type == "purchase_receipt" and row.source_id}
    if receipt_ids:
        receipts = (await db.execute(select(PurchaseReceipt).where(PurchaseReceipt.tenant_id == tenant_id, PurchaseReceipt.id.in_(receipt_ids)))).scalars().all()
        source_summaries.update({("purchase_receipt", row.id): {"type": "purchase_receipt", "id": str(row.id), "receipt_number": row.receipt_number, "purchase_order_id": str(row.purchase_order_id)} for row in receipts})
    values = [_serialize_movement(row, inventories.get(row.inventory_id), source_summaries.get((row.source_type, row.source_id))) for row in rows]
    return _page(values, skip=skip, limit=limit, paginated=paginated)


@router.get("/demand")
async def demand(
    state: Optional[DemandState] = None, supplier_id: Optional[UUID] = None, search: Optional[str] = None,
    skip: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
    paginated: bool = Query(default=False),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=False)
    _validate_collection(skip, limit)
    state_filter = _validate_choice(state, DEMAND_STATES, "state")
    supplier_filter = await _tenant_supplier(db, tenant_id, supplier_id)
    search_filter = _validate_text_filter(search, "search")
    items = list((await db.execute(select(Inventory).where(
        Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None),
    ))).scalars().all())
    item_ids = {item.id for item in items}
    suppliers = {row.id: row for row in (await db.execute(select(Supplier).where(
        Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None),
    ))).scalars().all()}
    shortage_sources: dict[UUID, list[dict]] = {item_id: [] for item_id in item_ids}
    shortage_totals: dict[UUID, int] = {item_id: 0 for item_id in item_ids}
    if item_ids:
        usages = (await db.execute(
            select(PartsUsage, RepairOrder).join(RepairOrder, RepairOrder.id == PartsUsage.repair_order_id).where(
                PartsUsage.tenant_id == tenant_id, PartsUsage.inventory_id.in_(item_ids),
                PartsUsage.deleted_at.is_(None), RepairOrder.tenant_id == tenant_id,
                RepairOrder.deleted_at.is_(None), RepairOrder.pricing_locked_at.is_(None),
                RepairOrder.status.in_(EDITABLE_REPAIR_STATUSES),
            )
        )).all()
        for usage, order in usages:
            packages = max(0, ceil(Decimal(usage.quantity)) - int(usage.stock_reserved_packages or 0))
            if packages:
                shortage_totals[usage.inventory_id] += packages
                shortage_sources[usage.inventory_id].append({
                    "type": "repair_order", "repair_order_id": str(order.id),
                    "order_number": order.order_number, "parts_usage_id": str(usage.id), "packages": packages,
                })
    supply_sources: dict[UUID, list[dict]] = {item_id: [] for item_id in item_ids}
    po_supply: dict[UUID, int] = {item_id: 0 for item_id in item_ids}
    if item_ids:
        supply_rows = (await db.execute(
            select(PurchaseOrderLine, PurchaseOrder).join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id).where(
                PurchaseOrderLine.tenant_id == tenant_id, PurchaseOrderLine.inventory_id.in_(item_ids),
                PurchaseOrderLine.deleted_at.is_(None), PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.deleted_at.is_(None), PurchaseOrder.status.in_(("submitted", "partially_received")),
            )
        )).all()
        for line, po in supply_rows:
            remaining = max(0, int(line.ordered_quantity) - int(line.received_quantity))
            if remaining:
                po_supply[line.inventory_id] += remaining
                supply_sources[line.inventory_id].append({
                    "type": "purchase_order", "purchase_order_id": str(po.id),
                    "po_number": po.po_number, "purchase_order_line_id": str(line.id), "packages": remaining,
                })
    fresh_as_of = _utc_now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    values = []
    for item in items:
        if supplier_filter is not None and item.preferred_supplier_id != supplier_filter.id:
            continue
        if search_filter and search_filter not in f"{item.sku} {item.name}".casefold():
            continue
        repair_shortage = shortage_totals[item.id]
        shelf = max(int(item.reorder_level or 0) - int(item.stock_quantity or 0), 0)
        gross_demand = repair_shortage + shelf
        if gross_demand <= 0:
            continue
        legacy_supply = max(0, int(item.on_order_quantity or 0))
        open_supply = po_supply[item.id] + legacy_supply
        recommended = max(gross_demand - open_supply, 0)
        demand_state = "unlinked" if item.is_placeholder else ("open" if recommended else "covered")
        if state_filter and demand_state != state_filter:
            continue
        sources = sorted(shortage_sources[item.id], key=lambda value: (value["order_number"], value["repair_order_id"], value["parts_usage_id"]))
        if shelf:
            sources.append({"type": "reorder_level", "packages": shelf})
        sources.extend(sorted(supply_sources[item.id], key=lambda value: (value["po_number"], value["purchase_order_id"], value["purchase_order_line_id"])))
        if legacy_supply:
            sources.append({"type": "legacy_on_order", "packages": legacy_supply, "linked": False})
        values.append({
            "inventory_id": str(item.id), "sku": item.sku, "name": item.name, "unit_type": item.unit_type,
            "state": demand_state, "stock_quantity": item.stock_quantity, "reorder_level": item.reorder_level,
            "repair_shortage_packages": repair_shortage, "shelf_replenishment_packages": shelf,
            "open_supply_packages": open_supply, "recommended_order_packages": recommended,
            "preferred_supplier": _supplier_summary(suppliers.get(item.preferred_supplier_id)),
            "fresh_as_of": fresh_as_of, "sources": sources,
        })
    state_order = {"open": 0, "unlinked": 1, "covered": 2}
    values.sort(key=lambda value: (state_order[value["state"]], -value["recommended_order_packages"], value["name"].casefold(), value["sku"].casefold(), value["inventory_id"]))
    return _page(values, skip=skip, limit=limit, paginated=paginated)


@router.get("/categories")
async def list_categories(
    active: Optional[bool] = None, search: Optional[str] = None, skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100), paginated: bool = Query(default=False), db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=False)
    _validate_collection(skip, limit)
    search_filter = _validate_text_filter(search, "search")
    rows = list((await db.execute(select(InventoryCategory).where(
        InventoryCategory.tenant_id == tenant_id, InventoryCategory.deleted_at.is_(None),
    ))).scalars().all())
    values = [{"id": str(row.id), "name": row.name, "normalized_name": row.normalized_name,
               "description": row.description, "is_active": row.is_active} for row in rows
              if (active is None or row.is_active is active)
              and (not search_filter or search_filter in f"{row.name} {row.description or ''}".casefold())]
    values.sort(key=lambda value: (value["normalized_name"], value["id"]))
    return _page(values, skip=skip, limit=limit, paginated=paginated)


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(body: CategoryInput, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="category_create", route="POST:/categories", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None:
        return replay
    name = " ".join(body.name.split())
    normalized = normalize_name(name)
    existing = (await db.execute(select(InventoryCategory).where(InventoryCategory.tenant_id == tenant_id, InventoryCategory.normalized_name == normalized, InventoryCategory.deleted_at.is_(None)))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Category already exists")
    row = InventoryCategory(tenant_id=tenant_id, name=name, normalized_name=normalized, description=body.description)
    db.add(row); await db.flush()
    output = _complete_mutation(record, {"id": str(row.id), "name": row.name, "normalized_name": row.normalized_name, "description": row.description, "is_active": row.is_active}, status_code=201)
    await db.commit()
    return output


@router.get("/purchase-orders")
async def list_purchase_orders(
    status_filter: Optional[POStatusFilter] = Query(default=None, alias="status"),
    supplier_id: Optional[UUID] = None, search: Optional[str] = None,
    skip: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
    paginated: bool = Query(default=False),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=False)
    _validate_collection(skip, limit)
    normalized_status = _validate_choice(status_filter, PO_STATUSES, "status")
    supplier_filter = await _tenant_supplier(db, tenant_id, supplier_id)
    search_filter = _validate_text_filter(search, "search")
    rows = list((await db.execute(select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.deleted_at.is_(None),
    ))).scalars().all())
    suppliers = {row.id: row for row in (await db.execute(select(Supplier).where(
        Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None),
    ))).scalars().all()}
    po_ids = {row.id for row in rows}
    lines_by_po: dict[UUID, list[PurchaseOrderLine]] = {po_id: [] for po_id in po_ids}
    if po_ids:
        for line in (await db.execute(select(PurchaseOrderLine).where(
            PurchaseOrderLine.tenant_id == tenant_id, PurchaseOrderLine.purchase_order_id.in_(po_ids),
            PurchaseOrderLine.deleted_at.is_(None),
        ))).scalars().all():
            lines_by_po[line.purchase_order_id].append(line)
    values = []
    for row in rows:
        supplier = suppliers.get(row.supplier_id)
        if normalized_status and row.status != normalized_status:
            continue
        if supplier_filter and row.supplier_id != supplier_filter.id:
            continue
        if search_filter and search_filter not in f"{row.po_number} {row.notes or ''} {supplier.name if supplier else ''}".casefold():
            continue
        lines = lines_by_po[row.id]
        ordered = sum(int(line.ordered_quantity) for line in lines)
        received = sum(int(line.received_quantity) for line in lines)
        values.append({
            "id": str(row.id), "po_number": row.po_number, "supplier_id": str(row.supplier_id),
            "supplier": _supplier_summary(supplier), "status": row.status, "version": row.version,
            "expected_at": row.expected_at.isoformat() if row.expected_at else None,
            "line_count": len(lines), "ordered_quantity": ordered, "received_quantity": received,
            "remaining_quantity": max(0, ordered - received),
            "created_at": row.created_at.isoformat(),
        })
    values.sort(key=lambda value: (value["created_at"], value["id"]), reverse=True)
    return _page(values, skip=skip, limit=limit, paginated=paginated)


@router.post("/purchase-orders", status_code=status.HTTP_201_CREATED)
async def create_purchase_order(body: POCreate, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    key = validate_idempotency_key(idempotency_key)
    fingerprint = canonical_fingerprint(route="POST:/purchase-orders", principal_id=current_user.id, payload=body.model_dump(mode="json"))
    replay = await find_idempotent_response(db, tenant_id=tenant_id, family="po_create", key=key, fingerprint=fingerprint)
    if replay:
        return Response(content=replay.response_body, status_code=replay.status_code, media_type="application/json", headers={"Idempotency-Replayed": "true"})
    supplier = (await db.execute(select(Supplier).where(Supplier.id == body.supplier_id, Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None), Supplier.is_active.is_(True)))).scalar_one_or_none()
    if supplier is None:
        raise _not_found()
    po = PurchaseOrder(tenant_id=tenant_id, po_number=body.po_number.strip(), supplier_id=supplier.id, expected_at=body.expected_at, notes=body.notes, created_by_user_id=current_user.id)
    db.add(po); await db.flush()
    seen: set[UUID] = set(); lines = []
    for data in body.lines:
        if data.inventory_id in seen: raise HTTPException(status_code=422, detail="Duplicate inventory line")
        seen.add(data.inventory_id)
        item = (await db.execute(select(Inventory).where(Inventory.id == data.inventory_id, Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None), Inventory.is_placeholder.is_(False)))).scalar_one_or_none()
        if item is None: raise _not_found()
        source = (await db.execute(select(InventorySupplierSource).where(
            InventorySupplierSource.tenant_id == tenant_id,
            InventorySupplierSource.inventory_id == item.id,
            InventorySupplierSource.supplier_id == supplier.id,
            InventorySupplierSource.deleted_at.is_(None),
            InventorySupplierSource.is_active.is_(True),
        ))).scalar_one_or_none()
        line = PurchaseOrderLine(
            tenant_id=tenant_id,
            purchase_order_id=po.id,
            inventory_id=item.id,
            supplier_source_id=source.id if source else None,
            supplier_part_number_snapshot=source.supplier_part_number if source else None,
            sku_snapshot=item.sku,
            description_snapshot=item.name,
            unit_type_snapshot=item.unit_type,
            unit_cost_snapshot=decimal_money(data.unit_cost),
            core_charge_snapshot=decimal_money(item.core_charge or 0),
            ordered_quantity=data.ordered_quantity,
        )
        db.add(line); lines.append(line)
    record = begin_idempotency(tenant_id=tenant_id, family="po_create", key=key, fingerprint=fingerprint); db.add(record)
    await db.flush(); body_out = _serialize_po(po, lines); complete_idempotency(record, status_code=201, body=body_out)
    await db.commit(); return body_out


@router.post("/purchase-orders/batch", status_code=status.HTTP_201_CREATED)
async def create_purchase_order_batch(
    body: POBatchCreate,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create one draft PO per supplier as one all-or-nothing operation."""
    tenant_id = await _tenant(db, current_user, mutate=True)
    key = validate_idempotency_key(idempotency_key)
    fingerprint = canonical_fingerprint(
        route="POST:/purchase-orders/batch",
        principal_id=current_user.id,
        payload=body.model_dump(mode="json"),
    )
    replay = await find_idempotent_response(
        db,
        tenant_id=tenant_id,
        family="po_batch_create",
        key=key,
        fingerprint=fingerprint,
    )
    if replay:
        return Response(
            content=replay.response_body,
            status_code=replay.status_code,
            media_type="application/json",
            headers={"Idempotency-Replayed": "true"},
        )

    supplier_ids = [group.supplier_id for group in body.groups]
    if len(set(supplier_ids)) != len(supplier_ids):
        raise HTTPException(status_code=422, detail="Duplicate supplier group")

    validated_groups: list[
        tuple[Supplier, list[tuple[BatchPOLineInput, Inventory, InventorySupplierSource]]]
    ] = []
    inventory_ids: set[UUID] = set()
    for group in body.groups:
        supplier = (await db.execute(select(Supplier).where(
            Supplier.id == group.supplier_id,
            Supplier.tenant_id == tenant_id,
            Supplier.deleted_at.is_(None),
            Supplier.is_active.is_(True),
        ))).scalar_one_or_none()
        if supplier is None:
            raise _not_found()

        lines: list[tuple[BatchPOLineInput, Inventory, InventorySupplierSource]] = []
        for data in group.lines:
            if data.inventory_id in inventory_ids:
                raise HTTPException(status_code=422, detail="Duplicate inventory line")
            inventory_ids.add(data.inventory_id)
            item = (await db.execute(select(Inventory).where(
                Inventory.id == data.inventory_id,
                Inventory.tenant_id == tenant_id,
                Inventory.deleted_at.is_(None),
                Inventory.is_placeholder.is_(False),
                Inventory.ets_retired_at.is_(None),
            ))).scalar_one_or_none()
            source = (await db.execute(select(InventorySupplierSource).where(
                InventorySupplierSource.id == data.source_id,
                InventorySupplierSource.tenant_id == tenant_id,
                InventorySupplierSource.inventory_id == data.inventory_id,
                InventorySupplierSource.supplier_id == supplier.id,
                InventorySupplierSource.deleted_at.is_(None),
                InventorySupplierSource.is_active.is_(True),
            ))).scalar_one_or_none()
            if item is None or source is None:
                raise _not_found()
            if data.ordered_quantity < source.minimum_order_quantity:
                raise HTTPException(status_code=422, detail="Quantity is below the supplier minimum")
            if data.ordered_quantity % source.pack_quantity:
                raise HTTPException(status_code=422, detail="Quantity must match the supplier pack size")
            lines.append((data, item, source))
        validated_groups.append((supplier, lines))

    purchase_orders: list[dict] = []
    for supplier, group_lines in validated_groups:
        po = PurchaseOrder(
            tenant_id=tenant_id,
            po_number=await _next_po_number(db, tenant_id),
            supplier_id=supplier.id,
            notes=body.notes,
            created_by_user_id=current_user.id,
        )
        db.add(po)
        await db.flush()
        lines: list[PurchaseOrderLine] = []
        for data, item, source in group_lines:
            line = PurchaseOrderLine(
                tenant_id=tenant_id,
                purchase_order_id=po.id,
                inventory_id=item.id,
                supplier_source_id=source.id,
                supplier_part_number_snapshot=source.supplier_part_number,
                sku_snapshot=item.sku,
                description_snapshot=item.name,
                unit_type_snapshot=item.unit_type,
                unit_cost_snapshot=decimal_money(data.unit_cost),
                core_charge_snapshot=decimal_money(item.core_charge or 0),
                ordered_quantity=data.ordered_quantity,
            )
            db.add(line)
            lines.append(line)
        await db.flush()
        purchase_orders.append({
            **_serialize_po(po, lines),
            "supplier": _supplier_summary(supplier),
            "line_count": len(lines),
            "ordered_quantity": sum(int(line.ordered_quantity) for line in lines),
        })

    response = {
        "purchase_orders": purchase_orders,
        "unassigned": [],
        "count": len(purchase_orders),
    }
    record = begin_idempotency(
        tenant_id=tenant_id,
        family="po_batch_create",
        key=key,
        fingerprint=fingerprint,
    )
    db.add(record)
    complete_idempotency(record, status_code=201, body=response)
    await db.commit()
    return response


@router.get("/purchase-orders/{po_id}")
async def get_purchase_order(po_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False); po = await _po(db, tenant_id, po_id)
    output = _serialize_po(po, await _po_lines(db, tenant_id, po.id))
    output["supplier"] = _supplier_summary(await _tenant_supplier(db, tenant_id, po.supplier_id))
    return output


@router.post("/purchase-orders/{po_id}/submit")
async def submit_purchase_order(po_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="po_submit", route=f"POST:/purchase-orders/{po_id}/submit", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None: return replay
    po = await _po(db, tenant_id, po_id, locked=True)
    if po.version != body.expected_version or po.status != "draft": raise HTTPException(status_code=409, detail="Purchase order changed")
    if not await _po_lines(db, tenant_id, po_id): raise HTTPException(status_code=409, detail="Purchase order has no lines")
    po.status = "submitted"; po.ordered_at = datetime.now(timezone.utc); po.submitted_by_user_id = current_user.id; po.version += 1
    output = _complete_mutation(record, _serialize_po(po, await _po_lines(db, tenant_id, po_id)))
    await db.commit(); return output


@router.post("/purchase-orders/{po_id}/cancel")
async def cancel_purchase_order(po_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="po_cancel", route=f"POST:/purchase-orders/{po_id}/cancel", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None: return replay
    po = await _po(db, tenant_id, po_id, locked=True)
    if po.version != body.expected_version or po.status not in {"draft", "submitted"}: raise HTTPException(status_code=409, detail="Purchase order changed")
    if (await _po_lines(db, tenant_id, po_id)).__len__() and any(line.received_quantity for line in await _po_lines(db, tenant_id, po_id)): raise HTTPException(status_code=409, detail="Purchase order has receipts")
    po.status = "cancelled"; po.notes = body.reason or po.notes; po.version += 1
    output = _complete_mutation(record, _serialize_po(po, await _po_lines(db, tenant_id, po_id)))
    await db.commit(); return output


@router.post("/purchase-orders/{po_id}/receipts", status_code=status.HTTP_201_CREATED)
async def receive_purchase_order(po_id: UUID, body: ReceiptCreate, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True); key = validate_idempotency_key(idempotency_key)
    fingerprint = canonical_fingerprint(route=f"POST:/purchase-orders/{po_id}/receipts", principal_id=current_user.id, payload=body.model_dump(mode="json"))
    replay = await find_idempotent_response(db, tenant_id=tenant_id, family="po_receipt", key=key, fingerprint=fingerprint)
    if replay: return Response(content=replay.response_body, status_code=replay.status_code, media_type="application/json", headers={"Idempotency-Replayed": "true"})
    po = await _po(db, tenant_id, po_id, locked=True)
    if po.version != body.expected_version or po.status not in {"submitted", "partially_received"}: raise HTTPException(status_code=409, detail="Purchase order changed")
    lines = {line.id: line for line in await _po_lines(db, tenant_id, po_id, locked=True)}
    if len(lines) < len(body.lines) or len({line.purchase_order_line_id for line in body.lines}) != len(body.lines): raise _not_found()
    receipt = PurchaseReceipt(tenant_id=tenant_id, purchase_order_id=po.id, receipt_number=f"RCV-{uuid4().hex[:12].upper()}", received_at=body.received_at, supplier_reference=body.supplier_reference, notes=body.notes, received_by_user_id=current_user.id, idempotency_key=key, request_fingerprint=fingerprint)
    db.add(receipt); await db.flush(); output = []
    for input_line in sorted(body.lines, key=lambda line: str(lines[line.purchase_order_line_id].inventory_id)):
        line = lines.get(input_line.purchase_order_line_id)
        if line is None or input_line.quantity > line.ordered_quantity - line.received_quantity: raise HTTPException(status_code=409, detail="Over-receipt")
        item = (await db.execute(select(Inventory).where(Inventory.id == line.inventory_id, Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
        if item is None: raise _not_found()
        before = int(item.stock_quantity or 0); old_wac = decimal_money(Decimal(item.cost)); wac = receipt_wac(old_balance=before, old_wac=old_wac, quantity=input_line.quantity, unit_cost=input_line.unit_cost)
        await apply_inventory_movement(db, item=item, quantity_delta=input_line.quantity, movement_type="po_receipt", actor=current_user, source_type="purchase_receipt", source_id=receipt.id, destination_type="purchase_order", destination_id=po.id, idempotency_key=f"{key}:{line.id}", wac_after=wac)
        line.received_quantity += input_line.quantity
        supplier_source = None
        if line.supplier_source_id is not None:
            supplier_source = (await db.execute(select(InventorySupplierSource).where(
                InventorySupplierSource.id == line.supplier_source_id,
                InventorySupplierSource.tenant_id == tenant_id,
                InventorySupplierSource.inventory_id == item.id,
                InventorySupplierSource.supplier_id == po.supplier_id,
            ).with_for_update())).scalar_one_or_none()
            if supplier_source is None:
                raise _not_found()
        if supplier_source is not None:
            supplier_source.last_unit_cost = decimal_money(input_line.unit_cost)
        db.add(PurchaseReceiptLine(tenant_id=tenant_id, purchase_receipt_id=receipt.id, purchase_order_line_id=line.id, inventory_id=item.id, quantity=input_line.quantity, unit_cost=decimal_money(input_line.unit_cost), wac_before=old_wac, wac_after=wac, balance_before=before, balance_after=before + input_line.quantity))
        output.append({"inventory_id": str(item.id), "received_quantity": input_line.quantity, "remaining_quantity": line.ordered_quantity - line.received_quantity, "balance_before": before, "balance_after": before + input_line.quantity, "wac_before": str(old_wac), "wac_after": str(wac)})
    po.status = "received" if all(line.received_quantity == line.ordered_quantity for line in lines.values()) else "partially_received"; po.version += 1
    response = {"receipt_id": str(receipt.id), "purchase_order_id": str(po.id), "purchase_order_status": po.status, "version": po.version, "lines": output}
    record = begin_idempotency(tenant_id=tenant_id, family="po_receipt", key=key, fingerprint=fingerprint); db.add(record); complete_idempotency(record, status_code=201, body=response)
    await db.commit(); return response


@router.get("/cores")
async def list_cores(
    status_filter: Optional[CoreStatusFilter] = Query(default=None, alias="status"),
    supplier_id: Optional[UUID] = None, inventory_id: Optional[UUID] = None,
    skip: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
    paginated: bool = Query(default=False),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=False)
    _validate_collection(skip, limit)
    normalized_status = _validate_choice(status_filter, CORE_STATUSES, "status")
    supplier_filter = await _tenant_supplier(db, tenant_id, supplier_id)
    inventory_filter = await _tenant_inventory(db, tenant_id, inventory_id)
    rows = list((await db.execute(select(CoreObligation).where(
        CoreObligation.tenant_id == tenant_id, CoreObligation.deleted_at.is_(None),
    ))).scalars().all())
    inventory_ids = {row.inventory_id for row in rows}
    inventories = {row.id: row for row in (await db.execute(select(Inventory).where(
        Inventory.tenant_id == tenant_id, Inventory.id.in_(inventory_ids), Inventory.deleted_at.is_(None),
    ))).scalars().all()} if inventory_ids else {}
    supplier_ids = {row.supplier_id for row in rows if row.supplier_id}
    suppliers = {row.id: row for row in (await db.execute(select(Supplier).where(
        Supplier.tenant_id == tenant_id, Supplier.id.in_(supplier_ids), Supplier.deleted_at.is_(None),
    ))).scalars().all()} if supplier_ids else {}
    usage_ids = {row.parts_usage_id for row in rows}
    usage_rows = (await db.execute(
        select(PartsUsage, RepairOrder).join(RepairOrder, RepairOrder.id == PartsUsage.repair_order_id).where(
            PartsUsage.tenant_id == tenant_id, PartsUsage.id.in_(usage_ids), PartsUsage.deleted_at.is_(None),
            RepairOrder.tenant_id == tenant_id, RepairOrder.deleted_at.is_(None),
        )
    )).all() if usage_ids else []
    sources = {usage.id: {"parts_usage_id": str(usage.id), "repair_order_id": str(order.id),
                          "order_number": order.order_number} for usage, order in usage_rows}
    values = [{
        "id": str(row.id), "inventory_id": str(row.inventory_id),
        "inventory": _inventory_summary(inventories.get(row.inventory_id)),
        "supplier_id": str(row.supplier_id) if row.supplier_id else None,
        "supplier": _supplier_summary(suppliers.get(row.supplier_id)),
        "quantity": row.quantity, "status": row.status, "version": row.version,
        "unit_core_value": str(row.unit_core_value_snapshot), "source": sources.get(row.parts_usage_id),
        "created_at": row.created_at.isoformat(),
    } for row in rows if (not normalized_status or row.status == normalized_status)
        and (not supplier_filter or row.supplier_id == supplier_filter.id)
        and (not inventory_filter or row.inventory_id == inventory_filter.id)]
    values.sort(key=lambda value: (value["created_at"], value["id"]), reverse=True)
    return _page(values, skip=skip, limit=limit, paginated=paginated)


@router.post("/cores/{obligation_id}/recover")
async def recover_core(obligation_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="core_recover", route=f"POST:/cores/{obligation_id}/recover", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None: return replay
    core = (await db.execute(select(CoreObligation).where(CoreObligation.id == obligation_id, CoreObligation.tenant_id == tenant_id, CoreObligation.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not core: raise _not_found()
    if core.status != "expected" or core.version != body.expected_version: raise HTTPException(status_code=409, detail="Core obligation changed")
    item = (await db.execute(select(Inventory).where(Inventory.id == core.inventory_id, Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not item: raise _not_found()
    before = int((await db.execute(select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(InventoryMovement.tenant_id == tenant_id, InventoryMovement.inventory_id == item.id, InventoryMovement.bucket == "core_on_hand"))).scalar() or 0)
    core.status = "on_hand"; core.version += 1; item.stock_version = int(item.stock_version or 0) + 1
    db.add(InventoryMovement(tenant_id=tenant_id, inventory_id=item.id, bucket="core_on_hand", movement_type="core_recovery", quantity_delta=core.quantity, balance_before=before, balance_after=before + core.quantity, unit_cost_snapshot=core.unit_core_value_snapshot, wac_before=Decimal(item.cost), wac_after=Decimal(item.cost), source_type="core_obligation", source_id=core.id, actor_user_id=current_user.id, actor_display_name_snapshot=f"{current_user.first_name} {current_user.last_name}".strip(), reason_code="core_recovery"))
    output = _complete_mutation(record, {"id": str(core.id), "status": core.status, "version": core.version})
    await db.commit(); return output


@router.post("/cores/{obligation_id}/waive")
async def waive_core(obligation_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="core_waive", route=f"POST:/cores/{obligation_id}/waive", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None: return replay
    core = (await db.execute(select(CoreObligation).where(CoreObligation.id == obligation_id, CoreObligation.tenant_id == tenant_id, CoreObligation.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not core: raise _not_found()
    if core.status not in {"expected", "on_hand"} or core.version != body.expected_version: raise HTTPException(status_code=409, detail="Core obligation changed")
    if not body.reason: raise HTTPException(status_code=422, detail="Waiver reason is required")
    core.status = "waived"; core.reason = body.reason; core.version += 1
    output = _complete_mutation(record, {"id": str(core.id), "status": core.status, "version": core.version})
    await db.commit(); return output


@router.get("/returns")
async def list_returns(
    kind: Optional[ReturnKindFilter] = None,
    status_filter: Optional[ReturnStatusFilter] = Query(default=None, alias="status"),
    supplier_id: Optional[UUID] = None, skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100), paginated: bool = Query(default=False),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _tenant(db, current_user, mutate=False)
    _validate_collection(skip, limit)
    normalized_kind = _validate_choice(kind, RETURN_KINDS, "kind")
    normalized_status = _validate_choice(status_filter, RETURN_STATUSES, "status")
    supplier_filter = await _tenant_supplier(db, tenant_id, supplier_id)
    rows = list((await db.execute(select(VendorReturn).where(
        VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None),
    ))).scalars().all())
    return_ids = {row.id for row in rows}
    lines_by_return: dict[UUID, list[VendorReturnLine]] = {return_id: [] for return_id in return_ids}
    if return_ids:
        for line in (await db.execute(select(VendorReturnLine).where(
            VendorReturnLine.tenant_id == tenant_id, VendorReturnLine.vendor_return_id.in_(return_ids),
            VendorReturnLine.deleted_at.is_(None),
        ))).scalars().all():
            lines_by_return[line.vendor_return_id].append(line)
    suppliers = {row.id: row for row in (await db.execute(select(Supplier).where(
        Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None),
    ))).scalars().all()}
    values = []
    for row in rows:
        if normalized_kind and row.kind != normalized_kind:
            continue
        if normalized_status and row.status != normalized_status:
            continue
        if supplier_filter and row.supplier_id != supplier_filter.id:
            continue
        lines = lines_by_return[row.id]
        values.append({
            "id": str(row.id), "return_number": row.return_number, "supplier_id": str(row.supplier_id),
            "supplier": _supplier_summary(suppliers.get(row.supplier_id)), "kind": row.kind,
            "status": row.status, "version": row.version, "line_count": len(lines),
            "total_quantity": sum(int(line.quantity) for line in lines),
            "expected_credit_total": str(decimal_money(sum((Decimal(line.expected_credit) for line in lines), Decimal("0")))),
            "reverses_return_id": str(row.reverses_return_id) if row.reverses_return_id else None,
            "created_at": row.created_at.isoformat(),
        })
    values.sort(key=lambda value: (value["created_at"], value["id"]), reverse=True)
    return _page(values, skip=skip, limit=limit, paginated=paginated)


@router.post("/returns", status_code=status.HTTP_201_CREATED)
async def create_return(body: ReturnCreate, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="return_create", route="POST:/returns", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None:
        return replay
    supplier = (await db.execute(select(Supplier).where(Supplier.id == body.supplier_id, Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None), Supplier.is_active.is_(True)))).scalar_one_or_none()
    if not supplier: raise _not_found()
    row = VendorReturn(tenant_id=tenant_id, return_number=f"RET-{uuid4().hex[:12].upper()}", supplier_id=supplier.id, kind=body.kind, reason=body.reason, notes=body.notes)
    db.add(row); await db.flush()
    for line in body.lines:
        if body.kind == "stock":
            if not line.purchase_receipt_line_id or line.core_obligation_id: raise HTTPException(status_code=422, detail="Stock return requires receipt line")
            origin_row = (await db.execute(
                select(PurchaseReceiptLine, PurchaseOrder)
                .join(PurchaseReceipt, PurchaseReceipt.id == PurchaseReceiptLine.purchase_receipt_id)
                .join(PurchaseOrder, PurchaseOrder.id == PurchaseReceipt.purchase_order_id)
                .where(
                    PurchaseReceiptLine.id == line.purchase_receipt_line_id,
                    PurchaseReceiptLine.tenant_id == tenant_id,
                    PurchaseOrder.tenant_id == tenant_id,
                    PurchaseOrder.deleted_at.is_(None),
                )
            )).one_or_none()
            if not origin_row: raise _not_found()
            origin, origin_po = origin_row
            if origin_po.supplier_id != supplier.id: raise _not_found()
            already_returned = int((await db.execute(
                select(func.coalesce(func.sum(VendorReturnLine.quantity), 0))
                .join(VendorReturn, VendorReturn.id == VendorReturnLine.vendor_return_id)
                .where(
                    VendorReturnLine.purchase_receipt_line_id == origin.id,
                    VendorReturnLine.tenant_id == tenant_id,
                    VendorReturn.status.in_(("shipped", "credited")),
                    VendorReturn.reverses_return_id.is_(None),
                    VendorReturn.deleted_at.is_(None),
                )
            )).scalar() or 0)
            if line.quantity > origin.quantity - already_returned:
                raise HTTPException(status_code=409, detail="Return quantity exceeds receipt origin")
            db.add(VendorReturnLine(tenant_id=tenant_id, vendor_return_id=row.id, purchase_receipt_line_id=origin.id, inventory_id=origin.inventory_id, quantity=line.quantity, expected_credit=decimal_money(line.expected_credit)))
        else:
            if not line.core_obligation_id or line.purchase_receipt_line_id: raise HTTPException(status_code=422, detail="Core return requires core obligation")
            origin = (await db.execute(select(CoreObligation).where(CoreObligation.id == line.core_obligation_id, CoreObligation.tenant_id == tenant_id, CoreObligation.deleted_at.is_(None)))).scalar_one_or_none()
            if not origin or origin.status != "on_hand" or origin.supplier_id != supplier.id or line.quantity != origin.quantity:
                raise _not_found()
            db.add(VendorReturnLine(tenant_id=tenant_id, vendor_return_id=row.id, core_obligation_id=origin.id, inventory_id=origin.inventory_id, quantity=line.quantity, expected_credit=decimal_money(line.expected_credit)))
    output = _complete_mutation(record, {"id": str(row.id), "return_number": row.return_number, "status": row.status, "version": row.version}, status_code=201)
    await db.commit(); return output


@router.post("/returns/{return_id}/submit")
async def submit_return(return_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="return_submit", route=f"POST:/returns/{return_id}/submit", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None: return replay
    row = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not row: raise _not_found()
    if row.status != "draft" or row.version != body.expected_version: raise HTTPException(status_code=409, detail="Return changed")
    row.status = "submitted"; row.submitted_at = datetime.now(timezone.utc); row.version += 1
    output = _complete_mutation(record, {"id": str(row.id), "status": row.status, "version": row.version})
    await db.commit(); return output

@router.patch("/purchase-orders/{po_id}")
async def update_purchase_order(po_id: UUID, body: POUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    po = await _po(db, tenant_id, po_id, locked=True)
    if po.status != "draft" or po.version != body.expected_version:
        raise HTTPException(status_code=409, detail="Purchase order changed")
    if body.expected_at is not None:
        po.expected_at = body.expected_at
    if body.notes is not None:
        po.notes = body.notes
    if body.lines is not None:
        old_lines = await _po_lines(db, tenant_id, po.id, locked=True)
        for line in old_lines:
            await db.delete(line)
        seen: set[UUID] = set()
        for data in body.lines:
            if data.inventory_id in seen:
                raise HTTPException(status_code=422, detail="Duplicate inventory line")
            seen.add(data.inventory_id)
            item = (await db.execute(select(Inventory).where(Inventory.id == data.inventory_id, Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None), Inventory.is_placeholder.is_(False)))).scalar_one_or_none()
            if not item:
                raise _not_found()
            source = (await db.execute(select(InventorySupplierSource).where(
                InventorySupplierSource.tenant_id == tenant_id,
                InventorySupplierSource.inventory_id == item.id,
                InventorySupplierSource.supplier_id == po.supplier_id,
                InventorySupplierSource.deleted_at.is_(None),
                InventorySupplierSource.is_active.is_(True),
            ))).scalar_one_or_none()
            db.add(PurchaseOrderLine(
                tenant_id=tenant_id,
                purchase_order_id=po.id,
                inventory_id=item.id,
                supplier_source_id=source.id if source else None,
                supplier_part_number_snapshot=source.supplier_part_number if source else None,
                sku_snapshot=item.sku,
                description_snapshot=item.name,
                unit_type_snapshot=item.unit_type,
                unit_cost_snapshot=decimal_money(data.unit_cost),
                core_charge_snapshot=decimal_money(item.core_charge or 0),
                ordered_quantity=data.ordered_quantity,
            ))
    po.version += 1
    await db.commit()
    return _serialize_po(po, await _po_lines(db, tenant_id, po.id))


@router.get("/returns/{return_id}")
async def get_return(return_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False)
    row = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)))).scalar_one_or_none()
    if not row: raise _not_found()
    lines = list((await db.execute(select(VendorReturnLine).where(VendorReturnLine.vendor_return_id == row.id, VendorReturnLine.tenant_id == tenant_id, VendorReturnLine.deleted_at.is_(None)).order_by(VendorReturnLine.id))).scalars().all())
    inventory_ids = {line.inventory_id for line in lines}
    inventories = {item.id: item for item in (await db.execute(select(Inventory).where(
        Inventory.tenant_id == tenant_id, Inventory.id.in_(inventory_ids), Inventory.deleted_at.is_(None),
    ))).scalars().all()} if inventory_ids else {}
    return {
        "id": str(row.id), "return_number": row.return_number, "supplier_id": str(row.supplier_id),
        "supplier": _supplier_summary(await _tenant_supplier(db, tenant_id, row.supplier_id)),
        "kind": row.kind, "status": row.status, "version": row.version, "reason": row.reason,
        "notes": row.notes, "reverses_return_id": str(row.reverses_return_id) if row.reverses_return_id else None,
        "lines": [{
            "id": str(line.id), "inventory_id": str(line.inventory_id),
            "inventory": _inventory_summary(inventories.get(line.inventory_id)), "quantity": line.quantity,
            "expected_credit": str(line.expected_credit),
            "actual_credit": str(line.actual_credit) if line.actual_credit is not None else None,
            "source": ({"type": "purchase_receipt_line", "id": str(line.purchase_receipt_line_id)}
                       if line.purchase_receipt_line_id else
                       {"type": "core_obligation", "id": str(line.core_obligation_id)}),
        } for line in lines],
    }


@router.patch("/returns/{return_id}")
async def update_return(return_id: UUID, body: ReturnUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    row = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not row: raise _not_found()
    if row.status != "draft" or row.version != body.expected_version: raise HTTPException(status_code=409, detail="Return changed")
    row.notes = body.notes; row.version += 1
    await db.commit(); return {"id": str(row.id), "status": row.status, "version": row.version}


@router.post("/returns/{return_id}/ship")
async def ship_return(return_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="return_ship", route=f"POST:/returns/{return_id}/ship", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None: return replay
    row = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not row: raise _not_found()
    if row.status != "submitted" or row.version != body.expected_version: raise HTTPException(status_code=409, detail="Return changed")
    lines = (await db.execute(select(VendorReturnLine).where(VendorReturnLine.vendor_return_id == row.id, VendorReturnLine.tenant_id == tenant_id, VendorReturnLine.deleted_at.is_(None)).order_by(VendorReturnLine.inventory_id).with_for_update())).scalars().all()
    for line in lines:
        item = (await db.execute(select(Inventory).where(Inventory.id == line.inventory_id, Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
        if not item: raise _not_found()
        if row.kind == "stock":
            await apply_inventory_movement(db, item=item, quantity_delta=-line.quantity, movement_type="vendor_return", actor=current_user, source_type="vendor_return", source_id=row.id, reason_code=row.reason, idempotency_key=f"{idempotency_key}:{line.id}")
            line.stock_value_snapshot = decimal_money(Decimal(item.cost) * line.quantity)
        else:
            core = (await db.execute(select(CoreObligation).where(CoreObligation.id == line.core_obligation_id, CoreObligation.tenant_id == tenant_id, CoreObligation.status == "on_hand", CoreObligation.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
            if not core or line.quantity != core.quantity: raise HTTPException(status_code=409, detail="Core obligation changed")
            core.status = "returned"; core.version += 1
            before = int((await db.execute(select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(InventoryMovement.tenant_id == tenant_id, InventoryMovement.inventory_id == item.id, InventoryMovement.bucket == "core_on_hand"))).scalar() or 0)
            db.add(InventoryMovement(tenant_id=tenant_id, inventory_id=item.id, bucket="core_on_hand", movement_type="core_return", quantity_delta=-line.quantity, balance_before=before, balance_after=before-line.quantity, unit_cost_snapshot=core.unit_core_value_snapshot, wac_before=Decimal(item.cost), wac_after=Decimal(item.cost), source_type="vendor_return", source_id=row.id, actor_user_id=current_user.id, actor_display_name_snapshot=f"{current_user.first_name} {current_user.last_name}".strip(), reason_code=row.reason, idempotency_key=f"{idempotency_key}:{line.id}"))
            item.stock_version = int(item.stock_version or 0) + 1
    row.status = "shipped"; row.shipped_at = datetime.now(timezone.utc); row.version += 1
    output = _complete_mutation(record, {"id": str(row.id), "status": row.status, "version": row.version})
    await db.commit(); return output


@router.post("/returns/{return_id}/credit")
async def credit_return(return_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="return_credit", route=f"POST:/returns/{return_id}/credit", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None: return replay
    row = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not row: raise _not_found()
    if row.status != "shipped" or row.version != body.expected_version: raise HTTPException(status_code=409, detail="Return changed")
    row.status = "credited"; row.credited_at = datetime.now(timezone.utc); row.version += 1
    output = _complete_mutation(record, {"id": str(row.id), "status": row.status, "version": row.version})
    await db.commit(); return output


@router.post("/returns/{return_id}/cancel")
async def cancel_return(return_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="return_cancel", route=f"POST:/returns/{return_id}/cancel", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None: return replay
    row = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not row: raise _not_found()
    if row.status not in {"draft", "submitted"} or row.version != body.expected_version: raise HTTPException(status_code=409, detail="Return changed")
    row.status = "cancelled"; row.version += 1
    output = _complete_mutation(record, {"id": str(row.id), "status": row.status, "version": row.version})
    await db.commit(); return output


@router.post("/returns/{return_id}/reverse", status_code=status.HTTP_201_CREATED)
async def reverse_return(return_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    replay, record = await _start_mutation(db, tenant_id=tenant_id, user=current_user, family="return_reverse", route=f"POST:/returns/{return_id}/reverse", idempotency_key=idempotency_key, payload=body.model_dump(mode="json"))
    if replay is not None: return replay
    original = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not original: raise _not_found()
    if original.status not in {"shipped", "credited"} or original.version != body.expected_version or not body.reason: raise HTTPException(status_code=409, detail="Return cannot be reversed")
    existing = (await db.execute(select(VendorReturn).where(VendorReturn.reverses_return_id == original.id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)))).scalar_one_or_none()
    if existing: raise HTTPException(status_code=409, detail="Return already reversed")
    reversal = VendorReturn(tenant_id=tenant_id, return_number=f"RET-REV-{uuid4().hex[:10].upper()}", supplier_id=original.supplier_id, kind=original.kind, status="credited", version=1, reason=body.reason, notes="Reversal", reverses_return_id=original.id, shipped_at=datetime.now(timezone.utc), credited_at=datetime.now(timezone.utc))
    db.add(reversal); await db.flush()
    lines = (await db.execute(select(VendorReturnLine).where(VendorReturnLine.vendor_return_id == original.id, VendorReturnLine.tenant_id == tenant_id, VendorReturnLine.deleted_at.is_(None)).order_by(VendorReturnLine.inventory_id).with_for_update())).scalars().all()
    for line in lines:
        item = (await db.execute(select(Inventory).where(Inventory.id == line.inventory_id, Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
        if not item: raise _not_found()
        if original.kind == "stock":
            await apply_inventory_movement(db, item=item, quantity_delta=line.quantity, movement_type="vendor_return_reversal", actor=current_user, source_type="vendor_return", source_id=reversal.id, destination_type="vendor_return", destination_id=original.id, reason_code=body.reason, idempotency_key=f"{idempotency_key}:{line.id}")
        else:
            core = (await db.execute(select(CoreObligation).where(CoreObligation.id == line.core_obligation_id, CoreObligation.tenant_id == tenant_id, CoreObligation.status == "returned", CoreObligation.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
            if not core: raise HTTPException(status_code=409, detail="Core obligation changed")
            core.status = "on_hand"; core.version += 1
            before = int((await db.execute(select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.inventory_id == item.id,
                InventoryMovement.bucket == "core_on_hand",
            ))).scalar() or 0)
            item.stock_version = int(item.stock_version or 0) + 1
            db.add(InventoryMovement(
                tenant_id=tenant_id, inventory_id=item.id, bucket="core_on_hand",
                movement_type="core_return_reversal", quantity_delta=line.quantity,
                balance_before=before, balance_after=before + line.quantity,
                unit_cost_snapshot=core.unit_core_value_snapshot,
                wac_before=Decimal(item.cost), wac_after=Decimal(item.cost),
                source_type="vendor_return", source_id=reversal.id,
                destination_type="vendor_return", destination_id=original.id,
                actor_user_id=current_user.id,
                actor_display_name_snapshot=f"{current_user.first_name} {current_user.last_name}".strip(),
                reason_code=body.reason, idempotency_key=f"{idempotency_key}:{line.id}",
            ))
        db.add(VendorReturnLine(tenant_id=tenant_id, vendor_return_id=reversal.id, purchase_receipt_line_id=line.purchase_receipt_line_id, core_obligation_id=line.core_obligation_id, inventory_id=line.inventory_id, quantity=line.quantity, expected_credit=line.expected_credit, stock_value_snapshot=line.stock_value_snapshot))
    output = _complete_mutation(record, {"id": str(reversal.id), "return_number": reversal.return_number, "status": reversal.status, "reverses_return_id": str(original.id)}, status_code=201)
    await db.commit(); return output
