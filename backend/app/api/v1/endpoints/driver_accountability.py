"""WorkOS-authorized driver identity and equipment custody endpoints."""

from datetime import datetime, timezone
from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.core.workos_auth import CurrentPrincipal, require_permission
from app.db.models.driver_accountability import (
    DriverProfile,
    EquipmentCustodyAsset,
    EquipmentCustodySession,
    FleetAccountabilityReview,
    FleetIncidentEvent,
    FleetTrailer,
)
from app.db.models.fleet import (
    DEFAULT_INSPECTION_CHECKLIST,
    FleetIncident,
    FleetInspection,
    FleetInspectionItem,
    IncidentSeverity,
    IncidentStatus,
    InspectionItemResult,
    InspectionResult,
    InspectionStatus,
)
from app.db.models.vehicle import Vehicle
from app.schemas.fleet import (
    IncidentResponse,
    InspectionComplete,
    InspectionDetailResponse,
    InspectionItemResponse,
    InspectionItemUpdate,
    InspectionResponse,
)
from app.schemas.driver_accountability import (
    AssignedEquipmentResponse,
    CustodyAssignmentCreate,
    CustodySessionResponse,
    DriverIncidentCreate,
    DriverInspectionCreate,
    DriverScorecardResponse,
    DriverProfileCreate,
    DriverProfileResponse,
    TrailerCreate,
    TrailerResponse,
)
from app.services.driver_accountability_service import (
    acknowledge_own_custody,
    create_driver_profile,
    create_fleet_trailer,
    get_driver_for_principal,
    start_custody_session,
)


router = APIRouter()


async def _driver_scorecard(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    driver_id: UUID,
) -> DriverScorecardResponse:
    sessions = list((await db.execute(select(EquipmentCustodySession).where(
        EquipmentCustodySession.tenant_id == tenant_id,
        EquipmentCustodySession.driver_id == driver_id,
        EquipmentCustodySession.deleted_at.is_(None),
    ))).scalars())
    session_ids = [session.id for session in sessions]
    assets = [] if not session_ids else list((await db.execute(select(EquipmentCustodyAsset).where(
        EquipmentCustodyAsset.tenant_id == tenant_id,
        EquipmentCustodyAsset.custody_session_id.in_(session_ids),
        EquipmentCustodyAsset.vehicle_id.is_not(None),
        EquipmentCustodyAsset.deleted_at.is_(None),
    ))).scalars())
    custody_miles = sum(
        max(0, asset.end_odometer - asset.start_odometer)
        for asset in assets
        if asset.start_odometer is not None and asset.end_odometer is not None
    )
    incidents = list((await db.execute(select(FleetIncident).where(
        FleetIncident.tenant_id == tenant_id,
        FleetIncident.driver_id_at_occurrence == driver_id,
        FleetIncident.status != IncidentStatus.VOIDED,
        FleetIncident.deleted_at.is_(None),
    ))).scalars())
    incident_ids = [incident.id for incident in incidents]
    reviews = [] if not incident_ids else list((await db.execute(
        select(FleetAccountabilityReview)
        .where(
            FleetAccountabilityReview.tenant_id == tenant_id,
            FleetAccountabilityReview.incident_id.in_(incident_ids),
            FleetAccountabilityReview.deleted_at.is_(None),
        )
        .order_by(FleetAccountabilityReview.incident_id, FleetAccountabilityReview.revision.desc())
    )).scalars())
    latest_by_incident: dict[UUID, FleetAccountabilityReview] = {}
    for review in reviews:
        latest_by_incident.setdefault(review.incident_id, review)
    latest = list(latest_by_incident.values())
    finalized = [review for review in latest if review.status == "finalized"]
    duty_issues = sum(review.finding == "driver_duty_issue" for review in finalized)
    shared = sum(review.finding == "shared_responsibility" for review in finalized)
    not_attributable = sum(review.finding in ("not_attributable", "non_driver_issue") for review in finalized)
    insufficient = sum(review.finding == "insufficient_evidence" for review in finalized)
    pending = len(incidents) - len(finalized)
    rate = round(duty_issues * 10000 / custody_miles, 2) if custody_miles else None
    return DriverScorecardResponse(
        driver_id=driver_id,
        custody_sessions=len(sessions),
        custody_miles=custody_miles,
        incidents_during_custody=len(incidents),
        open_incidents=sum(incident.status in (IncidentStatus.OPEN, IncidentStatus.IN_PROGRESS) for incident in incidents),
        finalized_reviews=len(finalized),
        confirmed_driver_duty_issues=duty_issues,
        shared_responsibility_findings=shared,
        not_attributable_findings=not_attributable,
        insufficient_evidence_findings=insufficient,
        disputed_or_pending_reviews=pending,
        reviewed_duty_issue_rate_per_10k_miles=rate,
        scoring_ready=custody_miles >= 1000 and bool(finalized),
    )


