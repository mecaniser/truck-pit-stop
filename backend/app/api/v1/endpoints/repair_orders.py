from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor
from app.schemas.repair_order import (
    RepairOrderCreate,
    RepairOrderUpdate,
    RepairOrderResponse,
    RepairOrderDetailResponse,
    PartsUsageCreate,
    PartsUsageResponse,
    LaborCreate,
    LaborUpdate,
    LaborResponse,
)

router = APIRouter()

# Only draft and quoted ROs can have parts/labor modified
EDITABLE_RO_STATUSES = (RepairOrderStatus.DRAFT, RepairOrderStatus.QUOTED)


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


@router.get("/{order_id}/detail", response_model=RepairOrderDetailResponse)
async def get_repair_order_detail(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id)
        .options(
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
            selectinload(RepairOrder.labor_items),
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    parts_resp = [
        PartsUsageResponse(
            id=pu.id,
            repair_order_id=pu.repair_order_id,
            inventory_id=pu.inventory_id,
            inventory_sku=pu.inventory_item.sku if pu.inventory_item else "",
            inventory_name=pu.inventory_item.name if pu.inventory_item else "",
            quantity=pu.quantity,
            unit_price=pu.unit_price,
            total_price=pu.total_price,
            created_at=pu.created_at,
        )
        for pu in order.parts_usage
    ]
    labor_resp = [LaborResponse.model_validate(li) for li in order.labor_items]
    return RepairOrderDetailResponse(
        **RepairOrderResponse.model_validate(order).model_dump(),
        parts_usage=parts_resp,
        labor_items=labor_resp,
    )


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


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repair_order(
    order_id: UUID,
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

    await db.delete(order)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Helpers for parts/labor and recompute ---


def _check_ro_access(current_user: User, order: RepairOrder) -> None:
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != order.customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif current_user.tenant_id != order.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _require_editable_ro(order: RepairOrder) -> None:
    if order.status not in EDITABLE_RO_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parts and labor can only be modified when repair order is draft or quoted",
        )


async def _recompute_repair_order_totals(db: AsyncSession, order_id: UUID) -> None:
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id)
        .options(
            selectinload(RepairOrder.parts_usage),
            selectinload(RepairOrder.labor_items),
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        return
    total_parts = sum(Decimal(str(pu.total_price)) for pu in order.parts_usage)
    total_labor = sum(Decimal(str(li.total_cost)) for li in order.labor_items)
    order.total_parts_cost = total_parts
    order.total_labor_cost = total_labor
    order.total_cost = total_parts + total_labor
    await db.commit()


# --- Parts ---


@router.post("/{order_id}/parts", response_model=PartsUsageResponse, status_code=status.HTTP_201_CREATED)
async def add_parts_to_repair_order(
    order_id: UUID,
    body: PartsUsageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    if order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    result = await db.execute(
        select(Inventory).where(
            and_(
                Inventory.id == body.inventory_id,
                Inventory.tenant_id == current_user.tenant_id,
            )
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")
    if inv.stock_quantity < body.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock: have {inv.stock_quantity}, requested {body.quantity}",
        )
    unit_price = body.unit_price if body.unit_price is not None else inv.selling_price
    total_price = unit_price * body.quantity
    pu = PartsUsage(
        tenant_id=current_user.tenant_id,
        repair_order_id=order_id,
        inventory_id=body.inventory_id,
        quantity=body.quantity,
        unit_price=unit_price,
        total_price=total_price,
    )
    db.add(pu)
    inv.stock_quantity -= body.quantity
    await db.commit()
    await db.refresh(pu)
    await _recompute_repair_order_totals(db, order_id)
    await db.refresh(pu)
    result = await db.execute(
        select(PartsUsage).where(PartsUsage.id == pu.id).options(selectinload(PartsUsage.inventory_item))
    )
    pu_loaded = result.scalar_one_or_none()
    inv_loaded = pu_loaded.inventory_item if pu_loaded else inv
    return PartsUsageResponse(
        id=pu.id,
        repair_order_id=pu.repair_order_id,
        inventory_id=pu.inventory_id,
        inventory_sku=inv_loaded.sku,
        inventory_name=inv_loaded.name,
        quantity=pu.quantity,
        unit_price=pu.unit_price,
        total_price=pu.total_price,
        created_at=pu.created_at,
    )


@router.get("/{order_id}/parts", response_model=List[PartsUsageResponse])
async def list_repair_order_parts(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id)
        .options(selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    out = []
    for pu in order.parts_usage:
        inv = pu.inventory_item
        out.append(
            PartsUsageResponse(
                id=pu.id,
                repair_order_id=pu.repair_order_id,
                inventory_id=pu.inventory_id,
                inventory_sku=inv.sku if inv else "",
                inventory_name=inv.name if inv else "",
                quantity=pu.quantity,
                unit_price=pu.unit_price,
                total_price=pu.total_price,
                created_at=pu.created_at,
            )
        )
    return out


@router.delete("/{order_id}/parts/{parts_usage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_parts_from_repair_order(
    order_id: UUID,
    parts_usage_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    result = await db.execute(
        select(PartsUsage).where(
            and_(
                PartsUsage.id == parts_usage_id,
                PartsUsage.repair_order_id == order_id,
                PartsUsage.tenant_id == current_user.tenant_id,
            )
        ).options(selectinload(PartsUsage.inventory_item))
    )
    pu = result.scalar_one_or_none()
    if not pu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parts usage not found")
    inv = pu.inventory_item
    if inv is not None:
        inv.stock_quantity += pu.quantity
    await db.delete(pu)
    await db.commit()
    await _recompute_repair_order_totals(db, order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Labor ---


@router.post("/{order_id}/labor", response_model=LaborResponse, status_code=status.HTTP_201_CREATED)
async def add_labor_to_repair_order(
    order_id: UUID,
    body: LaborCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    if order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    total_cost = body.hours * body.hourly_rate
    labor = Labor(
        tenant_id=current_user.tenant_id,
        repair_order_id=order_id,
        description=body.description or "",
        hours=body.hours,
        hourly_rate=body.hourly_rate,
        total_cost=total_cost,
        mechanic_id=body.mechanic_id,
        service_code=body.service_code,
    )
    db.add(labor)
    await db.commit()
    await db.refresh(labor)
    await _recompute_repair_order_totals(db, order_id)
    await db.refresh(labor)
    return LaborResponse.model_validate(labor)


@router.get("/{order_id}/labor", response_model=List[LaborResponse])
async def list_repair_order_labor(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id).options(selectinload(RepairOrder.labor_items))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    return [LaborResponse.model_validate(li) for li in order.labor_items]


@router.put("/{order_id}/labor/{labor_id}", response_model=LaborResponse)
async def update_repair_order_labor(
    order_id: UUID,
    labor_id: UUID,
    body: LaborUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    result = await db.execute(
        select(Labor).where(
            and_(
                Labor.id == labor_id,
                Labor.repair_order_id == order_id,
                Labor.tenant_id == current_user.tenant_id,
            )
        )
    )
    labor = result.scalar_one_or_none()
    if not labor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Labor item not found")
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(labor, field, value)
    if "hours" in update_data or "hourly_rate" in update_data:
        labor.total_cost = labor.hours * labor.hourly_rate
    await db.commit()
    await db.refresh(labor)
    await _recompute_repair_order_totals(db, order_id)
    await db.refresh(labor)
    return LaborResponse.model_validate(labor)


@router.delete("/{order_id}/labor/{labor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_labor_from_repair_order(
    order_id: UUID,
    labor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    )),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    result = await db.execute(select(RepairOrder).where(RepairOrder.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)
    _require_editable_ro(order)
    result = await db.execute(
        select(Labor).where(
            and_(
                Labor.id == labor_id,
                Labor.repair_order_id == order_id,
                Labor.tenant_id == current_user.tenant_id,
            )
        )
    )
    labor = result.scalar_one_or_none()
    if not labor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Labor item not found")
    await db.delete(labor)
    await db.commit()
    await _recompute_repair_order_totals(db, order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
