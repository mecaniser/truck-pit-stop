import traceback
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor
from app.db.models.quote import Quote
from app.db.models.mechanic_points import MechanicPoints, MechanicPointsBalance, PointsTransactionType
from app.services.email_service import send_email
from app.services.twilio_service import send_sms
from app.core.config import settings
from app.core.metrics import record_repair_order_created
from app.core.logging import get_logger
from app.core.phone import normalize_phone
from app.core.websocket import broadcast_repair_order_update
from app.core.websocket import broadcast_mechanic_timer_update
from app.core.websocket import broadcast_mechanic_attendance_update
from app.services.mechanic_time_service import fetch_tenant_and_mechanic, get_active_session, start_session, stop_active_session
from app.db.models.mechanic_time import MechanicSessionType
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
    QuickRepairOrderCreate,
    RepairOrderStartWorkResponse,
)

logger = get_logger(__name__)

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
    """Generate unique order number using MAX approach."""
    from app.core.unique_id import generate_unique_number
    return await generate_unique_number(
        db=db,
        model_class=RepairOrder,
        number_column=RepairOrder.order_number,
        tenant_id=tenant_id,
        prefix="RO-",
    )


@router.post("", response_model=RepairOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_repair_order(
    order_data: RepairOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
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
    
    # Use retry wrapper to handle rare race conditions on order number
    from app.core.unique_id import create_with_retry
    
    async def create_order_with_number(order_number: str) -> RepairOrder:
        repair_order = RepairOrder(
            tenant_id=current_user.tenant_id,
            order_number=order_number,
            status=RepairOrderStatus.DRAFT,
            **order_data.model_dump(),
        )
        db.add(repair_order)
        # Don't commit here - create_with_retry uses savepoints and handles commit
        return repair_order
    
    repair_order = await create_with_retry(
        db=db,
        create_fn=create_order_with_number,
        generate_number_fn=lambda: generate_order_number(db, current_user.tenant_id),
        entity_name="repair_order",
    )
    await db.refresh(repair_order)
    record_repair_order_created(str(current_user.tenant_id))
    
    return RepairOrderResponse.model_validate(repair_order)


@router.post("/quick", response_model=RepairOrderResponse, status_code=status.HTTP_201_CREATED)
async def quick_create_repair_order(
    data: QuickRepairOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    )),
):
    """Quick-create a repair order with minimal info. Auto-creates walk-in customer and vehicle."""
    try:
        tenant_id = current_user.tenant_id
        if not tenant_id:
            raise HTTPException(status_code=400, detail="User must be associated with a tenant")

        raw_phone = (data.phone or "").strip()
        # Normalize phone for consistent storage and lookup
        phone = normalize_phone(raw_phone) or ""

        # Find or create customer
        if phone:
            # Look for existing customer by phone in this tenant
            result = await db.execute(
                select(Customer).where(
                    and_(
                        Customer.tenant_id == tenant_id,
                        Customer.phone == phone,
                    )
                )
            )
            customer = result.scalar_one_or_none()
            if not customer:
                customer = Customer(
                    tenant_id=tenant_id,
                    first_name="Walk-in",
                    last_name=raw_phone or "Customer",  # Keep original format for display
                    email=f"walkin+{phone}@placeholder.truckpitstop.com",
                    phone=phone,  # Store normalized
                    source="walk_in",
                )
                db.add(customer)
                await db.flush()
        else:
            # Use or create a generic walk-in customer for this tenant
            # Use scalars().first() instead of scalar_one_or_none() to handle potential duplicates
            # from race conditions (no unique constraint on email+tenant_id)
            result = await db.execute(
                select(Customer).where(
                    and_(
                        Customer.tenant_id == tenant_id,
                        Customer.email == "walkin@placeholder.truckpitstop.com",
                    )
                ).limit(1)
            )
            customer = result.scalars().first()
            if not customer:
                customer = Customer(
                    tenant_id=tenant_id,
                    first_name="Walk-in",
                    last_name="Customer",
                    email="walkin@placeholder.truckpitstop.com",
                    source="walk_in",
                )
                db.add(customer)
                await db.flush()

        # Parse vehicle_description best-effort: "2019 Peterbilt 579" -> year=2019 make=Peterbilt model=579
        desc = data.vehicle_description.strip() if data.vehicle_description else ""
        parts = desc.split(None, 2) if desc else []
        year = None
        make = desc if desc else "Unknown"
        model = "N/A"

        if len(parts) >= 1 and parts[0].isdigit() and len(parts[0]) == 4:
            year = int(parts[0])
            if len(parts) >= 3:
                make = parts[1]
                model = parts[2]
            elif len(parts) == 2:
                make = parts[1]
                model = "N/A"
            else:
                make = "Unknown"
        elif len(parts) >= 2:
            make = parts[0]
            model = " ".join(parts[1:])

        vehicle = Vehicle(
            tenant_id=tenant_id,
            customer_id=customer.id,
            make=make,
            model=model,
            year=year,
        )
        db.add(vehicle)
        await db.flush()

        # Use retry wrapper to handle rare race conditions on order number
        from app.core.unique_id import create_with_retry
        
        async def create_order_with_number(order_number: str) -> RepairOrder:
            repair_order = RepairOrder(
                tenant_id=tenant_id,
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                order_number=order_number,
                status=RepairOrderStatus.DRAFT,
                description=data.complaint or None,
            )
            db.add(repair_order)
            # Don't commit here - create_with_retry uses savepoints and handles commit
            return repair_order
        
        repair_order = await create_with_retry(
            db=db,
            create_fn=create_order_with_number,
            generate_number_fn=lambda: generate_order_number(db, tenant_id),
            entity_name="repair_order",
        )
        await db.refresh(repair_order)
        record_repair_order_created(str(tenant_id))

        return RepairOrderResponse.model_validate(repair_order)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "quick_order_failed",
            error_type=type(e).__name__,
            error_message=str(e),
            traceback=traceback.format_exc(),
            phone=data.phone,
            vehicle_description=data.vehicle_description,
            complaint=data.complaint,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create order: {type(e).__name__}: {str(e)}"
        )


