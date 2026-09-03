from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.core.search import build_search
from pydantic import BaseModel
from decimal import Decimal

from app.core.config import settings
from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.default_catalog import DEFAULT_INVENTORY
from app.core.image_validation import read_validated_image
from app.db.models.user import User, UserRole
from app.db.models.inventory import Inventory
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.description_library import DescriptionLibraryEntry
from app.services.cloudinary_service import (
    is_cloudinary_configured,
    upload_inventory_photo,
    delete_cloudinary_image,
)
from app.tasks.description_library_refresh import process_on_demand_library_regenerate
from app.schemas.typeahead import InventoryTypeaheadResponse
from app.services.parts_operations_service import apply_inventory_movement
from app.services.part_activity_service import append_part_activity

router = APIRouter()


CATALOG_ACTIVITY_TYPES = {
    "sku": "part.identity_changed",
    "name": "part.identity_changed",
    "description": "part.identity_changed",
    "category": "part.category_changed",
    "location": "part.location_changed",
    "unit_type": "part.unit_changed",
    "reorder_level": "part.reorder_level_changed",
    "cost": "part.cost_changed",
    "selling_price": "part.selling_price_changed",
    "core_charge": "part.core_charge_changed",
    "supplier_name": "part.supplier_text_changed",
    "supplier_contact": "part.supplier_text_changed",
    "is_placeholder": "part.identity_changed",
}


async def _append_catalog_changes(
    db: AsyncSession, *, item: Inventory, actor: User,
    before: dict[str, object], updates: dict[str, object], correlation_id: UUID,
) -> None:
    for field in sorted(updates):
        if field not in CATALOG_ACTIVITY_TYPES or before.get(field) == updates[field]:
            continue
        money_snapshot = None
        if field in {"cost", "selling_price", "core_charge"}:
            money_snapshot = {"currency": "USD", field: str(updates[field])}
        await append_part_activity(
            db, tenant_id=item.tenant_id, inventory_id=item.id,
            category="catalog", event_type=CATALOG_ACTIVITY_TYPES[field],
            idempotency_key=f"inventory:{item.id}:update:{correlation_id}:{field}:v1",
            actor=actor, correlation_id=correlation_id,
            source_type="inventory", source_id=item.id, source_number=item.sku,
            before={field: before.get(field)}, after={field: updates[field]},
            money=money_snapshot,
        )


class InventoryResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    description: Optional[str]
    category: Optional[str]
    stock_quantity: int
    on_order_quantity: int
    reorder_level: int
    cost: Decimal
    selling_price: Decimal
    core_charge: Decimal = Decimal("0.00")
    # "each" (default) for discrete parts, or a fluid unit ("gallon", "quart",
    # "liter") so the Price Builder can offer 0.25-increment quantities.
    unit_type: str
    supplier_name: Optional[str]
    supplier_contact: Optional[str]
    image_url: Optional[str] = None
    location: Optional[str] = None
    is_placeholder: bool = False
    ets_retired_at: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


