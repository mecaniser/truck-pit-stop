from typing import List, Optional
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, cast, Date, or_
from sqlalchemy.orm import selectinload
from uuid import UUID
import json

from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.core.vehicle_display import vehicle_display_label
from app.core.security import get_password_hash
from app.core.password_policy import validate_password
from app.core.logging import get_logger
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.db.models.inventory import PartsUsage
from app.db.models.fleet import RepairOrderPMService
from app.db.models.mechanic_points import MechanicPoints, MechanicPointsBalance, PointsTransactionType
from app.db.models.pto_request import PTORequest, PTORequestStatus, PTORequestType
from app.db.models.work_photo import WorkPhoto
from app.db.models.mechanic_time import MechanicSessionType, MiscWorkCategory, MechanicTimeSession
from app.schemas.auth import UserResponse
from app.schemas.mechanic import MechanicCreate
from app.schemas.mechanic_update import MechanicUpdate
from app.services.cloudinary_service import upload_work_photo, is_cloudinary_configured
from app.services.mechanic_time_service import (
    compute_7day_trend,
    compute_day_summary,
    clock_in,
    clock_out,
    end_break,
    fetch_tenant_and_mechanic,
    start_break,
    start_session,
    stop_active_session,
    validate_local_time_str,
)
from app.core.websocket import (
    broadcast_mechanic_attendance_update,
    broadcast_mechanic_break_update,
    broadcast_mechanic_timer_update,
)
from pydantic import BaseModel, Field

logger = get_logger(__name__)

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


