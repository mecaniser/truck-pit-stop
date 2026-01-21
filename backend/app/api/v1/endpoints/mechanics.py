from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID

from app.core.dependencies import get_db, get_current_active_user
from app.core.security import get_password_hash
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.schemas.auth import UserResponse
from app.schemas.mechanic import MechanicCreate
from pydantic import BaseModel

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
