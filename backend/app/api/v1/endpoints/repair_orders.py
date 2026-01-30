from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor
from app.db.models.quote import Quote
from app.services.email_service import send_email
from app.core.config import settings
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


class AssignMechanicRequest(BaseModel):
    mechanic_id: UUID


@router.post("/{order_id}/assign-mechanic", response_model=RepairOrderResponse)
async def assign_mechanic(
    order_id: UUID,
    body: AssignMechanicRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    """Assign mechanic to repair order, set status to in_progress, notify customer"""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id)
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    
    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    # Check if this is a reassignment (mechanic already assigned)
    is_reassignment = order.assigned_mechanic_id is not None
    
    if is_reassignment:
        # Only admins can reassign
        if current_user.role not in (UserRole.SUPER_ADMIN, UserRole.GARAGE_ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop managers can reassign mechanics. Please contact your manager.",
            )
    else:
        # First assignment - must be approved status
        if order.status != RepairOrderStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only assign mechanic to approved repair orders",
            )
    
    # Verify mechanic exists and belongs to tenant
    result = await db.execute(
        select(User).where(
            and_(
                User.id == body.mechanic_id,
                User.tenant_id == current_user.tenant_id,
                User.role == UserRole.MECHANIC,
            )
        )
    )
    mechanic = result.scalar_one_or_none()
    if not mechanic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic not found")
    
    # Assign mechanic and update status (only on first assignment)
    order.assigned_mechanic_id = body.mechanic_id
    if not is_reassignment:
        order.status = RepairOrderStatus.ASSIGNED
    
    await db.commit()
    await db.refresh(order)
    
    # Send email notification to MECHANIC (not customer - customer notified when work starts)
    vehicle = order.vehicle
    vehicle_info = f"{vehicle.year} {vehicle.make} {vehicle.model}" if vehicle else "Vehicle"
    
    # Parse services from internal_notes
    services_html = ""
    if order.internal_notes:
        try:
            import json
            notes_data = json.loads(order.internal_notes)
            selected_services = notes_data.get("selected_services", [])
            if selected_services:
                services_html = '<ul style="margin: 10px 0; padding-left: 20px;">'
                for svc in selected_services:
                    services_html += f'<li>{svc.get("name", "Service")}</li>'
                services_html += '</ul>'
        except:
            pass
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #d97706; margin: 0;">🔧 Truck Pit Stop</h1>
        </div>
        
        <h2 style="color: #333;">New Job Assigned</h2>
        <p>Hi {mechanic.first_name},</p>
        <p>You have been assigned a new repair job. Please acknowledge and start when ready.</p>
        
        <div style="background: #fef3c7; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #fcd34d;">
            <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
            <p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>
            <p style="margin: 0 0 10px 0;"><strong>Description:</strong> {order.description or 'See services below'}</p>
            {f'<p style="margin: 0;"><strong>Services:</strong>{services_html}</p>' if services_html else ''}
        </div>
        
        <p style="margin: 30px 0; text-align: center;">
            <a href="{settings.FRONTEND_URL}/mechanic" 
               style="background-color: #d97706; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                View in Mechanic Portal
            </a>
        </p>
    </body>
    </html>
    """
    
    if mechanic.email:
        await send_email(
            db=db,
            tenant_id=str(current_user.tenant_id),
            to=mechanic.email,
            subject=f"New Job Assigned: {order.order_number} - Truck Pit Stop",
            body=html_body,
            template_name="job_assigned",
        )
    
    return RepairOrderResponse.model_validate(order)


# ============ Mechanic Workflow Endpoints ============

@router.post("/{order_id}/acknowledge", response_model=RepairOrderResponse)
async def acknowledge_job(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic acknowledges job assignment"""
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    
    if order.status != RepairOrderStatus.ASSIGNED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot acknowledge job in '{order.status.value}' status",
        )
    
    order.status = RepairOrderStatus.ACKNOWLEDGED
    await db.commit()
    await db.refresh(order)
    
    return RepairOrderResponse.model_validate(order)


