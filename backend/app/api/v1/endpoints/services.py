from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
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
        if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.GARAGE_ADMIN]:
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
        return []
    
    result = await db.execute(
        select(ServiceCategory)
        .where(and_(ServiceCategory.tenant_id == tenant_id, ServiceCategory.is_active == True))
        .order_by(ServiceCategory.sort_order, ServiceCategory.name)
    )
    categories = result.scalars().all()
    
    return [
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
        return []
    
    query = select(Service).where(Service.tenant_id == tenant_id)
    
    if active_only:
        query = query.where(Service.is_active == True)
    
    if category_id:
        query = query.where(Service.category_id == category_id)
    
    query = query.order_by(Service.sort_order, Service.name)
    
    result = await db.execute(query)
    services = result.scalars().all()
    
    return [
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