def _inventory_response(item: Inventory) -> InventoryResponse:
    return InventoryResponse(
        id=item.id,
        tenant_id=item.tenant_id,
        sku=item.sku,
        name=item.name,
        description=item.description,
        category=item.category,
        stock_quantity=item.stock_quantity,
        on_order_quantity=item.on_order_quantity,
        reorder_level=item.reorder_level,
        cost=item.cost,
        selling_price=item.selling_price,
        core_charge=item.core_charge,
        unit_type=item.unit_type,
        supplier_name=item.supplier_name,
        supplier_contact=item.supplier_contact,
        image_url=item.image_url,
        location=item.location,
        is_placeholder=item.is_placeholder,
        ets_retired_at=item.ets_retired_at.isoformat() if item.ets_retired_at else None,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


async def _resolve_typeahead_tenant_id(current_user: User, db: AsyncSession) -> Optional[UUID]:
    """Resolve a customer user's current tenant without exposing every catalog."""
    if current_user.role != UserRole.CUSTOMER:
        return current_user.tenant_id
    if not current_user.customer_id:
        return None
    result = await db.execute(
        select(Customer.tenant_id).where(
            Customer.id == current_user.customer_id,
            Customer.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


class InventoryCreate(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    stock_quantity: int = 0
    on_order_quantity: int = 0
    reorder_level: int = 0
    cost: Decimal
    selling_price: Decimal
    core_charge: Decimal = Decimal("0.00")
    unit_type: str = "each"
    supplier_name: Optional[str] = None
    supplier_contact: Optional[str] = None
    location: Optional[str] = None


class InventoryUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    stock_quantity: Optional[int] = None
    on_order_quantity: Optional[int] = None
    reorder_level: Optional[int] = None
    cost: Optional[Decimal] = None
    selling_price: Optional[Decimal] = None
    core_charge: Optional[Decimal] = None
    unit_type: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_contact: Optional[str] = None
    location: Optional[str] = None
    # Setting this false promotes an ad-hoc placeholder into a normally
    # stocked part, keeping the repair-order history already attached to it.
    is_placeholder: Optional[bool] = None
    stock_adjustment_reason: Optional[str] = None


class ReceiveShipmentRequest(BaseModel):
    quantity: int


def require_admin():
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
        return current_user
    return role_checker


class InventoryLibrarySuggestion(BaseModel):
    text: str
    times_used: int


class InventoryLibraryRegenerateResponse(BaseModel):
    queued: bool = True


async def _inventory_library_suggestions(db: AsyncSession, tenant_id, library_type: str, term: str, limit: int):
    result = await db.execute(
        select(
            DescriptionLibraryEntry.canonical_text,
            DescriptionLibraryEntry.source_count,
            func.word_similarity(term, DescriptionLibraryEntry.canonical_text).label("score"),
        )
        .where(
            DescriptionLibraryEntry.tenant_id == tenant_id,
            DescriptionLibraryEntry.library_type == library_type,
            func.word_similarity(term, DescriptionLibraryEntry.canonical_text) > 0.2,
        )
        .order_by(
            func.word_similarity(term, DescriptionLibraryEntry.canonical_text).desc(),
            DescriptionLibraryEntry.source_count.desc(),
        )
        .limit(limit)
    )
    return result.all()


@router.get("/name-suggestions", response_model=List[InventoryLibrarySuggestion])
async def get_inventory_name_suggestions(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Autocomplete for the new-part Name field, drawn from this tenant's
    AI-canonicalized part-name library (see
    app/services/description_library_service.py). A shop with no library yet
    (never regenerated) simply gets no suggestions here.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    term = q.strip()
    if not term:
        return []
    rows = await _inventory_library_suggestions(db, current_user.tenant_id, "part_name", term, limit)
    return [InventoryLibrarySuggestion(text=text, times_used=count) for text, count, _score in rows]


@router.get("/category-suggestions", response_model=List[InventoryLibrarySuggestion])
async def get_inventory_category_suggestions(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Autocomplete for the Category field, drawn from this tenant's
    AI-canonicalized part-category library.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    term = q.strip()
    if not term:
        return []
    rows = await _inventory_library_suggestions(db, current_user.tenant_id, "part_category", term, limit)
    return [InventoryLibrarySuggestion(text=text, times_used=count) for text, count, _score in rows]


@router.get("/description-suggestions", response_model=List[InventoryLibrarySuggestion])
async def get_inventory_description_suggestions(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Autocomplete for the part Description field, drawn from this tenant's
    AI-canonicalized part-description library.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    term = q.strip()
    if not term:
        return []
    rows = await _inventory_library_suggestions(db, current_user.tenant_id, "part_description", term, limit)
    return [InventoryLibrarySuggestion(text=text, times_used=count) for text, count, _score in rows]


@router.post(
    "/library/regenerate",
    response_model=InventoryLibraryRegenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_inventory_library_endpoint(
    current_user: User = Depends(require_admin()),
):
    """Owner/admin-triggered rebuild of this tenant's canonical part-name,
    part-category, and part-description libraries from the current Inventory
    catalog. Runs as a background Celery task — enqueues and returns
    immediately rather than blocking on the multi-minute Claude call.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ANTHROPIC_API_KEY is not configured")

    process_on_demand_library_regenerate.delay(str(current_user.tenant_id), "inventory")
    return InventoryLibraryRegenerateResponse()


@router.get("", response_model=List[InventoryResponse])
async def list_inventory(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    category: Optional[str] = None,
    low_stock: Optional[bool] = None,
    search: Optional[str] = None,
):
    query = select(Inventory).where(Inventory.deleted_at.is_(None))
    count_query = select(func.count(Inventory.id)).where(Inventory.deleted_at.is_(None))

    if current_user.tenant_id:
        query = query.where(Inventory.tenant_id == current_user.tenant_id)
        count_query = count_query.where(Inventory.tenant_id == current_user.tenant_id)

    if category:
        query = query.where(Inventory.category == category)
        count_query = count_query.where(Inventory.category == category)

    order_by = [Inventory.name]
    if search and search.strip():
        search_filter, relevance = build_search(
            search,
            primary=[Inventory.name, Inventory.sku],
            squashed=[Inventory.name, Inventory.sku],
            secondary=[Inventory.description, Inventory.location, Inventory.supplier_name],
            similarity=[Inventory.name],
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
        order_by = [relevance.desc(), Inventory.name, Inventory.id]

    # Keep low-stock semantics while making pagination consistent.
    if low_stock:
        low_stock_filter = Inventory.needs_restock()
        query = query.where(low_stock_filter)
        count_query = count_query.where(low_stock_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(query.order_by(*order_by).offset(skip).limit(limit))
    items = result.scalars().all()

    serialized_items = [_inventory_response(item) for item in items]
    return paginated_or_list(serialized_items, total, skip, limit, paginated)


class InventorySyncStatusResponse(BaseModel):
    ets_last_synced_at: Optional[datetime]


@router.get("/sync-status", response_model=InventorySyncStatusResponse)
async def get_inventory_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """When the Easy Truck Shop importer (backend/scripts/easytruck_sync) last
    committed data for this tenant. Set only by that script, never by normal
    record edits."""
    if not current_user.tenant_id:
        return InventorySyncStatusResponse(ets_last_synced_at=None)
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    return InventorySyncStatusResponse(
        ets_last_synced_at=tenant.ets_last_synced_at if tenant else None
    )


@router.get("/typeahead", response_model=List[InventoryTypeaheadResponse])
async def inventory_typeahead(
    q: Optional[str] = Query(None, max_length=100, description="Match an in-stock part by name, SKU, category, or location"),
    limit: int = Query(20, ge=1, le=50),
    in_stock: bool = Query(True, description="Limit the repair-order picker to parts that can be added"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return a small, capped inventory picker payload for adding RO parts."""
    tenant_id = await _resolve_typeahead_tenant_id(current_user, db)
    if not tenant_id:
        return []

    filters = [
        Inventory.tenant_id == tenant_id,
        Inventory.deleted_at.is_(None),
    ]
    if in_stock:
        filters.append(Inventory.stock_quantity > 0)

    term = (q or "").strip()
    if term:
        pattern = f"%{term}%"
        filters.append(
            or_(
                Inventory.name.ilike(pattern),
                Inventory.sku.ilike(pattern),
                Inventory.category.ilike(pattern),
                Inventory.description.ilike(pattern),
                Inventory.location.ilike(pattern),
            )
        )

    # Rank what the picker can actually use before ranking it alphabetically.
    # A catalogue this size holds hundreds of zero-stock placeholder rows
    # imported from Easy Truck Shop, and under a plain A-Z sort they filled the
    # whole limit: searching "tire" returned six spellings of an unstocked
    # "Brand new tire" while the stocked part sat past the cut. Sort stocked
    # parts first, then real catalogue rows over placeholders.
    result = await db.execute(
        select(Inventory)
        .where(*filters)
        .order_by(
            (Inventory.stock_quantity > 0).desc(),
            Inventory.is_placeholder.asc(),
            func.lower(Inventory.name),
            Inventory.id,
        )
        .limit(limit)
    )
    return [
        InventoryTypeaheadResponse(
            id=item.id,
            sku=item.sku,
            name=item.name,
            stock_quantity=item.stock_quantity,
            on_order_quantity=item.on_order_quantity,
            unit_type=item.unit_type,
            cost=item.cost,
            selling_price=item.selling_price,
        )
        for item in result.scalars().all()
    ]


@router.post("", response_model=InventoryResponse, status_code=status.HTTP_201_CREATED)
async def create_inventory_item(
    data: InventoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    # Parts inventory is always tenant-owned; a tenantless administrative
    # principal must never create an unscoped stock record.
    if not current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if data.stock_quantity < 0:
        raise HTTPException(status_code=422, detail="Stock quantity cannot be negative")

    values = data.model_dump()
    opening_quantity = values.pop("stock_quantity")
    item = Inventory(tenant_id=current_user.tenant_id, stock_quantity=0, **values)
    db.add(item)
    await db.flush()
    await append_part_activity(
        db, tenant_id=item.tenant_id, inventory_id=item.id,
        category="catalog", event_type="part.created",
        idempotency_key=f"inventory:{item.id}:created:v1", actor=current_user,
        correlation_id=item.id, source_type="inventory", source_id=item.id,
        source_number=item.sku,
        after={
            "sku": item.sku, "name": item.name, "description": item.description,
            "category": item.category, "location": item.location,
            "unit_type": item.unit_type, "reorder_level": item.reorder_level,
            "cost": item.cost, "selling_price": item.selling_price,
        },
        money={"currency": "USD", "cost": str(item.cost), "selling_price": str(item.selling_price)},
    )
    if opening_quantity:
        await apply_inventory_movement(
            db, item=item, quantity_delta=opening_quantity,
            movement_type="legacy_inventory_opening", actor=current_user,
            source_type="legacy_inventory_create", source_id=item.id,
            reason_code="opening_balance",
        )
    await db.commit()
    await db.refresh(item)
    return _inventory_response(item)


class PreloadInventoryResult(BaseModel):
    items_added: int


class ClearInventoryResult(BaseModel):
    items_deleted: int


@router.post("/preload", response_model=PreloadInventoryResult)
async def preload_default_inventory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """Load default inventory items for this tenant. Skips SKUs that already exist."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    tenant_id = current_user.tenant_id

    existing_skus_result = await db.execute(
        select(Inventory.sku).where(
            Inventory.tenant_id == tenant_id,
            Inventory.deleted_at.is_(None),
        )
    )
    existing_skus = {row[0] for row in existing_skus_result.all()}

    added = 0
    for item_data in DEFAULT_INVENTORY:
        if item_data["sku"] not in existing_skus:
            values = dict(item_data)
            opening_quantity = int(values.pop("stock_quantity", 0))
            item = Inventory(id=uuid4(), tenant_id=tenant_id, stock_quantity=0, **values)
            db.add(item)
            await db.flush()
            await append_part_activity(
                db, tenant_id=tenant_id, inventory_id=item.id,
                category="catalog", event_type="part.created",
                idempotency_key=f"inventory:{item.id}:preload-created:v1",
                actor=current_user, correlation_id=item.id,
                source_type="inventory", source_id=item.id, source_number=item.sku,
                after={"sku": item.sku, "name": item.name, "category": item.category,
                       "unit_type": item.unit_type, "reorder_level": item.reorder_level,
                       "cost": item.cost, "selling_price": item.selling_price},
                money={"currency": "USD", "cost": str(item.cost), "selling_price": str(item.selling_price)},
            )
            if opening_quantity:
                await apply_inventory_movement(
                    db, item=item, quantity_delta=opening_quantity,
                    movement_type="legacy_inventory_opening", actor=current_user,
                    source_type="legacy_inventory_preload", source_id=item.id,
                    reason_code="opening_balance",
                )
            added += 1

    await db.commit()
    return PreloadInventoryResult(items_added=added)


@router.post("/clear", response_model=ClearInventoryResult)
async def clear_all_inventory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """Soft-delete all inventory items for this tenant."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    tenant_id = current_user.tenant_id

    result = await db.execute(
        select(Inventory).where(
            Inventory.tenant_id == tenant_id,
            Inventory.deleted_at.is_(None),
        )
    )
    items = result.scalars().all()
    now = datetime.now(timezone.utc)
    for item in items:
        item.deleted_at = now

    await db.commit()
    return ClearInventoryResult(items_deleted=len(items))


@router.get("/{item_id}", response_model=InventoryResponse)
async def get_inventory_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    query = select(Inventory).where(
        Inventory.id == item_id,
        Inventory.deleted_at.is_(None),
        Inventory.tenant_id == current_user.tenant_id,
    )
    
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    return _inventory_response(item)


@router.put("/{item_id}", response_model=InventoryResponse)
async def update_inventory_item(
    item_id: UUID,
    data: InventoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    query = select(Inventory).where(
        Inventory.id == item_id,
        Inventory.deleted_at.is_(None),
        Inventory.tenant_id == current_user.tenant_id,
    )

    result = await db.execute(query)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    updates = data.model_dump(exclude_unset=True)
    adjustment_reason = updates.pop("stock_adjustment_reason", None)
    requested_stock = updates.pop("stock_quantity", None)
    if requested_stock is not None:
        if requested_stock < 0:
            raise HTTPException(status_code=422, detail="Stock quantity cannot be negative")
        tenant_enabled = bool(settings.PARTS_OPERATIONS_V1_ENABLED and current_user.tenant_id and (
            await db.execute(select(Tenant.parts_operations_enabled).where(Tenant.id == current_user.tenant_id))
        ).scalar_one_or_none())
        if tenant_enabled:
            if not adjustment_reason or not adjustment_reason.strip():
                raise HTTPException(status_code=422, detail="Stock adjustment reason is required")
            delta = requested_stock - int(item.stock_quantity or 0)
            if delta:
                await apply_inventory_movement(
                    db, item=item, quantity_delta=delta, movement_type="manual_adjustment",
                    actor=current_user, source_type="legacy_inventory_update", source_id=item.id,
                    reason_code="manual_adjustment", note=adjustment_reason.strip(),
                )
        else:
            delta = requested_stock - int(item.stock_quantity or 0)
            if delta:
                await apply_inventory_movement(
                    db, item=item, quantity_delta=delta, movement_type="manual_adjustment",
                    actor=current_user, source_type="legacy_inventory_update", source_id=item.id,
                    reason_code="legacy_manual_adjustment",
                    note=adjustment_reason.strip() if adjustment_reason else None,
                )
    before = {field: getattr(item, field) for field in updates}
    correlation_id = uuid4()
    for field, value in updates.items():
        setattr(item, field, value)
    await _append_catalog_changes(
        db, item=item, actor=current_user, before=before,
        updates=updates, correlation_id=correlation_id,
    )

    await db.commit()
    await db.refresh(item)

    return _inventory_response(item)


@router.post("/{item_id}/receive", response_model=InventoryResponse)
async def receive_shipment(
    item_id: UUID,
    body: ReceiveShipmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")

    if not current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    query = select(Inventory).where(
        Inventory.id == item_id,
        Inventory.tenant_id == current_user.tenant_id,
        Inventory.deleted_at.is_(None),
    ).with_for_update()

    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    await apply_inventory_movement(
        db, item=item, quantity_delta=body.quantity,
        movement_type="legacy_direct_receipt", actor=current_user,
        source_type="legacy_inventory_receive", source_id=item.id,
        reason_code="legacy_direct_receive",
    )
    item.on_order_quantity = max(0, (item.on_order_quantity or 0) - body.quantity)

    await db.commit()
    await db.refresh(item)

    return _inventory_response(item)


async def _get_owned_inventory_item(db: AsyncSession, item_id: UUID, current_user: User) -> Inventory:
    if not current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    query = select(Inventory).where(
        Inventory.id == item_id,
        Inventory.deleted_at.is_(None),
        Inventory.tenant_id == current_user.tenant_id,
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return item


@router.post("/{item_id}/photo", response_model=InventoryResponse)
async def upload_inventory_item_photo(
    item_id: UUID,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """Upload (or replace) the single reference photo for a part."""
    if not is_cloudinary_configured():
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail="Image uploads are not configured")

    item = await _get_owned_inventory_item(db, item_id, current_user)
    data_uri, _content_type = await read_validated_image(image)

    old_public_id = item.cloudinary_public_id
    try:
        image_url, public_id = await upload_inventory_photo(data_uri, str(item_id))
    except Exception:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail="Photo upload failed. Please try again.")

    old_image_url = item.image_url
    item.image_url = image_url
    item.cloudinary_public_id = public_id
    await append_part_activity(
        db, tenant_id=item.tenant_id, inventory_id=item.id,
        category="catalog", event_type="part.photo_changed",
        idempotency_key=f"inventory:{item.id}:photo:{uuid4()}:v1",
        actor=current_user, source_type="inventory", source_id=item.id,
        source_number=item.sku, before={"image_url": old_image_url},
        after={"image_url": image_url},
    )
    await db.commit()
    await db.refresh(item)

    if old_public_id:
        await delete_cloudinary_image(old_public_id)

    return _inventory_response(item)


@router.delete("/{item_id}/photo", response_model=InventoryResponse)
async def delete_inventory_item_photo(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    item = await _get_owned_inventory_item(db, item_id, current_user)

    old_public_id = item.cloudinary_public_id
    old_image_url = item.image_url
    item.image_url = None
    item.cloudinary_public_id = None
    if old_image_url:
        await append_part_activity(
            db, tenant_id=item.tenant_id, inventory_id=item.id,
            category="catalog", event_type="part.photo_changed",
            idempotency_key=f"inventory:{item.id}:photo-delete:{uuid4()}:v1",
            actor=current_user, source_type="inventory", source_id=item.id,
            source_number=item.sku, before={"image_url": old_image_url},
            after={"image_url": None},
        )
    await db.commit()
    await db.refresh(item)

    if old_public_id and is_cloudinary_configured():
        await delete_cloudinary_image(old_public_id)

    return _inventory_response(item)
