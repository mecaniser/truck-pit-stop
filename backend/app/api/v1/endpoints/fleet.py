"""Fleet management endpoints: weekly inspections and roadside incidents.

Scoped to the garage's own internal fleet (the house-account customer). Accessible
to the fleet manager and the garage owner/admin who own the fleet.
"""
import math
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.inventory import PartsUsage, Inventory
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.fleet import (
    FleetInspection,
    FleetInspectionItem,
    FleetIncident,
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
    FleetMechanicOption,
    FleetSettingsResponse,
)
from app.services.internal_fleet import ensure_internal_fleet_customer

router = APIRouter()

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
            "scheduled_for", "performed_at", "odometer", "notes", "created_at",
        )},
        **_vehicle_fields(insp.vehicle),
    )


def _incident_response(inc: FleetIncident) -> IncidentResponse:
    return IncidentResponse(
        **{k: getattr(inc, k) for k in (
            "id", "vehicle_id", "reported_by_id", "occurred_at", "location",
            "severity", "status", "description", "resolution_notes",
            "resolved_at", "repair_order_id", "created_at",
        )},
        **_vehicle_fields(inc.vehicle),
    )


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
    for category, label in DEFAULT_INSPECTION_CHECKLIST:
        db.add(FleetInspectionItem(
            id=uuid4(),
            tenant_id=current_user.tenant_id,
            inspection_id=inspection.id,
            category=category,
            label=label,
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
    if body.odometer is not None:
        insp.odometer = body.odometer
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
        .options(selectinload(FleetIncident.vehicle))
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


async def _load_incident(db: AsyncSession, tenant_id: UUID, incident_id: UUID) -> FleetIncident:
    result = await db.execute(
        select(FleetIncident)
        .where(and_(FleetIncident.id == incident_id, FleetIncident.tenant_id == tenant_id))
        .options(selectinload(FleetIncident.vehicle))
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
    rem = _pm_remaining(v)
    if rem is not None and rem < PM_DUE_SOON_MILES:
        return "pm"
    return "active"


def _board_work_order(ro: RepairOrder) -> BoardWorkOrder:
    return BoardWorkOrder(
        id=ro.order_number,
        repair_order_id=ro.id,
        status=_wo_label(ro),
        summary=ro.description,
        mechanic=_mechanic_name(ro.assigned_mechanic),
    )


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


def _build_board_truck(v: Vehicle, open_ro: Optional[RepairOrder], incident_count: int, open_wo_count: int = 0) -> BoardTruck:
    status_str = _derive_status(v, open_ro)
    wo = None
    mechanic = None
    if open_ro is not None:
        mechanic = _mechanic_name(open_ro.assigned_mechanic)
        wo = _board_work_order(open_ro)
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
        odometer=v.mileage,
        pm_interval_miles=v.pm_interval_miles or 25000,
        next_pm_miles=v.next_pm_miles,
        pm_remaining=_pm_remaining(v),
        location_label=v.last_location_label,
        location_city=v.last_location_city,
        lat=v.last_lat,
        lng=v.last_lng,
        moving=moving,
        speed_mph=v.last_speed_mph,
        heading=v.last_heading,
        assigned_mechanic=mechanic,
        work_order=wo,
        open_work_order_count=open_wo_count,
        open_incident_count=incident_count,
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


@router.get("/board", response_model=FleetBoardResponse)
async def fleet_board(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    vehicles = await _fleet_vehicles(db, current_user.tenant_id)
    ids = [v.id for v in vehicles]
    open_ros = await _open_ros_by_vehicle(db, ids)
    incidents = await _open_incident_counts(db, ids)

    trucks = [
        _build_board_truck(
            v, _most_urgent_ro(open_ros.get(v.id, [])), incidents.get(v.id, 0), len(open_ros.get(v.id, []))
        )
        for v in vehicles
    ]
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
        .where(and_(RepairOrder.vehicle_id == vehicle_id, RepairOrder.is_internal.is_(True)))
        .options(selectinload(RepairOrder.assigned_mechanic))
        .order_by(RepairOrder.created_at.desc())
    )
    ros = list(ro_result.scalars().all())
    open_ros = [r for r in ros if r.status not in TERMINAL_RO_STATUSES]
    completed = [r for r in ros if r.status in (RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED, RepairOrderStatus.PAID)]

    board = _build_board_truck(vehicle, _most_urgent_ro(open_ros), 0, len(open_ros))

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
        select(FleetIncident).where(FleetIncident.vehicle_id == vehicle_id).order_by(FleetIncident.occurred_at.desc())
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
        vehicle.driver_phone = body.driver_phone or None
    if body.odometer is not None:
        vehicle.mileage = body.odometer
    if body.pm_interval_miles is not None:
        vehicle.pm_interval_miles = body.pm_interval_miles
    if body.next_pm_miles is not None:
        vehicle.next_pm_miles = body.next_pm_miles
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
    return _build_board_truck(vehicle, _most_urgent_ro(open_list), counts.get(vehicle.id, 0), len(open_list))


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
            description=description,
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


@router.get("/settings", response_model=FleetSettingsResponse)
async def get_fleet_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    """Fleet-relevant garage settings (read-only), e.g. the in-house labor rate
    that owner/admin configure in garage settings."""
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return FleetSettingsResponse(internal_labor_rate=float(tenant.internal_labor_rate or 0))


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
    return _build_board_truck(vehicle, _most_urgent_ro(open_list), counts.get(vehicle.id, 0), len(open_list))


@router.post("/trucks/{vehicle_id}/schedule-pm", response_model=BoardTruck, status_code=status.HTTP_201_CREATED)
async def schedule_pm(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_fleet_access),
):
    vehicle = await _load_fleet_vehicle_or_404(db, current_user.tenant_id, vehicle_id)
    await _spawn_internal_ro(
        db, current_user.tenant_id, vehicle, is_pm=True,
        description=f"Preventive maintenance — Service interval {vehicle.pm_interval_miles or 25000:,} mi",
    )
    open_list = (await _open_ros_by_vehicle(db, [vehicle.id])).get(vehicle.id, [])
    counts = await _open_incident_counts(db, [vehicle.id])
    return _build_board_truck(vehicle, _most_urgent_ro(open_list), counts.get(vehicle.id, 0), len(open_list))