def _normalize_local_time(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _validate_shift_fields(start_local: Optional[str], end_local: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    normalized_start = _normalize_local_time(start_local)
    normalized_end = _normalize_local_time(end_local)
    try:
        if normalized_start is not None:
            validate_local_time_str(normalized_start)
        if normalized_end is not None:
            validate_local_time_str(normalized_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Shift overrides must use HH:MM format")
    if normalized_start and normalized_end and normalized_start >= normalized_end:
        raise HTTPException(status_code=400, detail="shift_start_local_override must be before shift_end_local_override")
    return normalized_start, normalized_end


class MechanicWithPoints(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    is_active: bool
    available_points: int = 0
    total_earned: int = 0
    streak_days: int = 0
    pending_requests: int = 0
    core_hours_target_minutes_override: Optional[int] = None
    shift_start_local_override: Optional[str] = None
    shift_end_local_override: Optional[str] = None


@router.get("", response_model=List[MechanicWithPoints])
async def list_mechanics(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    """List mechanics with their points info for dashboard"""
    if not current_user.tenant_id:
        return paginated_or_list([], 0, skip, limit, paginated)

    total_result = await db.execute(
        select(func.count(User.id)).where(
            and_(
                User.tenant_id == current_user.tenant_id,
                User.role == UserRole.MECHANIC,
            )
        )
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == current_user.tenant_id,
                User.role == UserRole.MECHANIC,
            )
        ).order_by(User.created_at.desc()).offset(skip).limit(limit)
    )
    mechanics = result.scalars().all()
    
    mechanic_ids = [mechanic.id for mechanic in mechanics]

    balances_by_mechanic: dict[UUID, MechanicPointsBalance] = {}
    pending_counts_by_mechanic: dict[UUID, int] = {}

    if mechanic_ids:
        balance_result = await db.execute(
            select(MechanicPointsBalance).where(
                and_(
                    MechanicPointsBalance.tenant_id == current_user.tenant_id,
                    MechanicPointsBalance.mechanic_id.in_(mechanic_ids),
                )
            )
        )
        balances_by_mechanic = {
            balance.mechanic_id: balance for balance in balance_result.scalars().all()
        }

        pending_result = await db.execute(
            select(PTORequest.mechanic_id, func.count(PTORequest.id))
            .where(
                and_(
                    PTORequest.tenant_id == current_user.tenant_id,
                    PTORequest.mechanic_id.in_(mechanic_ids),
                    PTORequest.status == PTORequestStatus.PENDING,
                )
            )
            .group_by(PTORequest.mechanic_id)
        )
        pending_counts_by_mechanic = {
            mechanic_id: int(count)
            for mechanic_id, count in pending_result.all()
        }

    mechanics_with_points = []
    for mechanic in mechanics:
        balance = balances_by_mechanic.get(mechanic.id)
        pending_count = pending_counts_by_mechanic.get(mechanic.id, 0)

        mechanics_with_points.append(MechanicWithPoints(
            id=str(mechanic.id),
            email=mechanic.email,
            first_name=mechanic.first_name or "",
            last_name=mechanic.last_name or "",
            phone=mechanic.phone,
            is_active=mechanic.is_active,
            available_points=balance.available_points if balance else 0,
            total_earned=balance.total_earned if balance else 0,
            streak_days=balance.current_streak_days if balance else 0,
            pending_requests=pending_count,
            core_hours_target_minutes_override=mechanic.core_hours_target_minutes_override,
            shift_start_local_override=mechanic.shift_start_local_override,
            shift_end_local_override=mechanic.shift_end_local_override,
        ))
    
    return paginated_or_list(mechanics_with_points, total, skip, limit, paginated)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_mechanic(
    mechanic_data: MechanicCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    # Validate password complexity
    validate_password(mechanic_data.password)
    normalized_shift_start, normalized_shift_end = _validate_shift_fields(
        mechanic_data.shift_start_local_override,
        mechanic_data.shift_end_local_override,
    )
    if (
        mechanic_data.core_hours_target_minutes_override is not None
        and not 1 <= mechanic_data.core_hours_target_minutes_override <= 1440
    ):
        raise HTTPException(status_code=400, detail="core_hours_target_minutes_override must be between 1 and 1440")
    
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )

    # Ensure email is unique
    result = await db.execute(select(User).where(User.email == mechanic_data.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    mechanic = User(
        email=mechanic_data.email,
        hashed_password=get_password_hash(mechanic_data.password),
        first_name=mechanic_data.first_name,
        last_name=mechanic_data.last_name,
        phone=mechanic_data.phone or None,
        address=mechanic_data.address or None,
        role=UserRole.MECHANIC,
        tenant_id=current_user.tenant_id,
        is_active=True,
        is_verified=True,
        core_hours_target_minutes_override=mechanic_data.core_hours_target_minutes_override,
        shift_start_local_override=normalized_shift_start,
        shift_end_local_override=normalized_shift_end,
    )

    db.add(mechanic)
    await db.commit()
    await db.refresh(mechanic)

    return UserResponse.model_validate(mechanic)


class MechanicWorkItem(BaseModel):
    id: str
    order_number: str
    status: str
    vehicle_info: str
    updated_at: str


class ServiceItem(BaseModel):
    name: str
    description: Optional[str] = None
    base_price: Optional[str] = None


class MechanicJobDetail(BaseModel):
    """Job detail for mechanic portal - NO customer info"""
    id: str
    order_number: str
    status: str
    description: Optional[str] = None
    vehicle_year: Optional[int] = None
    vehicle_make: str
    vehicle_model: str
    vehicle_vin: Optional[str] = None
    vehicle_license_plate: Optional[str] = None
    vehicle_mileage: Optional[int] = None
    services: List[ServiceItem] = []
    created_at: datetime
    updated_at: datetime
    work_started_at: Optional[datetime] = None
    hold_reason: Optional[str] = None
    held_at: Optional[datetime] = None
    work_completed_at: Optional[datetime] = None
    ro_today_tracked_minutes: int = 0


class MechanicJobSummary(BaseModel):
    """Job summary for mechanic job list"""
    id: str
    order_number: str
    status: str
    vehicle_info: str
    description: Optional[str] = None
    services_count: int = 0
    created_at: datetime
    updated_at: datetime
    work_started_at: Optional[datetime] = None
    hold_reason: Optional[str] = None
    held_at: Optional[datetime] = None
    ro_today_tracked_minutes: int = 0


def _service_item_key(name: str, description: Optional[str]) -> tuple[str, str]:
    return (name.strip().lower(), (description or "").strip().lower())


def _build_mechanic_scope_items(
    order: RepairOrder,
    pm_entries: Optional[List[RepairOrderPMService]] = None,
) -> List[ServiceItem]:
    """Build a mechanic-safe work scope from current RO line sources."""
    items: List[ServiceItem] = []
    seen: set[tuple[str, str]] = set()

    def add_item(name: Optional[str], description: Optional[str] = None, base_price: Optional[object] = None) -> None:
        normalized_name = (name or "").strip()
        if not normalized_name:
            return
        normalized_description = description.strip() if description else None
        key = _service_item_key(normalized_name, normalized_description)
        if key in seen:
            return
        seen.add(key)
        items.append(ServiceItem(
            name=normalized_name,
            description=normalized_description,
            base_price=str(base_price) if base_price is not None else None,
        ))

    for labor in sorted(order.labor_items or [], key=lambda line: (line.created_at, line.id)):
        add_item(labor.description, base_price=labor.total_cost)

    for entry in sorted(pm_entries or [], key=lambda item: (item.sort_order, item.created_at, item.id)):
        service = getattr(entry, "service", None)
        if service:
            add_item(service.name, service.description, service.base_price)

    if not items:
        for part in sorted(order.parts_usage or [], key=lambda row: (row.created_at, row.id)):
            inventory_item = getattr(part, "inventory_item", None)
            part_name = inventory_item.name if inventory_item else "Part"
            add_item(f"Install {part_name}")

    if not items:
        add_item(order.description)

    if not items and order.internal_notes:
        try:
            notes = json.loads(order.internal_notes)
            for svc in notes.get("selected_services", []):
                add_item(svc.get("name") or "Service", svc.get("description"), svc.get("base_price"))
        except (TypeError, ValueError):
            pass

    return items


class MechanicHistoryItem(BaseModel):
    """Work history item for mechanic"""
    id: str
    order_number: str
    status: str
    vehicle_info: str
    services_count: int = 0
    completed_at: datetime
    work_started_at: Optional[datetime] = None
    work_completed_at: Optional[datetime] = None
    actual_hours: Optional[float] = None
    points_earned: int = 0


class MechanicStats(BaseModel):
    """Stats for mechanic gamification"""
    jobs_completed_today: int = 0
    jobs_completed_week: int = 0
    jobs_completed_month: int = 0
    total_points: int = 0
    available_points: int = 0
    total_redeemed: int = 0
    streak_days: int = 0
    streak_multiplier: float = 1.0
    pto_days_available: float = 0.0  # 8000 pts = 1 day
    cash_value: float = 0.0  # $0.0375 per point


class RedeemRequest(BaseModel):
    redeem_type: str  # "pto" or "cash"
    points: int


class RedeemResponse(BaseModel):
    success: bool
    points_redeemed: int
    value: float  # PTO hours or cash amount
    remaining_points: int


class StartMiscTimerRequest(BaseModel):
    misc_category: str
    note: Optional[str] = None


class TimerActionResponse(BaseModel):
    success: bool
    session_id: Optional[str] = None
    attendance_session_id: Optional[str] = None
    break_session_id: Optional[str] = None
    auto_clocked_in: Optional[bool] = None
    auto_stopped_timer_session_id: Optional[str] = None
    auto_ended_break_session_id: Optional[str] = None
    message: str


class ClockActionRequest(BaseModel):
    note: Optional[str] = None


class BreakActionRequest(BaseModel):
    note: Optional[str] = None


class MechanicDaySummaryResponse(BaseModel):
    date: str
    timezone: str
    shift_start_local: str
    shift_end_local: str
    core_target_minutes: int
    tracked_minutes: int
    ro_minutes: int
    misc_minutes: int
    overtime_minutes: int
    utilization_percent: float
    efficiency_percent: Optional[float] = None
    book_hours: float
    actual_ro_hours: float
    active_session: Optional[dict] = None
    attendance_active: bool = False
    attendance_started_at: Optional[str] = None
    attendance_ended_at: Optional[str] = None
    break_active: bool = False
    break_started_at: Optional[str] = None
    attendance_minutes: int = 0
    break_minutes: int = 0
    idle_minutes: int = 0
    late_arrival_minutes: int = 0
    early_leave_minutes: int = 0
    flex_budget_minutes: int = 0
    flex_used_minutes: int = 0
    flex_remaining_minutes: int = 0
    flex_overrun_minutes: int = 0
    core_gap_minutes: int = 0
    core_countdown_elapsed_minutes: int = 0
    core_countdown_remaining_minutes: int = 0
    tracked_vs_attendance_gap_minutes: int = 0
    work_coverage_percent: Optional[float] = None
    trend_7_days: List[dict] = []


# Points constants
POINTS_PER_PTO_DAY = 8000  # 8000 points = 1 day off (~$300)
CASH_PER_POINT = 0.0375   # $0.0375 per point (8000 pts = $300)


async def _compute_ro_today_tracked_minutes_map(
    db: AsyncSession,
    *,
    tenant: Tenant,
    mechanic_id: UUID,
    order_ids: list[UUID],
) -> dict[UUID, int]:
    if not order_ids:
        return {}
    tz = ZoneInfo(tenant.timezone or "America/New_York")
    local_today = datetime.now(tz).date()
    day_start_local = datetime.combine(local_today, datetime.min.time(), tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    day_start_utc = day_start_local.astimezone(timezone.utc)
    day_end_utc = day_end_local.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)

    result = await db.execute(
        select(MechanicTimeSession).where(
            and_(
                MechanicTimeSession.tenant_id == tenant.id,
                MechanicTimeSession.mechanic_id == mechanic_id,
                MechanicTimeSession.repair_order_id.in_(order_ids),
                MechanicTimeSession.deleted_at.is_(None),
                MechanicTimeSession.started_at < day_end_utc,
                or_(MechanicTimeSession.ended_at.is_(None), MechanicTimeSession.ended_at > day_start_utc),
            )
        )
    )
    sessions = result.scalars().all()

    totals: dict[UUID, int] = {}
    for session in sessions:
        if not session.repair_order_id:
            continue
        start = max(session.started_at, day_start_utc)
        end = min(session.ended_at or now_utc, day_end_utc)
        if end <= start:
            continue
        minutes = int((end - start).total_seconds() // 60)
        totals[session.repair_order_id] = totals.get(session.repair_order_id, 0) + minutes
    return totals


@router.get("/my-stats", response_model=MechanicStats)
async def get_my_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Get stats for the current mechanic - gamification"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    
    # Get balance record
    result = await db.execute(
        select(MechanicPointsBalance).where(
            MechanicPointsBalance.mechanic_id == current_user.id
        )
    )
    balance = result.scalar_one_or_none()
    
    available_points = balance.available_points if balance else 0
    total_earned = balance.total_earned if balance else 0
    total_redeemed = balance.total_redeemed if balance else 0
    streak_days = balance.current_streak_days if balance else 0
    
    # Calculate streak multiplier
    streak_multiplier = 1.0
    if streak_days >= 10:
        streak_multiplier = 1.25
    elif streak_days >= 5:
        streak_multiplier = 1.10
    
    # Count jobs completed today (from points transactions)
    result = await db.execute(
        select(func.count(MechanicPoints.id)).where(
            and_(
                MechanicPoints.mechanic_id == current_user.id,
                MechanicPoints.transaction_type == PointsTransactionType.EARNED,
                cast(MechanicPoints.created_at, Date) == today,
            )
        )
    )
    jobs_today = result.scalar() or 0
    
    # Count jobs this week
    result = await db.execute(
        select(func.count(MechanicPoints.id)).where(
            and_(
                MechanicPoints.mechanic_id == current_user.id,
                MechanicPoints.transaction_type == PointsTransactionType.EARNED,
                cast(MechanicPoints.created_at, Date) >= week_start,
            )
        )
    )
    jobs_week = result.scalar() or 0
    
    # Count jobs this month
    result = await db.execute(
        select(func.count(MechanicPoints.id)).where(
            and_(
                MechanicPoints.mechanic_id == current_user.id,
                MechanicPoints.transaction_type == PointsTransactionType.EARNED,
                cast(MechanicPoints.created_at, Date) >= month_start,
            )
        )
    )
    jobs_month = result.scalar() or 0
    
    # Calculate redemption values
    pto_days = available_points / POINTS_PER_PTO_DAY
    cash_value = available_points * CASH_PER_POINT
    
    return MechanicStats(
        jobs_completed_today=jobs_today,
        jobs_completed_week=jobs_week,
        jobs_completed_month=jobs_month,
        total_points=total_earned,
        available_points=available_points,
        total_redeemed=total_redeemed,
        streak_days=streak_days,
        streak_multiplier=streak_multiplier,
        pto_days_available=round(pto_days, 2),
        cash_value=round(cash_value, 2),
    )


@router.post("/me/attendance/clock-in", response_model=TimerActionResponse)
async def clock_in_mechanic(
    body: Optional[ClockActionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Mechanic has no tenant")

    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=current_user.id,
    )
    try:
        attendance = await clock_in(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            note=body.note if body else None,
            start_source="manual_clock_in",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await db.commit()
    await broadcast_mechanic_attendance_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(current_user.id),
        attendance_session_id=str(attendance.id),
        action="clock_in",
    )
    return TimerActionResponse(
        success=True,
        attendance_session_id=str(attendance.id),
        message="Clocked in",
    )


@router.post("/me/attendance/clock-out", response_model=TimerActionResponse)
async def clock_out_mechanic(
    body: Optional[ClockActionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Mechanic has no tenant")

    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=current_user.id,
    )
    try:
        result = await clock_out(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            note=body.note if body else None,
            end_source="manual_clock_out",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await db.commit()
    await broadcast_mechanic_attendance_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(current_user.id),
        attendance_session_id=str(result.attendance_session.id),
        action="clock_out",
    )
    if result.ended_break_session:
        await broadcast_mechanic_break_update(
            tenant_id=str(current_user.tenant_id),
            mechanic_id=str(current_user.id),
            break_session_id=str(result.ended_break_session.id),
            action="end",
        )
    if result.stopped_timer_session:
        await broadcast_mechanic_timer_update(
            tenant_id=str(current_user.tenant_id),
            mechanic_id=str(current_user.id),
            session_id=str(result.stopped_timer_session.id),
            action="stop_from_clock_out",
        )
    return TimerActionResponse(
        success=True,
        attendance_session_id=str(result.attendance_session.id),
        auto_stopped_timer_session_id=str(result.stopped_timer_session.id) if result.stopped_timer_session else None,
        auto_ended_break_session_id=str(result.ended_break_session.id) if result.ended_break_session else None,
        message="Clocked out",
    )


@router.post("/me/break/start", response_model=TimerActionResponse)
async def start_mechanic_break(
    body: Optional[BreakActionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Mechanic has no tenant")

    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=current_user.id,
    )
    try:
        result = await start_break(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            note=body.note if body else None,
            start_source="manual_break_start",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await db.commit()
    await broadcast_mechanic_break_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(current_user.id),
        break_session_id=str(result.break_session.id),
        action="start",
    )
    if result.stopped_timer_session:
        await broadcast_mechanic_timer_update(
            tenant_id=str(current_user.tenant_id),
            mechanic_id=str(current_user.id),
            session_id=str(result.stopped_timer_session.id),
            action="stop_from_break_start",
        )
    return TimerActionResponse(
        success=True,
        break_session_id=str(result.break_session.id),
        auto_stopped_timer_session_id=str(result.stopped_timer_session.id) if result.stopped_timer_session else None,
        message="Break started",
    )


@router.post("/me/break/end", response_model=TimerActionResponse)
async def end_mechanic_break(
    body: Optional[BreakActionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Mechanic has no tenant")

    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=current_user.id,
    )
    try:
        break_session = await end_break(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=current_user,
            note=body.note if body else None,
            end_source="manual_break_end",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await db.commit()
    await broadcast_mechanic_break_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(current_user.id),
        break_session_id=str(break_session.id),
        action="end",
    )
    return TimerActionResponse(
        success=True,
        break_session_id=str(break_session.id),
        message="Break ended",
    )


@router.post("/me/timer/start-misc", response_model=TimerActionResponse)
async def start_misc_timer(
    body: StartMiscTimerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    if body.misc_category not in [m.value for m in MiscWorkCategory]:
        raise HTTPException(status_code=400, detail="Invalid misc category")
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Mechanic has no tenant")

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    session, auto_clocked_in, attendance_session_id, _auto_held_ro = await start_session(
        db,
        tenant=tenant,
        mechanic=current_user,
        actor_user=current_user,
        session_type=MechanicSessionType.MISC.value,
        misc_category=body.misc_category,
        note=body.note,
    )
    await db.commit()
    await db.refresh(session)

    await broadcast_mechanic_timer_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(current_user.id),
        session_id=str(session.id),
        action="start",
    )
    if auto_clocked_in:
        await broadcast_mechanic_attendance_update(
            tenant_id=str(current_user.tenant_id),
            mechanic_id=str(current_user.id),
            attendance_session_id=attendance_session_id,
            action="auto_clock_in",
        )

    return TimerActionResponse(
        success=True,
        session_id=str(session.id),
        auto_clocked_in=auto_clocked_in,
        message="Misc timer started",
    )


@router.post("/me/timer/stop", response_model=TimerActionResponse)
async def stop_my_timer(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Mechanic has no tenant")

    stopped = await stop_active_session(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=current_user.id,
        actor_user=current_user,
        stop_reason="manual",
    )
    if not stopped:
        raise HTTPException(status_code=400, detail="No active timer to stop")

    await db.commit()
    await broadcast_mechanic_timer_update(
        tenant_id=str(current_user.tenant_id),
        mechanic_id=str(current_user.id),
        session_id=str(stopped.id),
        action="stop",
    )
    return TimerActionResponse(success=True, session_id=str(stopped.id), message="Timer stopped")


@router.get("/me/day-summary", response_model=MechanicDaySummaryResponse)
async def get_my_day_summary(
    date_value: Optional[date] = Query(None, alias="date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Mechanic has no tenant")

    tenant, mechanic = await fetch_tenant_and_mechanic(
        db,
        tenant_id=current_user.tenant_id,
        mechanic_id=current_user.id,
    )
    summary = await compute_day_summary(
        db,
        tenant=tenant,
        mechanic=mechanic,
        target_date=date_value,
    )
    trend = await compute_7day_trend(
        db,
        tenant=tenant,
        mechanic=mechanic,
        end_date=date_value,
    )
    return MechanicDaySummaryResponse(
        **summary,
        trend_7_days=trend,
    )


@router.post("/redeem", response_model=RedeemResponse)
async def redeem_points(
    request: RedeemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Redeem points for PTO or cash"""
    if request.redeem_type not in ("pto", "cash"):
        raise HTTPException(status_code=400, detail="Invalid redeem type. Use 'pto' or 'cash'")
    
    if request.points <= 0:
        raise HTTPException(status_code=400, detail="Points must be positive")
    
    # Get balance
    result = await db.execute(
        select(MechanicPointsBalance).where(
            MechanicPointsBalance.mechanic_id == current_user.id
        )
    )
    balance = result.scalar_one_or_none()
    
    if not balance or balance.available_points < request.points:
        raise HTTPException(status_code=400, detail="Insufficient points")
    
    # Calculate value
    if request.redeem_type == "pto":
        # Must redeem in full day increments
        if request.points < POINTS_PER_PTO_DAY:
            raise HTTPException(
                status_code=400, 
                detail=f"Minimum {POINTS_PER_PTO_DAY} points required for PTO (1 day)"
            )
        days = request.points // POINTS_PER_PTO_DAY
        actual_points = days * POINTS_PER_PTO_DAY
        value = float(days)  # Days of PTO
        tx_type = PointsTransactionType.REDEEMED_PTO
        notes = f"Redeemed {days} day(s) PTO"
    else:
        actual_points = request.points
        value = actual_points * CASH_PER_POINT
        tx_type = PointsTransactionType.REDEEMED_CASH
        notes = f"Redeemed ${value:.2f} cash"
    
    # Create redemption transaction
    redemption = MechanicPoints(
        tenant_id=current_user.tenant_id,
        mechanic_id=current_user.id,
        transaction_type=tx_type,
        points=-actual_points,  # Negative for redemption
        multiplier=Decimal("1.00"),
        notes=notes,
        redemption_value=Decimal(str(value)),
    )
    db.add(redemption)
    
    # Update balance
    balance.available_points -= actual_points
    balance.total_redeemed += actual_points
    
    await db.commit()
    
    return RedeemResponse(
        success=True,
        points_redeemed=actual_points,
        value=value,
        remaining_points=balance.available_points,
    )


@router.get("/my-jobs", response_model=List[MechanicJobSummary])
async def get_my_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Get all jobs assigned to the current mechanic"""
    base_query = select(RepairOrder).where(
        and_(
            RepairOrder.tenant_id == current_user.tenant_id,
            RepairOrder.assigned_mechanic_id == current_user.id,
            RepairOrder.status.in_([
                RepairOrderStatus.ASSIGNED,
                RepairOrderStatus.ACKNOWLEDGED,
                RepairOrderStatus.IN_PROGRESS,
                RepairOrderStatus.PENDING_REVIEW,
            ]),
            RepairOrder.deleted_at.is_(None),
        )
    )

    total_result = await db.execute(
        select(func.count(RepairOrder.id)).where(
            and_(
                RepairOrder.tenant_id == current_user.tenant_id,
                RepairOrder.assigned_mechanic_id == current_user.id,
                RepairOrder.status.in_([
                    RepairOrderStatus.ASSIGNED,
                    RepairOrderStatus.ACKNOWLEDGED,
                    RepairOrderStatus.IN_PROGRESS,
                    RepairOrderStatus.PENDING_REVIEW,
                ]),
                RepairOrder.deleted_at.is_(None),
            )
        )
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        base_query
        .options(
            selectinload(RepairOrder.vehicle),
            selectinload(RepairOrder.labor_items),
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
        )
        .order_by(RepairOrder.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    orders = result.scalars().all()
    order_ids = [order.id for order in orders]
    pm_entries_by_order: dict[UUID, list[RepairOrderPMService]] = {order_id: [] for order_id in order_ids}
    if order_ids:
        pm_result = await db.execute(
            select(RepairOrderPMService)
            .where(RepairOrderPMService.repair_order_id.in_(order_ids))
            .options(selectinload(RepairOrderPMService.service))
        )
        for entry in pm_result.scalars().all():
            pm_entries_by_order.setdefault(entry.repair_order_id, []).append(entry)
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    ro_today_minutes = await _compute_ro_today_tracked_minutes_map(
        db,
        tenant=tenant,
        mechanic_id=current_user.id,
        order_ids=order_ids,
    )
    
    jobs = []
    for order in orders:
        vehicle = order.vehicle
        vehicle_info = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "Unknown"
        
        services = _build_mechanic_scope_items(order, pm_entries_by_order.get(order.id, []))
        
        jobs.append(MechanicJobSummary(
            id=str(order.id),
            order_number=order.order_number,
            status=order.status.value,
            vehicle_info=vehicle_info,
            description=order.description,
            services_count=len(services),
            created_at=order.created_at,
            updated_at=order.updated_at,
            work_started_at=getattr(order, 'work_started_at', None),
            hold_reason=order.hold_reason,
            held_at=order.held_at,
            ro_today_tracked_minutes=ro_today_minutes.get(order.id, 0),
        ))
    
    return paginated_or_list(jobs, total, skip, limit, paginated)


@router.get("/my-history", response_model=List[MechanicHistoryItem])
async def get_my_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Get completed work history for the current mechanic"""
    base_query = select(RepairOrder).where(
        and_(
            RepairOrder.tenant_id == current_user.tenant_id,
            RepairOrder.assigned_mechanic_id == current_user.id,
            RepairOrder.status.in_([
                RepairOrderStatus.COMPLETED,
                RepairOrderStatus.INVOICED,
                RepairOrderStatus.PAID,
            ]),
            RepairOrder.deleted_at.is_(None),
        )
    )

    total_result = await db.execute(
        select(func.count(RepairOrder.id)).where(
            and_(
                RepairOrder.tenant_id == current_user.tenant_id,
                RepairOrder.assigned_mechanic_id == current_user.id,
                RepairOrder.status.in_([
                    RepairOrderStatus.COMPLETED,
                    RepairOrderStatus.INVOICED,
                    RepairOrderStatus.PAID,
                ]),
                RepairOrder.deleted_at.is_(None),
            )
        )
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        base_query
        .options(
            selectinload(RepairOrder.vehicle),
            selectinload(RepairOrder.labor_items),
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
        )
        .order_by(RepairOrder.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    orders = result.scalars().all()
    order_ids = [order.id for order in orders]
    pm_entries_by_order: dict[UUID, list[RepairOrderPMService]] = {order_id: [] for order_id in order_ids}
    if order_ids:
        pm_result = await db.execute(
            select(RepairOrderPMService)
            .where(RepairOrderPMService.repair_order_id.in_(order_ids))
            .options(selectinload(RepairOrderPMService.service))
        )
        for entry in pm_result.scalars().all():
            pm_entries_by_order.setdefault(entry.repair_order_id, []).append(entry)
    
    # Get points earned for each order
    points_result = await db.execute(
        select(MechanicPoints.repair_order_id, MechanicPoints.points)
        .where(
            and_(
                MechanicPoints.mechanic_id == current_user.id,
                MechanicPoints.repair_order_id.in_(order_ids),
                MechanicPoints.transaction_type == PointsTransactionType.EARNED,
            )
        )
    )
    points_by_order = {row.repair_order_id: row.points for row in points_result.all()}
    
    history = []
    for order in orders:
        vehicle = order.vehicle
        vehicle_info = vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number) if vehicle else "Unknown"
        
        services_count = len(_build_mechanic_scope_items(order, pm_entries_by_order.get(order.id, [])))
        
        ws = getattr(order, 'work_started_at', None)
        wc = getattr(order, 'work_completed_at', None)
        actual_hrs = None
        if ws and wc:
            actual_hrs = round((wc - ws).total_seconds() / 3600, 2)

        history.append(MechanicHistoryItem(
            id=str(order.id),
            order_number=order.order_number,
            status=order.status.value,
            vehicle_info=vehicle_info,
            services_count=services_count,
            completed_at=order.updated_at,
            work_started_at=ws,
            work_completed_at=wc,
            actual_hours=actual_hrs,
            points_earned=points_by_order.get(order.id, 0),
        ))
    
    return paginated_or_list(history, total, skip, limit, paginated)


@router.get("/my-jobs/{order_id}", response_model=MechanicJobDetail)
async def get_my_job_detail(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Get job detail for mechanic - NO customer info exposed"""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None))
        .options(
            selectinload(RepairOrder.vehicle),
            selectinload(RepairOrder.labor_items),
            selectinload(RepairOrder.parts_usage).selectinload(PartsUsage.inventory_item),
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    ro_today_minutes = await _compute_ro_today_tracked_minutes_map(
        db,
        tenant=tenant,
        mechanic_id=current_user.id,
        order_ids=[order.id],
    )
    
    vehicle = order.vehicle
    pm_result = await db.execute(
        select(RepairOrderPMService)
        .where(RepairOrderPMService.repair_order_id == order.id)
        .options(selectinload(RepairOrderPMService.service))
    )
    services = _build_mechanic_scope_items(order, pm_result.scalars().all())
    
    return MechanicJobDetail(
        id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        description=order.description,
        vehicle_year=vehicle.year if vehicle else None,
        vehicle_make=vehicle.make if vehicle else "Unknown",
        vehicle_model=vehicle.model if vehicle else "Unknown",
        vehicle_vin=vehicle.vin if vehicle else None,
        vehicle_license_plate=vehicle.license_plate if vehicle else None,
        vehicle_mileage=vehicle.mileage if vehicle else None,
        services=services,
        created_at=order.created_at,
        updated_at=order.updated_at,
        work_started_at=getattr(order, 'work_started_at', None),
        work_completed_at=getattr(order, 'work_completed_at', None),
        hold_reason=order.hold_reason,
        held_at=order.held_at,
        ro_today_tracked_minutes=ro_today_minutes.get(order.id, 0),
    )


@router.get("/{mechanic_id}/work", response_model=list[MechanicWorkItem])
async def get_mechanic_work(
    mechanic_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.MECHANIC)),
):
    # Ensure mechanic exists and belongs to tenant
    result = await db.execute(select(User).where(User.id == mechanic_id, User.role == UserRole.MECHANIC))
    mechanic = result.scalar_one_or_none()
    if not mechanic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic not found")

    # Tenant check: mechanics can only see their own work; admins only within tenant
    if current_user.role == UserRole.MECHANIC:
        if current_user.id != mechanic.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        tenant_id = current_user.tenant_id
    else:
        if not current_user.tenant_id or mechanic.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        tenant_id = current_user.tenant_id

    base_filters = and_(
        RepairOrder.tenant_id == tenant_id,
        RepairOrder.assigned_mechanic_id == mechanic.id,
    )
    total_result = await db.execute(
        select(func.count(RepairOrder.id)).where(base_filters)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(RepairOrder, Vehicle)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .where(base_filters)
        .order_by(RepairOrder.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()
    work_items: list[MechanicWorkItem] = []
    for order, vehicle in rows:
        work_items.append(
            MechanicWorkItem(
                id=str(order.id),
                order_number=order.order_number,
                status=order.status.value if hasattr(order.status, "value") else str(order.status),
                vehicle_info=vehicle_display_label(vehicle.year, vehicle.make, vehicle.model, vehicle.unit_number),
                updated_at=order.updated_at.isoformat(),
            )
        )
    return paginated_or_list(work_items, total, skip, limit, paginated)


class MechanicPasswordUpdate(BaseModel):
    new_password: str = Field(..., min_length=8, description="New password for the mechanic")


@router.put("/{mechanic_id}", response_model=UserResponse)
async def update_mechanic(
    mechanic_id: UUID,
    mechanic_update: MechanicUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )

    result = await db.execute(
        select(User).where(
            and_(
                User.id == mechanic_id,
                User.role == UserRole.MECHANIC,
                User.tenant_id == current_user.tenant_id,
            )
        )
    )
    mechanic = result.scalar_one_or_none()
    if not mechanic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic not found")

    if mechanic_update.email and mechanic_update.email != mechanic.email:
        email_check = await db.execute(select(User).where(User.email == mechanic_update.email))
        if email_check.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    provided_fields = mechanic_update.model_fields_set
    merged_shift_start, merged_shift_end = _validate_shift_fields(
        mechanic_update.shift_start_local_override if "shift_start_local_override" in provided_fields else mechanic.shift_start_local_override,
        mechanic_update.shift_end_local_override if "shift_end_local_override" in provided_fields else mechanic.shift_end_local_override,
    )
    if "core_hours_target_minutes_override" in provided_fields:
        if (
            mechanic_update.core_hours_target_minutes_override is not None
            and not 1 <= mechanic_update.core_hours_target_minutes_override <= 1440
        ):
            raise HTTPException(status_code=400, detail="core_hours_target_minutes_override must be between 1 and 1440")

    if mechanic_update.first_name is not None:
        mechanic.first_name = mechanic_update.first_name
    if mechanic_update.last_name is not None:
        mechanic.last_name = mechanic_update.last_name
    if mechanic_update.email is not None:
        mechanic.email = mechanic_update.email
    if mechanic_update.phone is not None:
        mechanic.phone = mechanic_update.phone or None
    if mechanic_update.address is not None:
        mechanic.address = mechanic_update.address or None
    if mechanic_update.password:
        validate_password(mechanic_update.password)
        mechanic.hashed_password = get_password_hash(mechanic_update.password)
    if "core_hours_target_minutes_override" in provided_fields:
        mechanic.core_hours_target_minutes_override = mechanic_update.core_hours_target_minutes_override
    if "shift_start_local_override" in provided_fields:
        mechanic.shift_start_local_override = merged_shift_start
    if "shift_end_local_override" in provided_fields:
        mechanic.shift_end_local_override = merged_shift_end

    db.add(mechanic)
    await db.commit()
    await db.refresh(mechanic)

    return UserResponse.model_validate(mechanic)


@router.put("/{mechanic_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def update_mechanic_password(
    mechanic_id: UUID,
    password_update: MechanicPasswordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be associated with a tenant",
        )

    result = await db.execute(
        select(User).where(
            and_(
                User.id == mechanic_id,
                User.role == UserRole.MECHANIC,
                User.tenant_id == current_user.tenant_id,
            )
        )
    )
    mechanic = result.scalar_one_or_none()
    if not mechanic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic not found")

    # Validate password complexity
    validate_password(password_update.new_password)
    
    mechanic.hashed_password = get_password_hash(password_update.new_password)
    db.add(mechanic)
    await db.commit()

    return


# ============ PTO REQUEST ENDPOINTS ============

class PTORequestCreate(BaseModel):
    request_type: str  # "pto" or "cash"
    pto_start_date: Optional[date] = None
    pto_end_date: Optional[date] = None
    points_requested: int
    notes: Optional[str] = None


class PTORequestResponse(BaseModel):
    id: str
    mechanic_id: str
    mechanic_name: str
    request_type: str
    status: str
    pto_start_date: Optional[date] = None
    pto_end_date: Optional[date] = None
    pto_days: Optional[int] = None
    points_requested: int
    cash_value: Optional[float] = None
    mechanic_notes: Optional[str] = None
    manager_notes: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None


@router.post("/pto-requests", response_model=PTORequestResponse)
async def create_pto_request(
    request: PTORequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic creates a PTO or cash-out request"""
    if request.request_type not in ("pto", "cash"):
        raise HTTPException(status_code=400, detail="Invalid request type")
    
    # Validate points
    result = await db.execute(
        select(MechanicPointsBalance).where(
            MechanicPointsBalance.mechanic_id == current_user.id
        )
    )
    balance = result.scalar_one_or_none()
    
    if not balance or balance.available_points < request.points_requested:
        raise HTTPException(status_code=400, detail="Insufficient points")
    
    # Validate PTO request
    pto_days = None
    cash_value = None
    
    if request.request_type == "pto":
        if not request.pto_start_date or not request.pto_end_date:
            raise HTTPException(status_code=400, detail="PTO dates required")
        if request.pto_end_date < request.pto_start_date:
            raise HTTPException(status_code=400, detail="End date must be after start date")
        
        pto_days = (request.pto_end_date - request.pto_start_date).days + 1
        required_points = pto_days * POINTS_PER_PTO_DAY
        
        if request.points_requested < required_points:
            raise HTTPException(
                status_code=400, 
                detail=f"Need {required_points} points for {pto_days} day(s)"
            )
    else:
        cash_value = int(request.points_requested * CASH_PER_POINT * 100)  # In cents
    
    pto_request = PTORequest(
        tenant_id=current_user.tenant_id,
        mechanic_id=current_user.id,
        request_type=PTORequestType.PTO if request.request_type == "pto" else PTORequestType.CASH,
        status=PTORequestStatus.PENDING,
        pto_start_date=request.pto_start_date,
        pto_end_date=request.pto_end_date,
        pto_days=pto_days,
        points_requested=request.points_requested,
        cash_value=cash_value,
        mechanic_notes=request.notes,
    )
    
    db.add(pto_request)
    await db.commit()
    await db.refresh(pto_request)
    
    return PTORequestResponse(
        id=str(pto_request.id),
        mechanic_id=str(current_user.id),
        mechanic_name=f"{current_user.first_name} {current_user.last_name}",
        request_type=request.request_type,
        status="pending",
        pto_start_date=pto_request.pto_start_date,
        pto_end_date=pto_request.pto_end_date,
        pto_days=pto_days,
        points_requested=request.points_requested,
        cash_value=cash_value / 100 if cash_value else None,
        mechanic_notes=request.notes,
        created_at=pto_request.created_at,
    )


@router.get("/pto-requests/my", response_model=List[PTORequestResponse])
async def get_my_pto_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic views their own PTO requests"""
    total_result = await db.execute(
        select(func.count(PTORequest.id)).where(PTORequest.mechanic_id == current_user.id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(PTORequest)
        .where(PTORequest.mechanic_id == current_user.id)
        .order_by(PTORequest.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    requests = result.scalars().all()
    
    items = [
        PTORequestResponse(
            id=str(r.id),
            mechanic_id=str(r.mechanic_id),
            mechanic_name=f"{current_user.first_name} {current_user.last_name}",
            request_type=r.request_type.value,
            status=r.status.value,
            pto_start_date=r.pto_start_date,
            pto_end_date=r.pto_end_date,
            pto_days=r.pto_days,
            points_requested=r.points_requested,
            cash_value=r.cash_value / 100 if r.cash_value else None,
            mechanic_notes=r.mechanic_notes,
            manager_notes=r.manager_notes,
            created_at=r.created_at,
            processed_at=r.processed_at,
        )
        for r in requests
    ]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.delete("/pto-requests/{request_id}", status_code=204)
async def cancel_pto_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic cancels their pending PTO request"""
    result = await db.execute(
        select(PTORequest).where(
            and_(
                PTORequest.id == request_id,
                PTORequest.mechanic_id == current_user.id,
            )
        )
    )
    pto_request = result.scalar_one_or_none()
    
    if not pto_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if pto_request.status != PTORequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Can only cancel pending requests")
    
    pto_request.status = PTORequestStatus.CANCELLED
    await db.commit()


@router.get("/pto-requests/pending", response_model=List[PTORequestResponse])
async def get_pending_pto_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    """Manager views all pending PTO requests"""
    total_result = await db.execute(
        select(func.count(PTORequest.id)).where(
            and_(
                PTORequest.tenant_id == current_user.tenant_id,
                PTORequest.status == PTORequestStatus.PENDING,
            )
        )
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(PTORequest, User)
        .join(User, PTORequest.mechanic_id == User.id)
        .where(
            and_(
                PTORequest.tenant_id == current_user.tenant_id,
                PTORequest.status == PTORequestStatus.PENDING,
            )
        )
        .order_by(PTORequest.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()
    
    items = [
        PTORequestResponse(
            id=str(r.id),
            mechanic_id=str(r.mechanic_id),
            mechanic_name=f"{u.first_name} {u.last_name}",
            request_type=r.request_type.value,
            status=r.status.value,
            pto_start_date=r.pto_start_date,
            pto_end_date=r.pto_end_date,
            pto_days=r.pto_days,
            points_requested=r.points_requested,
            cash_value=r.cash_value / 100 if r.cash_value else None,
            mechanic_notes=r.mechanic_notes,
            manager_notes=r.manager_notes,
            created_at=r.created_at,
            processed_at=r.processed_at,
        )
        for r, u in rows
    ]
    return paginated_or_list(items, total, skip, limit, paginated)


class ProcessPTORequest(BaseModel):
    action: str  # "approve" or "deny"
    manager_notes: Optional[str] = None


@router.post("/pto-requests/{request_id}/process", response_model=PTORequestResponse)
async def process_pto_request(
    request_id: UUID,
    body: ProcessPTORequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    """Manager approves or denies a PTO request"""
    if body.action not in ("approve", "deny"):
        raise HTTPException(status_code=400, detail="Invalid action")
    
    result = await db.execute(
        select(PTORequest, User)
        .join(User, PTORequest.mechanic_id == User.id)
        .where(
            and_(
                PTORequest.id == request_id,
                PTORequest.tenant_id == current_user.tenant_id,
            )
        )
    )
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    
    pto_request, mechanic = row
    
    if pto_request.status != PTORequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Request already processed")
    
    if body.action == "approve":
        # Verify mechanic still has enough points
        result = await db.execute(
            select(MechanicPointsBalance).where(
                MechanicPointsBalance.mechanic_id == pto_request.mechanic_id
            )
        )
        balance = result.scalar_one_or_none()
        
        if not balance or balance.available_points < pto_request.points_requested:
            raise HTTPException(status_code=400, detail="Mechanic no longer has enough points")
        
        # Deduct points
        balance.available_points -= pto_request.points_requested
        balance.total_redeemed += pto_request.points_requested
        
        # Create points transaction
        tx_type = PointsTransactionType.REDEEMED_PTO if pto_request.request_type == PTORequestType.PTO else PointsTransactionType.REDEEMED_CASH
        value = pto_request.pto_days if pto_request.request_type == PTORequestType.PTO else (pto_request.cash_value / 100 if pto_request.cash_value else 0)
        
        points_tx = MechanicPoints(
            tenant_id=pto_request.tenant_id,
            mechanic_id=pto_request.mechanic_id,
            transaction_type=tx_type,
            points=-pto_request.points_requested,
            multiplier=Decimal("1.00"),
            notes=f"Approved: {pto_request.request_type.value} request",
            redemption_value=Decimal(str(value)),
        )
        db.add(points_tx)
        
        pto_request.status = PTORequestStatus.APPROVED
    else:
        pto_request.status = PTORequestStatus.DENIED
    
    pto_request.manager_notes = body.manager_notes
    pto_request.processed_by_id = current_user.id
    pto_request.processed_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(pto_request)
    
    return PTORequestResponse(
        id=str(pto_request.id),
        mechanic_id=str(pto_request.mechanic_id),
        mechanic_name=f"{mechanic.first_name} {mechanic.last_name}",
        request_type=pto_request.request_type.value,
        status=pto_request.status.value,
        pto_start_date=pto_request.pto_start_date,
        pto_end_date=pto_request.pto_end_date,
        pto_days=pto_request.pto_days,
        points_requested=pto_request.points_requested,
        cash_value=pto_request.cash_value / 100 if pto_request.cash_value else None,
        mechanic_notes=pto_request.mechanic_notes,
        manager_notes=pto_request.manager_notes,
        created_at=pto_request.created_at,
        processed_at=pto_request.processed_at,
    )


# ============ WORK PHOTOS ============

class WorkPhotoUpload(BaseModel):
    image: str = Field(..., description="Base64 encoded image data")
    caption: Optional[str] = Field(None, max_length=500, description="Optional caption/note")


class WorkPhotoResponse(BaseModel):
    id: str
    image_url: str
    caption: Optional[str]
    uploaded_at: datetime
    mechanic_name: str


@router.post("/my-jobs/{job_id}/photos", response_model=WorkPhotoResponse)
async def upload_job_photo(
    job_id: UUID,
    body: WorkPhotoUpload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Upload a work photo for a job.
    Only allowed for jobs assigned to the current mechanic in active statuses.
    """
    if current_user.role != UserRole.MECHANIC:
        raise HTTPException(status_code=403, detail="Only mechanics can upload work photos")
    
    if not is_cloudinary_configured():
        raise HTTPException(
            status_code=424,
            detail="Photo upload service is not configured. Add Cloudinary settings before uploading photos.",
        )
    
    # Verify job belongs to this mechanic and is in active status
    result = await db.execute(
        select(RepairOrder).where(
            and_(
                RepairOrder.id == job_id,
                RepairOrder.assigned_mechanic_id == current_user.id,
                RepairOrder.status.in_([
                    RepairOrderStatus.ASSIGNED,
                    RepairOrderStatus.ACKNOWLEDGED,
                    RepairOrderStatus.IN_PROGRESS,
                ]),
                RepairOrder.deleted_at.is_(None),
            )
        )
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=404, 
            detail="Job not found or not in active status"
        )
    
    try:
        # Upload to Cloudinary
        image_url = await upload_work_photo(
            base64_image=body.image,
            repair_order_id=str(job_id),
            mechanic_id=str(current_user.id),
        )
        
        # Save to database
        photo = WorkPhoto(
            repair_order_id=job_id,
            mechanic_id=current_user.id,
            image_url=image_url,
            caption=body.caption,
        )
        db.add(photo)
        await db.commit()
        await db.refresh(photo)
        
        logger.info(
            "Work photo uploaded",
            photo_id=str(photo.id),
            repair_order_id=str(job_id),
            mechanic_id=str(current_user.id),
        )
        
        return WorkPhotoResponse(
            id=str(photo.id),
            image_url=photo.image_url,
            caption=photo.caption,
            uploaded_at=photo.uploaded_at,
            mechanic_name=f"{current_user.first_name} {current_user.last_name}",
        )
        
    except Exception as e:
        logger.error("Failed to upload work photo", error=str(e))
        raise HTTPException(
            status_code=424,
            detail="Photo upload service failed. Check the Cloudinary settings and try again.",
        ) from e


@router.get("/my-jobs/{job_id}/photos", response_model=List[WorkPhotoResponse])
async def list_job_photos(
    job_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.MECHANIC, UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
    ),
):
    """
    List all photos for a job.
    Mechanics can see photos for their assigned jobs.
    Managers can see photos for any job in their tenant.
    """
    # Build query based on role
    if current_user.role == UserRole.MECHANIC:
        # Mechanic can only see their own assigned jobs within their tenant.
        result = await db.execute(
            select(RepairOrder).where(
                and_(
                    RepairOrder.id == job_id,
                    RepairOrder.assigned_mechanic_id == current_user.id,
                    RepairOrder.tenant_id == current_user.tenant_id,
                )
            )
        )
    elif current_user.role in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        # Manager can see any job in their tenant
        result = await db.execute(
            select(RepairOrder).where(
                and_(
                    RepairOrder.id == job_id,
                    RepairOrder.tenant_id == current_user.tenant_id,
                )
            )
        )
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get photos with mechanic info
    total_result = await db.execute(
        select(func.count(WorkPhoto.id)).where(WorkPhoto.repair_order_id == job_id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(WorkPhoto, User)
        .outerjoin(User, WorkPhoto.mechanic_id == User.id)
        .where(WorkPhoto.repair_order_id == job_id)
        .order_by(WorkPhoto.uploaded_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()
    
    items = [
        WorkPhotoResponse(
            id=str(photo.id),
            image_url=photo.image_url,
            caption=photo.caption,
            uploaded_at=photo.uploaded_at,
            mechanic_name=f"{mechanic.first_name} {mechanic.last_name}" if mechanic else "Unknown",
        )
        for photo, mechanic in rows
    ]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.delete("/my-jobs/{job_id}/photos/{photo_id}")
async def delete_job_photo(
    job_id: UUID,
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.MECHANIC, UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
    ),
):
    """
    Delete a work photo.
    Mechanics can delete their own photos.
    Managers can delete any photo in their tenant.
    """
    # Get the photo
    result = await db.execute(
        select(WorkPhoto, RepairOrder)
        .join(RepairOrder, WorkPhoto.repair_order_id == RepairOrder.id)
        .where(
            and_(
                WorkPhoto.id == photo_id,
                WorkPhoto.repair_order_id == job_id,
            )
        )
    )
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    
    photo, order = row
    
    # Check permissions
    if current_user.role == UserRole.MECHANIC:
        if order.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=403, detail="Photo not in your tenant")
        if photo.mechanic_id != current_user.id:
            raise HTTPException(status_code=403, detail="Can only delete your own photos")
    elif current_user.role in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN):
        if order.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=403, detail="Photo not in your tenant")
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Delete from database (Cloudinary cleanup can be done async/later)
    await db.delete(photo)
    await db.commit()
    
    logger.info(
        "Work photo deleted",
        photo_id=str(photo_id),
        repair_order_id=str(job_id),
        deleted_by=str(current_user.id),
    )
    
    return {"status": "deleted"}