@router.get("", response_model=List[RepairOrderResponse])
async def list_repair_orders(
    customer_id: Optional[UUID] = Query(None),
    vehicle_id: Optional[UUID] = Query(None),
    status: Optional[RepairOrderStatus] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(RepairOrder)
    count_query = select(func.count(RepairOrder.id))
    
    if current_user.role == UserRole.CUSTOMER:
        # Customers can only see their own repair orders
        if not current_user.customer_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        query = query.where(RepairOrder.customer_id == current_user.customer_id)
        count_query = count_query.where(RepairOrder.customer_id == current_user.customer_id)
    else:
        # Staff can filter by customer/vehicle/status or see all in tenant
        if not current_user.tenant_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        query = query.where(RepairOrder.tenant_id == current_user.tenant_id)
        count_query = count_query.where(RepairOrder.tenant_id == current_user.tenant_id)
        if customer_id:
            query = query.where(RepairOrder.customer_id == customer_id)
            count_query = count_query.where(RepairOrder.customer_id == customer_id)
    
    if vehicle_id:
        query = query.where(RepairOrder.vehicle_id == vehicle_id)
        count_query = count_query.where(RepairOrder.vehicle_id == vehicle_id)
    if status:
        query = query.where(RepairOrder.status == status)
        count_query = count_query.where(RepairOrder.status == status)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(query.offset(skip).limit(limit).order_by(RepairOrder.created_at.desc()))
    orders = result.scalars().all()
    
    # Get quote_sent status for all orders
    order_ids = [o.id for o in orders]
    if order_ids:
        quote_result = await db.execute(
            select(Quote.repair_order_id, Quote.sent_to_customer)
            .where(Quote.repair_order_id.in_(order_ids))
        )
        quote_sent_map = {row[0]: row[1] for row in quote_result.fetchall()}

        invoice_result = await db.execute(
            select(Invoice.repair_order_id, Invoice.status, Invoice.zelle_pending_submitted_at)
            .where(Invoice.repair_order_id.in_(order_ids))
        )
        pending_zelle_map = {
            row[0]: (row[2] is not None and row[1] != InvoiceStatus.PAID)
            for row in invoice_result.fetchall()
        }
    else:
        quote_sent_map = {}
        pending_zelle_map = {}
    
    items = [
        RepairOrderResponse(
            **RepairOrderResponse.model_validate(o).model_dump(exclude={'quote_sent', 'pending_zelle_confirmation'}),
            quote_sent=quote_sent_map.get(o.id),
            pending_zelle_confirmation=pending_zelle_map.get(o.id, False),
        )
        for o in orders
    ]
    return paginated_or_list(items, total, skip, limit, paginated)


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

    invoice_result = await db.execute(
        select(Invoice).where(Invoice.repair_order_id == order.id).limit(1)
    )
    invoice = invoice_result.scalar_one_or_none()
    pending_zelle_confirmation = bool(
        invoice and invoice.zelle_pending_submitted_at is not None and invoice.status != InvoiceStatus.PAID
    )
    return RepairOrderDetailResponse(
        **RepairOrderResponse.model_validate(order).model_dump(exclude={'pending_zelle_confirmation'}),
        pending_zelle_confirmation=pending_zelle_confirmation,
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
    
    invoice_result = await db.execute(
        select(Invoice).where(Invoice.repair_order_id == order.id).limit(1)
    )
    invoice = invoice_result.scalar_one_or_none()
    pending_zelle_confirmation = bool(
        invoice and invoice.zelle_pending_submitted_at is not None and invoice.status != InvoiceStatus.PAID
    )

    return RepairOrderResponse(
        **RepairOrderResponse.model_validate(order).model_dump(exclude={'pending_zelle_confirmation'}),
        pending_zelle_confirmation=pending_zelle_confirmation,
    )


@router.put("/{order_id}", response_model=RepairOrderResponse)
async def update_repair_order(
    order_id: UUID,
    order_data: RepairOrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
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

    # Keep real-time clients in sync for status/workflow edits from the side panel.
    if "status" in update_data or "assigned_mechanic_id" in update_data:
        await broadcast_repair_order_update(
            tenant_id=str(order.tenant_id),
            customer_id=str(order.customer_id),
            order_id=str(order.id),
            order_number=order.order_number,
            status=order.status.value,
            updated_at=order.updated_at.isoformat() if order.updated_at else None,
        )
    
    return RepairOrderResponse.model_validate(order)


class AssignMechanicRequest(BaseModel):
    mechanic_id: UUID


@router.post("/{order_id}/assign-mechanic", response_model=RepairOrderResponse)
async def assign_mechanic(
    order_id: UUID,
    body: AssignMechanicRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
    )),
):
    """Assign/reassign mechanic, set status to assigned when needed, and notify mechanic."""
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
        if current_user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
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
    
    # Assign mechanic and update status
    order.assigned_mechanic_id = body.mechanic_id
    # Set status to ASSIGNED if still APPROVED (handles edge cases where previous assignment didn't update status)
    if order.status == RepairOrderStatus.APPROVED:
        order.status = RepairOrderStatus.ASSIGNED
    
    await db.commit()
    await db.refresh(order)
    
    # Broadcast WebSocket update
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
        hold_reason=order.hold_reason,
        held_at=order.held_at.isoformat() if order.held_at else None,
    )
    
    # Send email notification to MECHANIC (not customer - customer notified when work starts)
    vehicle = order.vehicle
    vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Vehicle"
    portal_url = f"{settings.FRONTEND_URL.rstrip('/')}/mechanic"
    
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
            <a href="{portal_url}" 
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

    if mechanic.phone:
        try:
            await send_sms(
                db=db,
                tenant_id=str(current_user.tenant_id),
                to=mechanic.phone,
                body=(
                    f"New job assigned: Order #{order.order_number} for {vehicle_info}. "
                    f"Portal: {portal_url} - Truck Pit Stop"
                ),
                template_name="job_assigned_sms",
            )
        except Exception:
            pass

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
    
    # Broadcast WebSocket update
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
        hold_reason=order.hold_reason,
        held_at=order.held_at.isoformat() if order.held_at else None,
    )
    
    return RepairOrderResponse.model_validate(order)


@router.post("/{order_id}/start-work", response_model=RepairOrderStartWorkResponse)
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
    
    resume_existing = False
    if order.status in (RepairOrderStatus.ASSIGNED, RepairOrderStatus.ACKNOWLEDGED):
        order.status = RepairOrderStatus.IN_PROGRESS
        order.work_started_at = datetime.now(timezone.utc)
    elif order.status == RepairOrderStatus.IN_PROGRESS:
        resume_existing = True
        if order.work_started_at is None:
            order.work_started_at = datetime.now(timezone.utc)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start work on job in '{order.status.value}' status",
        )

    # Auto-start mechanic repair-order timer (single active timer policy).
    started_session = None
    auto_clocked_in = False
    attendance_session_id: Optional[str] = None
    try:
        tenant, mechanic = await fetch_tenant_and_mechanic(
            db,
            tenant_id=order.tenant_id,
            mechanic_id=current_user.id,
        )
        started_session, auto_clocked_in, attendance_session_id = await start_session(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            session_type=MechanicSessionType.REPAIR_ORDER.value,
            repair_order_id=order.id,
            stop_previous_reason="auto_switch",
        )
    except Exception:
        # Don't block workflow transition if timer start fails.
        pass

    await db.commit()
    await db.refresh(order)
    
    # Broadcast WebSocket update
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
        hold_reason=order.hold_reason,
        held_at=order.held_at.isoformat() if order.held_at else None,
    )
    try:
        await broadcast_mechanic_timer_update(
            tenant_id=str(order.tenant_id),
            mechanic_id=str(current_user.id),
            session_id=str(started_session.id) if started_session else str(order.id),
            action="resume_from_repair_order" if resume_existing else "start_from_repair_order",
        )
        if auto_clocked_in and attendance_session_id:
            await broadcast_mechanic_attendance_update(
                tenant_id=str(order.tenant_id),
                mechanic_id=str(current_user.id),
                attendance_session_id=attendance_session_id,
                action="auto_clock_in",
            )
    except Exception:
        pass
    
    if not resume_existing:
        # Notify customer that work has started
        customer = order.customer
        if customer and customer.email:
            vehicle = order.vehicle
            vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "your vehicle"
            
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
        
        # SMS notification
        if customer and customer.phone:
            vehicle = order.vehicle
            vi = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "your vehicle"
            try:
                await send_sms(
                    db,
                    str(order.tenant_id),
                    customer.phone,
                    f"Work has started on your {vi}. Order #{order.order_number}. We'll text you when it's done. - Truck Pit Stop",
                    template_name="work_started_sms",
                    customer_id=customer.id,
                    source="automated",
                )
            except Exception:
                pass  # Don't fail the request if SMS fails
    
    return RepairOrderStartWorkResponse(
        **RepairOrderResponse.model_validate(order).model_dump(),
        auto_clocked_in=auto_clocked_in,
    )


HOLD_REASONS = [
    "waiting_for_parts",
    "waiting_for_customer_approval",
    "need_more_info",
    "other",
]


class HoldRequest(BaseModel):
    reason: str


@router.post("/{order_id}/hold", response_model=RepairOrderResponse)
async def hold_repair_order(
    order_id: UUID,
    body: HoldRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic puts an in-progress RO on hold (waiting for parts, customer approval, etc.)"""
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    if order.status != RepairOrderStatus.IN_PROGRESS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot hold job in '{order.status.value}' status")
    if order.hold_reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is already on hold")

    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hold reason is required")

    order.hold_reason = reason
    order.held_at = datetime.now(timezone.utc)

    # Auto-stop the active RO timer for this order.
    stopped_session = None
    active_session = await get_active_session(db, tenant_id=order.tenant_id, mechanic_id=current_user.id)
    if (
        active_session
        and (active_session.session_type.value if hasattr(active_session.session_type, "value") else active_session.session_type)
        == MechanicSessionType.REPAIR_ORDER.value
        and active_session.repair_order_id == order.id
    ):
        stopped_session = await stop_active_session(
            db,
            tenant_id=order.tenant_id,
            mechanic_id=current_user.id,
            actor_user=current_user,
            stop_reason="hold",
        )

    await db.commit()
    await db.refresh(order)

    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
        hold_reason=order.hold_reason,
        held_at=order.held_at.isoformat() if order.held_at else None,
    )
    try:
        await broadcast_mechanic_timer_update(
            tenant_id=str(order.tenant_id),
            mechanic_id=str(current_user.id),
            session_id=str(stopped_session.id) if stopped_session else str(order.id),
            action="hold_repair_order",
        )
    except Exception:
        pass

    return RepairOrderResponse.model_validate(order)


@router.post("/{order_id}/resume", response_model=RepairOrderStartWorkResponse)
async def resume_repair_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic resumes a held RO — clears hold state and restarts the timer."""
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
    if order.status != RepairOrderStatus.IN_PROGRESS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot resume job in '{order.status.value}' status")
    if not order.hold_reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is not on hold")

    order.hold_reason = None
    order.held_at = None

    # Restart the RO timer.
    started_session = None
    auto_clocked_in = False
    attendance_session_id: Optional[str] = None
    try:
        tenant, mechanic = await fetch_tenant_and_mechanic(db, tenant_id=order.tenant_id, mechanic_id=current_user.id)
        started_session, auto_clocked_in, attendance_session_id = await start_session(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            session_type=MechanicSessionType.REPAIR_ORDER.value,
            repair_order_id=order.id,
            stop_previous_reason="resume_from_hold",
        )
    except Exception:
        pass

    await db.commit()
    await db.refresh(order)

    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
        hold_reason=order.hold_reason,
        held_at=order.held_at.isoformat() if order.held_at else None,
    )
    try:
        await broadcast_mechanic_timer_update(
            tenant_id=str(order.tenant_id),
            mechanic_id=str(current_user.id),
            session_id=str(started_session.id) if started_session else str(order.id),
            action="resume_from_hold",
        )
        if auto_clocked_in and attendance_session_id:
            await broadcast_mechanic_attendance_update(
                tenant_id=str(order.tenant_id),
                mechanic_id=str(current_user.id),
                attendance_session_id=attendance_session_id,
                action="auto_clock_in",
            )
    except Exception:
        pass

    return RepairOrderStartWorkResponse(
        **RepairOrderResponse.model_validate(order).model_dump(),
        auto_clocked_in=auto_clocked_in,
    )


