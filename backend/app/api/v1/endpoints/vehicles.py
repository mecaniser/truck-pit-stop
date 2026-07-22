from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, exists, func, or_
from sqlalchemy.orm import selectinload
from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.phone import normalize_phone
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.customer import Customer
from app.db.models.vehicle_relationship import FleetMembership, VehicleCustomerRelationship
from app.schemas.vehicle import (
    VehicleCreate,
    VehicleUpdate,
    VehicleCustomerUpdate,
    VehicleRelationshipCreate,
    VehicleRelationshipResponse,
    VehicleRelationshipSync,
    VehicleResponse,
)
from app.schemas.typeahead import VehicleTypeaheadResponse
from app.services.vehicle_nhtsa_service import sync_vehicle_nhtsa_snapshot
from app.services.vehicle_identity import (
    end_fleet_membership,
    ensure_fleet_membership,
    ensure_vehicle_relationship,
    find_vehicle_by_vin,
    normalize_vin,
    seed_vehicle_account_relationships,
)

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

    # Fleet managers can create a truck only for a company already participating
    # in fleet operations. The dedicated Fleet endpoint can enroll a company.
    if current_user.role == UserRole.FLEET_MANAGER and not customer.fleet_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Fleet managers can only manage fleet-enabled companies",
        )

    create_data = vehicle_data.model_dump(exclude={"customer_id"})
    create_data["vin"] = normalize_vin(create_data.get("vin"))
    duplicate = await find_vehicle_by_vin(db, customer.tenant_id, create_data.get("vin"))
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This VIN already belongs to truck {duplicate.id}. Link the existing truck instead of creating a duplicate.",
        )
    if "driver_phone" in create_data:
        create_data["driver_phone"] = normalize_phone(create_data["driver_phone"])

    vehicle = Vehicle(
        tenant_id=customer.tenant_id,
        customer_id=vehicle_data.customer_id,
        **create_data,
    )
    await sync_vehicle_nhtsa_snapshot(vehicle)
    
    db.add(vehicle)
    await db.flush()
    await seed_vehicle_account_relationships(db, vehicle, customer)
    if customer.fleet_enabled:
        await ensure_fleet_membership(
            db,
            tenant_id=customer.tenant_id,
            vehicle_id=vehicle.id,
            fleet_customer_id=customer.id,
        )
    await db.commit()
    await db.refresh(vehicle)
    
    return VehicleResponse.model_validate(vehicle)


