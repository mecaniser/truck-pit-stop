"""Fleet management endpoints: weekly inspections and roadside incidents.

Scoped to the garage's own internal fleet (the house-account customer). Accessible
to the fleet manager and the garage owner/admin who own the fleet.
"""
import math
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db, get_current_active_user
from app.core.image_validation import read_validated_image
from app.core.phone import normalize_phone
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.fleet_board_read_model import FleetBoardReadModel
from app.db.models.inventory import PartsUsage, Inventory
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.labor import Labor, LaborLineType
from app.db.models.service import Service, ServicePart
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.fleet import (
    FleetInspection,
    FleetInspectionItem,
    FleetIncident,
    FleetIncidentPhoto,
    VehiclePMService,
    RepairOrderPMService,
    InspectionStatus,
    InspectionResult,
    InspectionItemResult,
    IncidentStatus,
    DEFAULT_INSPECTION_CHECKLIST,
    INSPECTION_INTERVAL_DAYS,
)
from app.schemas.fleet import (
    InspectionCreate,
    InspectionComplete,
    InspectionItemUpdate,
    InspectionResponse,
    InspectionDetailResponse,
    InspectionItemResponse,
    IncidentCreate,
    IncidentUpdate,
    IncidentResponse,
    FleetVehicleResponse,
    FleetSummaryResponse,
    BoardTruck,
    BoardWorkOrder,
    FleetStats,
    FleetBoardResponse,
    HistoryEntry,
    PartEntry,
    IncidentEntry,
    NearestUnit,
    TruckDetailResponse,
    TruckUpdate,
    WorkOrderCreate,
    WorkOrderComplete,
    SchedulePMRequest,
    PMServiceEntry,
    PMServicesUpdate,
    AddServiceRequest,
    FleetInvoiceEntry,
    FleetManagerOption,
    FleetMechanicOption,
    FleetSettingsResponse,
    FleetPhotoResponse,
)
from app.core.logging import get_logger
from app.services.internal_fleet import (
    ensure_internal_fleet_customer,
    fleet_labor_uses_customer_rate,
    project_pm_due_date,
)
from app.services.cloudinary_service import create_direct_image_upload_signature, is_cloudinary_configured, upload_work_photo

router = APIRouter()
logger = get_logger(__name__)

FLEET_ROLES = (UserRole.FLEET_MANAGER, UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)

# Repair-order statuses that count as a closed/terminal work order.
TERMINAL_RO_STATUSES = {
    RepairOrderStatus.COMPLETED,
    RepairOrderStatus.INVOICED,
    RepairOrderStatus.PAID,
    RepairOrderStatus.CANCELLED,
    RepairOrderStatus.DECLINED,
}
PM_DUE_SOON_MILES = 2500  # matches the design's PM "due soon" threshold
PM_DUE_SOON_DAYS = 14      # date-based PM "due soon" window
# Operator-set idle statuses (no open work order). "active" = on the road.
VALID_STATUS_OVERRIDES = {"active", "yard", "available", "out_of_service"}

# RepairOrder status -> shop-floor work-order label (design vocabulary).
WO_STATUS_LABELS = {
    RepairOrderStatus.DRAFT: "Draft",
    RepairOrderStatus.QUOTED: "Diagnosing",
    RepairOrderStatus.APPROVED: "Scheduled",
    RepairOrderStatus.ASSIGNED: "Assigned",
    RepairOrderStatus.ACKNOWLEDGED: "Assigned",
    RepairOrderStatus.IN_PROGRESS: "In progress",
    RepairOrderStatus.PENDING_REVIEW: "Quality check",
}


def require_fleet_access(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role not in FLEET_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    return current_user


def require_garage_owner_only(current_user: User = Depends(get_current_active_user)) -> User:
    """Owner-only guard. Fleet managers/admins cannot delete inspection records."""
    if current_user.role != UserRole.GARAGE_OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the shop owner can delete inspections")
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must be associated with a tenant")
    return current_user


async def _fleet_customer_id(db: AsyncSession, tenant_id: UUID) -> UUID:
    customer = await ensure_internal_fleet_customer(db, tenant_id)
    await db.commit()
    return customer.id


async def _get_fleet_vehicle(db: AsyncSession, tenant_id: UUID, vehicle_id: UUID) -> Vehicle:
    fleet_customer_id = await _fleet_customer_id(db, tenant_id)
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.id == vehicle_id,
                Vehicle.tenant_id == tenant_id,
                Vehicle.customer_id == fleet_customer_id,
            )
        )
    )
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fleet vehicle not found")
    return vehicle


def _vehicle_fields(v: Optional[Vehicle]) -> dict:
    if not v:
        return {"vehicle_make": "", "vehicle_model": "", "vehicle_year": None, "vehicle_unit_number": None}
    return {
        "vehicle_make": v.make or "",
        "vehicle_model": v.model or "",
        "vehicle_year": v.year,
        "vehicle_unit_number": v.unit_number,
    }


def _inspection_response(insp: FleetInspection) -> InspectionResponse:
    return InspectionResponse(
        **{k: getattr(insp, k) for k in (
            "id", "vehicle_id", "inspector_id", "status", "result",
            "scheduled_for", "performed_at", "odometer", "notes", "repair_order_id", "created_at",
        )},
        **_vehicle_fields(insp.vehicle),
    )


def _incident_response(inc: FleetIncident) -> IncidentResponse:
    photos = inc.__dict__.get("photos") or []
    return IncidentResponse(
        **{k: getattr(inc, k) for k in (
            "id", "vehicle_id", "reported_by_id", "occurred_at", "location",
            "severity", "status", "description", "resolution_notes",
            "resolved_at", "repair_order_id", "created_at",
        )},
        photos=[_incident_photo_response(photo) for photo in sorted(photos, key=lambda p: p.uploaded_at, reverse=True)],
        **_vehicle_fields(inc.vehicle),
    )


def _uploader_name(user: Optional[User]) -> str:
    if not user:
        return "Unknown"
    return f"{user.first_name} {user.last_name}".strip() or user.email or "Unknown"


def _incident_photo_response(photo: FleetIncidentPhoto) -> FleetPhotoResponse:
    return FleetPhotoResponse(
        id=photo.id,
        image_url=photo.image_url,
        caption=photo.caption,
        uploaded_at=photo.uploaded_at,
        uploader_name=_uploader_name(getattr(photo, "uploaded_by", None)),
    )


class DirectPhotoUploadSignatureResponse(BaseModel):
    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    folder: str
    upload_url: str


class DirectFleetIncidentPhotoCreate(BaseModel):
    image_url: str
    public_id: str
    caption: Optional[str] = None


_read_validated_fleet_image = read_validated_image


# ---------------------------------------------------------------------------
# Roster & summary
# ---------------------------------------------------------------------------

@router.get("/vehicles", response_model=List[FleetVehicleResponse])
async def list_fleet_vehicles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    fleet_customer_id = await _fleet_customer_id(db, current_user.tenant_id)
    result = await db.execute(
        select(Vehicle).where(
            and_(Vehicle.tenant_id == current_user.tenant_id, Vehicle.customer_id == fleet_customer_id)
        ).order_by(Vehicle.unit_number, Vehicle.make)
    )
    vehicles = list(result.scalars().all())
    vehicle_ids = [v.id for v in vehicles]
    if not vehicle_ids:
        return []

    # Latest completed inspection per vehicle.
    completed = await db.execute(
        select(FleetInspection)
        .where(
            and_(
                FleetInspection.vehicle_id.in_(vehicle_ids),
                FleetInspection.status == InspectionStatus.COMPLETED,
            )
        )
        .order_by(FleetInspection.vehicle_id, FleetInspection.performed_at.desc())
    )
    last_by_vehicle: dict[UUID, FleetInspection] = {}
    for insp in completed.scalars().all():
        if insp.vehicle_id not in last_by_vehicle:
            last_by_vehicle[insp.vehicle_id] = insp

    # Open incident counts per vehicle.
    inc_rows = await db.execute(
        select(FleetIncident.vehicle_id, func.count(FleetIncident.id))
        .where(
            and_(
                FleetIncident.vehicle_id.in_(vehicle_ids),
                FleetIncident.status != IncidentStatus.RESOLVED,
            )
        )
        .group_by(FleetIncident.vehicle_id)
    )
    open_incidents = {row[0]: row[1] for row in inc_rows.all()}

    today = datetime.now(timezone.utc).date()
    items: list[FleetVehicleResponse] = []
    for v in vehicles:
        last = last_by_vehicle.get(v.id)
        if last and last.performed_at:
            next_due = last.performed_at.date() + timedelta(days=INSPECTION_INTERVAL_DAYS)
            overdue = today > next_due
            last_at = last.performed_at
            last_result = last.result
        else:
            next_due = None  # never inspected
            overdue = True
            last_at = None
            last_result = None
        items.append(FleetVehicleResponse(
            id=v.id, make=v.make, model=v.model, year=v.year, unit_number=v.unit_number,
            vin=v.vin, license_plate=v.license_plate, mileage=v.mileage,
            last_inspection_at=last_at, last_inspection_result=last_result,
            next_inspection_due=next_due, inspection_overdue=overdue,
            open_incident_count=open_incidents.get(v.id, 0),
        ))
    return items


@router.get("/summary", response_model=FleetSummaryResponse)
async def fleet_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    vehicles = await list_fleet_vehicles(db=db, current_user=current_user)
    total = len(vehicles)
    overdue = sum(1 for v in vehicles if v.inspection_overdue)
    due = total - overdue
    open_incidents = sum(v.open_incident_count for v in vehicles)
    return FleetSummaryResponse(
        total_vehicles=total,
        inspections_due=due,
        inspections_overdue=overdue,
        open_incidents=open_incidents,
    )


