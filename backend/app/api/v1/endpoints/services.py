from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.default_catalog import DEFAULT_CATEGORIES, DEFAULT_SERVICES
from app.db.models.appointment import Appointment
from app.db.models.inventory import Inventory
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.service import Service, ServiceCategory, ServicePart
from app.db.models.description_library import DescriptionLibraryEntry
from app.core.config import settings
from app.tasks.description_library_refresh import process_on_demand_library_regenerate

router = APIRouter()


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


# Schemas
class ServiceCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int = 0
    is_pm: bool = False


class ServiceCategoryResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    icon: Optional[str]
    sort_order: int
    is_active: bool
    is_pm: bool = False

    class Config:
        from_attributes = True


class ServiceCreate(BaseModel):
    category_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    duration_minutes: int = 60
    base_price: Optional[Decimal] = None
    icon: Optional[str] = None
    sort_order: int = 0
    requires_vehicle: bool = True


class ServiceUpdate(BaseModel):
    category_id: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    base_price: Optional[Decimal] = None
    clear_base_price: bool = False
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    requires_vehicle: Optional[bool] = None


class ServicePartCreate(BaseModel):
    inventory_id: UUID
    # Decimal so a bundled fluid part (e.g. 5 gal of oil in an "Oil Change"
    # service) can be entered fractionally.
    quantity: Decimal = Decimal("1")


class ServicePartUpdate(BaseModel):
    quantity: Decimal


class ServicePartResponse(BaseModel):
    id: str
    inventory_id: str
    sku: str
    name: str
    quantity: Decimal
    unit_type: str = "each"
    unit_price: str
    line_total: str
    stock_quantity: int

    class Config:
        from_attributes = True


class ServiceResponse(BaseModel):
    id: str
    category_id: Optional[str]
    name: str
    description: Optional[str]
    duration_minutes: int
    base_price: Optional[str]
    icon: Optional[str]
    sort_order: int
    is_active: bool
    requires_vehicle: bool
    category: Optional[ServiceCategoryResponse] = None
    parts: List[ServicePartResponse] = []
    labor_cost: str
    parts_cost: str
    computed_total_price: str

    class Config:
        from_attributes = True


def require_admin():
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
        return current_user
    return role_checker


async def _resolve_tenant_id(current_user: User, db: AsyncSession) -> Optional[UUID]:
    if current_user.tenant_id:
        return current_user.tenant_id
    if current_user.customer_id:
        from app.db.models.customer import Customer
        result = await db.execute(select(Customer).where(Customer.id == current_user.customer_id))
        customer = result.scalar_one_or_none()
        if customer:
            return customer.tenant_id
    return None


async def _get_labor_rate(db: AsyncSession, tenant_id: UUID) -> Decimal:
    result = await db.execute(select(Tenant.labor_rate).where(Tenant.id == tenant_id))
    rate = result.scalar_one_or_none()
    return Decimal(str(rate)) if rate is not None else Decimal("100.00")


def _build_parts_response(service: Service) -> List[ServicePartResponse]:
    items: List[ServicePartResponse] = []
    for sp in service.service_parts:
        inv = sp.inventory_item
        if not inv or inv.deleted_at is not None:
            continue
        unit_price = Decimal(str(inv.selling_price))
        line_total = _money(unit_price * Decimal(sp.quantity))
        items.append(
            ServicePartResponse(
                id=str(sp.id),
                inventory_id=str(inv.id),
                sku=inv.sku,
                name=inv.name,
                quantity=sp.quantity,
                unit_type=inv.unit_type,
                unit_price=str(_money(unit_price)),
                line_total=str(line_total),
                stock_quantity=int(inv.stock_quantity or 0),
            )
        )
    return items


