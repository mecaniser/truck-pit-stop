from typing import List, Optional
from datetime import datetime, timedelta, date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, cast, Date
from sqlalchemy.orm import selectinload
from uuid import UUID
import json

from app.core.dependencies import get_db, get_current_active_user
from app.core.security import get_password_hash
from app.core.password_policy import validate_password
from app.db.models.user import User, UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.mechanic_points import MechanicPoints, MechanicPointsBalance, PointsTransactionType
from app.db.models.pto_request import PTORequest, PTORequestStatus, PTORequestType
from app.schemas.auth import UserResponse
from app.schemas.mechanic import MechanicCreate
from app.schemas.mechanic_update import MechanicUpdate
from pydantic import BaseModel, Field

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


@router.get("", response_model=List[MechanicWithPoints])
async def list_mechanics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    """List mechanics with their points info for dashboard"""
    if not current_user.tenant_id:
        return []

    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == current_user.tenant_id,
                User.role == UserRole.MECHANIC,
            )
        )
    )
    mechanics = result.scalars().all()
    
    mechanics_with_points = []
    for mechanic in mechanics:
        # Get points balance
        result = await db.execute(
            select(MechanicPointsBalance).where(
                MechanicPointsBalance.mechanic_id == mechanic.id
            )
        )
        balance = result.scalar_one_or_none()
        
        # Get pending requests count
        result = await db.execute(
            select(func.count(PTORequest.id)).where(
                and_(
                    PTORequest.mechanic_id == mechanic.id,
                    PTORequest.status == PTORequestStatus.PENDING,
                )
            )
        )
        pending_count = result.scalar() or 0
        
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
        ))
    
    return mechanics_with_points


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_mechanic(
    mechanic_data: MechanicCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    # Validate password complexity
    validate_password(mechanic_data.password)
    
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
    work_completed_at: Optional[datetime] = None


class MechanicJobSummary(BaseModel):
    """Job summary for mechanic job list"""
    id: str
    order_number: str
    status: str
    vehicle_info: str
    description: Optional[str] = None
    services_count: int = 0
    updated_at: datetime
    work_started_at: Optional[datetime] = None


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


# Points constants
POINTS_PER_PTO_DAY = 8000  # 8000 points = 1 day off (~$300)
CASH_PER_POINT = 0.0375   # $0.0375 per point (8000 pts = $300)


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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Get all jobs assigned to the current mechanic"""
    result = await db.execute(
        select(RepairOrder)
        .where(
            and_(
                RepairOrder.tenant_id == current_user.tenant_id,
                RepairOrder.assigned_mechanic_id == current_user.id,
                RepairOrder.status.in_([
                    RepairOrderStatus.ASSIGNED,
                    RepairOrderStatus.ACKNOWLEDGED,
                    RepairOrderStatus.IN_PROGRESS,
                    RepairOrderStatus.PENDING_REVIEW,
                ]),
            )
        )
        .options(selectinload(RepairOrder.vehicle))
        .order_by(RepairOrder.updated_at.desc())
    )
    orders = result.scalars().all()
    
    jobs = []
    for order in orders:
        vehicle = order.vehicle
        vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Unknown"
        
        # Count services
        services_count = 0
        if order.internal_notes:
            try:
                notes = json.loads(order.internal_notes)
                services_count = len(notes.get("selected_services", []))
            except:
                pass
        
        jobs.append(MechanicJobSummary(
            id=str(order.id),
            order_number=order.order_number,
            status=order.status.value,
            vehicle_info=vehicle_info,
            description=order.description,
            services_count=services_count,
            updated_at=order.updated_at,
            work_started_at=getattr(order, 'work_started_at', None),
        ))
    
    return jobs


@router.get("/my-history", response_model=List[MechanicHistoryItem])
async def get_my_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Get completed work history for the current mechanic"""
    result = await db.execute(
        select(RepairOrder)
        .where(
            and_(
                RepairOrder.tenant_id == current_user.tenant_id,
                RepairOrder.assigned_mechanic_id == current_user.id,
                RepairOrder.status.in_([
                    RepairOrderStatus.COMPLETED,
                    RepairOrderStatus.INVOICED,
                    RepairOrderStatus.PAID,
                ]),
            )
        )
        .options(selectinload(RepairOrder.vehicle))
        .order_by(RepairOrder.updated_at.desc())
        .limit(50)  # Limit history to last 50 jobs
    )
    orders = result.scalars().all()
    
    # Get points earned for each order
    order_ids = [order.id for order in orders]
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
        vehicle_info = f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip() if vehicle else "Unknown"
        
        services_count = 0
        if order.internal_notes:
            try:
                notes = json.loads(order.internal_notes)
                services_count = len(notes.get("selected_services", []))
            except:
                pass
        
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
    
    return history


@router.get("/my-jobs/{order_id}", response_model=MechanicJobDetail)
async def get_my_job_detail(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Get job detail for mechanic - NO customer info exposed"""
    result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.id == order_id)
        .options(selectinload(RepairOrder.vehicle))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    
    if order.assigned_mechanic_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This job is not assigned to you")
    
    vehicle = order.vehicle
    
    # Parse services
    services = []
    if order.internal_notes:
        try:
            notes = json.loads(order.internal_notes)
            for svc in notes.get("selected_services", []):
                services.append(ServiceItem(
                    name=svc.get("name", "Service"),
                    description=svc.get("description"),
                    base_price=svc.get("base_price"),
                ))
        except:
            pass
    
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
    )


@router.get("/{mechanic_id}/work", response_model=list[MechanicWorkItem])
async def get_mechanic_work(
    mechanic_id: UUID,
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

    result = await db.execute(
        select(RepairOrder, Customer, Vehicle)
        .join(Customer, RepairOrder.customer_id == Customer.id)
        .join(Vehicle, RepairOrder.vehicle_id == Vehicle.id)
        .where(
            and_(
                RepairOrder.tenant_id == tenant_id,
                RepairOrder.assigned_mechanic_id == mechanic.id,
            )
        )
        .order_by(RepairOrder.updated_at.desc())
    )
    rows = result.all()
    work_items: list[MechanicWorkItem] = []
    for order, customer, vehicle in rows:
        work_items.append(
            MechanicWorkItem(
                id=str(order.id),
                order_number=order.order_number,
                status=order.status.value if hasattr(order.status, "value") else str(order.status),
                vehicle_info=f"{vehicle.year or ''} {vehicle.make} {vehicle.model}".strip(),
                updated_at=order.updated_at.isoformat(),
            )
        )
    return work_items


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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    """Mechanic views their own PTO requests"""
    result = await db.execute(
        select(PTORequest)
        .where(PTORequest.mechanic_id == current_user.id)
        .order_by(PTORequest.created_at.desc())
        .limit(20)
    )
    requests = result.scalars().all()
    
    return [
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)),
):
    """Manager views all pending PTO requests"""
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
    )
    rows = result.all()
    
    return [
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