async def _active_vehicle_custody(
    db: AsyncSession,
    principal: CurrentPrincipal,
    driver: DriverProfile,
    vehicle_id: UUID,
) -> tuple[EquipmentCustodySession, EquipmentCustodyAsset, Vehicle]:
    row = (
        await db.execute(
            select(EquipmentCustodySession, EquipmentCustodyAsset, Vehicle)
            .join(EquipmentCustodyAsset, EquipmentCustodyAsset.custody_session_id == EquipmentCustodySession.id)
            .join(Vehicle, Vehicle.id == EquipmentCustodyAsset.vehicle_id)
            .where(
                EquipmentCustodySession.tenant_id == principal.tenant_id,
                EquipmentCustodySession.driver_id == driver.id,
                EquipmentCustodySession.status.in_(("assigned", "active")),
                EquipmentCustodySession.deleted_at.is_(None),
                EquipmentCustodyAsset.vehicle_id == vehicle_id,
                EquipmentCustodyAsset.released_at.is_(None),
                EquipmentCustodyAsset.deleted_at.is_(None),
                Vehicle.tenant_id == principal.tenant_id,
                Vehicle.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Assigned equipment not found")
    return row


def _inspection_response(insp: FleetInspection) -> InspectionResponse:
    vehicle = insp.vehicle
    return InspectionResponse(
        id=insp.id, vehicle_id=insp.vehicle_id, inspector_id=insp.inspector_id,
        status=insp.status, result=insp.result, scheduled_for=insp.scheduled_for,
        performed_at=insp.performed_at, odometer=insp.odometer, notes=insp.notes,
        repair_order_id=insp.repair_order_id, created_at=insp.created_at,
        vehicle_make=vehicle.make if vehicle else "",
        vehicle_model=vehicle.model if vehicle else "",
        vehicle_year=vehicle.year if vehicle else None,
        vehicle_unit_number=vehicle.unit_number if vehicle else None,
    )


def _inspection_detail(insp: FleetInspection) -> InspectionDetailResponse:
    return InspectionDetailResponse(
        **_inspection_response(insp).model_dump(),
        items=[InspectionItemResponse.model_validate(item) for item in sorted(insp.items, key=lambda item: (item.category, item.label))],
    )


async def _own_inspection(
    db: AsyncSession,
    principal: CurrentPrincipal,
    driver: DriverProfile,
    inspection_id: UUID,
) -> FleetInspection:
    inspection = (
        await db.execute(
            select(FleetInspection)
            .where(
                FleetInspection.id == inspection_id,
                FleetInspection.tenant_id == principal.tenant_id,
                FleetInspection.driver_id == driver.id,
                FleetInspection.deleted_at.is_(None),
            )
            .options(selectinload(FleetInspection.vehicle), selectinload(FleetInspection.items))
        )
    ).scalar_one_or_none()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection


@router.get("/drivers", response_model=List[DriverProfileResponse])
async def list_drivers(
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("fleet:view")),
):
    return list(
        (
            await db.execute(
                select(DriverProfile)
                .where(
                    DriverProfile.tenant_id == principal.tenant_id,
                    DriverProfile.deleted_at.is_(None),
                )
                .order_by(DriverProfile.last_name, DriverProfile.first_name)
            )
        ).scalars()
    )


@router.get("/drivers/{driver_id}/scorecard", response_model=DriverScorecardResponse)
async def driver_scorecard(
    driver_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("fleet:view", "accountability:review")),
):
    driver = (
        await db.execute(select(DriverProfile).where(
            DriverProfile.id == driver_id,
            DriverProfile.tenant_id == principal.tenant_id,
            DriverProfile.deleted_at.is_(None),
        ))
    ).scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return await _driver_scorecard(db, tenant_id=principal.tenant_id, driver_id=driver.id)


@router.post(
    "/drivers",
    response_model=DriverProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_driver(
    body: DriverProfileCreate,
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("fleet:assign")),
):
    driver = await create_driver_profile(
        db,
        tenant_id=principal.tenant_id,
        first_name=body.first_name,
        last_name=body.last_name,
        employer_customer_id=body.employer_customer_id,
        phone=body.phone,
        email=body.email,
        employee_number=body.employee_number,
    )
    await db.commit()
    await db.refresh(driver)
    return driver


@router.get("/trailers", response_model=List[TrailerResponse])
async def list_trailers(
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("fleet:view")),
):
    return list(
        (
            await db.execute(
                select(FleetTrailer)
                .where(
                    FleetTrailer.tenant_id == principal.tenant_id,
                    FleetTrailer.deleted_at.is_(None),
                )
                .order_by(FleetTrailer.unit_number, FleetTrailer.created_at)
            )
        ).scalars()
    )


