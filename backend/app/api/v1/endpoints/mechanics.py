from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
import json

from app.core.dependencies import get_db, get_current_active_user
from app.core.security import get_password_hash
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.schemas.auth import UserResponse
from app.schemas.mechanic import MechanicCreate
from app.schemas.mechanic_update import MechanicUpdate
from pydantic import BaseModel, Field

router = APIRouter()


def require_role(*allowed_roles: UserRole):
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker


@router.get("", response_model=List[UserResponse])
async def list_mechanics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.GARAGE_ADMIN)),
):
    if not current_user.tenant_id:
        return []

    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == current_user.tenant_id,
                User.role == UserRole.MECHANIC,
            )
        )
    )
    mechanics = result.scalars().all()
    return [UserResponse.model_validate(user) for user in mechanics]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_mechanic(
    mechanic_data: MechanicCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.GARAGE_ADMIN)),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )

    # Ensure email is unique
    result = await db.execute(select(User).where(User.email == mechanic_data.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    mechanic = User(
        email=mechanic_data.email,
        hashed_password=get_password_hash(mechanic_data.password),
        first_name=mechanic_data.first_name,
        last_name=mechanic_data.last_name,
        phone=mechanic_data.phone or None,
        address=mechanic_data.address or None,
        role=UserRole.MECHANIC,
        tenant_id=current_user.tenant_id,
        is_active=True,
        is_verified=True,
    )

    db.add(mechanic)
    await db.commit()
    await db.refresh(mechanic)

    return UserResponse.model_validate(mechanic)


class MechanicWorkItem(BaseModel):
    id: str
    order_number: str
    status: str
    customer_name: str
    vehicle_info: str
    updated_at: str


class ServiceItem(BaseModel):
    name: str
    description: Optional[str] = None
    base_price: Optional[str] = None


class MechanicJobDetail(BaseModel):
    """Job detail for mechanic portal - NO customer info"""
    id: str
    order_number: str
    status: str
    description: Optional[str] = None
    vehicle_year: Optional[int] = None
    vehicle_make: str
    vehicle_model: str
    vehicle_vin: Optional[str] = None
    vehicle_license_plate: Optional[str] = None
    vehicle_mileage: Optional[int] = None
    services: List[ServiceItem] = []
    created_at: datetime
    updated_at: datetime


class MechanicJobSummary(BaseModel):
    """Job summary for mechanic job list"""
    id: str
    order_number: str
    status: str
    vehicle_info: str
    description: Optional[str] = None
    services_count: int = 0
    updated_at: datetime


class MechanicHistoryItem(BaseModel):
    """Work history item for mechanic"""
    id: str
    order_number: str
    status: str
    vehicle_info: str
    services_count: int = 0
    completed_at: datetime


@router.get("/my-jobs", response_model=List[MechanicJobSummary])
async def get_my_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Get all jobs assigned to the current mechanic"""
    result = await db.execute(
        select(RepairOrder)
        .where(
            and_(
                RepairOrder.assigned_mechanic_id == current_user.id,
                RepairOrder.status.in_([
                    RepairOrderStatus.ASSIGNED,
                    RepairOrderStatus.ACKNOWLEDGED,
                    RepairOrderStatus.IN_PROGRESS,
                    RepairOrderStatus.PENDING_REVIEW,
                ]),
            )
        )
        .options(selectinload(RepairOrder.vehicle))
        .order_by(RepairOrder.updated_at.desc())
    )
    orders = result.scalars().all()
    
    jobs = []
    for order in orders:
        vehicle = order.vehicle
        vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Unknown"
        
        # Count services
        services_count = 0
        if order.internal_notes:
            try:
                notes = json.loads(order.internal_notes)
                services_count = len(notes.get("selected_services", []))
            except:
                pass
        
        jobs.append(MechanicJobSummary(
            id=str(order.id),
            order_number=order.order_number,
            status=order.status.value,
            vehicle_info=vehicle_info,
            description=order.description,
            services_count=services_count,
            updated_at=order.updated_at,
        ))
    
    return jobs


@router.get("/my-history", response_model=List[MechanicHistoryItem])
async def get_my_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Get completed work history for the current mechanic"""
    result = await db.execute(
        select(RepairOrder)
        .where(
            and_(
                RepairOrder.assigned_mechanic_id == current_user.id,
                RepairOrder.status.in_([
                    RepairOrderStatus.COMPLETED,
                    RepairOrderStatus.INVOICED,
                    RepairOrderStatus.PAID,
                ]),
            )
        )
        .options(selectinload(RepairOrder.vehicle))
        .order_by(RepairOrder.updated_at.desc())
        .limit(50)  # Limit history to last 50 jobs
    )
    orders = result.scalars().all()
    
    history = []
    for order in orders:
        vehicle = order.vehicle
        vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Unknown"
        
        services_count = 0
        if order.internal_notes:
            try:
                notes = json.loads(order.internal_notes)
                services_count = len(notes.get("selected_services", []))
            except:
                pass
        
        history.append(MechanicHistoryItem(
            id=str(order.id),
            order_number=order.order_number,
            status=order.status.value,
            vehicle_info=vehicle_info,
            services_count=services_count,
            completed_at=order.updated_at,
        ))
    
    return history


@router.get("/my-jobs/{order_id}", response_model=MechanicJobDetail)
async def get_my_job_detail(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Get job detail for mechanic - NO customer info exposed"""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id)
        .options(selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    
    vehicle = order.vehicle
    
    # Parse services
    services = []
    if order.internal_notes:
        try:
            notes = json.loads(order.internal_notes)
            for svc in notes.get("selected_services", []):
                services.append(ServiceItem(
                    name=svc.get("name", "Service"),
                    description=svc.get("description"),
                    base_price=svc.get("base_price"),
                ))
        except:
            pass
    
    return MechanicJobDetail(
        id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        description=order.description,
        vehicle_year=vehicle.year if vehicle else None,
        vehicle_make=vehicle.make if vehicle else "Unknown",
        vehicle_model=vehicle.model if vehicle else "Unknown",
        vehicle_vin=vehicle.vin if vehicle else None,
        vehicle_license_plate=vehicle.license_plate if vehicle else None,
        vehicle_mileage=vehicle.mileage if vehicle else None,
        services=services,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


@router.get("/{mechanic_id}/work", response_model=list[MechanicWorkItem])
async def get_mechanic_work(
    mechanic_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.GARAGE_ADMIN, UserRole.MECHANIC)),
):
    # Ensure mechanic exists and belongs to tenant
    result = await db.execute(select(User).where(User.id == mechanic_id, User.role == UserRole.MECHANIC))
    mechanic = result.scalar_one_or_none()
    if not mechanic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic not found")

    # Tenant check: mechanics can only see their own work; admins only within tenant
    if current_user.role == UserRole.MECHANIC:
        if current_user.id != mechanic.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        tenant_id = current_user.tenant_id
    else:
        if not current_user.tenant_id or mechanic.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        tenant_id = current_user.tenant_id

    result = await db.execute(
        select(RepairOrder, Customer, Vehicle)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.assigned_mechanic_id == mechanic.id,
            )
        )
        .order_by(RepairOrder.updated_at.desc())
    )
    rows = result.all()
    work_items: list[MechanicWorkItem] = []
    for order, customer, vehicle in rows:
        work_items.append(
            MechanicWorkItem(
                id=str(order.id),
                order_number=order.order_number,
                status=order.status.value if hasattr(order.status, "value") else str(order.status),
                customer_name=f"{customer.first_name} {customer.last_name}",
                vehicle_info=f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip(),
                updated_at=order.updated_at.isoformat(),
            )
        )
    return work_items


class MechanicPasswordUpdate(BaseModel):
    new_password: str = Field(..., min_length=8, description="New password for the mechanic")


@router.put("/{mechanic_id}", response_model=UserResponse)
async def update_mechanic(
    mechanic_id: UUID,
    mechanic_update: MechanicUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.GARAGE_ADMIN)),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )

    result = await db.execute(
        select(User).where(
            and_(
                User.id == mechanic_id,
                User.role == UserRole.MECHANIC,
                User.tenant_id == current_user.tenant_id,
            )
        )
    )
    mechanic = result.scalar_one_or_none()
    if not mechanic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic not found")

    if mechanic_update.email and mechanic_update.email != mechanic.email:
        email_check = await db.execute(select(User).where(User.email == mechanic_update.email))
        if email_check.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    if mechanic_update.first_name is not None:
        mechanic.first_name = mechanic_update.first_name
    if mechanic_update.last_name is not None:
        mechanic.last_name = mechanic_update.last_name
    if mechanic_update.email is not None:
        mechanic.email = mechanic_update.email
    if mechanic_update.phone is not None:
        mechanic.phone = mechanic_update.phone or None
    if mechanic_update.address is not None:
        mechanic.address = mechanic_update.address or None
    if mechanic_update.password:
        mechanic.hashed_password = get_password_hash(mechanic_update.password)

    db.add(mechanic)
    await db.commit()
    await db.refresh(mechanic)

    return UserResponse.model_validate(mechanic)


@router.put("/{mechanic_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def update_mechanic_password(
    mechanic_id: UUID,
    password_update: MechanicPasswordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.GARAGE_ADMIN)),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )

    result = await db.execute(
        select(User).where(
            and_(
                User.id == mechanic_id,
                User.role == UserRole.MECHANIC,
                User.tenant_id == current_user.tenant_id,
            )
        )
    )
    mechanic = result.scalar_one_or_none()
    if not mechanic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic not found")

    mechanic.hashed_password = get_password_hash(password_update.new_password)
    db.add(mechanic)
    await db.commit()

    return