def _serialize_service(
    service: Service,
    labor_rate: Decimal,
    *,
    include_category: bool = False,
) -> ServiceResponse:
    parts = _build_parts_response(service)
    parts_cost = _money(sum((Decimal(p.line_total) for p in parts), Decimal("0.00")))
    # base_price acts as a labor-only override. When set, the service charges that flat
    # labor figure plus any bundled parts on top; when null, labor = rate × duration.
    if service.base_price is not None:
        effective_labor = _money(Decimal(str(service.base_price)))
    else:
        effective_labor = _money(labor_rate * (Decimal(service.duration_minutes) / Decimal(60)))
    computed_total = _money(effective_labor + parts_cost)

    category_resp: Optional[ServiceCategoryResponse] = None
    if include_category and service.category:
        c = service.category
        category_resp = ServiceCategoryResponse(
            id=str(c.id),
            name=c.name,
            description=c.description,
            icon=c.icon,
            sort_order=c.sort_order,
            is_active=c.is_active,
        )

    return ServiceResponse(
        id=str(service.id),
        category_id=str(service.category_id) if service.category_id else None,
        name=service.name,
        description=service.description,
        duration_minutes=service.duration_minutes,
        base_price=str(_money(Decimal(str(service.base_price)))) if service.base_price is not None else None,
        icon=service.icon,
        sort_order=service.sort_order,
        is_active=service.is_active,
        requires_vehicle=service.requires_vehicle,
        category=category_resp,
        parts=parts,
        labor_cost=str(effective_labor),
        parts_cost=str(parts_cost),
        computed_total_price=str(computed_total),
    )


async def _load_service_with_parts(db: AsyncSession, service_id: UUID) -> Optional[Service]:
    result = await db.execute(
        select(Service)
        .where(Service.id == service_id)
        .options(
            selectinload(Service.service_parts).selectinload(ServicePart.inventory_item),
            selectinload(Service.category),
        )
    )
    return result.scalar_one_or_none()


# --- Service Categories ---

@router.post("/categories", response_model=ServiceCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: ServiceCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    category = ServiceCategory(
        tenant_id=current_user.tenant_id,
        **data.model_dump(),
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)

    return ServiceCategoryResponse(
        id=str(category.id),
        name=category.name,
        description=category.description,
        icon=category.icon,
        sort_order=category.sort_order,
        is_active=category.is_active,
        is_pm=category.is_pm,
    )


@router.get("/categories", response_model=List[ServiceCategoryResponse])
async def list_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _resolve_tenant_id(current_user, db)
    if not tenant_id:
        return paginated_or_list([], 0, skip, limit, paginated)

    base_query = select(ServiceCategory).where(
        and_(ServiceCategory.tenant_id == tenant_id, ServiceCategory.is_active == True)
    )
    total_result = await db.execute(
        select(func.count(ServiceCategory.id)).where(
            and_(ServiceCategory.tenant_id == tenant_id, ServiceCategory.is_active == True)
        )
    )
    total = total_result.scalar() or 0
    query = base_query.order_by(ServiceCategory.sort_order, ServiceCategory.name).offset(skip).limit(limit)
    result = await db.execute(query)
    categories = result.scalars().all()

    items = [
        ServiceCategoryResponse(
            id=str(c.id),
            name=c.name,
            description=c.description,
            icon=c.icon,
            sort_order=c.sort_order,
            is_active=c.is_active,
            is_pm=c.is_pm,
        )
        for c in categories
    ]
    return paginated_or_list(items, total, skip, limit, paginated)


# --- Services ---

class ServiceNameSuggestion(BaseModel):
    text: str
    times_used: int


async def _library_suggestions(db: AsyncSession, tenant_id, library_type: str, term: str, limit: int):
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


@router.get("/name-suggestions", response_model=List[ServiceNameSuggestion])
async def get_service_name_suggestions(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """Autocomplete for the new-service Name field, drawn from this tenant's
    AI-canonicalized service-name library (see
    app/services/description_library_service.py). A shop with no library yet
    (never regenerated) simply gets no suggestions here.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")

    term = q.strip()
    if not term:
        return []

    rows = await _library_suggestions(db, current_user.tenant_id, "service_name", term, limit)
    return [ServiceNameSuggestion(text=text, times_used=count) for text, count, _score in rows]


class LibraryRegenerateResponse(BaseModel):
    queued: bool = True


@router.post(
    "/name-library/regenerate",
    response_model=LibraryRegenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_service_name_library_endpoint(
    current_user: User = Depends(require_admin()),
):
    """Owner/admin-triggered rebuild of this tenant's canonical service-name
    library from the current Services catalog. Runs as a background Celery
    task — enqueues and returns immediately rather than blocking on the
    multi-minute Claude call.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a tenant")
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ANTHROPIC_API_KEY is not configured")

    process_on_demand_library_regenerate.delay(str(current_user.tenant_id), "service_name")
    return LibraryRegenerateResponse()


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    data: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    service = Service(
        tenant_id=current_user.tenant_id,
        **data.model_dump(),
    )
    db.add(service)
    await db.commit()

    service_loaded = await _load_service_with_parts(db, service.id)
    labor_rate = await _get_labor_rate(db, current_user.tenant_id)
    return _serialize_service(service_loaded, labor_rate, include_category=True)


@router.get("", response_model=List[ServiceResponse])
async def list_services(
    category_id: Optional[UUID] = Query(None),
    active_only: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = await _resolve_tenant_id(current_user, db)
    if not tenant_id:
        return paginated_or_list([], 0, skip, limit, paginated)

    query = (
        select(Service)
        .where(Service.tenant_id == tenant_id)
        .options(
            selectinload(Service.service_parts).selectinload(ServicePart.inventory_item),
            selectinload(Service.category),
        )
    )
    count_query = select(func.count(Service.id)).where(Service.tenant_id == tenant_id)

    if active_only:
        query = query.where(Service.is_active == True)
        count_query = count_query.where(Service.is_active == True)

    if category_id:
        query = query.where(Service.category_id == category_id)
        count_query = count_query.where(Service.category_id == category_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Service.sort_order, Service.name).offset(skip).limit(limit)

    result = await db.execute(query)
    services = result.scalars().all()

    labor_rate = await _get_labor_rate(db, tenant_id)
    items = [_serialize_service(s, labor_rate, include_category=True) for s in services]
    return paginated_or_list(items, total, skip, limit, paginated)


class PreloadServicesResult(BaseModel):
    categories_added: int
    services_added: int


class ClearServicesResult(BaseModel):
    categories_deleted: int
    services_deleted: int
    services_deactivated: int


@router.post("/preload", response_model=PreloadServicesResult)
async def preload_default_services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """Load default service categories and services for this tenant. Skips names that already exist."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    tenant_id = current_user.tenant_id

    # Existing category names
    cat_names_result = await db.execute(
        select(ServiceCategory.name).where(ServiceCategory.tenant_id == tenant_id)
    )
    existing_cat_names = {row[0] for row in cat_names_result.all()}

    # Existing service names
    svc_names_result = await db.execute(
        select(Service.name).where(Service.tenant_id == tenant_id)
    )
    existing_svc_names = {row[0] for row in svc_names_result.all()}

    # Add missing categories
    cat_map: dict[str, ServiceCategory] = {}
    cats_added = 0
    for cat_data in DEFAULT_CATEGORIES:
        if cat_data["name"] not in existing_cat_names:
            cat = ServiceCategory(id=uuid4(), tenant_id=tenant_id, **cat_data)
            db.add(cat)
            cat_map[cat_data["name"]] = cat
            cats_added += 1
    await db.flush()

    # Load existing categories into map for services that reference them
    existing_cats_result = await db.execute(
        select(ServiceCategory).where(ServiceCategory.tenant_id == tenant_id)
    )
    for cat in existing_cats_result.scalars().all():
        if cat.name not in cat_map:
            cat_map[cat.name] = cat

    # Add missing services
    svcs_added = 0
    for svc_data in DEFAULT_SERVICES:
        if svc_data["name"] not in existing_svc_names:
            cat = cat_map.get(svc_data["category"])
            svc = Service(
                id=uuid4(),
                tenant_id=tenant_id,
                category_id=cat.id if cat else None,
                name=svc_data["name"],
                description=svc_data["description"],
                duration_minutes=svc_data["duration_minutes"],
                base_price=svc_data["base_price"],
                icon=svc_data["icon"],
                sort_order=svc_data["sort_order"],
            )
            db.add(svc)
            svcs_added += 1

    await db.commit()
    return PreloadServicesResult(categories_added=cats_added, services_added=svcs_added)


@router.post("/clear", response_model=ClearServicesResult)
async def clear_all_services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """Delete services with no appointments; deactivate those linked to appointments."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    tenant_id = current_user.tenant_id

    svc_result = await db.execute(
        select(Service).where(Service.tenant_id == tenant_id)
    )
    services = svc_result.scalars().all()

    # Find which service IDs have at least one appointment
    svc_ids = [s.id for s in services]
    linked_ids: set = set()
    if svc_ids:
        appt_result = await db.execute(
            select(Appointment.service_id).where(Appointment.service_id.in_(svc_ids)).distinct()
        )
        linked_ids = {row[0] for row in appt_result.all()}

    deleted = 0
    deactivated = 0
    for svc in services:
        if svc.id in linked_ids:
            svc.is_active = False
            deactivated += 1
        else:
            await db.delete(svc)
            deleted += 1
    await db.flush()

    # Delete categories that have no remaining services
    cat_result = await db.execute(
        select(ServiceCategory).where(ServiceCategory.tenant_id == tenant_id)
    )
    categories = cat_result.scalars().all()
    cats_deleted = 0
    for cat in categories:
        remaining = await db.execute(
            select(func.count(Service.id)).where(Service.category_id == cat.id)
        )
        if (remaining.scalar() or 0) == 0:
            await db.delete(cat)
            cats_deleted += 1

    await db.commit()
    return ClearServicesResult(
        categories_deleted=cats_deleted,
        services_deleted=deleted,
        services_deactivated=deactivated,
    )


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    service_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = await _load_service_with_parts(db, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    labor_rate = await _get_labor_rate(db, service.tenant_id)
    return _serialize_service(service, labor_rate, include_category=True)


@router.put("/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: UUID,
    data: ServiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    result = await db.execute(select(Service).where(Service.id == service_id))
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    if service.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    update_data = data.model_dump(exclude_unset=True)
    clear_base = update_data.pop("clear_base_price", False)
    for field, value in update_data.items():
        setattr(service, field, value)
    if clear_base:
        service.base_price = None

    await db.commit()

    service_loaded = await _load_service_with_parts(db, service.id)
    labor_rate = await _get_labor_rate(db, service.tenant_id)
    return _serialize_service(service_loaded, labor_rate, include_category=True)


# --- Service Parts ---

@router.post(
    "/{service_id}/parts",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_service_part(
    service_id: UUID,
    data: ServicePartCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")

    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    svc_result = await db.execute(
        select(Service).where(
            and_(Service.id == service_id, Service.tenant_id == current_user.tenant_id)
        )
    )
    service = svc_result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    inv_result = await db.execute(
        select(Inventory).where(
            and_(
                Inventory.id == data.inventory_id,
                Inventory.tenant_id == current_user.tenant_id,
                Inventory.deleted_at.is_(None),
            )
        )
    )
    inv = inv_result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    existing_result = await db.execute(
        select(ServicePart).where(
            and_(
                ServicePart.service_id == service_id,
                ServicePart.inventory_id == data.inventory_id,
            )
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        existing.quantity = data.quantity
    else:
        db.add(
            ServicePart(
                tenant_id=current_user.tenant_id,
                service_id=service_id,
                inventory_id=data.inventory_id,
                quantity=data.quantity,
            )
        )

    await db.commit()
    service_loaded = await _load_service_with_parts(db, service_id)
    labor_rate = await _get_labor_rate(db, current_user.tenant_id)
    return _serialize_service(service_loaded, labor_rate, include_category=True)


@router.put("/{service_id}/parts/{part_id}", response_model=ServiceResponse)
async def update_service_part(
    service_id: UUID,
    part_id: UUID,
    data: ServicePartUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    result = await db.execute(
        select(ServicePart).where(
            and_(
                ServicePart.id == part_id,
                ServicePart.service_id == service_id,
                ServicePart.tenant_id == current_user.tenant_id,
            )
        )
    )
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Service part not found")

    part.quantity = data.quantity
    await db.commit()

    service_loaded = await _load_service_with_parts(db, service_id)
    labor_rate = await _get_labor_rate(db, current_user.tenant_id)
    return _serialize_service(service_loaded, labor_rate, include_category=True)


@router.delete("/{service_id}/parts/{part_id}", response_model=ServiceResponse)
async def delete_service_part(
    service_id: UUID,
    part_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User must be associated with a tenant")

    result = await db.execute(
        select(ServicePart).where(
            and_(
                ServicePart.id == part_id,
                ServicePart.service_id == service_id,
                ServicePart.tenant_id == current_user.tenant_id,
            )
        )
    )
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Service part not found")

    await db.delete(part)
    await db.commit()

    service_loaded = await _load_service_with_parts(db, service_id)
    labor_rate = await _get_labor_rate(db, current_user.tenant_id)
    return _serialize_service(service_loaded, labor_rate, include_category=True)
