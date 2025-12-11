from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import RepairOrderCreate, RepairOrderUpdate, RepairOrderResponse

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


async def generate_order_number(db: AsyncSession, tenant_id: UUID) -> str:
    """Generate unique order number"""
    # Get count of orders for this tenant
    result = await db.execute(
        select(func.count(RepairOrder.id)).where(RepairOrder.tenant_id == tenant_id)
    )
    count = result.scalar() or 0
    return f"RO-{str(tenant_id).replace('-', '').upper()[:8]}-{count + 1:06d}"


@router.post("", response_model=RepairOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_repair_order(
    order_data: RepairOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    
    # Verify customer exists and belongs to tenant
    result = await db.execute(
        select(Customer).where(
            and_(
                Customer.id == order_data.customer_id,
                Customer.tenant_id == current_user.tenant_id,
            )
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Verify vehicle exists and belongs to customer
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.id == order_data.vehicle_id,
                Vehicle.customer_id == order_data.customer_id,
                Vehicle.tenant_id == current_user.tenant_id,
            )
        )
    )
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found or does not belong to customer",
        )
    
    # Generate order number
    order_number = await generate_order_number(db, current_user.tenant_id)
    
    repair_order = RepairOrder(
        tenant_id=current_user.tenant_id,
        order_number=order_number,
        status=RepairOrderStatus.DRAFT,
        **order_data.model_dump(),
    )
    
    db.add(repair_order)
    await db.commit()
    await db.refresh(repair_order)
    
    return RepairOrderResponse.model_validate(repair_order)


@router.get("", response_model=List[RepairOrderResponse])
async def list_repair_orders(
    customer_id: Optional[UUID] = Query(None),
    vehicle_id: Optional[UUID] = Query(None),
    status: Optional[RepairOrderStatus] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(RepairOrder)
    
    if current_user.role == UserRole.CUSTOMER:
        # Customers can only see their own repair orders
        if not current_user.customer_id:
            return []
        query = query.where(RepairOrder.customer_id == current_user.customer_id)
    else:
        # Staff can filter by customer/vehicle/status or see all in tenant
        if not current_user.tenant_id:
            return []
        query = query.where(RepairOrder.tenant_id == current_user.tenant_id)
        if customer_id:
            query = query.where(RepairOrder.customer_id == customer_id)
    
    if vehicle_id:
        query = query.where(RepairOrder.vehicle_id == vehicle_id)
    if status:
        query = query.where(RepairOrder.status == status)
    
    query = query.offset(skip).limit(limit).order_by(RepairOrder.created_at.desc())
    result = await db.execute(query)
    orders = result.scalars().all()
    
    return [RepairOrderResponse.model_validate(o) for o in orders]


@router.get("/{order_id}", response_model=RepairOrderResponse)
async def get_repair_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != order.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    elif current_user.tenant_id != order.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    return RepairOrderResponse.model_validate(order)


@router.put("/{order_id}", response_model=RepairOrderResponse)
async def update_repair_order(
    order_id: UUID,
    order_data: RepairOrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    )),
):
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair order not found",
        )
    
    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Update fields
    update_data = order_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(order, field, value)
    
    await db.commit()
    await db.refresh(order)
    
    return RepairOrderResponse.model_validate(order)

