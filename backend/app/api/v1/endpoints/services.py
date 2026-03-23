from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.default_catalog import DEFAULT_CATEGORIES, DEFAULT_SERVICES
from app.db.models.appointment import Appointment
from app.db.models.user import User, UserRole
from app.db.models.service import Service, ServiceCategory

router = APIRouter()


# Schemas
class ServiceCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int = 0


class ServiceCategoryResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    icon: Optional[str]
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class ServiceCreate(BaseModel):
    category_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    duration_minutes: int = 60
    base_price: Decimal
    icon: Optional[str] = None
    sort_order: int = 0
    requires_vehicle: bool = True


class ServiceUpdate(BaseModel):
    category_id: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    base_price: Optional[Decimal] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    requires_vehicle: Optional[bool] = None


class ServiceResponse(BaseModel):
    id: str
    category_id: Optional[str]
    name: str
    description: Optional[str]
    duration_minutes: int
    base_price: str
    icon: Optional[str]
    sort_order: int
    is_active: bool
    requires_vehicle: bool
    category: Optional[ServiceCategoryResponse] = None

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
    )


@router.get("/categories", response_model=List[ServiceCategoryResponse])
async def list_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tenant_id = current_user.tenant_id
    if not tenant_id and current_user.customer_id:
        # Customer - get tenant from their customer record
        from app.db.models.customer import Customer
        result = await db.execute(select(Customer).where(Customer.id == current_user.customer_id))
        customer = result.scalar_one_or_none()
        if customer:
            tenant_id = customer.tenant_id
    
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
        )
        for c in categories
    ]
    return paginated_or_list(items, total, skip, limit, paginated)


# --- Services ---

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
    await db.refresh(service)
    
    return ServiceResponse(
        id=str(service.id),
        category_id=str(service.category_id) if service.category_id else None,
        name=service.name,
        description=service.description,
        duration_minutes=service.duration_minutes,
        base_price=str(service.base_price),
        icon=service.icon,
        sort_order=service.sort_order,
        is_active=service.is_active,
        requires_vehicle=service.requires_vehicle,
    )


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
    tenant_id = current_user.tenant_id
    if not tenant_id and current_user.customer_id:
        from app.db.models.customer import Customer
        result = await db.execute(select(Customer).where(Customer.id == current_user.customer_id))
        customer = result.scalar_one_or_none()
        if customer:
            tenant_id = customer.tenant_id
    
    if not tenant_id:
        return paginated_or_list([], 0, skip, limit, paginated)
    
    query = select(Service).where(Service.tenant_id == tenant_id)
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
    
    items = [
        ServiceResponse(
            id=str(s.id),
            category_id=str(s.category_id) if s.category_id else None,
            name=s.name,
            description=s.description,
            duration_minutes=s.duration_minutes,
            base_price=str(s.base_price),
            icon=s.icon,
            sort_order=s.sort_order,
            is_active=s.is_active,
            requires_vehicle=s.requires_vehicle,
        )
        for s in services
    ]
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
    result = await db.execute(select(Service).where(Service.id == service_id))
    service = result.scalar_one_or_none()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    return ServiceResponse(
        id=str(service.id),
        category_id=str(service.category_id) if service.category_id else None,
        name=service.name,
        description=service.description,
        duration_minutes=service.duration_minutes,
        base_price=str(service.base_price),
        icon=service.icon,
        sort_order=service.sort_order,
        is_active=service.is_active,
        requires_vehicle=service.requires_vehicle,
    )


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
    for field, value in update_data.items():
        setattr(service, field, value)
    
    await db.commit()
    await db.refresh(service)
    
    return ServiceResponse(
        id=str(service.id),
        category_id=str(service.category_id) if service.category_id else None,
        name=service.name,
        description=service.description,
        duration_minutes=service.duration_minutes,
        base_price=str(service.base_price),
        icon=service.icon,
        sort_order=service.sort_order,
        is_active=service.is_active,
        requires_vehicle=service.requires_vehicle,
    )
