from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from decimal import Decimal

from app.core.config import settings
from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.default_catalog import DEFAULT_INVENTORY
from app.db.models.user import User, UserRole
from app.db.models.inventory import Inventory
from app.db.models.description_library import DescriptionLibraryEntry
from app.tasks.description_library_refresh import process_on_demand_library_regenerate

router = APIRouter()


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
    # "each" (default) for discrete parts, or a fluid unit ("gallon", "quart",
    # "liter") so the Price Builder can offer 0.25-increment quantities.
    unit_type: str
    supplier_name: Optional[str]
    supplier_contact: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


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
    unit_type: str = "each"
    supplier_name: Optional[str] = None
    supplier_contact: Optional[str] = None


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
    unit_type: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_contact: Optional[str] = None


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
):
    query = select(Inventory).where(Inventory.deleted_at.is_(None))
    count_query = select(func.count(Inventory.id)).where(Inventory.deleted_at.is_(None))

    if current_user.tenant_id:
        query = query.where(Inventory.tenant_id == current_user.tenant_id)
        count_query = count_query.where(Inventory.tenant_id == current_user.tenant_id)

    if category:
        query = query.where(Inventory.category == category)
        count_query = count_query.where(Inventory.category == category)

    # Keep low-stock semantics while making pagination consistent.
    if low_stock:
        low_stock_filter = Inventory.stock_quantity <= Inventory.reorder_level
        query = query.where(low_stock_filter)
        count_query = count_query.where(low_stock_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(query.order_by(Inventory.name).offset(skip).limit(limit))
    items = result.scalars().all()

    serialized_items = [
        InventoryResponse(
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
            unit_type=item.unit_type,
            supplier_name=item.supplier_name,
            supplier_contact=item.supplier_contact,
            created_at=item.created_at.isoformat(),
            updated_at=item.updated_at.isoformat(),
        )
        for item in items
    ]
    return paginated_or_list(serialized_items, total, skip, limit, paginated)


@router.post("", response_model=InventoryResponse, status_code=status.HTTP_201_CREATED)
async def create_inventory_item(
    data: InventoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    item = Inventory(
        tenant_id=current_user.tenant_id,
        **data.model_dump(),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

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
        unit_type=item.unit_type,
        supplier_name=item.supplier_name,
        supplier_contact=item.supplier_contact,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


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
            item = Inventory(id=uuid4(), tenant_id=tenant_id, **item_data)
            db.add(item)
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
    query = select(Inventory).where(
        Inventory.id == item_id,
        Inventory.deleted_at.is_(None)
    )
    
    if current_user.tenant_id:
        query = query.where(Inventory.tenant_id == current_user.tenant_id)
    
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

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
        unit_type=item.unit_type,
        supplier_name=item.supplier_name,
        supplier_contact=item.supplier_contact,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


@router.put("/{item_id}", response_model=InventoryResponse)
async def update_inventory_item(
    item_id: UUID,
    data: InventoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    query = select(Inventory).where(
        Inventory.id == item_id,
        Inventory.deleted_at.is_(None)
    )

    if current_user.tenant_id:
        query = query.where(Inventory.tenant_id == current_user.tenant_id)

    result = await db.execute(query)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)

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
        unit_type=item.unit_type,
        supplier_name=item.supplier_name,
        supplier_contact=item.supplier_contact,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


@router.post("/{item_id}/receive", response_model=InventoryResponse)
async def receive_shipment(
    item_id: UUID,
    body: ReceiveShipmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")

    query = select(Inventory).where(
        Inventory.id == item_id,
        Inventory.deleted_at.is_(None),
    )
    if current_user.tenant_id:
        query = query.where(Inventory.tenant_id == current_user.tenant_id)

    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    item.stock_quantity = (item.stock_quantity or 0) + body.quantity
    item.on_order_quantity = max(0, (item.on_order_quantity or 0) - body.quantity)

    await db.commit()
    await db.refresh(item)

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
        unit_type=item.unit_type,
        supplier_name=item.supplier_name,
        supplier_contact=item.supplier_contact,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )
