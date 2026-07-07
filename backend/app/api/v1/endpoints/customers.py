from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.phone import normalize_phone
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder
from app.db.models.inventory import PartsUsage
from app.db.models.labor import Labor
from app.db.models.appointment import Appointment
from app.db.models.invoice import Invoice
from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse, CustomerWithVehiclesResponse
from app.schemas.vehicle import VehicleBase, VehicleUpdate, VehicleResponse
from app.services.vehicle_nhtsa_service import sync_vehicle_nhtsa_snapshot
from app.services.vin_decoder_service import decode_vin, VINDecodeResult

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


@router.post("", response_model=CustomerWithVehiclesResponse, status_code=status.HTTP_201_CREATED)
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
    
    # Require either a vehicle or explicit no_vehicle flag
    if not customer_data.initial_vehicle and not customer_data.no_vehicle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer must have a vehicle or 'no_vehicle' must be set to true",
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
    
    # Extract customer fields only (exclude vehicle data)
    customer_fields = customer_data.model_dump(exclude={'initial_vehicle', 'no_vehicle'})
    customer_fields["phone"] = normalize_phone(customer_fields.get("phone"))
    if "company_name" in customer_fields:
        company = (customer_fields.get("company_name") or "").strip()
        customer_fields["company_name"] = company or None
    customer = Customer(
        tenant_id=current_user.tenant_id,
        **customer_fields,
    )
    
    db.add(customer)
    await db.flush()  # Get customer.id before creating vehicle
    
    # Create initial vehicle if provided
    if customer_data.initial_vehicle:
        vehicle = Vehicle(
            tenant_id=current_user.tenant_id,
            customer_id=customer.id,
            **customer_data.initial_vehicle.model_dump(),
        )
        await sync_vehicle_nhtsa_snapshot(vehicle)
        db.add(vehicle)
    
    await db.commit()
    
    # Reload with vehicles
    result = await db.execute(
        select(Customer)
        .options(selectinload(Customer.vehicles))
        .where(Customer.id == customer.id)
    )
    customer = result.scalar_one()
    
    return CustomerWithVehiclesResponse.model_validate(customer)


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
    
    # The internal-fleet house account is managed via the dedicated fleet view,
    # not listed among real customers.
    base_filter = and_(
        Customer.tenant_id == current_user.tenant_id,
        Customer.is_internal_fleet.is_(False),
    )
    total_result = await db.execute(
        select(func.count(Customer.id)).where(base_filter)
    )
    total = total_result.scalar() or 0
    result = await db.execute(select(Customer).where(base_filter).offset(skip).limit(limit))
    customers = result.scalars().all()
    items = [CustomerResponse.model_validate(c) for c in customers]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.get("/internal-fleet", response_model=CustomerResponse)
async def get_internal_fleet_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.FLEET_MANAGER,
    )),
):
    """Return the tenant's internal-fleet house account (the garage's own trucks)."""
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )
    from app.services.internal_fleet import ensure_internal_fleet_customer
    customer = await ensure_internal_fleet_customer(db, current_user.tenant_id)
    await db.commit()
    return CustomerResponse.model_validate(customer)


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
    if "phone" in update_data:
        update_data["phone"] = normalize_phone(update_data["phone"])
    if "company_name" in update_data:
        company = (update_data.get("company_name") or "").strip()
        update_data["company_name"] = company or None
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

    # Delete vehicles explicitly so this endpoint does not rely on ORM cascade behavior.
    vehicles_result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.customer_id == customer_id,
                Vehicle.tenant_id == customer.tenant_id,
            )
        )
    )
    vehicles = vehicles_result.scalars().all()
    for vehicle in vehicles:
        await db.delete(vehicle)

    try:
        await db.delete(customer)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete customer due to related records",
        )

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
    await sync_vehicle_nhtsa_snapshot(vehicle)
    
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

    if {"vin", "year"} & set(update_data.keys()) or (vehicle.vin and vehicle.nhtsa_decoded_at is None):
        await sync_vehicle_nhtsa_snapshot(vehicle)
    
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


# ============================================================================
# CUSTOMER HISTORY
# ============================================================================

@router.get("/{customer_id}/history")
async def get_customer_history(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return lifetime activity for a customer: per-RO summary + aggregate stats
    (total spend, lifetime savings, RO count)."""

    # Access check
    customer_row = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = customer_row.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user.tenant_id != customer.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Fetch all ROs for this customer (with vehicle joined for display fields)
    orders_result = await db.execute(
        select(RepairOrder)
        .options(selectinload(RepairOrder.vehicle))
        .where(RepairOrder.customer_id == customer_id, RepairOrder.deleted_at.is_(None))
        .order_by(RepairOrder.created_at.desc())
    )
    orders = orders_result.scalars().all()
    order_ids = [o.id for o in orders]

    # Aggregate savings per RO via parts_usage (list_price - unit_price) * quantity
    savings_by_order: dict = {}
    if order_ids:
        parts_result = await db.execute(
            select(
                PartsUsage.repair_order_id,
                func.coalesce(
                    func.sum(
                        (func.coalesce(PartsUsage.list_price, PartsUsage.unit_price) - PartsUsage.unit_price)
                        * PartsUsage.quantity
                    ),
                    0,
                ),
            )
            .where(PartsUsage.repair_order_id.in_(order_ids))
            .group_by(PartsUsage.repair_order_id)
        )
        for ro_id, saving in parts_result.all():
            savings_by_order[ro_id] = float(saving or 0)

    completed_statuses = {"completed", "invoiced", "paid"}

    items = []
    lifetime_savings = 0.0
    lifetime_spend = 0.0
    completed_count = 0
    for o in orders:
        saving = savings_by_order.get(o.id, 0.0)
        total = float(o.total_cost or 0)
        is_completed = o.status.value if hasattr(o.status, "value") else str(o.status)
        if is_completed in completed_statuses:
            completed_count += 1
            lifetime_spend += total
            lifetime_savings += saving
        v = o.vehicle
        items.append({
            "id": str(o.id),
            "order_number": o.order_number,
            "status": is_completed,
            "vehicle_make": v.make if v else "",
            "vehicle_model": v.model if v else "",
            "vehicle_year": v.year if v else None,
            "vehicle_unit_number": v.unit_number if v else None,
            "total_cost": f"{total:.2f}",
            "savings": f"{saving:.2f}",
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "work_completed_at": o.work_completed_at.isoformat() if o.work_completed_at else None,
        })

    return {
        "items": items,
        "stats": {
            "total_orders": len(orders),
            "completed_orders": completed_count,
            "lifetime_spend": f"{lifetime_spend:.2f}",
            "lifetime_savings": f"{lifetime_savings:.2f}",
        },
    }


@router.get("/{customer_id}/history/{order_id}")
async def get_customer_history_detail(
    customer_id: UUID,
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Compact detail for a single RO in customer history: labor, parts, mechanic,
    amount paid, notes."""

    result = await db.execute(
        select(RepairOrder)
        .where(and_(
            RepairOrder.id == order_id,
            RepairOrder.customer_id == customer_id,
            RepairOrder.deleted_at.is_(None),
        ))
        .options(
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
            selectinload(RepairOrder.labor_items),
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Repair order not found")
    if current_user.role == UserRole.CUSTOMER:
        if current_user.customer_id != customer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user.tenant_id != order.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    mechanic_name = None
    if order.assigned_mechanic_id:
        mech_row = await db.execute(select(User).where(User.id == order.assigned_mechanic_id))
        mech = mech_row.scalar_one_or_none()
        if mech:
            mechanic_name = f"{mech.first_name} {mech.last_name}".strip()

    invoice_row = await db.execute(
        select(Invoice).where(Invoice.repair_order_id == order.id).limit(1)
    )
    invoice = invoice_row.scalar_one_or_none()
    amount_paid = None
    if invoice and invoice.paid_at is not None:
        amount_paid = f"{float(invoice.total_amount or 0):.2f}"

    labor = [
        {
            "id": str(li.id),
            "description": li.description,
            "hours": f"{float(li.hours or 0):.2f}",
            "hourly_rate": f"{float(li.hourly_rate or 0):.2f}",
            "total_cost": f"{float(li.total_cost or 0):.2f}",
        }
        for li in order.labor_items
    ]
    parts = [
        {
            "id": str(pu.id),
            "name": pu.inventory_item.name if pu.inventory_item else None,
            "sku": pu.inventory_item.sku if pu.inventory_item else None,
            "quantity": pu.quantity,
            "unit_price": f"{float(pu.unit_price or 0):.2f}",
            "total_price": f"{float(pu.total_price or 0):.2f}",
        }
        for pu in order.parts_usage
    ]

    return {
        "id": str(order.id),
        "order_number": order.order_number,
        "mechanic_name": mechanic_name,
        "amount_paid": amount_paid,
        "total_cost": f"{float(order.total_cost or 0):.2f}",
        "customer_notes": order.customer_notes,
        "internal_notes": order.internal_notes,
        "labor": labor,
        "parts": parts,
    }


# ============================================================================
# VIN DECODER ENDPOINT
# ============================================================================

@router.get("/vin/decode/{vin}", response_model=VINDecodeResult)
async def decode_vehicle_vin(
    vin: str,
    model_year: Optional[int] = Query(None, description="Optional model year for better accuracy"),
    current_user: User = Depends(get_current_active_user),
):
    """
    Decode a VIN using the free NHTSA vPIC API.
    Returns vehicle make, model, year, and other specifications.
    """
    try:
        result = await decode_vin(vin, model_year)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to decode VIN: {str(e)}",
        )
