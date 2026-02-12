from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder
from app.db.models.appointment import Appointment
from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse, CustomerWithVehiclesResponse
from app.schemas.vehicle import VehicleBase, VehicleUpdate, VehicleResponse

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


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    
    # Check if customer email already exists for this tenant
    result = await db.execute(
        select(Customer).where(
            and_(
                Customer.email == customer_data.email,
                Customer.tenant_id == current_user.tenant_id,
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer with this email already exists",
        )
    
    customer = Customer(
        tenant_id=current_user.tenant_id,
        **customer_data.model_dump(),
    )
    
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    
    return CustomerResponse.model_validate(customer)


@router.get("", response_model=List[CustomerResponse])
async def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role == UserRole.CUSTOMER:
        # Customers can only see their own profile
        if not current_user.customer_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        result = await db.execute(
            select(Customer).where(Customer.id == current_user.customer_id)
        )
        customer = result.scalar_one_or_none()
        customers = [CustomerResponse.model_validate(customer)] if customer else []
        total = len(customers)
        response_items = customers[skip : skip + limit] if paginated else customers
        return paginated_or_list(response_items, total, skip, limit, paginated)
    
    # Staff can see all customers in their tenant
    if not current_user.tenant_id:
        return paginated_or_list([], 0, skip, limit, paginated)
    
    total_result = await db.execute(
        select(func.count(Customer.id)).where(Customer.tenant_id == current_user.tenant_id)
    )
    total = total_result.scalar() or 0
    result = await db.execute(select(Customer).where(Customer.tenant_id == current_user.tenant_id).offset(skip).limit(limit))
    customers = result.scalars().all()
    items = [CustomerResponse.model_validate(c) for c in customers]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access: customers can only see their own profile
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    # Staff can only see customers in their tenant
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    return CustomerResponse.model_validate(customer)


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    customer_data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Update fields
    update_data = customer_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)
    
    await db.commit()
    await db.refresh(customer)
    
    return CustomerResponse.model_validate(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    if current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    repair_order_count_result = await db.execute(
        select(func.count(RepairOrder.id)).where(RepairOrder.customer_id == customer_id)
    )
    repair_order_count = repair_order_count_result.scalar() or 0
    if repair_order_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete customer with repair orders",
        )

    # If there is a linked customer-portal user, detach it from this customer.
    # For customer-role users, also deactivate access after detaching.
    linked_users_result = await db.execute(
        select(User).where(User.customer_id == customer_id)
    )
    linked_users = linked_users_result.scalars().all()
    for linked_user in linked_users:
        linked_user.customer_id = None
        if linked_user.role == UserRole.CUSTOMER:
            linked_user.is_active = False

    # Remove orphanable appointments so customer deletion can proceed cleanly.
    # Repair-order-backed history is still protected by the guard above.
    appointments_result = await db.execute(
        select(Appointment).where(
            and_(
                Appointment.customer_id == customer_id,
                Appointment.tenant_id == customer.tenant_id,
            )
        )
    )
    appointments = appointments_result.scalars().all()
    for appointment in appointments:
        await db.delete(appointment)

    await db.delete(customer)
    await db.commit()

    return None


# ============================================================================
# NESTED VEHICLE ENDPOINTS
# ============================================================================

@router.get("/{customer_id}/vehicles", response_model=List[VehicleResponse])
async def list_customer_vehicles(
    customer_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all vehicles for a specific customer"""
    # First verify customer exists and user has access
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Get vehicles
    total_result = await db.execute(select(func.count(Vehicle.id)).where(Vehicle.customer_id == customer_id))
    total = total_result.scalar() or 0
    query = (
        select(Vehicle)
        .where(Vehicle.customer_id == customer_id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    vehicles = result.scalars().all()
    items = [VehicleResponse.model_validate(v) for v in vehicles]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.post("/{customer_id}/vehicles", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_customer_vehicle(
    customer_id: UUID,
    vehicle_data: VehicleBase,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new vehicle for a specific customer"""
    # Verify customer exists
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    vehicle = Vehicle(
        tenant_id=customer.tenant_id,
        customer_id=customer_id,
        **vehicle_data.model_dump(),
    )
    
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    
    return VehicleResponse.model_validate(vehicle)


@router.get("/{customer_id}/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def get_customer_vehicle(
    customer_id: UUID,
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a specific vehicle for a customer"""
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.id == vehicle_id,
                Vehicle.customer_id == customer_id,
            )
        )
    )
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
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


@router.put("/{customer_id}/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def update_customer_vehicle(
    customer_id: UUID,
    vehicle_id: UUID,
    vehicle_data: VehicleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a specific vehicle for a customer"""
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.id == vehicle_id,
                Vehicle.customer_id == customer_id,
            )
        )
    )
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
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


@router.delete("/{customer_id}/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer_vehicle(
    customer_id: UUID,
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    """Delete a specific vehicle for a customer (staff only)"""
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.id == vehicle_id,
                Vehicle.customer_id == customer_id,
            )
        )
    )
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    if current_user.tenant_id != vehicle.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    await db.delete(vehicle)
    await db.commit()
    
    return None


@router.get("/{customer_id}/with-vehicles", response_model=CustomerWithVehiclesResponse)
async def get_customer_with_vehicles(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a customer with all their vehicles in a single response"""
    result = await db.execute(
        select(Customer)
        .options(selectinload(Customer.vehicles))
        .where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    return CustomerWithVehiclesResponse.model_validate(customer)