@router.post("/{order_id}/start-work", response_model=RepairOrderResponse)
async def start_work(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic starts work - notifies customer"""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id)
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    
    if order.status not in (RepairOrderStatus.ASSIGNED, RepairOrderStatus.ACKNOWLEDGED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start work on job in '{order.status.value}' status",
        )
    
    order.status = RepairOrderStatus.IN_PROGRESS
    await db.commit()
    await db.refresh(order)
    
    # Notify customer that work has started
    customer = order.customer
    if customer and customer.email:
        vehicle = order.vehicle
        vehicle_info = f"{vehicle.year} {vehicle.make} {vehicle.model}" if vehicle else "your vehicle"
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #d97706; margin: 0;">🔧 Truck Pit Stop</h1>
            </div>
            
            <h2 style="color: #333;">Work Has Started!</h2>
            <p>Hi {customer.first_name},</p>
            <p>Great news! Work has begun on your vehicle.</p>
            
            <div style="background: #f0fdf4; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #bbf7d0;">
                <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
                <p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>
                <p style="margin: 0; font-size: 18px; color: #16a34a;"><strong>Status: In Progress</strong></p>
            </div>
            
            <p>We'll notify you when the work is complete. You can also check your customer portal for updates.</p>
            
            <p style="margin: 30px 0; text-align: center;">
                <a href="{settings.FRONTEND_URL}/portal" 
                   style="background-color: #d97706; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                    View in Portal
                </a>
            </p>
        </body>
        </html>
        """
        
        await send_email(
            db=db,
            tenant_id=str(order.tenant_id),
            to=customer.email,
            subject=f"Work Started on {order.order_number} - Truck Pit Stop",
            body=html_body,
            template_name="work_started",
        )
    
    return RepairOrderResponse.model_validate(order)


@router.post("/{order_id}/complete-work", response_model=RepairOrderResponse)
async def complete_work(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic marks work as complete - notifies manager for review"""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id)
        .options(selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    
    if order.status != RepairOrderStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete job in '{order.status.value}' status",
        )
    
    order.status = RepairOrderStatus.PENDING_REVIEW
    await db.commit()
    await db.refresh(order)
    
    # Notify managers that work is ready for review
    # Get all admins for this tenant
    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == order.tenant_id,
                User.role.in_([UserRole.SUPER_ADMIN, UserRole.GARAGE_ADMIN]),
                User.is_active == True,
            )
        )
    )
    managers = result.scalars().all()
    
    vehicle = order.vehicle
    vehicle_info = f"{vehicle.year} {vehicle.make} {vehicle.model}" if vehicle else "Vehicle"
    
    for manager in managers:
        if manager.email:
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #d97706; margin: 0;">🔧 Truck Pit Stop</h1>
                </div>
                
                <h2 style="color: #333;">Work Ready for Review</h2>
                <p>Hi {manager.first_name},</p>
                <p>{current_user.first_name} {current_user.last_name} has completed work on a repair order and it's ready for your review.</p>
                
                <div style="background: #fef3c7; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #fcd34d;">
                    <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
                    <p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>
                    <p style="margin: 0 0 10px 0;"><strong>Mechanic:</strong> {current_user.first_name} {current_user.last_name}</p>
                    <p style="margin: 0; font-size: 18px; color: #d97706;"><strong>Status: Pending Review</strong></p>
                </div>
                
                <p style="margin: 30px 0; text-align: center;">
                    <a href="{settings.FRONTEND_URL}/dashboard/repair-orders" 
                       style="background-color: #d97706; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                        Review in Dashboard
                    </a>
                </p>
            </body>
            </html>
            """
            
            await send_email(
                db=db,
                tenant_id=str(order.tenant_id),
                to=manager.email,
                subject=f"Review Needed: {order.order_number} - Truck Pit Stop",
                body=html_body,
                template_name="work_pending_review",
            )
    
    return RepairOrderResponse.model_validate(order)


@router.post("/{order_id}/approve-completion", response_model=RepairOrderResponse)
async def approve_completion(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.SUPER_ADMIN,
        UserRole.GARAGE_ADMIN,
    )),
):
    """Manager approves completed work - notifies customer"""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id)
        .options(selectinload(RepairOrder.customer), selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    
    if current_user.tenant_id != order.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    if order.status != RepairOrderStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve job in '{order.status.value}' status",
        )
    
    order.status = RepairOrderStatus.COMPLETED
    await db.commit()
    await db.refresh(order)
    
    # Notify customer that work is complete
    customer = order.customer
    if customer and customer.email:
        vehicle = order.vehicle
        vehicle_info = f"{vehicle.year} {vehicle.make} {vehicle.model}" if vehicle else "your vehicle"
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #d97706; margin: 0;">🔧 Truck Pit Stop</h1>
            </div>
            
            <h2 style="color: #16a34a;">Work Complete!</h2>
            <p>Hi {customer.first_name},</p>
            <p>Great news! The work on your vehicle has been completed and verified.</p>
            
            <div style="background: #f0fdf4; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #bbf7d0;">
                <p style="margin: 0 0 10px 0;"><strong>Order #:</strong> {order.order_number}</p>
                <p style="margin: 0 0 10px 0;"><strong>Vehicle:</strong> {vehicle_info}</p>
                <p style="margin: 0; font-size: 18px; color: #16a34a;"><strong>Status: Completed ✓</strong></p>
            </div>
            
            <p>You can pick up your vehicle or view the invoice in your customer portal.</p>
            
            <p style="margin: 30px 0; text-align: center;">
                <a href="{settings.FRONTEND_URL}/portal" 
                   style="background-color: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                    View in Portal
                </a>
            </p>
            
            <p style="color: #666; font-size: 14px;">
                Thank you for choosing Truck Pit Stop!
            </p>
        </body>
        </html>
        """
        
        await send_email(
            db=db,
            tenant_id=str(order.tenant_id),
            to=customer.email,
            subject=f"Work Complete: {order.order_number} - Truck Pit Stop",
            body=html_body,
            template_name="work_complete",
        )
    
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

    # Delete related records first (no cascade in FK)
    # Delete quote if exists
    quote_result = await db.execute(select(Quote).where(Quote.repair_order_id == order_id))
    quote = quote_result.scalar_one_or_none()
    if quote:
        await db.delete(quote)

    # Delete parts usage
    parts_result = await db.execute(select(PartsUsage).where(PartsUsage.repair_order_id == order_id))
    for part in parts_result.scalars().all():
        await db.delete(part)

    # Delete labor items
    labor_result = await db.execute(select(Labor).where(Labor.repair_order_id == order_id))
    for labor in labor_result.scalars().all():
        await db.delete(labor)

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