@router.post(
    "/trailers",
    response_model=TrailerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_trailer(
    body: TrailerCreate,
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("fleet:manage")),
):
    trailer = await create_fleet_trailer(
        db,
        tenant_id=principal.tenant_id,
        **body.model_dump(),
    )
    await db.commit()
    await db.refresh(trailer)
    return trailer


@router.post(
    "/custody",
    response_model=CustodySessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_custody(
    body: CustodyAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("fleet:assign")),
):
    custody = await start_custody_session(
        db,
        tenant_id=principal.tenant_id,
        driver_id=body.driver_id,
        assigned_by_user_id=principal.local_user_id,
        vehicle_id=body.vehicle_id,
        trailer_ids=body.trailer_ids,
        starts_at=body.starts_at,
        start_odometer=body.start_odometer,
        dispatch_reference=body.dispatch_reference,
        handoff_notes=body.handoff_notes,
    )
    await db.commit()
    return custody


@router.get("/me", response_model=DriverProfileResponse)
async def driver_me(
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use")),
):
    return await get_driver_for_principal(db, principal)


@router.get("/me/scorecard", response_model=DriverScorecardResponse)
async def my_scorecard(
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use")),
):
    driver = await get_driver_for_principal(db, principal)
    return await _driver_scorecard(db, tenant_id=principal.tenant_id, driver_id=driver.id)


@router.get("/me/custody", response_model=List[CustodySessionResponse])
async def my_custody(
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use")),
):
    driver = await get_driver_for_principal(db, principal)
    return list(
        (
            await db.execute(
                select(EquipmentCustodySession)
                .where(
                    EquipmentCustodySession.tenant_id == principal.tenant_id,
                    EquipmentCustodySession.driver_id == driver.id,
                    EquipmentCustodySession.status.in_(("assigned", "active")),
                    EquipmentCustodySession.deleted_at.is_(None),
                )
                .options(selectinload(EquipmentCustodySession.assets))
                .order_by(EquipmentCustodySession.starts_at.desc())
            )
        ).scalars()
    )


@router.post(
    "/me/custody/{custody_session_id}/acknowledge",
    response_model=CustodySessionResponse,
)
async def acknowledge_custody(
    custody_session_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use")),
):
    custody = await acknowledge_own_custody(
        db,
        principal=principal,
        custody_session_id=custody_session_id,
    )
    await db.commit()
    await db.refresh(custody, attribute_names=["assets"])
    return custody