@router.get("/{vehicle_id}/relationships", response_model=List[VehicleRelationshipResponse])
async def list_vehicle_relationships(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    vehicle = (await db.execute(select(Vehicle).where(
        Vehicle.id == vehicle_id,
        Vehicle.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    if current_user.tenant_id != vehicle.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if current_user.role == UserRole.CUSTOMER:
        linked = (await db.execute(select(exists(select(VehicleCustomerRelationship.id).where(
            VehicleCustomerRelationship.vehicle_id == vehicle.id,
            VehicleCustomerRelationship.customer_id == current_user.customer_id,
            VehicleCustomerRelationship.effective_to.is_(None),
            VehicleCustomerRelationship.deleted_at.is_(None),
        ))))).scalar()
        if vehicle.customer_id != current_user.customer_id and not linked:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    rows = (await db.execute(
        select(VehicleCustomerRelationship, Customer)
        .join(Customer, Customer.id == VehicleCustomerRelationship.customer_id)
        .where(
            VehicleCustomerRelationship.vehicle_id == vehicle.id,
            VehicleCustomerRelationship.tenant_id == vehicle.tenant_id,
            VehicleCustomerRelationship.deleted_at.is_(None),
        )
        .order_by(
            VehicleCustomerRelationship.effective_to.is_(None).desc(),
            VehicleCustomerRelationship.effective_from.desc(),
        )
    )).all()
    return [
        VehicleRelationshipResponse(
            id=relationship.id,
            vehicle_id=relationship.vehicle_id,
            customer_id=relationship.customer_id,
            relationship_type=relationship.relationship_type,
            effective_from=relationship.effective_from,
            effective_to=relationship.effective_to,
            is_primary=relationship.is_primary,
            customer_company_name=(customer.company_name or f"{customer.first_name} {customer.last_name}".strip()),
        )
        for relationship, customer in rows
    ]


@router.post("/{vehicle_id}/relationships", response_model=VehicleRelationshipResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle_relationship(
    vehicle_id: UUID,
    body: VehicleRelationshipCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.FLEET_MANAGER,
    )),
):
    vehicle = (await db.execute(select(Vehicle).where(
        Vehicle.id == vehicle_id,
        Vehicle.tenant_id == current_user.tenant_id,
        Vehicle.deleted_at.is_(None),
    ))).scalar_one_or_none()
    customer = (await db.execute(select(Customer).where(
        Customer.id == body.customer_id,
        Customer.tenant_id == current_user.tenant_id,
        Customer.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not vehicle or not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Truck or company not found")
    if current_user.role == UserRole.FLEET_MANAGER and body.relationship_type == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only shop administrators can record an ownership transfer",
        )

    if body.replace_primary:
        now = datetime.now(timezone.utc)
        current_rows = list((await db.execute(select(VehicleCustomerRelationship).where(
            VehicleCustomerRelationship.vehicle_id == vehicle.id,
            VehicleCustomerRelationship.relationship_type == body.relationship_type,
            VehicleCustomerRelationship.is_primary.is_(True),
            VehicleCustomerRelationship.effective_to.is_(None),
            VehicleCustomerRelationship.deleted_at.is_(None),
        ))).scalars().all())
        for current in current_rows:
            current.effective_to = now
            current.is_primary = False

    relationship = await ensure_vehicle_relationship(
        db,
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        customer_id=customer.id,
        relationship_type=body.relationship_type,
        is_primary=body.is_primary or body.replace_primary,
    )
    if body.relationship_type == "owner" and (body.is_primary or body.replace_primary):
        # Compatibility pointer for old customer-specific screens. Historical
        # repair orders retain their own customer_id and are never rewritten.
        vehicle.customer_id = customer.id
    if body.relationship_type == "operator" and customer.fleet_enabled:
        # Linking a truck to a fleet-enabled company from the main dashboard
        # must be reciprocal with Fleet Board's "Link existing truck" flow.
        await ensure_fleet_membership(
            db,
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            fleet_customer_id=customer.id,
        )
    await db.commit()
    await db.refresh(relationship)
    return VehicleRelationshipResponse(
        id=relationship.id,
        vehicle_id=relationship.vehicle_id,
        customer_id=relationship.customer_id,
        relationship_type=relationship.relationship_type,
        effective_from=relationship.effective_from,
        effective_to=relationship.effective_to,
        is_primary=relationship.is_primary,
        customer_company_name=(customer.company_name or f"{customer.first_name} {customer.last_name}".strip()),
    )


@router.put("/{vehicle_id}/relationships", response_model=VehicleResponse)
async def sync_vehicle_relationships(
    vehicle_id: UUID,
    body: VehicleRelationshipSync,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.FLEET_MANAGER,
    )),
):
    """Relink a truck to one company while retaining dated relationship history."""
    vehicle = (await db.execute(select(Vehicle).where(
        Vehicle.id == vehicle_id,
        Vehicle.tenant_id == current_user.tenant_id,
        Vehicle.deleted_at.is_(None),
    ))).scalar_one_or_none()
    customer = (await db.execute(select(Customer).where(
        Customer.id == body.customer_id,
        Customer.tenant_id == current_user.tenant_id,
        Customer.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not vehicle or not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Truck or company not found")

    desired = set(body.relationship_types)
    if current_user.role == UserRole.FLEET_MANAGER and "owner" in desired:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only shop administrators can record an ownership transfer",
        )

    now = datetime.now(timezone.utc)
    active = list((await db.execute(select(VehicleCustomerRelationship).where(
        VehicleCustomerRelationship.tenant_id == current_user.tenant_id,
        VehicleCustomerRelationship.vehicle_id == vehicle.id,
        VehicleCustomerRelationship.effective_to.is_(None),
        VehicleCustomerRelationship.deleted_at.is_(None),
    ))).scalars().all())
    selected_active = [row for row in active if row.customer_id == customer.id]

    # Removing the only current owner would leave the compatibility pointer and
    # customer screens ambiguous. Assign the replacement owner first; that same
    # save automatically closes the previous ownership period.
    removing_selected_owner = any(
        row.relationship_type == "owner" for row in selected_active
    ) and "owner" not in desired
    if removing_selected_owner:
        replacement_owners = [
            row for row in active
            if row.relationship_type == "owner" and row.customer_id != customer.id
        ]
        if not replacement_owners:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Assign a replacement owner before unlinking the truck's only owner",
            )
        replacement = sorted(
            replacement_owners,
            key=lambda row: (not row.is_primary, row.effective_from),
        )[0]
        replacement.is_primary = True
        vehicle.customer_id = replacement.customer_id

    for relationship in selected_active:
        if relationship.relationship_type in desired:
            continue
        relationship.effective_to = now
        relationship.is_primary = False
        if relationship.relationship_type == "operator":
            await end_fleet_membership(
                db,
                tenant_id=current_user.tenant_id,
                vehicle_id=vehicle.id,
                fleet_customer_id=customer.id,
            )

    if "owner" in desired:
        for relationship in active:
            if relationship.relationship_type == "owner" and relationship.customer_id != customer.id:
                relationship.effective_to = now
                relationship.is_primary = False
        await ensure_vehicle_relationship(
            db,
            tenant_id=current_user.tenant_id,
            vehicle_id=vehicle.id,
            customer_id=customer.id,
            relationship_type="owner",
            is_primary=True,
        )
        vehicle.customer_id = customer.id

    if "default_payer" in desired:
        for relationship in active:
            if relationship.relationship_type == "default_payer" and relationship.customer_id != customer.id:
                relationship.effective_to = now
                relationship.is_primary = False
        await ensure_vehicle_relationship(
            db,
            tenant_id=current_user.tenant_id,
            vehicle_id=vehicle.id,
            customer_id=customer.id,
            relationship_type="default_payer",
            is_primary=True,
        )

    if "operator" in desired:
        customer.fleet_enabled = True
        await ensure_fleet_membership(
            db,
            tenant_id=current_user.tenant_id,
            vehicle_id=vehicle.id,
            fleet_customer_id=customer.id,
        )

    if "unit_number" in body.model_fields_set:
        vehicle.unit_number = (body.unit_number or "").strip() or None

    await db.commit()
    await db.refresh(vehicle)
    return VehicleResponse.model_validate(vehicle)


@router.delete("/{vehicle_id}/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_vehicle_relationship(
    vehicle_id: UUID,
    relationship_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.FLEET_MANAGER,
    )),
):
    """End one active truck/company link without deleting its history."""
    relationship = (await db.execute(select(VehicleCustomerRelationship).where(
        VehicleCustomerRelationship.id == relationship_id,
        VehicleCustomerRelationship.vehicle_id == vehicle_id,
        VehicleCustomerRelationship.tenant_id == current_user.tenant_id,
        VehicleCustomerRelationship.effective_to.is_(None),
        VehicleCustomerRelationship.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not relationship:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active truck relationship not found")
    if current_user.role == UserRole.FLEET_MANAGER and relationship.relationship_type == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only shop administrators can change truck ownership",
        )

    vehicle = (await db.execute(select(Vehicle).where(
        Vehicle.id == vehicle_id,
        Vehicle.tenant_id == current_user.tenant_id,
        Vehicle.deleted_at.is_(None),
    ))).scalar_one()
    if relationship.relationship_type == "owner":
        replacements = list((await db.execute(select(VehicleCustomerRelationship).where(
            VehicleCustomerRelationship.vehicle_id == vehicle_id,
            VehicleCustomerRelationship.relationship_type == "owner",
            VehicleCustomerRelationship.id != relationship.id,
            VehicleCustomerRelationship.effective_to.is_(None),
            VehicleCustomerRelationship.deleted_at.is_(None),
        ).order_by(
            VehicleCustomerRelationship.is_primary.desc(),
            VehicleCustomerRelationship.effective_from.desc(),
        ))).scalars().all())
        if not replacements:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Assign a replacement owner before unlinking the truck's only owner",
            )
        replacements[0].is_primary = True
        vehicle.customer_id = replacements[0].customer_id
    elif relationship.relationship_type == "operator":
        await end_fleet_membership(
            db,
            tenant_id=current_user.tenant_id,
            vehicle_id=vehicle_id,
            fleet_customer_id=relationship.customer_id,
        )

    relationship.effective_to = datetime.now(timezone.utc)
    relationship.is_primary = False
    await db.commit()


@router.get("", response_model=List[VehicleResponse])
async def list_vehicles(
    customer_id: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = select(Vehicle)
    
    if current_user.role == UserRole.CUSTOMER:
        # Customers can only see their own vehicles
        if not current_user.customer_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        query = query.where(Vehicle.customer_id == current_user.customer_id)
    else:
        # Staff can filter by customer or see all in tenant
        if not current_user.tenant_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        query = query.where(Vehicle.tenant_id == current_user.tenant_id)
        if customer_id:
            query = query.where(Vehicle.customer_id == customer_id)
    
    count_query = select(func.count(Vehicle.id))
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        count_query = count_query.where(Vehicle.customer_id == current_user.customer_id)
    else:
        if not current_user.tenant_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        count_query = count_query.where(Vehicle.tenant_id == current_user.tenant_id)
        if customer_id:
            count_query = count_query.where(Vehicle.customer_id == customer_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    result = await db.execute(query.offset(skip).limit(limit))
    vehicles = result.scalars().all()
    items = [VehicleResponse.model_validate(v) for v in vehicles]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.get("/typeahead", response_model=List[VehicleTypeaheadResponse])
async def vehicle_typeahead(
    q: Optional[str] = Query(None, max_length=100, description="Match vehicle unit, VIN, plate, make, or model"),
    customer_id: Optional[UUID] = Query(None, description="Restrict results to a selected customer"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return a small, capped vehicle picker payload for the RO workspace.

    Joining the parent customer lets this lookup exclude soft-deleted parent
    records and enforce fleet-manager scope in the same database query.
    """
    filters = [Vehicle.deleted_at.is_(None), Customer.deleted_at.is_(None)]

    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id:
            return []
        filters.append(Vehicle.customer_id == current_user.customer_id)
    else:
        if not current_user.tenant_id:
            return []
        filters.append(Vehicle.tenant_id == current_user.tenant_id)
        if current_user.role == UserRole.FLEET_MANAGER:
            filters.append(or_(
                Customer.is_internal_fleet.is_(True),
                exists(select(FleetMembership.id).where(
                    FleetMembership.vehicle_id == Vehicle.id,
                    FleetMembership.tenant_id == current_user.tenant_id,
                    FleetMembership.effective_to.is_(None),
                    FleetMembership.deleted_at.is_(None),
                )),
            ))

    if customer_id:
        filters.append(or_(
            Vehicle.customer_id == customer_id,
            exists(select(VehicleCustomerRelationship.id).where(
                VehicleCustomerRelationship.vehicle_id == Vehicle.id,
                VehicleCustomerRelationship.customer_id == customer_id,
                VehicleCustomerRelationship.effective_to.is_(None),
                VehicleCustomerRelationship.deleted_at.is_(None),
            )),
        ))

    term = (q or "").strip()
    if term:
        pattern = f"%{term}%"
        filters.append(
            or_(
                Vehicle.unit_number.ilike(pattern),
                Vehicle.vin.ilike(pattern),
                Vehicle.license_plate.ilike(pattern),
                Vehicle.make.ilike(pattern),
                Vehicle.model.ilike(pattern),
            )
        )

    result = await db.execute(
        select(Vehicle)
        .join(Customer, Vehicle.customer_id == Customer.id)
        .where(*filters)
        .order_by(
            func.lower(Vehicle.unit_number),
            func.lower(Vehicle.make),
            func.lower(Vehicle.model),
            Vehicle.id,
        )
        .limit(limit)
    )
    return [
        VehicleTypeaheadResponse(
            id=vehicle.id,
            customer_id=vehicle.customer_id,
            make=vehicle.make,
            model=vehicle.model,
            year=vehicle.year,
            unit_number=vehicle.unit_number,
            license_plate=vehicle.license_plate,
            vin=vehicle.vin,
        )
        for vehicle in result.scalars().all()
    ]


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
    current_user: User = Depends(require_role(
        UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.MECHANIC,
        UserRole.RECEPTIONIST, UserRole.FLEET_MANAGER,
    )),
):
    """Staff-only full update endpoint"""
    result = await db.execute(
        select(Vehicle).options(selectinload(Vehicle.customer)).where(Vehicle.id == vehicle_id)
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

    if current_user.role == UserRole.FLEET_MANAGER:
        membership = (await db.execute(select(FleetMembership.id).where(
            FleetMembership.vehicle_id == vehicle.id,
            FleetMembership.tenant_id == current_user.tenant_id,
            FleetMembership.effective_to.is_(None),
            FleetMembership.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if not membership and not (vehicle.customer and vehicle.customer.is_internal_fleet):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Fleet managers can only manage active fleet vehicles",
            )
    
    # Update fields
    update_data = vehicle_data.model_dump(exclude_unset=True)
    if "vin" in update_data:
        update_data["vin"] = normalize_vin(update_data["vin"])
        duplicate = await find_vehicle_by_vin(
            db, vehicle.tenant_id, update_data["vin"], exclude_vehicle_id=vehicle.id
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"This VIN already belongs to truck {duplicate.id}.",
            )
    if "driver_phone" in update_data:
        update_data["driver_phone"] = normalize_phone(update_data["driver_phone"])
    for field, value in update_data.items():
        setattr(vehicle, field, value)

    if {"vin", "year"} & set(update_data.keys()) or (vehicle.vin and vehicle.nhtsa_decoded_at is None):
        await sync_vehicle_nhtsa_snapshot(vehicle)
    
    await db.commit()
    await db.refresh(vehicle)
    
    return VehicleResponse.model_validate(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleResponse)
async def customer_update_vehicle(
    vehicle_id: UUID,
    vehicle_data: VehicleCustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Customer update endpoint - limited fields only (license plate, color, mileage, notes)"""
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Customers can only update their own vehicles
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
    
    # Update only allowed fields
    update_data = vehicle_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(vehicle, field, value)
    
    await db.commit()
    await db.refresh(vehicle)
    
    return VehicleResponse.model_validate(vehicle)
