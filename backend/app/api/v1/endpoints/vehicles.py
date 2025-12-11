from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.customer import Customer
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleResponse

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


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    vehicle_data: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Check if customer exists and user has access
    result = await db.execute(select(Customer).where(Customer.id == vehicle_data.customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access: customers can only add vehicles to their own account
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != vehicle_data.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    # Staff can only add vehicles for customers in their tenant
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    vehicle = Vehicle(
        tenant_id=customer.tenant_id,
        customer_id=vehicle_data.customer_id,
        **vehicle_data.model_dump(exclude={"customer_id"}),
    )
    
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    
    return VehicleResponse.model_validate(vehicle)


@router.get("", response_model=List[VehicleResponse])
async def list_vehicles(
    customer_id: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(Vehicle)
    
    if current_user.role == UserRole.CUSTOMER:
        # Customers can only see their own vehicles
        if not current_user.customer_id:
            return []
        query = query.where(Vehicle.customer_id == current_user.customer_id)
    else:
        # Staff can filter by customer or see all in tenant
        if not current_user.tenant_id:
            return []
        query = query.where(Vehicle.tenant_id == current_user.tenant_id)
        if customer_id:
            query = query.where(Vehicle.customer_id == customer_id)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    vehicles = result.scalars().all()
    
    return [VehicleResponse.model_validate(v) for v in vehicles]


@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != vehicle.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != vehicle.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    return VehicleResponse.model_validate(vehicle)


@router.put("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: UUID,
    vehicle_data: VehicleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != vehicle.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != vehicle.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Update fields
    update_data = vehicle_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(vehicle, field, value)
    
    await db.commit()
    await db.refresh(vehicle)
    
    return VehicleResponse.model_validate(vehicle)