# ---------------------------------------------------------------------------
# Inspections
# ---------------------------------------------------------------------------

@router.get("/inspections", response_model=List[InspectionResponse])
async def list_inspections(
    vehicle_id: Optional[UUID] = Query(None),
    status_filter: Optional[InspectionStatus] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    query = (
        select(FleetInspection)
        .where(FleetInspection.tenant_id == current_user.tenant_id)
        .options(selectinload(FleetInspection.vehicle))
        .order_by(FleetInspection.scheduled_for.desc(), FleetInspection.created_at.desc())
    )
    if vehicle_id:
        query = query.where(FleetInspection.vehicle_id == vehicle_id)
    if status_filter:
        query = query.where(FleetInspection.status == status_filter)
    result = await db.execute(query)
    return [_inspection_response(i) for i in result.scalars().all()]


@router.post("/inspections", response_model=InspectionDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_inspection(
    body: InspectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    vehicle = await _get_fleet_vehicle(db, current_user.tenant_id, body.vehicle_id)
    inspection = FleetInspection(
        id=uuid4(),
        tenant_id=current_user.tenant_id,
        vehicle_id=vehicle.id,
        status=InspectionStatus.SCHEDULED,
        scheduled_for=body.scheduled_for or datetime.now(timezone.utc).date(),
    )
    db.add(inspection)
    for category, label, is_warning in DEFAULT_INSPECTION_CHECKLIST:
        db.add(FleetInspectionItem(
            id=uuid4(),
            tenant_id=current_user.tenant_id,
            inspection_id=inspection.id,
            category=category,
            label=label,
            is_warning_light=is_warning,
            result=InspectionItemResult.PENDING,
        ))
    await db.commit()
    return await _load_inspection_detail(db, current_user.tenant_id, inspection.id)


async def _load_inspection_detail(db: AsyncSession, tenant_id: UUID, inspection_id: UUID) -> InspectionDetailResponse:
    result = await db.execute(
        select(FleetInspection)
        .where(and_(FleetInspection.id == inspection_id, FleetInspection.tenant_id == tenant_id))
        .options(selectinload(FleetInspection.vehicle), selectinload(FleetInspection.items))
    )
    insp = result.scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    base = _inspection_response(insp)
    items = sorted(insp.items, key=lambda i: (i.category, i.label))
    return InspectionDetailResponse(
        **base.model_dump(),
        items=[InspectionItemResponse.model_validate(i) for i in items],
    )


@router.get("/inspections/{inspection_id}", response_model=InspectionDetailResponse)
async def get_inspection(
    inspection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    return await _load_inspection_detail(db, current_user.tenant_id, inspection_id)


@router.patch("/inspections/{inspection_id}/items/{item_id}", response_model=InspectionDetailResponse)
async def update_inspection_item(
    inspection_id: UUID,
    item_id: UUID,
    body: InspectionItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    result = await db.execute(
        select(FleetInspectionItem).where(
            and_(
                FleetInspectionItem.id == item_id,
                FleetInspectionItem.inspection_id == inspection_id,
                FleetInspectionItem.tenant_id == current_user.tenant_id,
            )
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection item not found")
    # A completed inspection is a point-in-time record — don't let items change
    # after the fact. Re-inspect (a new inspection) to record the current state.
    insp_status = (await db.execute(
        select(FleetInspection.status).where(FleetInspection.id == inspection_id)
    )).scalar_one_or_none()
    if insp_status in (InspectionStatus.COMPLETED, InspectionStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This inspection is closed. Start a new inspection to record the current condition.",
        )
    if body.result is not None:
        item.result = body.result
    if body.note is not None:
        item.note = body.note
    await db.commit()
    return await _load_inspection_detail(db, current_user.tenant_id, inspection_id)


@router.post("/inspections/{inspection_id}/complete", response_model=InspectionDetailResponse)
async def complete_inspection(
    inspection_id: UUID,
    body: InspectionComplete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    result = await db.execute(
        select(FleetInspection)
        .where(and_(FleetInspection.id == inspection_id, FleetInspection.tenant_id == current_user.tenant_id))
        .options(selectinload(FleetInspection.items))
    )
    insp = result.scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    if insp.status == InspectionStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inspection already completed")

    # Odometer is required — it keeps the mileage-based PM estimate fresh.
    if body.odometer is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter the truck's current odometer to complete the inspection",
        )
    vehicle = await _get_fleet_vehicle(db, current_user.tenant_id, insp.vehicle_id)
    if vehicle.mileage is not None and body.odometer < vehicle.mileage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Odometer ({body.odometer:,} mi) is below the last recorded {vehicle.mileage:,} mi — check the reading",
        )

    # Compute overall result from items unless explicitly overridden.
    if body.result is not None:
        overall = body.result
    elif any(i.result == InspectionItemResult.FAIL for i in insp.items):
        overall = InspectionResult.FAIL
    elif any(i.result == InspectionItemResult.PENDING for i in insp.items):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All checklist items must be marked before completing the inspection",
        )
    else:
        overall = InspectionResult.PASS

    insp.status = InspectionStatus.COMPLETED
    insp.result = overall
    insp.performed_at = datetime.now(timezone.utc)
    insp.inspector_id = current_user.id
    insp.odometer = body.odometer
    vehicle.mileage = body.odometer  # refresh the truck's odometer so PM-by-miles recomputes
    # Reconcile the truck's active dashboard warning lights from this inspection
    # (a FAIL on a "Dashboard warnings" item means that light is illuminated).
    warning_on = [
        i.label for i in insp.items
        if i.is_warning_light and i.result == InspectionItemResult.FAIL
    ]
    if any(i.is_warning_light for i in insp.items):
        vehicle.active_warning_lights = ",".join(warning_on) if warning_on else None
    if body.notes is not None:
        insp.notes = body.notes
    await db.commit()
    return await _load_inspection_detail(db, current_user.tenant_id, inspection_id)


@router.post("/inspections/{inspection_id}/cancel", response_model=InspectionResponse)
async def cancel_inspection(
    inspection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    result = await db.execute(
        select(FleetInspection)
        .where(and_(FleetInspection.id == inspection_id, FleetInspection.tenant_id == current_user.tenant_id))
        .options(selectinload(FleetInspection.vehicle))
    )
    insp = result.scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    if insp.status == InspectionStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Completed inspections cannot be cancelled")
    insp.status = InspectionStatus.CANCELLED
    await db.commit()
    return _inspection_response(insp)


async def _reconcile_vehicle_warning_lights(db: AsyncSession, tenant_id: UUID, vehicle_id: UUID) -> None:
    """Recompute a truck's active warning lights from its most recent completed
    inspection — used after an inspection is deleted so stale lights clear."""
    result = await db.execute(
        select(FleetInspection)
        .where(and_(
            FleetInspection.vehicle_id == vehicle_id,
            FleetInspection.tenant_id == tenant_id,
            FleetInspection.status == InspectionStatus.COMPLETED,
        ))
        .options(selectinload(FleetInspection.items))
        .order_by(FleetInspection.performed_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    veh_result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = veh_result.scalar_one_or_none()
    if vehicle is None:
        return
    if latest is None:
        vehicle.active_warning_lights = None
        return
    warning_on = [i.label for i in latest.items if i.is_warning_light and i.result == InspectionItemResult.FAIL]
    vehicle.active_warning_lights = ",".join(warning_on) if warning_on else None


@router.delete("/inspections/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inspection(
    inspection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_garage_owner_only),
):
    """Permanently delete an inspection record. Garage owner only."""
    result = await db.execute(
        select(FleetInspection).where(
            and_(FleetInspection.id == inspection_id, FleetInspection.tenant_id == current_user.tenant_id)
        )
    )
    insp = result.scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    vehicle_id = insp.vehicle_id
    await db.delete(insp)  # checklist items cascade
    await db.flush()
    # Re-derive the truck's warning lights from whatever completed inspection
    # remains, so lights from the deleted inspection don't linger.
    await _reconcile_vehicle_warning_lights(db, current_user.tenant_id, vehicle_id)
    await db.commit()
    return None


@router.post("/inspections/{inspection_id}/create-work-order", response_model=InspectionDetailResponse)
async def create_work_order_for_inspection(
    inspection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Spawn an internal work order to fix a completed inspection's failed items,
    and link it back to the inspection for traceability."""
    result = await db.execute(
        select(FleetInspection)
        .where(and_(FleetInspection.id == inspection_id, FleetInspection.tenant_id == current_user.tenant_id))
        .options(selectinload(FleetInspection.items), selectinload(FleetInspection.vehicle))
    )
    insp = result.scalar_one_or_none()
    if not insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    if insp.status != InspectionStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Complete the inspection before creating a work order")
    if insp.repair_order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A work order already exists for this inspection")

    failed = [i.label for i in insp.items if i.result == InspectionItemResult.FAIL]
    if not failed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This inspection has no failed items to fix")

    when = insp.performed_at.date().isoformat() if insp.performed_at else insp.scheduled_for.isoformat()
    description = f"From {when} inspection: " + ", ".join(failed)
    ro = await _spawn_internal_ro(
        db, current_user.tenant_id, insp.vehicle, is_pm=False, description=description[:480],
    )
    insp.repair_order_id = ro.id
    await db.commit()
    return await _load_inspection_detail(db, current_user.tenant_id, inspection_id)


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------

@router.get("/incidents", response_model=List[IncidentResponse])
async def list_incidents(
    vehicle_id: Optional[UUID] = Query(None),
    status_filter: Optional[IncidentStatus] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    query = (
        select(FleetIncident)
        .where(FleetIncident.tenant_id == current_user.tenant_id)
        .options(
            selectinload(FleetIncident.vehicle),
            selectinload(FleetIncident.photos).selectinload(FleetIncidentPhoto.uploaded_by),
        )
        .order_by(FleetIncident.occurred_at.desc())
    )
    if vehicle_id:
        query = query.where(FleetIncident.vehicle_id == vehicle_id)
    if status_filter:
        query = query.where(FleetIncident.status == status_filter)
    result = await db.execute(query)
    return [_incident_response(i) for i in result.scalars().all()]


@router.post("/incidents", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    body: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    vehicle = await _get_fleet_vehicle(db, current_user.tenant_id, body.vehicle_id)
    incident = FleetIncident(
        id=uuid4(),
        tenant_id=current_user.tenant_id,
        vehicle_id=vehicle.id,
        reported_by_id=current_user.id,
        occurred_at=body.occurred_at,
        location=body.location,
        severity=body.severity,
        status=IncidentStatus.OPEN,
        description=body.description,
    )
    db.add(incident)
    await db.commit()
    await db.refresh(incident, attribute_names=["vehicle"])
    return _incident_response(incident)


@router.post("/incidents/{incident_id}/photos", response_model=FleetPhotoResponse, status_code=status.HTTP_201_CREATED)
async def upload_incident_photo(
    incident_id: UUID,
    image: UploadFile = File(...),
    caption: Optional[str] = Form(None, max_length=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    incident = await _load_incident(db, current_user.tenant_id, incident_id)
    if not is_cloudinary_configured():
        raise HTTPException(status_code=424, detail="Photo upload service is not configured. Add Cloudinary settings before uploading photos.")
    data_uri, _content_type = await _read_validated_fleet_image(image)
    try:
        image_url = await upload_work_photo(
            base64_image=data_uri,
            repair_order_id=f"fleet_incidents/{incident.id}",
            mechanic_id=str(current_user.id),
        )
    except Exception as exc:
        logger.error(
            "fleet_incident_photo_upload_failed",
            incident_id=str(incident.id),
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id),
            error=str(exc),
        )
        raise HTTPException(status_code=424, detail="Photo upload service failed. Check the Cloudinary settings and try again.") from exc
    photo = FleetIncidentPhoto(
        id=uuid4(),
        tenant_id=current_user.tenant_id,
        incident_id=incident.id,
        uploaded_by_id=current_user.id,
        image_url=image_url,
        caption=caption.strip() if caption else None,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo, attribute_names=["uploaded_by"])
    return _incident_photo_response(photo)


@router.post("/incidents/{incident_id}/photos/direct-upload-signature", response_model=DirectPhotoUploadSignatureResponse)
async def create_incident_photo_upload_signature(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    incident = await _load_incident(db, current_user.tenant_id, incident_id)
    if not is_cloudinary_configured():
        raise HTTPException(status_code=424, detail="Photo upload service is not configured. Add Cloudinary settings before uploading photos.")

    return create_direct_image_upload_signature(f"work_photos/fleet_incidents/{incident.id}")


@router.post("/incidents/{incident_id}/photos/direct", response_model=FleetPhotoResponse, status_code=status.HTTP_201_CREATED)
async def create_incident_photo_from_direct_upload(
    incident_id: UUID,
    body: DirectFleetIncidentPhotoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    incident = await _load_incident(db, current_user.tenant_id, incident_id)
    expected_folder = f"work_photos/fleet_incidents/{incident.id}/"
    if not body.public_id.startswith(expected_folder):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded photo does not belong to this incident")

    photo = FleetIncidentPhoto(
        id=uuid4(),
        tenant_id=current_user.tenant_id,
        incident_id=incident.id,
        uploaded_by_id=current_user.id,
        image_url=body.image_url,
        cloudinary_public_id=body.public_id,
        caption=body.caption.strip() if body.caption else None,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo, attribute_names=["uploaded_by"])
    return _incident_photo_response(photo)


@router.delete("/incidents/{incident_id}/photos/{photo_id}")
async def delete_incident_photo(
    incident_id: UUID,
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    result = await db.execute(
        select(FleetIncidentPhoto, FleetIncident)
        .join(FleetIncident, FleetIncidentPhoto.incident_id == FleetIncident.id)
        .where(
            and_(
                FleetIncidentPhoto.id == photo_id,
                FleetIncidentPhoto.incident_id == incident_id,
                FleetIncident.tenant_id == current_user.tenant_id,
            )
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    photo, incident = row
    await db.delete(photo)
    await db.commit()
    logger.info(
        "fleet_incident_photo_deleted",
        photo_id=str(photo_id),
        incident_id=str(incident.id),
        tenant_id=str(current_user.tenant_id),
        deleted_by=str(current_user.id),
    )
    return {"message": "Photo deleted"}


async def _load_incident(db: AsyncSession, tenant_id: UUID, incident_id: UUID) -> FleetIncident:
    result = await db.execute(
        select(FleetIncident)
        .where(and_(FleetIncident.id == incident_id, FleetIncident.tenant_id == tenant_id))
        .options(
            selectinload(FleetIncident.vehicle),
            selectinload(FleetIncident.photos).selectinload(FleetIncidentPhoto.uploaded_by),
        )
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    return _incident_response(await _load_incident(db, current_user.tenant_id, incident_id))


@router.patch("/incidents/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: UUID,
    body: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    incident = await _load_incident(db, current_user.tenant_id, incident_id)
    if body.severity is not None:
        incident.severity = body.severity
    if body.location is not None:
        incident.location = body.location
    if body.description is not None:
        incident.description = body.description
    if body.resolution_notes is not None:
        incident.resolution_notes = body.resolution_notes
    if body.status is not None:
        incident.status = body.status
        if body.status == IncidentStatus.RESOLVED and incident.resolved_at is None:
            incident.resolved_at = datetime.now(timezone.utc)
        if body.status != IncidentStatus.RESOLVED:
            incident.resolved_at = None
    await db.commit()
    return _incident_response(incident)


@router.post("/incidents/{incident_id}/create-repair", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_repair_for_incident(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    incident = await _load_incident(db, current_user.tenant_id, incident_id)
    if incident.repair_order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A repair order already exists for this incident")

    from app.api.v1.endpoints.repair_orders import generate_order_number
    from app.core.unique_id import create_with_retry
    from app.core.metrics import record_repair_order_created

    fleet_customer_id = await _fleet_customer_id(db, current_user.tenant_id)

    async def _create(order_number: str) -> RepairOrder:
        ro = RepairOrder(
            id=uuid4(),
            tenant_id=current_user.tenant_id,
            customer_id=fleet_customer_id,
            vehicle_id=incident.vehicle_id,
            order_number=order_number,
            status=RepairOrderStatus.DRAFT,
            is_internal=True,
            description=f"Incident repair: {incident.description[:240]}",
        )
        db.add(ro)
        return ro

    ro = await create_with_retry(
        db=db,
        create_fn=_create,
        generate_number_fn=lambda: generate_order_number(db, current_user.tenant_id),
        entity_name="repair_order",
    )
    incident.repair_order_id = ro.id
    if incident.status == IncidentStatus.OPEN:
        incident.status = IncidentStatus.IN_PROGRESS
    await db.commit()
    record_repair_order_created(str(current_user.tenant_id))
    await db.refresh(incident, attribute_names=["vehicle"])
    return _incident_response(incident)


@router.delete("/incidents/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_incident(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Delete a road-incident log entry. Blocked when a repair order was spawned
    from it — handle/delete that repair order first, so the incident→repair trail
    isn't silently orphaned."""
    incident = await _load_incident(db, current_user.tenant_id, incident_id)
    if incident.repair_order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This incident has a linked repair order. Delete or unlink the repair order first.",
        )
    await db.delete(incident)
    await db.commit()


# ---------------------------------------------------------------------------
# Fleet board & truck detail (design: KPI strip + truck cards + detail)
# ---------------------------------------------------------------------------

def _mechanic_name(user: Optional[User]) -> Optional[str]:
    if not user:
        return None
    return f"{user.first_name} {user.last_name}".strip() or user.email


def _wo_label(ro: RepairOrder) -> str:
    if ro.hold_reason and "part" in ro.hold_reason.lower():
        return "Awaiting parts"
    return WO_STATUS_LABELS.get(ro.status, "In shop")


def _pm_remaining(v: Vehicle) -> Optional[int]:
    if v.next_pm_miles is None or v.mileage is None:
        return None
    return v.next_pm_miles - v.mileage


def _pm_days_remaining(v: Vehicle) -> Optional[int]:
    if v.pm_due_date is None:
        return None
    return (v.pm_due_date - date.today()).days


def _pm_due_soon(v: Vehicle) -> bool:
    """PM is due soon when either the odometer or the scheduled date is close."""
    rem_mi = _pm_remaining(v)
    if rem_mi is not None and rem_mi < PM_DUE_SOON_MILES:
        return True
    rem_days = _pm_days_remaining(v)
    if rem_days is not None and rem_days <= PM_DUE_SOON_DAYS:
        return True
    return False


def _derive_status(v: Vehicle, open_ro: Optional[RepairOrder]) -> str:
    if open_ro is not None:
        if open_ro.hold_reason and "part" in open_ro.hold_reason.lower():
            return "parts"
        # A fresh, unassigned, not-yet-started work order is a draft — keep it
        # visually distinct from a truck that's actively in the shop.
        if (
            open_ro.status == RepairOrderStatus.DRAFT
            and open_ro.assigned_mechanic_id is None
            and open_ro.work_started_at is None
        ):
            return "draft"
        return "shop"
    # No open work order: operator's manual status wins, then PM (date or mileage).
    if v.status_override in VALID_STATUS_OVERRIDES:
        return v.status_override
    if _pm_due_soon(v):
        return "pm"
    return "active"


def _board_work_order(ro: RepairOrder) -> BoardWorkOrder:
    raw = ro.status.value if hasattr(ro.status, "value") else str(ro.status)
    return BoardWorkOrder(
        id=ro.order_number,
        repair_order_id=ro.id,
        status=_wo_label(ro),
        raw_status=raw,
        summary=ro.description,
        mechanic=_mechanic_name(ro.assigned_mechanic),
        is_pm=bool(ro.is_pm),
    )


def _open_pm_ro(ros: list[RepairOrder]) -> Optional[RepairOrder]:
    """The truck's open PM work order, if one exists. Only one PM should be open
    at a time (completing it rolls the schedule forward); if several exist we take
    the most-urgent so the card drives the one furthest along."""
    pms = [r for r in ros if r.is_pm]
    return _most_urgent_ro(pms) if pms else None


# Lower sort key = more urgent. Parts-hold beats everything, then active work
# down to drafts; most-recently-created breaks ties.
_WO_URGENCY = {
    RepairOrderStatus.IN_PROGRESS: 0,
    RepairOrderStatus.PENDING_REVIEW: 1,
    RepairOrderStatus.ACKNOWLEDGED: 2,
    RepairOrderStatus.ASSIGNED: 3,
    RepairOrderStatus.APPROVED: 4,
    RepairOrderStatus.QUOTED: 5,
    RepairOrderStatus.DRAFT: 6,
}


def _most_urgent_ro(ros: list[RepairOrder]) -> Optional[RepairOrder]:
    if not ros:
        return None

    def key(r: RepairOrder):
        is_parts = bool(r.hold_reason and "part" in r.hold_reason.lower())
        created = r.created_at.timestamp() if r.created_at else 0
        return (0 if is_parts else 1, _WO_URGENCY.get(r.status, 9), -created)

    return sorted(ros, key=key)[0]


def _build_board_truck(
    v: Vehicle,
    open_ro: Optional[RepairOrder],
    incident_count: int,
    open_wo_count: int = 0,
    pm_ro: Optional[RepairOrder] = None,
    pm_services: Optional[list["PMServiceEntry"]] = None,
) -> BoardTruck:
    status_str = _derive_status(v, open_ro)
    wo = None
    mechanic = None
    if open_ro is not None:
        mechanic = _mechanic_name(open_ro.assigned_mechanic)
        wo = _board_work_order(open_ro)
    # The open PM work order (if any) drives the PM Schedule card's Start/Complete
    # actions. It may or may not be the most-urgent open WO shown above.
    pm_wo = _board_work_order(pm_ro) if pm_ro is not None else None
    moving = bool(v.last_speed_mph and v.last_speed_mph > 0)
    return BoardTruck(
        id=v.id,
        unit_number=v.unit_number,
        year=v.year,
        make=v.make,
        model=v.model,
        brand_short=(v.make[:2].upper() if v.make else None),
        body_type=v.nhtsa_body_class,
        vin=v.vin,
        plate=v.license_plate,
        status=status_str,
        driver_name=v.driver_name,
        driver_phone=v.driver_phone,
        odometer=v.mileage,
        pm_interval_miles=v.pm_interval_miles or 25000,
        next_pm_miles=v.next_pm_miles,
        pm_remaining=_pm_remaining(v),
        pm_interval_days=v.pm_interval_days or 70,
        pm_due_date=v.pm_due_date,
        pm_days_remaining=_pm_days_remaining(v),
        location_label=v.last_location_label,
        location_city=v.last_location_city,
        lat=v.last_lat,
        lng=v.last_lng,
        moving=moving,
        speed_mph=v.last_speed_mph,
        heading=v.last_heading,
        assigned_mechanic=mechanic,
        work_order=wo,
        pm_work_order=pm_wo,
        pm_services=pm_services or [],
        open_work_order_count=open_wo_count,
        open_incident_count=incident_count,
        status_override=v.status_override if v.status_override in VALID_STATUS_OVERRIDES else None,
        warning_lights=[s for s in (v.active_warning_lights or "").split(",") if s],
    )


async def _fleet_vehicles(db: AsyncSession, tenant_id: UUID) -> list[Vehicle]:
    fleet_customer_id = await _fleet_customer_id(db, tenant_id)
    result = await db.execute(
        select(Vehicle).where(
            and_(
                Vehicle.tenant_id == tenant_id,
                Vehicle.customer_id == fleet_customer_id,
                Vehicle.deleted_at.is_(None),
            )
        ).order_by(Vehicle.unit_number, Vehicle.make)
    )
    return list(result.scalars().all())


async def _fleet_board_vehicles(db: AsyncSession, tenant_id: UUID) -> list[Vehicle]:
    """Read the existing internal fleet without creating or committing on GET."""
    result = await db.execute(
        select(Vehicle)
        .join(Customer, Customer.id == Vehicle.customer_id)
        .where(
            and_(
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
                Customer.is_internal_fleet.is_(True),
                Customer.deleted_at.is_(None),
            )
        )
        .order_by(Vehicle.unit_number, Vehicle.make)
    )
    return list(result.scalars().all())


async def _open_ros_by_vehicle(db: AsyncSession, vehicle_ids: list[UUID]) -> dict[UUID, list[RepairOrder]]:
    """All active (non-terminal) internal ROs per vehicle, newest first.

    A truck can have several open work orders at once (e.g. multiple in a week);
    callers pick the most-urgent for the board card and list the rest on the
    truck profile.
    """
    if not vehicle_ids:
        return {}
    result = await db.execute(
        select(RepairOrder)
        .where(
            and_(
                RepairOrder.vehicle_id.in_(vehicle_ids),
                RepairOrder.is_internal.is_(True),
                RepairOrder.status.notin_(list(TERMINAL_RO_STATUSES)),
                RepairOrder.deleted_at.is_(None),
            )
        )
        .options(selectinload(RepairOrder.assigned_mechanic))
        .order_by(RepairOrder.vehicle_id, RepairOrder.created_at.desc())
    )
    out: dict[UUID, list[RepairOrder]] = {}
    for ro in result.scalars().all():
        out.setdefault(ro.vehicle_id, []).append(ro)
    return out


async def _open_incident_counts(db: AsyncSession, vehicle_ids: list[UUID]) -> dict[UUID, int]:
    if not vehicle_ids:
        return {}
    rows = await db.execute(
        select(FleetIncident.vehicle_id, func.count(FleetIncident.id))
        .where(
            and_(
                FleetIncident.vehicle_id.in_(vehicle_ids),
                FleetIncident.status != IncidentStatus.RESOLVED,
            )
        )
        .group_by(FleetIncident.vehicle_id)
    )
    return {row[0]: row[1] for row in rows.all()}


async def _fleet_board_from_projection(
    db: AsyncSession, tenant_id: UUID
) -> tuple[list[BoardTruck], set[UUID]]:
    """Load board cards through the compact projection and bounded lookups.

    Missing rows are intentionally returned to the legacy builder during a
    migration restore/backfill. Once backfilled this path is bounded reads:
    card rows, live driver phones, mechanics referenced by open work orders,
    and PM services.
    """
    rows = list((await db.execute(
        select(FleetBoardReadModel)
        .where(FleetBoardReadModel.tenant_id == tenant_id)
        .order_by(FleetBoardReadModel.vehicle_id)
    )).scalars().all())
    if not rows:
        return [], set()

    mechanic_ids = {
        UUID(payload["assigned_mechanic_id"])
        for row in rows
        for payload in (row.urgent_work_order, row.pm_work_order)
        if payload and payload.get("assigned_mechanic_id")
    }
    mechanics: dict[UUID, str] = {}
    if mechanic_ids:
        mechanic_rows = await db.execute(select(User).where(User.id.in_(mechanic_ids)))
        mechanics = {
            user.id: _mechanic_name(user) or ""
            for user in mechanic_rows.scalars().all()
        }

    phone_rows = await db.execute(
        select(Vehicle.id, Vehicle.driver_phone).where(Vehicle.id.in_([row.vehicle_id for row in rows]))
    )
    driver_phones = {vehicle_id: driver_phone for vehicle_id, driver_phone in phone_rows.all()}

    pm_services = await _pm_services_by_vehicle(db, tenant_id, [row.vehicle_id for row in rows])
    trucks: list[BoardTruck] = []
    for row in rows:
        data = dict(row.vehicle_data)

        def work_order(payload: Optional[dict]) -> Optional[BoardWorkOrder]:
            if not payload:
                return None
            mechanic_id = payload.get("assigned_mechanic_id")
            return BoardWorkOrder(
                id=payload["order_number"],
                repair_order_id=payload["id"],
                status=("Awaiting parts" if payload.get("awaiting_parts") else WO_STATUS_LABELS.get(payload["status"], "In shop")),
                raw_status=payload["status"],
                summary=payload.get("description"),
                mechanic=mechanics.get(UUID(mechanic_id)) if mechanic_id else None,
                is_pm=bool(payload.get("is_pm")),
            )

        urgent = work_order(row.urgent_work_order)
        data.update({
            "id": row.vehicle_id,
            "driver_phone": driver_phones.get(row.vehicle_id) or data.get("driver_phone"),
            "status": _derive_projected_status(data, row.urgent_work_order),
            "moving": bool(data.get("speed_mph") and data["speed_mph"] > 0),
            "assigned_mechanic": urgent.mechanic if urgent else None,
            "work_order": urgent,
            "pm_work_order": work_order(row.pm_work_order),
            "pm_services": pm_services.get(row.vehicle_id, []),
            "open_work_order_count": row.open_work_order_count,
            "open_incident_count": row.open_incident_count,
            "warning_lights": [value for value in (data.pop("active_warning_lights", "") or "").split(",") if value],
        })
        trucks.append(BoardTruck(**data))
    return trucks, {row.vehicle_id for row in rows}


def _derive_projected_status(vehicle: dict, urgent_work_order: Optional[dict]) -> str:
    """Status equivalent of ``_derive_status`` for projection JSON data."""
    if urgent_work_order:
        if urgent_work_order.get("awaiting_parts"):
            return "parts"
        if (
            urgent_work_order.get("status") == RepairOrderStatus.DRAFT.value
            and urgent_work_order.get("assigned_mechanic_id") is None
            and urgent_work_order.get("work_started_at") is None
        ):
            return "draft"
        return "shop"
    if vehicle.get("status_override") in VALID_STATUS_OVERRIDES:
        return vehicle["status_override"]
    mileage = vehicle.get("mileage")
    next_pm = vehicle.get("next_pm_miles")
    pm_due_date = vehicle.get("pm_due_date")
    pm_due_soon = next_pm is not None and mileage is not None and next_pm - mileage < PM_DUE_SOON_MILES
    if pm_due_date:
        due = date.fromisoformat(pm_due_date) if isinstance(pm_due_date, str) else pm_due_date
        pm_due_soon = pm_due_soon or (due - date.today()).days <= PM_DUE_SOON_DAYS
    return "pm" if pm_due_soon else "active"


@router.get("/board", response_model=FleetBoardResponse)
async def fleet_board(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    trucks, projected_ids = await _fleet_board_from_projection(db, current_user.tenant_id)
    # Projection rows are backfilled by the migration. Retain the old builder
    # only for missing rows so restores and rolling deployments stay correct.
    vehicles = await _fleet_board_vehicles(db, current_user.tenant_id)
    missing_vehicles = [vehicle for vehicle in vehicles if vehicle.id not in projected_ids]
    if missing_vehicles:
        ids = [v.id for v in missing_vehicles]
        open_ros = await _open_ros_by_vehicle(db, ids)
        incidents = await _open_incident_counts(db, ids)
        pm_svcs = await _pm_services_by_vehicle(db, current_user.tenant_id, ids)
        trucks.extend(
            _build_board_truck(
                v, _most_urgent_ro(open_ros.get(v.id, [])), incidents.get(v.id, 0), len(open_ros.get(v.id, [])),
                pm_ro=_open_pm_ro(open_ros.get(v.id, [])), pm_services=pm_svcs.get(v.id, []),
            )
            for v in missing_vehicles
        )
    trucks.sort(key=lambda truck: ((truck.unit_number or ""), str(truck.id)))
    stats = FleetStats(
        total=len(trucks),
        active=sum(1 for t in trucks if t.status == "active"),
        shop=sum(1 for t in trucks if t.status == "shop"),
        pm=sum(1 for t in trucks if t.status == "pm"),
        parts=sum(1 for t in trucks if t.status == "parts"),
        open_wo=sum(1 for t in trucks if t.work_order is not None),
        incidents_total=sum(t.open_incident_count for t in trucks),
    )
    return FleetBoardResponse(trucks=trucks, stats=stats)


def _haversine_miles(a_lat, a_lng, b_lat, b_lng) -> int:
    R = 3958.8
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlmb = math.radians(b_lng - a_lng)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return round(2 * R * math.asin(math.sqrt(h)))


async def _load_fleet_vehicle_or_404(db: AsyncSession, tenant_id: UUID, vehicle_id: UUID) -> Vehicle:
    return await _get_fleet_vehicle(db, tenant_id, vehicle_id)


@router.get("/trucks/{vehicle_id}", response_model=TruckDetailResponse)
async def truck_detail(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    vehicle = await _load_fleet_vehicle_or_404(db, current_user.tenant_id, vehicle_id)

    # All internal ROs for this truck (for history, work order, spend, parts).
    ro_result = await db.execute(
        select(RepairOrder)
        .where(and_(
            RepairOrder.vehicle_id == vehicle_id,
            RepairOrder.is_internal.is_(True),
            RepairOrder.deleted_at.is_(None),
        ))
        .options(selectinload(RepairOrder.assigned_mechanic))
        .order_by(RepairOrder.created_at.desc())
    )
    ros = list(ro_result.scalars().all())
    open_ros = [r for r in ros if r.status not in TERMINAL_RO_STATUSES]
    completed = [r for r in ros if r.status in (RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED, RepairOrderStatus.PAID)]

    board = _build_board_truck(vehicle, _most_urgent_ro(open_ros), 0, len(open_ros), pm_ro=_open_pm_ro(open_ros))

    # History: completed internal ROs (PM/Repair) + completed inspections.
    history: list[HistoryEntry] = []
    crew: set[str] = set()
    lifetime = 0.0
    for r in completed:
        mech = _mechanic_name(r.assigned_mechanic)
        if mech:
            crew.add(mech)
        cost = float(r.total_cost or 0)
        lifetime += cost
        history.append(HistoryEntry(
            id=r.id,
            date=r.work_completed_at or r.updated_at,
            kind="PM" if r.is_pm else "Repair",
            odometer=r.mileage_out or r.mileage_in,
            summary=r.description,
            mechanic=mech,
            cost=cost,
        ))
    insp_result = await db.execute(
        select(FleetInspection)
        .where(and_(FleetInspection.vehicle_id == vehicle_id, FleetInspection.status == InspectionStatus.COMPLETED))
        .options(selectinload(FleetInspection.inspector))
    )
    for insp in insp_result.scalars().all():
        mech = _mechanic_name(insp.inspector)
        history.append(HistoryEntry(
            id=insp.id,
            date=insp.performed_at,
            kind="Inspection",
            odometer=insp.odometer,
            summary=f"Weekly inspection — {insp.result.value if insp.result else 'completed'}",
            mechanic=mech,
            cost=None,
        ))
    history.sort(key=lambda h: (h.date or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)

    # Parts & warranty across this truck's ROs.
    ro_ids = [r.id for r in ros]
    parts: list[PartEntry] = []
    if ro_ids:
        pu_result = await db.execute(
            select(PartsUsage)
            .where(PartsUsage.repair_order_id.in_(ro_ids))
            .options(selectinload(PartsUsage.inventory_item))
            .order_by(PartsUsage.created_at.desc())
        )
        today = datetime.now(timezone.utc).date()
        for pu in pu_result.scalars().all():
            parts.append(PartEntry(
                id=pu.id,
                name=pu.inventory_item.name if pu.inventory_item else "Part",
                date=pu.created_at,
                odometer=vehicle.mileage,
                mechanic=None,
                warranty_until=pu.warranty_until,
                warranty_miles=pu.warranty_miles,
                active=bool(pu.warranty_until and pu.warranty_until >= today),
            ))

    # Incidents for this truck.
    inc_result = await db.execute(
        select(FleetIncident)
        .where(FleetIncident.vehicle_id == vehicle_id)
        .options(selectinload(FleetIncident.photos).selectinload(FleetIncidentPhoto.uploaded_by))
        .order_by(FleetIncident.occurred_at.desc())
    )
    incident_rows = list(inc_result.scalars().all())
    incidents = [
        IncidentEntry(
            id=i.id,
            date=i.occurred_at,
            type=(i.description.split("\n")[0][:60] if i.description else "Incident"),
            severity=i.severity,
            status=i.status,
            location=i.location,
            note=i.description,
            repair_order_id=i.repair_order_id,
            photos=[_incident_photo_response(photo) for photo in sorted(i.photos or [], key=lambda p: p.uploaded_at, reverse=True)],
        )
        for i in incident_rows
    ]
    open_incident_count = sum(1 for i in incident_rows if i.status != IncidentStatus.RESOLVED)
    board.open_incident_count = open_incident_count

    # Nearest units (needs coordinates on both ends).
    nearest: list[NearestUnit] = []
    if vehicle.last_lat is not None and vehicle.last_lng is not None:
        others = await _fleet_vehicles(db, current_user.tenant_id)
        others_open = await _open_ros_by_vehicle(db, [o.id for o in others if o.id != vehicle_id])
        cand = []
        for o in others:
            if o.id == vehicle_id or o.last_lat is None or o.last_lng is None:
                continue
            miles = _haversine_miles(vehicle.last_lat, vehicle.last_lng, o.last_lat, o.last_lng)
            cand.append(NearestUnit(
                id=o.id, unit_number=o.unit_number, city=o.last_location_city,
                status=_derive_status(o, _most_urgent_ro(others_open.get(o.id, []))), miles=miles,
            ))
        cand.sort(key=lambda n: n.miles)
        nearest = cand[:3]

    return TruckDetailResponse(
        truck=board,
        open_work_orders=[_board_work_order(r) for r in open_ros],
        driver_phone=vehicle.driver_phone,
        billing_contact_name=vehicle.billing_contact_name,
        billing_contact_email=vehicle.billing_contact_email,
        billing_contact_phone=vehicle.billing_contact_phone,
        bill_labor_at_customer_rate=vehicle.bill_labor_at_customer_rate,
        lifetime_spend=round(lifetime, 2),
        incidents_count=len(incident_rows),
        crew=sorted(crew),
        history=history,
        parts=parts,
        incidents=incidents,
        nearest=nearest,
    )


@router.patch("/trucks/{vehicle_id}", response_model=BoardTruck)
async def update_truck(
    vehicle_id: UUID,
    body: TruckUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    vehicle = await _load_fleet_vehicle_or_404(db, current_user.tenant_id, vehicle_id)
    # Identity edits (make/model are required columns — ignore blanks).
    vin_changed = False
    if body.unit_number is not None:
        vehicle.unit_number = body.unit_number or None
    if body.vin is not None:
        new_vin = body.vin.strip().upper() or None
        vin_changed = new_vin != vehicle.vin
        vehicle.vin = new_vin
    if body.make is not None and body.make.strip():
        vehicle.make = body.make.strip()
    if body.model is not None and body.model.strip():
        vehicle.model = body.model.strip()
    if body.year is not None:
        vehicle.year = body.year
    if body.license_plate is not None:
        vehicle.license_plate = body.license_plate or None
    if body.driver_name is not None:
        vehicle.driver_name = body.driver_name or None
    if body.driver_phone is not None:
        vehicle.driver_phone = normalize_phone(body.driver_phone)
    if body.billing_contact_name is not None:
        vehicle.billing_contact_name = body.billing_contact_name or None
    if body.billing_contact_email is not None:
        vehicle.billing_contact_email = body.billing_contact_email.strip().lower() or None
    if body.billing_contact_phone is not None:
        vehicle.billing_contact_phone = normalize_phone(body.billing_contact_phone)
    if body.bill_labor_at_customer_rate is not None:
        vehicle.bill_labor_at_customer_rate = body.bill_labor_at_customer_rate
    if body.odometer is not None:
        vehicle.mileage = body.odometer
    if body.pm_interval_miles is not None:
        vehicle.pm_interval_miles = body.pm_interval_miles
    if body.next_pm_miles is not None:
        vehicle.next_pm_miles = body.next_pm_miles
    if body.pm_interval_days is not None:
        vehicle.pm_interval_days = body.pm_interval_days
    if body.pm_due_date is not None:
        vehicle.pm_due_date = body.pm_due_date
    if body.telematics_device_id is not None:
        vehicle.telematics_device_id = body.telematics_device_id or None
    # Manual location entry.
    if body.lat is not None:
        vehicle.last_lat = body.lat
    if body.lng is not None:
        vehicle.last_lng = body.lng
    if body.location_label is not None:
        vehicle.last_location_label = body.location_label or None
    if body.location_city is not None:
        vehicle.last_location_city = body.location_city or None
    if body.speed_mph is not None:
        vehicle.last_speed_mph = body.speed_mph
    if body.heading is not None:
        vehicle.last_heading = body.heading or None
    if body.status_override is not None:
        val = body.status_override.strip().lower()
        if val in ("", "auto"):
            vehicle.status_override = None
        elif val in VALID_STATUS_OVERRIDES:
            vehicle.status_override = val
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    if any(v is not None for v in (body.lat, body.lng, body.speed_mph, body.heading, body.location_label)):
        vehicle.last_location_at = datetime.now(timezone.utc)
    # Refresh body type from the new VIN (only touches nhtsa_* fields, not make/model).
    if vin_changed and vehicle.vin:
        from app.services.vehicle_nhtsa_service import sync_vehicle_nhtsa_snapshot
        try:
            await sync_vehicle_nhtsa_snapshot(vehicle)
        except Exception:
            pass
    await db.commit()

    open_list = (await _open_ros_by_vehicle(db, [vehicle.id])).get(vehicle.id, [])
    counts = await _open_incident_counts(db, [vehicle.id])
    return _build_board_truck(vehicle, _most_urgent_ro(open_list), counts.get(vehicle.id, 0), len(open_list), pm_ro=_open_pm_ro(open_list))


async def _load_fleet_ro_or_404(db: AsyncSession, tenant_id: UUID, ro_id: UUID) -> RepairOrder:
    result = await db.execute(
        select(RepairOrder)
        .where(and_(
            RepairOrder.id == ro_id,
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.is_internal.is_(True),
            RepairOrder.deleted_at.is_(None),
        ))
        .options(
            selectinload(RepairOrder.assigned_mechanic),
            selectinload(RepairOrder.customer),
            selectinload(RepairOrder.vehicle),
        )
    )
    ro = result.scalar_one_or_none()
    if not ro:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work order not found")
    return ro


@router.post("/work-orders/{ro_id}/start", response_model=BoardWorkOrder)
async def start_work_order(
    ro_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Move an internal work order into progress. Fleet-manager driven —
    assigning a mechanic is optional, not required to start."""
    ro = await _load_fleet_ro_or_404(db, current_user.tenant_id, ro_id)
    startable = (
        RepairOrderStatus.DRAFT, RepairOrderStatus.ASSIGNED,
        RepairOrderStatus.ACKNOWLEDGED, RepairOrderStatus.IN_PROGRESS,
    )
    if ro.status not in startable:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot start a work order in '{ro.status.value}' status")
    if ro.status != RepairOrderStatus.IN_PROGRESS:
        ro.status = RepairOrderStatus.IN_PROGRESS
        if ro.work_started_at is None:
            ro.work_started_at = datetime.now(timezone.utc)
        await db.commit()
    ro = await _load_fleet_ro_or_404(db, current_user.tenant_id, ro_id)
    return _board_work_order(ro)


@router.post("/work-orders/{ro_id}/complete", response_model=BoardWorkOrder)
async def complete_work_order(
    ro_id: UUID,
    body: Optional[WorkOrderComplete] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Complete a fleet work order and create its billable customer invoice."""
    ro = await _load_fleet_ro_or_404(db, current_user.tenant_id, ro_id)
    if ro.status not in (RepairOrderStatus.IN_PROGRESS, RepairOrderStatus.PENDING_REVIEW):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot complete a work order in '{ro.status.value}' status")

    veh_result = await db.execute(select(Vehicle).where(Vehicle.id == ro.vehicle_id))
    veh = veh_result.scalar_one_or_none()
    if not veh or not veh.billing_contact_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Add this truck's invoice contact email before completing its work order.",
        )

    # Mileage-out: use the manual reading if provided (fallback), otherwise the
    # truck's current odometer (kept current by inspections).
    manual_out = body.mileage_out if body else None
    if manual_out is not None:
        ro.mileage_out = manual_out
    elif veh is not None and veh.mileage is not None:
        ro.mileage_out = veh.mileage

    ro.status = RepairOrderStatus.COMPLETED
    ro.work_completed_at = datetime.now(timezone.utc)
    # A completed PM rolls the truck's next PM forward (mileage + date), using
    # the mileage-out we just recorded.
    if ro.is_pm and veh is not None:
        from app.services.internal_fleet import advance_vehicle_pm
        advance_vehicle_pm(veh, ro.mileage_out)
    # Completing a work order clears the truck's dashboard warning lights —
    # the issue behind them is assumed resolved (a later inspection re-flags any
    # that are still on).
    if veh is not None:
        veh.active_warning_lights = None
    await db.commit()
    from app.api.v1.endpoints.invoices import auto_create_invoice_for_order
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one()
    await auto_create_invoice_for_order(
        db=db, order=ro, tenant=tenant, created_by_user_id=current_user.id,
    )
    ro = await _load_fleet_ro_or_404(db, current_user.tenant_id, ro_id)
    return _board_work_order(ro)


async def _spawn_internal_ro(db: AsyncSession, tenant_id: UUID, vehicle: Vehicle, *, is_pm: bool, description: str) -> RepairOrder:
    from app.api.v1.endpoints.repair_orders import generate_order_number
    from app.core.unique_id import create_with_retry
    from app.core.metrics import record_repair_order_created

    fleet_customer_id = await _fleet_customer_id(db, tenant_id)

    async def _create(order_number: str) -> RepairOrder:
        ro = RepairOrder(
            id=uuid4(), tenant_id=tenant_id, customer_id=fleet_customer_id,
            vehicle_id=vehicle.id, order_number=order_number,
            status=RepairOrderStatus.DRAFT, is_internal=True, is_pm=is_pm,
            bill_labor_at_customer_rate=vehicle.bill_labor_at_customer_rate,
            description=description,
            # Auto-capture mileage-in from the truck's current odometer (kept
            # current by inspections). Fleet managers don't re-enter it.
            mileage_in=vehicle.mileage,
        )
        db.add(ro)
        return ro

    ro = await create_with_retry(
        db=db, create_fn=_create,
        generate_number_fn=lambda: generate_order_number(db, tenant_id),
        entity_name="repair_order",
    )
    await db.commit()
    record_repair_order_created(str(tenant_id))
    return ro


# ---------- PM services (per-truck default package + per-work-order instance) ----------

async def _load_pm_services(db: AsyncSession, tenant_id: UUID, service_ids: list[UUID]) -> list[Service]:
    """Load the given services (tenant-scoped, active), preserving the caller's
    order and dropping unknown ids. Parts are eager-loaded for cost seeding."""
    if not service_ids:
        return []
    result = await db.execute(
        select(Service)
        .where(and_(
            Service.id.in_(service_ids),
            Service.tenant_id == tenant_id,
            Service.is_active.is_(True),
        ))
        .options(selectinload(Service.service_parts).selectinload(ServicePart.inventory_item))
    )
    by_id = {s.id: s for s in result.scalars().all()}
    # Preserve request order; de-dup.
    seen: set[UUID] = set()
    ordered: list[Service] = []
    for sid in service_ids:
        if sid in by_id and sid not in seen:
            ordered.append(by_id[sid])
            seen.add(sid)
    return ordered


def _pm_service_entries(services: list[Service]) -> list[PMServiceEntry]:
    return [
        PMServiceEntry(
            service_id=s.id, name=s.name,
            duration_minutes=s.duration_minutes or 0, sort_order=i,
        )
        for i, s in enumerate(services)
    ]


async def _vehicle_pm_service_ids(db: AsyncSession, vehicle_id: UUID) -> list[UUID]:
    result = await db.execute(
        select(VehiclePMService.service_id)
        .where(VehiclePMService.vehicle_id == vehicle_id)
        .order_by(VehiclePMService.sort_order)
    )
    return list(result.scalars().all())


async def _vehicle_pm_services(db: AsyncSession, tenant_id: UUID, vehicle_id: UUID) -> list[Service]:
    return await _load_pm_services(db, tenant_id, await _vehicle_pm_service_ids(db, vehicle_id))


async def _pm_services_by_vehicle(
    db: AsyncSession, tenant_id: UUID, vehicle_ids: list[UUID]
) -> dict[UUID, list[PMServiceEntry]]:
    """Default PM service packages for many trucks at once (board view). Reads
    the join rows and service names in two queries, then groups per vehicle."""
    if not vehicle_ids:
        return {}
    rows = await db.execute(
        select(VehiclePMService.vehicle_id, VehiclePMService.service_id,
               VehiclePMService.sort_order, Service.name, Service.duration_minutes)
        .join(Service, Service.id == VehiclePMService.service_id)
        .where(and_(
            VehiclePMService.vehicle_id.in_(vehicle_ids),
            Service.is_active.is_(True),
        ))
        .order_by(VehiclePMService.vehicle_id, VehiclePMService.sort_order)
    )
    out: dict[UUID, list[PMServiceEntry]] = {}
    for vid, sid, order, name, duration in rows.all():
        out.setdefault(vid, []).append(
            PMServiceEntry(service_id=sid, name=name, duration_minutes=duration or 0, sort_order=order)
        )
    return out


async def _set_vehicle_pm_services(
    db: AsyncSession, tenant_id: UUID, vehicle_id: UUID, services: list[Service]
) -> None:
    """Replace a truck's default PM package with the given services (order kept)."""
    existing = await db.execute(
        select(VehiclePMService).where(VehiclePMService.vehicle_id == vehicle_id)
    )
    for row in existing.scalars().all():
        await db.delete(row)
    for i, s in enumerate(services):
        db.add(VehiclePMService(
            id=uuid4(), tenant_id=tenant_id, vehicle_id=vehicle_id,
            service_id=s.id, sort_order=i,
        ))


async def _apply_pm_services_to_ro(
    db: AsyncSession, tenant_id: UUID, ro: RepairOrder, services: list[Service]
) -> None:
    """Attach `services` to the PM work order: record the per-PM service list,
    roll the service names into the description (manager-facing scope), and
    re-seed the owner-facing labor + parts cost lines from those services.

    Idempotent: prior service-sourced rows are cleared and rebuilt, so this can
    run again whenever the service selection changes (while the WO is a draft).
    """
    from decimal import Decimal

    # 1) Replace the per-PM service rows.
    existing = await db.execute(
        select(RepairOrderPMService).where(RepairOrderPMService.repair_order_id == ro.id)
    )
    for row in existing.scalars().all():
        await db.delete(row)
    for i, s in enumerate(services):
        db.add(RepairOrderPMService(
            id=uuid4(), tenant_id=tenant_id, repair_order_id=ro.id,
            service_id=s.id, sort_order=i,
        ))

    # 2) Clear previously seeded (service-sourced) labor & parts lines. Manually
    # added lines (source_service_id IS NULL) are left untouched.
    old_labor = await db.execute(
        select(Labor).where(and_(
            Labor.repair_order_id == ro.id,
            Labor.source_service_id.isnot(None),
        ))
    )
    for row in old_labor.scalars().all():
        await db.delete(row)
    old_parts = await db.execute(
        select(PartsUsage).where(and_(
            PartsUsage.repair_order_id == ro.id,
            PartsUsage.source_service_id.isnot(None),
        ))
    )
    for row in old_parts.scalars().all():
        await db.delete(row)

    # 3) Manager-facing scope: PM description lists the selected service names.
    #    When no services are selected, keep whatever description the spawn set.
    if services:
        names = ", ".join(s.name for s in services)
        ro.description = f"Preventive maintenance: {names}"

    # 4) Owner-facing costing: fleet parts are always at inventory cost. Labor
    # may use the truck's snapshotted customer-rate setting.
    tenant_res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_res.scalar_one_or_none()
    labor_rate = Decimal(str(
        (tenant.labor_rate if fleet_labor_uses_customer_rate(ro) else tenant.internal_labor_rate) if tenant else 0
    ))

    for s in services:
        hours = Decimal(str(s.duration_minutes or 0)) / Decimal("60")
        if hours > 0:
            db.add(Labor(
                id=uuid4(), tenant_id=tenant_id, repair_order_id=ro.id,
                description=s.name, hours=hours, hourly_rate=labor_rate,
                total_cost=(hours * labor_rate).quantize(Decimal("0.01")),
                line_type=LaborLineType.FLAT_SERVICE, source_service_id=s.id,
            ))
        for sp in s.service_parts:
            inv = sp.inventory_item
            if inv is None:
                continue
            # Internal orders cost parts at inventory cost, not selling price.
            unit_price = Decimal(str(inv.cost or 0))
            qty = sp.quantity or 1
            db.add(PartsUsage(
                id=uuid4(), tenant_id=tenant_id, repair_order_id=ro.id,
                inventory_id=inv.id, quantity=qty,
                unit_price=unit_price, list_price=unit_price,
                total_price=(unit_price * qty).quantize(Decimal("0.01")),
                source_service_id=s.id,
            ))


async def _ro_pm_services(db: AsyncSession, tenant_id: UUID, ro_id: UUID) -> list[Service]:
    result = await db.execute(
        select(RepairOrderPMService.service_id)
        .where(RepairOrderPMService.repair_order_id == ro_id)
        .order_by(RepairOrderPMService.sort_order)
    )
    return await _load_pm_services(db, tenant_id, list(result.scalars().all()))


@router.get("/pm-service-catalog", response_model=List[PMServiceEntry])
async def pm_service_catalog(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """The services a PM can be scoped with: active services whose catalog
    category is flagged as preventive maintenance (ServiceCategory.is_pm). The
    flag (not the category name) defines the PM set, so a PM category can be
    renamed without breaking the fleet PM picker."""
    from app.db.models.service import ServiceCategory

    result = await db.execute(
        select(Service)
        .join(ServiceCategory, ServiceCategory.id == Service.category_id)
        .where(and_(
            Service.tenant_id == current_user.tenant_id,
            Service.is_active.is_(True),
            ServiceCategory.is_pm.is_(True),
        ))
        .order_by(Service.sort_order, Service.name)
    )
    return _pm_service_entries(list(result.scalars().all()))


@router.get("/trucks/{vehicle_id}/pm-services", response_model=List[PMServiceEntry])
async def get_truck_pm_services(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """The truck's saved default PM service package."""
    await _load_fleet_vehicle_or_404(db, current_user.tenant_id, vehicle_id)
    return _pm_service_entries(await _vehicle_pm_services(db, current_user.tenant_id, vehicle_id))


@router.put("/trucks/{vehicle_id}/pm-services", response_model=List[PMServiceEntry])
async def set_truck_pm_services(
    vehicle_id: UUID,
    body: PMServicesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Replace the truck's default PM service package."""
    await _load_fleet_vehicle_or_404(db, current_user.tenant_id, vehicle_id)
    services = await _load_pm_services(db, current_user.tenant_id, body.service_ids)
    await _set_vehicle_pm_services(db, current_user.tenant_id, vehicle_id, services)
    await db.commit()
    return _pm_service_entries(services)


@router.get("/work-orders/{ro_id}/pm-services", response_model=List[PMServiceEntry])
async def get_wo_pm_services(
    ro_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """The services attached to a specific PM work order."""
    await _load_fleet_ro_or_404(db, current_user.tenant_id, ro_id)
    return _pm_service_entries(await _ro_pm_services(db, current_user.tenant_id, ro_id))


@router.put("/work-orders/{ro_id}/pm-services", response_model=List[PMServiceEntry])
async def set_wo_pm_services(
    ro_id: UUID,
    body: PMServicesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Adjust a PM work order's services and re-seed its cost lines. Only allowed
    while the work order is still a draft (before work starts)."""
    ro = await _load_fleet_ro_or_404(db, current_user.tenant_id, ro_id)
    if ro.status != RepairOrderStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PM services can only be changed while the work order is a draft.",
        )
    from app.api.v1.endpoints.repair_orders import _recompute_repair_order_totals
    services = await _load_pm_services(db, current_user.tenant_id, body.service_ids)
    await _apply_pm_services_to_ro(db, current_user.tenant_id, ro, services)
    await db.commit()
    await _recompute_repair_order_totals(db, ro.id)
    return _pm_service_entries(services)


@router.get("/service-catalog", response_model=List[PMServiceEntry])
async def service_catalog(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """The full active service catalog (Diagnostic, inspections, repairs, …) for
    hand-adding a service to a non-PM internal work order. Unlike the PM catalog
    this is not restricted to PM-flagged categories."""
    result = await db.execute(
        select(Service)
        .where(and_(Service.tenant_id == current_user.tenant_id, Service.is_active.is_(True)))
        .order_by(Service.sort_order, Service.name)
    )
    return _pm_service_entries(list(result.scalars().all()))


@router.post("/work-orders/{ro_id}/add-service", response_model=BoardWorkOrder)
async def add_service_to_work_order(
    ro_id: UUID,
    body: AddServiceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Add a single catalog service to a non-PM internal work order. Seeds one
    labor line (service duration × in-house rate) plus the service's parts at
    internal cost — the same costing PM services use. PM work orders are scoped
    through their service picker instead, so this is rejected for them."""
    from decimal import Decimal
    from app.api.v1.endpoints.repair_orders import _recompute_repair_order_totals

    ro = await _load_fleet_ro_or_404(db, current_user.tenant_id, ro_id)
    if ro.is_pm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is a PM work order — adjust its services with the PM picker.",
        )
    if ro.status in TERMINAL_RO_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot add work to a work order in '{ro.status.value}' status.",
        )

    svc_res = await db.execute(
        select(Service)
        .where(and_(
            Service.id == body.service_id,
            Service.tenant_id == current_user.tenant_id,
            Service.is_active.is_(True),
        ))
        .options(selectinload(Service.service_parts).selectinload(ServicePart.inventory_item))
    )
    service = svc_res.scalar_one_or_none()
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    tenant_res = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = tenant_res.scalar_one_or_none()
    labor_rate = Decimal(str(
        (tenant.labor_rate if fleet_labor_uses_customer_rate(ro) else tenant.internal_labor_rate) if tenant else 0
    ))

    hours = Decimal(str(service.duration_minutes or 0)) / Decimal("60")
    if hours > 0:
        db.add(Labor(
            id=uuid4(), tenant_id=current_user.tenant_id, repair_order_id=ro.id,
            description=service.name, hours=hours, hourly_rate=labor_rate,
            total_cost=(hours * labor_rate).quantize(Decimal("0.01")),
            line_type=LaborLineType.FLAT_SERVICE, source_service_id=service.id,
        ))
    for sp in service.service_parts:
        inv = sp.inventory_item
        if inv is None:
            continue
        unit_price = Decimal(str(inv.cost or 0))
        qty = sp.quantity or 1
        db.add(PartsUsage(
            id=uuid4(), tenant_id=current_user.tenant_id, repair_order_id=ro.id,
            inventory_id=inv.id, quantity=qty,
            unit_price=unit_price, list_price=unit_price,
            total_price=(unit_price * qty).quantize(Decimal("0.01")),
            source_service_id=service.id,
        ))

    await db.commit()
    await _recompute_repair_order_totals(db, ro.id)
    ro = await _load_fleet_ro_or_404(db, current_user.tenant_id, ro_id)
    return _board_work_order(ro)


@router.get("/settings", response_model=FleetSettingsResponse)
async def get_fleet_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Fleet-relevant garage settings: the in-house labor rate and fleet company
    name (owner/admin configure these), plus a live read of the fleet managers
    and truck count derived from the fleet board."""
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    managers_result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == current_user.tenant_id,
                User.role == UserRole.FLEET_MANAGER,
                User.is_active.is_(True),
            )
        ).order_by(User.first_name, User.last_name)
    )
    fleet_managers = [
        FleetManagerOption(
            id=u.id,
            name=f"{u.first_name} {u.last_name}".strip() or u.email,
            email=u.email,
        )
        for u in managers_result.scalars().all()
    ]

    trucks = await _fleet_vehicles(db, current_user.tenant_id)

    return FleetSettingsResponse(
        internal_labor_rate=float(tenant.internal_labor_rate or 0),
        labor_rate=float(tenant.labor_rate or 0),
        fleet_company_name=tenant.fleet_company_name,
        fleet_managers=fleet_managers,
        truck_count=len(trucks),
    )


@router.get("/invoices", response_model=List[FleetInvoiceEntry])
async def list_fleet_invoices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Invoices for fleet work orders, newest first, with truck context."""
    from app.db.models.invoice import Invoice

    result = await db.execute(
        select(Invoice, RepairOrder, Vehicle)
        .join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id, isouter=True)
        .where(and_(
            Invoice.tenant_id == current_user.tenant_id,
            RepairOrder.is_internal.is_(True),
        ))
        .order_by(Invoice.created_at.desc())
    )
    entries = []
    for inv, ro, veh in result.all():
        status_val = inv.status.value if hasattr(inv.status, "value") else str(inv.status)
        vehicle_label = None
        if veh is not None:
            vehicle_label = " ".join(str(p) for p in [veh.year, veh.make, veh.model] if p) or None
        entries.append(FleetInvoiceEntry(
            id=inv.id,
            invoice_number=inv.invoice_number,
            repair_order_id=ro.id,
            order_number=ro.order_number,
            status=status_val,
            total_amount=float(inv.total_amount or 0),
            created_at=inv.created_at,
            vehicle_id=veh.id if veh is not None else None,
            unit_number=veh.unit_number if veh is not None else None,
            vehicle_label=vehicle_label,
        ))
    return entries


@router.get("/mechanics", response_model=List[FleetMechanicOption])
async def list_fleet_mechanics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Active mechanics in the tenant, for assigning to fleet work orders."""
    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == current_user.tenant_id,
                User.role == UserRole.MECHANIC,
                User.is_active.is_(True),
            )
        ).order_by(User.first_name, User.last_name)
    )
    return [
        FleetMechanicOption(id=u.id, name=f"{u.first_name} {u.last_name}".strip() or u.email)
        for u in result.scalars().all()
    ]


@router.post("/trucks/{vehicle_id}/work-order", response_model=BoardTruck, status_code=status.HTTP_201_CREATED)
async def new_work_order(
    vehicle_id: UUID,
    body: Optional[WorkOrderCreate] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    vehicle = await _load_fleet_vehicle_or_404(db, current_user.tenant_id, vehicle_id)

    # A truck can carry several open work orders at once, so no single-open guard.
    description = (body.description.strip() if body and body.description else "") or "Fleet work order"
    await _spawn_internal_ro(db, current_user.tenant_id, vehicle, is_pm=False, description=description)
    open_list = (await _open_ros_by_vehicle(db, [vehicle.id])).get(vehicle.id, [])
    counts = await _open_incident_counts(db, [vehicle.id])
    return _build_board_truck(vehicle, _most_urgent_ro(open_list), counts.get(vehicle.id, 0), len(open_list), pm_ro=_open_pm_ro(open_list))


@router.post("/trucks/{vehicle_id}/schedule-pm", response_model=BoardTruck, status_code=status.HTTP_201_CREATED)
async def schedule_pm(
    vehicle_id: UUID,
    body: Optional[SchedulePMRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Schedule the next PM: set the due date and/or mileage, and optionally
    create the PM work order now."""
    vehicle = await _load_fleet_vehicle_or_404(db, current_user.tenant_id, vehicle_id)
    body = body or SchedulePMRequest()

    if body.next_pm_miles is not None:
        vehicle.next_pm_miles = body.next_pm_miles
    # Due date: honor a date the manager explicitly picked (they may know the
    # truck will sit idle and not hit the mileage soon). Otherwise project the
    # date from the mileage target (today + miles_remaining / 600 mi-day) so the
    # default never contradicts the odometer trigger.
    if body.due_date is not None:
        vehicle.pm_due_date = body.due_date
    else:
        projected = project_pm_due_date(vehicle.next_pm_miles, vehicle.mileage)
        if projected is not None:
            vehicle.pm_due_date = projected

    # Resolve which services this PM uses: an explicit override if provided,
    # otherwise the truck's saved default package.
    if body.service_ids is not None:
        services = await _load_pm_services(db, current_user.tenant_id, body.service_ids)
    else:
        services = await _vehicle_pm_services(db, current_user.tenant_id, vehicle.id)

    # Optionally persist the selection as the truck's new default package.
    if body.save_as_default and body.service_ids is not None:
        await _set_vehicle_pm_services(db, current_user.tenant_id, vehicle.id, services)

    if body.create_work_order:
        # _spawn_internal_ro commits (and persists the schedule changes above).
        ro = await _spawn_internal_ro(
            db, current_user.tenant_id, vehicle, is_pm=True,
            description=f"Preventive maintenance — Service interval {vehicle.pm_interval_miles or 25000:,} mi",
        )
        if services:
            from app.api.v1.endpoints.repair_orders import _recompute_repair_order_totals
            await _apply_pm_services_to_ro(db, current_user.tenant_id, ro, services)
            await db.commit()
            await _recompute_repair_order_totals(db, ro.id)
    else:
        await db.commit()

    open_list = (await _open_ros_by_vehicle(db, [vehicle.id])).get(vehicle.id, [])
    counts = await _open_incident_counts(db, [vehicle.id])
    return _build_board_truck(vehicle, _most_urgent_ro(open_list), counts.get(vehicle.id, 0), len(open_list), pm_ro=_open_pm_ro(open_list))
