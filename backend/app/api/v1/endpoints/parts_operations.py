"""DB-038 tenant-safe purchasing, immutable activity, returns, and core custody."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.parts_operations import (
    CoreObligation, InventoryCategory, InventoryMovement, PurchaseOrder,
    PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine, VendorReturn,
    VendorReturnLine,
)
from app.db.models.supplier import Supplier
from app.db.models.user import User
from app.services.parts_operations_service import (
    apply_inventory_movement, begin_idempotency, canonical_fingerprint,
    complete_idempotency, decimal_money, find_idempotent_response,
    normalize_name, receipt_wac, require_parts_operations_enabled,
    require_parts_role, validate_idempotency_key,
)

router = APIRouter()


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


def _serialize_movement(row: InventoryMovement) -> dict:
    return {"id": str(row.id), "inventory_id": str(row.inventory_id), "bucket": row.bucket,
            "movement_type": row.movement_type, "quantity_delta": row.quantity_delta,
            "balance_before": row.balance_before, "balance_after": row.balance_after,
            "wac_before": str(row.wac_before) if row.wac_before is not None else None,
            "wac_after": str(row.wac_after) if row.wac_after is not None else None,
            "source_type": row.source_type, "source_id": str(row.source_id) if row.source_id else None,
            "occurred_at": row.occurred_at.isoformat()}


def _serialize_po(po: PurchaseOrder, lines: list[PurchaseOrderLine]) -> dict:
    return {"id": str(po.id), "po_number": po.po_number, "supplier_id": str(po.supplier_id),
            "status": po.status, "version": po.version, "expected_at": po.expected_at.isoformat() if po.expected_at else None,
            "notes": po.notes, "lines": [{"id": str(line.id), "inventory_id": str(line.inventory_id),
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
    low_stock = (await db.execute(select(func.count(Inventory.id)).where(Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None), Inventory.stock_quantity <= Inventory.reorder_level))).scalar() or 0
    open_pos = (await db.execute(select(func.count(PurchaseOrder.id)).where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.deleted_at.is_(None), PurchaseOrder.status.in_(("draft", "submitted", "partially_received"))))).scalar() or 0
    return {"low_stock_count": low_stock, "open_purchase_order_count": open_pos}


@router.get("/activity")
async def activity(inventory_id: Optional[UUID] = None, skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False)
    if not 0 <= skip or not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="Invalid pagination")
    stmt = select(InventoryMovement).where(InventoryMovement.tenant_id == tenant_id)
    if inventory_id:
        stmt = stmt.where(InventoryMovement.inventory_id == inventory_id)
    rows = (await db.execute(stmt.order_by(InventoryMovement.occurred_at.desc(), InventoryMovement.id.desc()).offset(skip).limit(limit))).scalars().all()
    return [_serialize_movement(row) for row in rows]


@router.get("/demand")
async def demand(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False)
    items = (await db.execute(select(Inventory).where(Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None)).order_by(Inventory.name))).scalars().all()
    result = []
    for item in items:
        shortages = (await db.execute(select(PartsUsage).where(PartsUsage.tenant_id == tenant_id, PartsUsage.inventory_id == item.id, PartsUsage.deleted_at.is_(None), PartsUsage.stock_shortage_override.is_(True)))).scalars().all()
        repair_shortage = sum(max(0, int(__import__('math').ceil(line.quantity)) - int(line.stock_reserved_packages or 0)) for line in shortages)
        shelf = max(int(item.reorder_level or 0) - int(item.stock_quantity or 0), 0)
        open_supply = int(item.on_order_quantity or 0)
        result.append({"inventory_id": str(item.id), "sku": item.sku, "name": item.name, "unit_type": item.unit_type,
                       "stock_quantity": item.stock_quantity, "reorder_level": item.reorder_level,
                       "repair_shortage_packages": repair_shortage, "shelf_replenishment_packages": shelf,
                       "open_supply_packages": open_supply, "recommended_order_packages": max(repair_shortage + shelf - open_supply, 0),
                       "sources": []})
    return result


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False)
    rows = (await db.execute(select(InventoryCategory).where(InventoryCategory.tenant_id == tenant_id, InventoryCategory.deleted_at.is_(None)).order_by(InventoryCategory.name))).scalars().all()
    return [{"id": str(row.id), "name": row.name, "normalized_name": row.normalized_name, "description": row.description, "is_active": row.is_active} for row in rows]


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
async def list_purchase_orders(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False)
    rows = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.deleted_at.is_(None)).order_by(PurchaseOrder.created_at.desc()))).scalars().all()
    return [{"id": str(row.id), "po_number": row.po_number, "supplier_id": str(row.supplier_id), "status": row.status, "version": row.version} for row in rows]


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
        line = PurchaseOrderLine(tenant_id=tenant_id, purchase_order_id=po.id, inventory_id=item.id, sku_snapshot=item.sku, description_snapshot=item.name, unit_type_snapshot=item.unit_type, unit_cost_snapshot=decimal_money(data.unit_cost), core_charge_snapshot=decimal_money(item.core_charge or 0), ordered_quantity=data.ordered_quantity)
        db.add(line); lines.append(line)
    record = begin_idempotency(tenant_id=tenant_id, family="po_create", key=key, fingerprint=fingerprint); db.add(record)
    await db.flush(); body_out = _serialize_po(po, lines); complete_idempotency(record, status_code=201, body=body_out)
    await db.commit(); return body_out


@router.get("/purchase-orders/{po_id}")
async def get_purchase_order(po_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False); po = await _po(db, tenant_id, po_id)
    return _serialize_po(po, await _po_lines(db, tenant_id, po.id))


@router.post("/purchase-orders/{po_id}/submit")
async def submit_purchase_order(po_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True); validate_idempotency_key(idempotency_key)
    po = await _po(db, tenant_id, po_id, locked=True)
    if po.version != body.expected_version or po.status != "draft": raise HTTPException(status_code=409, detail="Purchase order changed")
    if not await _po_lines(db, tenant_id, po_id): raise HTTPException(status_code=409, detail="Purchase order has no lines")
    po.status = "submitted"; po.ordered_at = datetime.now(timezone.utc); po.submitted_by_user_id = current_user.id; po.version += 1
    await db.commit(); return _serialize_po(po, await _po_lines(db, tenant_id, po_id))


@router.post("/purchase-orders/{po_id}/cancel")
async def cancel_purchase_order(po_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True); validate_idempotency_key(idempotency_key)
    po = await _po(db, tenant_id, po_id, locked=True)
    if po.version != body.expected_version or po.status not in {"draft", "submitted"}: raise HTTPException(status_code=409, detail="Purchase order changed")
    if (await _po_lines(db, tenant_id, po_id)).__len__() and any(line.received_quantity for line in await _po_lines(db, tenant_id, po_id)): raise HTTPException(status_code=409, detail="Purchase order has receipts")
    po.status = "cancelled"; po.notes = body.reason or po.notes; po.version += 1
    await db.commit(); return _serialize_po(po, await _po_lines(db, tenant_id, po_id))


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
        db.add(PurchaseReceiptLine(tenant_id=tenant_id, purchase_receipt_id=receipt.id, purchase_order_line_id=line.id, inventory_id=item.id, quantity=input_line.quantity, unit_cost=decimal_money(input_line.unit_cost), wac_before=old_wac, wac_after=wac, balance_before=before, balance_after=before + input_line.quantity))
        output.append({"inventory_id": str(item.id), "received_quantity": input_line.quantity, "remaining_quantity": line.ordered_quantity - line.received_quantity, "balance_before": before, "balance_after": before + input_line.quantity, "wac_before": str(old_wac), "wac_after": str(wac)})
    po.status = "received" if all(line.received_quantity == line.ordered_quantity for line in lines.values()) else "partially_received"; po.version += 1
    response = {"receipt_id": str(receipt.id), "purchase_order_id": str(po.id), "purchase_order_status": po.status, "version": po.version, "lines": output}
    record = begin_idempotency(tenant_id=tenant_id, family="po_receipt", key=key, fingerprint=fingerprint); db.add(record); complete_idempotency(record, status_code=201, body=response)
    await db.commit(); return response


@router.get("/cores")
async def list_cores(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False)
    rows = (await db.execute(select(CoreObligation).where(CoreObligation.tenant_id == tenant_id, CoreObligation.deleted_at.is_(None)).order_by(CoreObligation.created_at.desc()))).scalars().all()
    return [{"id": str(row.id), "inventory_id": str(row.inventory_id), "supplier_id": str(row.supplier_id) if row.supplier_id else None, "quantity": row.quantity, "status": row.status, "version": row.version} for row in rows]


@router.post("/cores/{obligation_id}/recover")
async def recover_core(obligation_id: UUID, body: VersionCommand, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    core = (await db.execute(select(CoreObligation).where(CoreObligation.id == obligation_id, CoreObligation.tenant_id == tenant_id, CoreObligation.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not core: raise _not_found()
    if core.status != "expected" or core.version != body.expected_version: raise HTTPException(status_code=409, detail="Core obligation changed")
    item = (await db.execute(select(Inventory).where(Inventory.id == core.inventory_id, Inventory.tenant_id == tenant_id, Inventory.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not item: raise _not_found()
    before = int((await db.execute(select(func.coalesce(func.sum(InventoryMovement.quantity_delta), 0)).where(InventoryMovement.tenant_id == tenant_id, InventoryMovement.inventory_id == item.id, InventoryMovement.bucket == "core_on_hand"))).scalar() or 0)
    core.status = "on_hand"; core.version += 1; item.stock_version = int(item.stock_version or 0) + 1
    db.add(InventoryMovement(tenant_id=tenant_id, inventory_id=item.id, bucket="core_on_hand", movement_type="core_recovery", quantity_delta=core.quantity, balance_before=before, balance_after=before + core.quantity, unit_cost_snapshot=core.unit_core_value_snapshot, wac_before=Decimal(item.cost), wac_after=Decimal(item.cost), source_type="core_obligation", source_id=core.id, actor_user_id=current_user.id, actor_display_name_snapshot=f"{current_user.first_name} {current_user.last_name}".strip(), reason_code="core_recovery"))
    await db.commit(); return {"id": str(core.id), "status": core.status, "version": core.version}


@router.post("/cores/{obligation_id}/waive")
async def waive_core(obligation_id: UUID, body: VersionCommand, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    core = (await db.execute(select(CoreObligation).where(CoreObligation.id == obligation_id, CoreObligation.tenant_id == tenant_id, CoreObligation.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not core: raise _not_found()
    if core.status not in {"expected", "on_hand"} or core.version != body.expected_version: raise HTTPException(status_code=409, detail="Core obligation changed")
    if not body.reason: raise HTTPException(status_code=422, detail="Waiver reason is required")
    core.status = "waived"; core.reason = body.reason; core.version += 1
    await db.commit(); return {"id": str(core.id), "status": core.status, "version": core.version}


@router.get("/returns")
async def list_returns(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False)
    rows = (await db.execute(select(VendorReturn).where(VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)).order_by(VendorReturn.created_at.desc()))).scalars().all()
    return [{"id": str(row.id), "return_number": row.return_number, "supplier_id": str(row.supplier_id), "kind": row.kind, "status": row.status, "version": row.version} for row in rows]


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
async def submit_return(return_id: UUID, body: VersionCommand, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    row = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not row: raise _not_found()
    if row.status != "draft" or row.version != body.expected_version: raise HTTPException(status_code=409, detail="Return changed")
    row.status = "submitted"; row.submitted_at = datetime.now(timezone.utc); row.version += 1
    await db.commit(); return {"id": str(row.id), "status": row.status, "version": row.version}

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
            db.add(PurchaseOrderLine(tenant_id=tenant_id, purchase_order_id=po.id, inventory_id=item.id, sku_snapshot=item.sku, description_snapshot=item.name, unit_type_snapshot=item.unit_type, unit_cost_snapshot=decimal_money(data.unit_cost), core_charge_snapshot=decimal_money(item.core_charge or 0), ordered_quantity=data.ordered_quantity))
    po.version += 1
    await db.commit()
    return _serialize_po(po, await _po_lines(db, tenant_id, po.id))


@router.get("/returns/{return_id}")
async def get_return(return_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=False)
    row = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)))).scalar_one_or_none()
    if not row: raise _not_found()
    lines = (await db.execute(select(VendorReturnLine).where(VendorReturnLine.vendor_return_id == row.id, VendorReturnLine.tenant_id == tenant_id, VendorReturnLine.deleted_at.is_(None)))).scalars().all()
    return {"id": str(row.id), "return_number": row.return_number, "supplier_id": str(row.supplier_id), "kind": row.kind, "status": row.status, "version": row.version, "reason": row.reason, "notes": row.notes, "lines": [{"id": str(line.id), "inventory_id": str(line.inventory_id), "quantity": line.quantity, "expected_credit": str(line.expected_credit), "actual_credit": str(line.actual_credit) if line.actual_credit is not None else None} for line in lines]}


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
    tenant_id = await _tenant(db, current_user, mutate=True); validate_idempotency_key(idempotency_key)
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
    await db.commit(); return {"id": str(row.id), "status": row.status, "version": row.version}


@router.post("/returns/{return_id}/credit")
async def credit_return(return_id: UUID, body: VersionCommand, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    row = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not row: raise _not_found()
    if row.status != "shipped" or row.version != body.expected_version: raise HTTPException(status_code=409, detail="Return changed")
    row.status = "credited"; row.credited_at = datetime.now(timezone.utc); row.version += 1
    await db.commit(); return {"id": str(row.id), "status": row.status, "version": row.version}


@router.post("/returns/{return_id}/cancel")
async def cancel_return(return_id: UUID, body: VersionCommand, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True)
    row = (await db.execute(select(VendorReturn).where(VendorReturn.id == return_id, VendorReturn.tenant_id == tenant_id, VendorReturn.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if not row: raise _not_found()
    if row.status not in {"draft", "submitted"} or row.version != body.expected_version: raise HTTPException(status_code=409, detail="Return changed")
    row.status = "cancelled"; row.version += 1
    await db.commit(); return {"id": str(row.id), "status": row.status, "version": row.version}


@router.post("/returns/{return_id}/reverse", status_code=status.HTTP_201_CREATED)
async def reverse_return(return_id: UUID, body: VersionCommand, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    tenant_id = await _tenant(db, current_user, mutate=True); validate_idempotency_key(idempotency_key)
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
    await db.commit(); return {"id": str(reversal.id), "return_number": reversal.return_number, "status": reversal.status, "reverses_return_id": str(original.id)}
