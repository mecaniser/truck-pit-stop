"""Tenant-safe domain operations for driver identity and equipment custody."""

from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workos_auth import CurrentPrincipal
from app.db.models.customer import Customer
from app.db.models.driver_accountability import (
    DriverProfile,
    EquipmentCustodyAsset,
    EquipmentCustodySession,
    FleetTrailer,
)
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


def _not_found(detail: str) -> HTTPException:
    # Tenant mismatches deliberately use 404 so callers cannot enumerate
    # records belonging to another organization.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


async def get_driver_for_principal(
    db: AsyncSession,
    principal: CurrentPrincipal,
    *,
    require_active: bool = True,
) -> DriverProfile:
    query = select(DriverProfile).where(
        DriverProfile.tenant_id == principal.tenant_id,
        DriverProfile.user_id == principal.local_user_id,
        DriverProfile.deleted_at.is_(None),
    )
    if require_active:
        query = query.where(DriverProfile.employment_status == "active")
    driver = (await db.execute(query)).scalar_one_or_none()
    if not driver:
        raise _not_found("Driver profile not found")
    return driver


async def create_driver_profile(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    first_name: str,
    last_name: str,
    employer_customer_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    employee_number: Optional[str] = None,
) -> DriverProfile:
    if employer_customer_id:
        employer = (
            await db.execute(
                select(Customer).where(
                    Customer.id == employer_customer_id,
                    Customer.tenant_id == tenant_id,
                    Customer.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not employer:
            raise _not_found("Driver employer not found")

    if user_id:
        user = (
            await db.execute(
                select(User).where(
                    User.id == user_id,
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not user or user.role != UserRole.DRIVER or not user.is_active:
            raise _not_found("Active driver user not found")
        linked = (
            await db.execute(
                select(DriverProfile.id).where(
                    DriverProfile.user_id == user_id,
                    DriverProfile.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if linked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already linked to a driver profile",
            )

    driver = DriverProfile(
        tenant_id=tenant_id,
        user_id=user_id,
        employer_customer_id=employer_customer_id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        phone=phone,
        email=email.strip().lower() if email else None,
        employee_number=employee_number.strip() if employee_number else None,
    )
    db.add(driver)
    await db.flush()
    return driver


async def create_fleet_trailer(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    owner_customer_id: Optional[UUID] = None,
    vin: Optional[str] = None,
    unit_number: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    year: Optional[int] = None,
    license_plate: Optional[str] = None,
    body_type: Optional[str] = None,
    notes: Optional[str] = None,
) -> FleetTrailer:
    if owner_customer_id:
        owner = (
            await db.execute(
                select(Customer).where(
                    Customer.id == owner_customer_id,
                    Customer.tenant_id == tenant_id,
                    Customer.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not owner:
            raise _not_found("Trailer owner not found")
    trailer = FleetTrailer(
        tenant_id=tenant_id,
        owner_customer_id=owner_customer_id,
        vin=vin.strip().upper() if vin else None,
        unit_number=unit_number.strip() if unit_number else None,
        make=make.strip() if make else None,
        model=model.strip() if model else None,
        year=year,
        license_plate=license_plate.strip().upper() if license_plate else None,
        body_type=body_type.strip() if body_type else None,
        notes=notes,
    )
    db.add(trailer)
    await db.flush()
    return trailer


async def start_custody_session(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    driver_id: UUID,
    assigned_by_user_id: UUID,
    vehicle_id: UUID,
    trailer_ids: Iterable[UUID] = (),
    starts_at: Optional[datetime] = None,
    start_odometer: Optional[int] = None,
    dispatch_reference: Optional[str] = None,
    handoff_notes: Optional[str] = None,
) -> EquipmentCustodySession:
    driver = (
        await db.execute(
            select(DriverProfile).where(
                DriverProfile.id == driver_id,
                DriverProfile.tenant_id == tenant_id,
                DriverProfile.employment_status == "active",
                DriverProfile.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not driver:
        raise _not_found("Active driver profile not found")

    actor = (
        await db.execute(
            select(User).where(
                User.id == assigned_by_user_id,
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not actor:
        raise _not_found("Assigning user not found")

    vehicle = (
        await db.execute(
            select(Vehicle).where(
                Vehicle.id == vehicle_id,
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not vehicle:
        raise _not_found("Truck not found")

    normalized_trailer_ids = tuple(dict.fromkeys(trailer_ids))
    trailers: list[FleetTrailer] = []
    if normalized_trailer_ids:
        trailers = list(
            (
                await db.execute(
                    select(FleetTrailer).where(
                        FleetTrailer.id.in_(normalized_trailer_ids),
                        FleetTrailer.tenant_id == tenant_id,
                        FleetTrailer.deleted_at.is_(None),
                    )
                )
            ).scalars()
        )
        if len(trailers) != len(normalized_trailer_ids):
            raise _not_found("Trailer not found")

    conflict_predicates = [EquipmentCustodyAsset.vehicle_id == vehicle_id]
    if normalized_trailer_ids:
        conflict_predicates.append(EquipmentCustodyAsset.trailer_id.in_(normalized_trailer_ids))
    active_conflict = (
        await db.execute(
            select(EquipmentCustodyAsset.id)
            .where(
                EquipmentCustodyAsset.tenant_id == tenant_id,
                EquipmentCustodyAsset.released_at.is_(None),
                EquipmentCustodyAsset.deleted_at.is_(None),
                or_(*conflict_predicates),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if active_conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more equipment records already have active custody",
        )

    began_at = starts_at or datetime.now(timezone.utc)
    session = EquipmentCustodySession(
        tenant_id=tenant_id,
        driver_id=driver.id,
        assigned_by_user_id=actor.id,
        status="assigned",
        starts_at=began_at,
        dispatch_reference=dispatch_reference,
        handoff_notes=handoff_notes,
    )
    session.assets.append(
        EquipmentCustodyAsset(
            tenant_id=tenant_id,
            vehicle_id=vehicle.id,
            equipment_role="power_unit",
            attached_at=began_at,
            start_odometer=start_odometer,
        )
    )
    for trailer in trailers:
        session.assets.append(
            EquipmentCustodyAsset(
                tenant_id=tenant_id,
                trailer_id=trailer.id,
                equipment_role="trailer",
                attached_at=began_at,
            )
        )
    db.add(session)
    await db.flush()
    return session


async def acknowledge_own_custody(
    db: AsyncSession,
    *,
    principal: CurrentPrincipal,
    custody_session_id: UUID,
) -> EquipmentCustodySession:
    driver = await get_driver_for_principal(db, principal)
    session = (
        await db.execute(
            select(EquipmentCustodySession).where(
                EquipmentCustodySession.id == custody_session_id,
                EquipmentCustodySession.tenant_id == principal.tenant_id,
                EquipmentCustodySession.driver_id == driver.id,
                EquipmentCustodySession.status == "assigned",
                EquipmentCustodySession.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not session:
        raise _not_found("Assigned custody session not found")
    session.status = "active"
    session.acknowledged_at = datetime.now(timezone.utc)
    await db.flush()
    return session


async def close_custody_session(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    custody_session_id: UUID,
    released_by_user_id: UUID,
    end_odometer: Optional[int] = None,
    ended_at: Optional[datetime] = None,
) -> EquipmentCustodySession:
    session = (
        await db.execute(
            select(EquipmentCustodySession).where(
                EquipmentCustodySession.id == custody_session_id,
                EquipmentCustodySession.tenant_id == tenant_id,
                EquipmentCustodySession.status.in_(("assigned", "active")),
                EquipmentCustodySession.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not session:
        raise _not_found("Open custody session not found")

    actor = (
        await db.execute(
            select(User.id).where(
                User.id == released_by_user_id,
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not actor:
        raise _not_found("Releasing user not found")

    closed_at = ended_at or datetime.now(timezone.utc)
    assets = list(
        (
            await db.execute(
                select(EquipmentCustodyAsset).where(
                    EquipmentCustodyAsset.custody_session_id == session.id,
                    EquipmentCustodyAsset.tenant_id == tenant_id,
                    EquipmentCustodyAsset.released_at.is_(None),
                    EquipmentCustodyAsset.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    for asset in assets:
        asset.released_at = closed_at
        if asset.vehicle_id is not None:
            asset.end_odometer = end_odometer
    session.status = "closed"
    session.ends_at = closed_at
    session.released_by_user_id = actor
    await db.flush()
    return session