@router.get("/me/equipment", response_model=List[AssignedEquipmentResponse])
async def my_assigned_equipment(
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use")),
):
    driver = await get_driver_for_principal(db, principal)
    rows = (
        await db.execute(
            select(EquipmentCustodySession, EquipmentCustodyAsset, Vehicle, FleetTrailer)
            .join(EquipmentCustodyAsset, EquipmentCustodyAsset.custody_session_id == EquipmentCustodySession.id)
            .outerjoin(Vehicle, Vehicle.id == EquipmentCustodyAsset.vehicle_id)
            .outerjoin(FleetTrailer, FleetTrailer.id == EquipmentCustodyAsset.trailer_id)
            .where(
                EquipmentCustodySession.tenant_id == principal.tenant_id,
                EquipmentCustodySession.driver_id == driver.id,
                EquipmentCustodySession.status.in_(("assigned", "active")),
                EquipmentCustodySession.deleted_at.is_(None),
                EquipmentCustodyAsset.released_at.is_(None),
                EquipmentCustodyAsset.deleted_at.is_(None),
            )
            .order_by(EquipmentCustodySession.starts_at.desc(), EquipmentCustodyAsset.equipment_role)
        )
    ).all()
    return [
        AssignedEquipmentResponse(
            custody_session_id=session.id,
            custody_status=session.status,
            custody_starts_at=session.starts_at,
            custody_acknowledged_at=session.acknowledged_at,
            asset_id=asset.id,
            equipment_role=asset.equipment_role,
            vehicle_id=asset.vehicle_id,
            trailer_id=asset.trailer_id,
            unit_number=(vehicle.unit_number if vehicle else trailer.unit_number),
            vin=(vehicle.vin if vehicle else trailer.vin),
            make=(vehicle.make if vehicle else trailer.make),
            model=(vehicle.model if vehicle else trailer.model),
            year=(vehicle.year if vehicle else trailer.year),
            license_plate=(vehicle.license_plate if vehicle else trailer.license_plate),
            odometer=(vehicle.mileage if vehicle else None),
        )
        for session, asset, vehicle, trailer in rows
    ]


@router.get("/me/inspections", response_model=List[InspectionResponse])
async def my_inspections(
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use", "inspections:perform")),
):
    driver = await get_driver_for_principal(db, principal)
    inspections = (
        await db.execute(
            select(FleetInspection)
            .where(
                FleetInspection.tenant_id == principal.tenant_id,
                FleetInspection.driver_id == driver.id,
                FleetInspection.deleted_at.is_(None),
            )
            .options(selectinload(FleetInspection.vehicle))
            .order_by(FleetInspection.created_at.desc())
        )
    ).scalars()
    return [_inspection_response(inspection) for inspection in inspections]


@router.post("/me/inspections", response_model=InspectionDetailResponse, status_code=201)
async def start_my_inspection(
    body: DriverInspectionCreate,
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use", "inspections:perform")),
):
    driver = await get_driver_for_principal(db, principal)
    custody, _asset, vehicle = await _active_vehicle_custody(db, principal, driver, body.vehicle_id)
    existing = (
        await db.execute(
            select(FleetInspection)
            .where(
                FleetInspection.tenant_id == principal.tenant_id,
                FleetInspection.driver_id == driver.id,
                FleetInspection.vehicle_id == vehicle.id,
                FleetInspection.status == InspectionStatus.SCHEDULED,
                FleetInspection.deleted_at.is_(None),
            )
            .options(selectinload(FleetInspection.vehicle), selectinload(FleetInspection.items))
            .order_by(FleetInspection.created_at.desc())
        )
    ).scalars().first()
    if existing:
        return _inspection_detail(existing)
    inspection = FleetInspection(
        id=uuid4(), tenant_id=principal.tenant_id, vehicle_id=vehicle.id,
        custody_session_id=custody.id, driver_id=driver.id,
        status=InspectionStatus.SCHEDULED,
        scheduled_for=datetime.now(timezone.utc).date(), inspection_type="pre_trip",
    )
    db.add(inspection)
    for category, label, is_warning in DEFAULT_INSPECTION_CHECKLIST:
        db.add(FleetInspectionItem(
            id=uuid4(), tenant_id=principal.tenant_id, inspection_id=inspection.id,
            category=category, label=label, is_warning_light=is_warning,
            result=InspectionItemResult.PENDING,
        ))
    await db.commit()
    return _inspection_detail(await _own_inspection(db, principal, driver, inspection.id))


@router.get("/me/inspections/{inspection_id}", response_model=InspectionDetailResponse)
async def get_my_inspection(
    inspection_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use", "inspections:perform")),
):
    driver = await get_driver_for_principal(db, principal)
    return _inspection_detail(await _own_inspection(db, principal, driver, inspection_id))