@router.post("/{order_id}/complete-work", response_model=RepairOrderResponse)
async def complete_work(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic marks work as complete - awards points and notifies manager"""
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
    
    if order.status != RepairOrderStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete job in '{order.status.value}' status",
        )
    
    order.status = RepairOrderStatus.PENDING_REVIEW
    order.work_completed_at = datetime.now(timezone.utc)
    # Clear hold state if completing from hold
    order.hold_reason = None
    order.held_at = None

    # Auto-stop active repair-order timer for this work order when work completes.
    stopped_session = None
    try:
        active_session = await get_active_session(
            db,
            tenant_id=order.tenant_id,
            mechanic_id=current_user.id,
        )
        if (
            active_session
            and (active_session.session_type.value if hasattr(active_session.session_type, "value") else active_session.session_type)
            == MechanicSessionType.REPAIR_ORDER.value
            and active_session.repair_order_id == order.id
        ):
            stopped_session = await stop_active_session(
                db,
                tenant_id=order.tenant_id,
                mechanic_id=current_user.id,
                actor_user=current_user,
                stop_reason="auto_complete_work",
            )
    except Exception:
        pass
    
    # ============ AWARD POINTS ============
    # Points = job value (1 point per $1)
    # Use service prices from internal_notes if available, else total_labor_cost
    labor_value = float(order.total_labor_cost or 0)
    
    # Check for services in internal_notes (quote-based orders with service menu prices)
    if order.internal_notes:
        try:
            import json
            notes_data = json.loads(order.internal_notes)
            selected_services = notes_data.get("selected_services", [])
            if selected_services:
                service_total = sum(
                    float(svc.get("base_price", 0))
                    for svc in selected_services
                )
                if service_total > labor_value:
                    labor_value = service_total
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    
    # Get or create balance record
    result = await db.execute(
        select(MechanicPointsBalance).where(
            MechanicPointsBalance.mechanic_id == current_user.id
        )
    )
    balance = result.scalar_one_or_none()
    
    if not balance:
        balance = MechanicPointsBalance(
            tenant_id=current_user.tenant_id,
            mechanic_id=current_user.id,
            available_points=0,
            total_earned=0,
            total_redeemed=0,
            current_streak_days=0,
        )
        db.add(balance)
    
    # Calculate streak multiplier
    today = date.today()
    multiplier = Decimal("1.00")
    
    if balance.last_work_date:
        last_work = balance.last_work_date.date() if hasattr(balance.last_work_date, 'date') else balance.last_work_date
        days_since = (today - last_work).days
        
        if days_since == 0:
            # Same day, keep streak
            pass
        elif days_since == 1:
            # Consecutive day, increment streak
            balance.current_streak_days += 1
        else:
            # Streak broken
            balance.current_streak_days = 1
    else:
        balance.current_streak_days = 1
    
    balance.last_work_date = today
    
    # Apply streak bonus
    if balance.current_streak_days >= 10:
        multiplier = Decimal("1.25")  # 25% bonus after 10 days
    elif balance.current_streak_days >= 5:
        multiplier = Decimal("1.10")  # 10% bonus after 5 days
    
    # Calculate final points
    base_points = int(labor_value)  # 1 point per $1 labor
    final_points = int(base_points * float(multiplier))
    
    # Minimum 10 points per job (even if no labor recorded yet)
    if final_points < 10:
        final_points = 10
        labor_value = 10.0
    
    # Create points transaction
    points_tx = MechanicPoints(
        tenant_id=current_user.tenant_id,
        mechanic_id=current_user.id,
        transaction_type=PointsTransactionType.EARNED,
        points=final_points,
        repair_order_id=order.id,
        labor_value=Decimal(str(labor_value)),
        multiplier=multiplier,
        notes=f"Completed {order.order_number}" + (f" (streak x{multiplier})" if multiplier > 1 else ""),
    )
    db.add(points_tx)
    
    # Update balance
    balance.available_points += final_points
    balance.total_earned += final_points
    
    await db.commit()
    await db.refresh(order)
    
    # Broadcast WebSocket update
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )
    try:
        await broadcast_mechanic_timer_update(
            tenant_id=str(order.tenant_id),
            mechanic_id=str(current_user.id),
            session_id=str(stopped_session.id) if stopped_session else str(order.id),
            action="stop_from_repair_order",
        )
    except Exception:
        pass
    
    # Notify managers that work is ready for review
    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == order.tenant_id,
                User.role.in_([UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN]),
                User.is_active == True,
            )
        )
    )
    managers = result.scalars().all()
    
    vehicle = order.vehicle
    vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Vehicle"
    
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
    
    # SMS to customer: work is done, under review
    customer = order.customer
    if customer and customer.phone:
        vehicle = order.vehicle
        vi = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "your vehicle"
        try:
            await send_sms(
                db,
                str(order.tenant_id),
                customer.phone,
                f"Repair on your {vi} is complete and under review. Order #{order.order_number}. - Truck Pit Stop",
                template_name="work_complete_sms",
                customer_id=customer.id,
                source="automated",
            )
        except Exception:
            pass
    
    return RepairOrderResponse.model_validate(order)


class ApproveCompletionRequest(BaseModel):
    review_notes: Optional[str] = None


@router.post("/{order_id}/approve-completion", response_model=RepairOrderResponse)
async def approve_completion(
    order_id: UUID,
    body: Optional[ApproveCompletionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
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
    
    # Append review notes to internal_notes if provided
    if body and body.review_notes:
        import json
        from datetime import datetime
        review_entry = {
            "type": "manager_review",
            "notes": body.review_notes,
            "reviewed_by": f"{current_user.first_name} {current_user.last_name}",
            "reviewed_at": datetime.utcnow().isoformat(),
        }
        try:
            existing_notes = json.loads(order.internal_notes) if order.internal_notes else {}
        except json.JSONDecodeError:
            existing_notes = {"raw_notes": order.internal_notes}
        
        if "reviews" not in existing_notes:
            existing_notes["reviews"] = []
        existing_notes["reviews"].append(review_entry)
        order.internal_notes = json.dumps(existing_notes)
    
    await db.commit()
    await db.refresh(order)
    
    # Broadcast WebSocket update
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )
    
    # Notify customer that work is complete
    customer = order.customer
    if customer and customer.email:
        vehicle = order.vehicle
        vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "your vehicle"
        
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
    
    # SMS: ready for pickup
    if customer and customer.phone:
        vehicle = order.vehicle
        vi = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "your vehicle"
        try:
            await send_sms(
                db,
                str(order.tenant_id),
                customer.phone,
                f"Your {vi} is ready for pickup! Order #{order.order_number}. Invoice will follow shortly. - Truck Pit Stop",
                template_name="ready_pickup_sms",
                customer_id=customer.id,
                source="automated",
            )
        except Exception:
            pass
    
    return RepairOrderResponse.model_validate(order)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repair_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
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

    # Save identifiers before deletion so we can broadcast cache invalidation.
    tenant_id = str(order.tenant_id)
    customer_id = str(order.customer_id)
    order_id_str = str(order.id)
    order_number = order.order_number

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

    # Broadcast deletion so dashboards/lists update without manual refresh.
    await broadcast_repair_order_update(
        tenant_id=tenant_id,
        customer_id=customer_id,
        order_id=order_id_str,
        order_number=order_number,
        status="deleted",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

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
        UserRole.GARAGE_OWNER,
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
        unit_cost=inv.cost,
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
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)

    total_result = await db.execute(
        select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id == order_id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(PartsUsage)
        .where(PartsUsage.repair_order_id == order_id)
        .options(selectinload(PartsUsage.inventory_item))
        .order_by(PartsUsage.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    parts_usage = result.scalars().all()

    out = []
    for pu in parts_usage:
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
    return paginated_or_list(out, total, skip, limit, paginated)


@router.delete("/{order_id}/parts/{parts_usage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_parts_from_repair_order(
    order_id: UUID,
    parts_usage_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
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
        UserRole.GARAGE_OWNER,
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
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(RepairOrder).where(RepairOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repair order not found")
    _check_ro_access(current_user, order)

    total_result = await db.execute(
        select(func.count(Labor.id)).where(Labor.repair_order_id == order_id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(Labor)
        .where(Labor.repair_order_id == order_id)
        .order_by(Labor.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    labor_items = result.scalars().all()
    items = [LaborResponse.model_validate(li) for li in labor_items]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.put("/{order_id}/labor/{labor_id}", response_model=LaborResponse)
async def update_repair_order_labor(
    order_id: UUID,
    labor_id: UUID,
    body: LaborUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
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
        UserRole.GARAGE_OWNER,
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