@router.patch("/me/inspections/{inspection_id}/items/{item_id}", response_model=InspectionDetailResponse)
async def update_my_inspection_item(
    inspection_id: UUID,
    item_id: UUID,
    body: InspectionItemUpdate,
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use", "inspections:perform")),
):
    driver = await get_driver_for_principal(db, principal)
    inspection = await _own_inspection(db, principal, driver, inspection_id)
    if inspection.status != InspectionStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="This inspection is closed")
    item = next((candidate for candidate in inspection.items if candidate.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Inspection item not found")
    if body.result is not None:
        item.result = body.result
    if body.note is not None:
        item.note = body.note
    await db.commit()
    return _inspection_detail(inspection)


@router.post("/me/inspections/{inspection_id}/complete", response_model=InspectionDetailResponse)
async def complete_my_inspection(
    inspection_id: UUID,
    body: InspectionComplete,
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use", "inspections:perform")),
):
    driver = await get_driver_for_principal(db, principal)
    inspection = await _own_inspection(db, principal, driver, inspection_id)
    if inspection.status != InspectionStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="This inspection is closed")
    if body.odometer is None:
        raise HTTPException(status_code=400, detail="Enter the current odometer")
    if any(item.result == InspectionItemResult.PENDING for item in inspection.items):
        raise HTTPException(status_code=400, detail="Complete every checklist item before submitting")
    if inspection.vehicle.mileage is not None and body.odometer < inspection.vehicle.mileage:
        raise HTTPException(status_code=400, detail="Odometer is below the last recorded mileage")
    inspection.status = InspectionStatus.COMPLETED
    inspection.result = InspectionResult.FAIL if any(
        item.result == InspectionItemResult.FAIL for item in inspection.items
    ) else InspectionResult.PASS
    inspection.performed_at = datetime.now(timezone.utc)
    inspection.inspector_id = principal.local_user_id
    inspection.attested_at = inspection.performed_at
    inspection.attestation_version = "driver-pti-v1"
    inspection.attested_name = f"{driver.first_name} {driver.last_name}".strip()
    inspection.odometer = body.odometer
    inspection.notes = body.notes
    inspection.vehicle.mileage = body.odometer
    await db.commit()
    return _inspection_detail(inspection)


@router.get("/me/incidents", response_model=List[IncidentResponse])
async def my_incidents(
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use", "incidents:report")),
):
    driver = await get_driver_for_principal(db, principal)
    incidents = (
        await db.execute(
            select(FleetIncident)
            .where(
                FleetIncident.tenant_id == principal.tenant_id,
                or_(FleetIncident.driver_id_at_occurrence == driver.id,
                    FleetIncident.reported_by_id == principal.local_user_id),
                FleetIncident.status != IncidentStatus.VOIDED,
                FleetIncident.deleted_at.is_(None),
            )
            .options(selectinload(FleetIncident.vehicle), selectinload(FleetIncident.photos))
            .order_by(FleetIncident.occurred_at.desc())
        )
    ).scalars()
    return [IncidentResponse.model_validate(incident) for incident in incidents]


@router.post("/me/incidents", response_model=IncidentResponse, status_code=201)
async def report_my_incident(
    body: DriverIncidentCreate,
    db: AsyncSession = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("driver_portal:use", "incidents:report")),
):
    driver = await get_driver_for_principal(db, principal)
    custody, _asset, vehicle = await _active_vehicle_custody(db, principal, driver, body.vehicle_id)
    if body.trailer_id is not None:
        assigned_trailer = (
            await db.execute(select(EquipmentCustodyAsset.id).where(
                EquipmentCustodyAsset.custody_session_id == custody.id,
                EquipmentCustodyAsset.trailer_id == body.trailer_id,
                EquipmentCustodyAsset.released_at.is_(None),
                EquipmentCustodyAsset.deleted_at.is_(None),
            ))
        ).scalar_one_or_none()
        if not assigned_trailer:
            raise HTTPException(status_code=404, detail="Assigned trailer not found")
    incident = FleetIncident(
        id=uuid4(), tenant_id=principal.tenant_id, vehicle_id=vehicle.id,
        trailer_id=body.trailer_id, custody_session_id=custody.id,
        driver_id_at_occurrence=driver.id, reported_by_id=principal.local_user_id,
        occurred_at=body.occurred_at, location=body.location,
        severity=IncidentSeverity(body.severity), status=IncidentStatus.OPEN,
        description=body.description, incident_type=body.incident_type,
    )
    db.add(incident)
    db.add(FleetIncidentEvent(
        id=uuid4(), tenant_id=principal.tenant_id, incident_id=incident.id,
        actor_user_id=principal.local_user_id, event_type="reported",
        data_json={"source": "driver_portal", "severity": body.severity,
                   "custody_session_id": str(custody.id)},
    ))
    await db.commit()
    await db.refresh(incident, attribute_names=["vehicle", "photos"])
    return IncidentResponse.model_validate(incident)
