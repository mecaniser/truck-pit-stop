from typing import List, Optional
from uuid import UUID
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from pydantic import BaseModel, ConfigDict
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.core.pagination import paginated_or_list
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.service import Service, ServicePart
from app.db.models.inventory import Inventory
from app.db.models.tenant import Tenant
from app.db.models.appointment import Appointment, AppointmentStatus
from sqlalchemy.orm import selectinload
from app.services import booking_payments as booking

router = APIRouter()


# Schemas
class AppointmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_kind: str | None = None
    service_id: UUID
    vehicle_id: Optional[UUID] = None
    scheduled_at: datetime
    customer_notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    status: Optional[AppointmentStatus] = None
    internal_notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: str
    confirmation_number: str
    customer_id: str
    vehicle_id: Optional[str]
    service_id: str
    service_name: str
    scheduled_at: datetime
    duration_minutes: int
    status: str
    price: str
    customer_notes: Optional[str]
    paid_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True
        extra = "allow"

    booking_kind: str | None = None
    booking_payment_version: int | None = None
    booking_payment_state: str | None = None
    hold_expires_at: datetime | None = None
    price_snapshot_sha256: str | None = None
    version: int | None = None
    currency: str | None = None
    receipt: dict | None = None
    payment_attempt_id: str | None = None
    payment_attempt_state: str | None = None
    payment_provider: str | None = None


class PaymentIntentResponse(BaseModel):
    client_secret: str
    appointment_id: str


class TimeSlot(BaseModel):
    time: str
    available: bool
    starts_at: datetime
    timezone: str


def generate_confirmation_number() -> str:
    """Generate a unique confirmation number like APT-XXXX-XXXX"""
    chars = string.ascii_uppercase + string.digits
    return f"APT-{''.join(secrets.choice(chars) for _ in range(4))}-{''.join(secrets.choice(chars) for _ in range(4))}"


# --- Appointments ---

@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    data: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Create an idempotent unpaid hold; only verified full payment confirms it."""
    appointment = await booking.reserve(db, current_user, data, idempotency_key)
    return await booking.snapshot(db, appointment)


class BookingAttemptCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int
    price_snapshot_sha256: str
    quickbooks_token: str | None = None

class BookingPaymentVerify(BaseModel):
    model_config = ConfigDict(extra='forbid')
    attempt_id: UUID
    expected_version: int

@router.get('/payment-capability')
async def booking_payment_capability(service_id: UUID, db: AsyncSession=Depends(get_db), current_user: User=Depends(get_current_active_user)):
    if not current_user.tenant_id or current_user.role != UserRole.CUSTOMER: raise HTTPException(404,'Service not found')
    service=await db.scalar(select(Service).where(Service.id==service_id,Service.tenant_id==current_user.tenant_id,Service.is_active.is_(True),Service.deleted_at.is_(None)))
    tenant=await db.get(Tenant,current_user.tenant_id)
    if not service or not tenant:raise HTTPException(404,'Service not found')
    try:await booking.price(service,tenant)
    except HTTPException as error:
        return {'available':False,'provider':None,'reason_code':error.detail['code'],'message':error.detail['message'],'shop_timezone':tenant.timezone,'currency':'usd','token_url':None}
    capability=await booking.provider.booking_provider_capability(db,tenant)
    return {'available':capability.available,'provider':capability.binding.provider if capability.binding else None,'reason_code':capability.reason_code,'message':capability.message,'shop_timezone':tenant.timezone,'currency':'usd','token_url':capability.token_url}

@router.post('/{appointment_id}/payment-attempts')
async def start_booking_payment(appointment_id: UUID, body:BookingAttemptCreate, db:AsyncSession=Depends(get_db),current_user:User=Depends(get_current_active_user),idempotency_key:str|None=Header(None,alias='Idempotency-Key')):
    return await booking.start_attempt(db,current_user,appointment_id,body,idempotency_key)

async def _reject_unverified_appointment_payment(
    appointment_id: UUID,
    db: AsyncSession,
    current_user: User,
):
    """Admit only the appointment's tenant/principal, then fail without writes."""
    staff_roles = (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST)
    if not current_user.tenant_id or current_user.role not in (UserRole.CUSTOMER, *staff_roles):
        raise HTTPException(status_code=404, detail="Appointment not found")
    filters = [
        Appointment.id == appointment_id,
        Appointment.tenant_id == current_user.tenant_id,
        Appointment.deleted_at.is_(None),
    ]
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id:
            raise HTTPException(status_code=404, detail="Appointment not found")
        filters.append(Appointment.customer_id == current_user.customer_id)
    result = await db.execute(select(Appointment.id).where(*filters).execution_options(autoflush=False))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    raise HTTPException(
        status_code=409,
        detail={
            "code": "appointment_payment_verification_unavailable",
            "message": "Online payment for this appointment is unavailable. Contact the shop for help.",
        },
    )


@router.post("/{appointment_id}/payment-intent", response_model=PaymentIntentResponse)
async def create_appointment_payment(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Payment remains unavailable until a shop-bound verified flow exists."""
    await _reject_unverified_appointment_payment(appointment_id, db, current_user)


@router.post("/{appointment_id}/confirm-payment")
async def confirm_appointment_payment(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    body: BookingPaymentVerify | None = None,
):
    """Never infer payment success from a caller's confirmation request."""
    if body is None:
        await _reject_unverified_appointment_payment(appointment_id, db, current_user)
    return await booking.verify_attempt(db,current_user,appointment_id,body)


@router.get("", response_model=List[AppointmentResponse])
async def list_appointments(
    status_filter: Optional[AppointmentStatus] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    paginated: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List appointments (filtered by user role)"""

    filters = [Appointment.tenant_id == current_user.tenant_id, Appointment.deleted_at.is_(None)]
    if current_user.role not in {UserRole.CUSTOMER, *booking.STAFF}:
        return paginated_or_list([], 0, skip, limit, paginated)

    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        filters.append(Appointment.customer_id == current_user.customer_id)
    else:
        if not current_user.tenant_id:
            return paginated_or_list([], 0, skip, limit, paginated)
        filters.append(Appointment.tenant_id == current_user.tenant_id)

    if status_filter:
        filters.append(Appointment.status == status_filter)

    if from_date:
        filters.append(func.date(Appointment.scheduled_at) >= from_date)

    if to_date:
        filters.append(func.date(Appointment.scheduled_at) <= to_date)

    count_query = select(func.count(Appointment.id)).where(*filters)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = (
        select(Appointment, Service)
        .join(Service)
        .where(*filters)
        .order_by(Appointment.scheduled_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    items = [await booking.snapshot(db, apt, svc.name, actor=current_user) for apt, svc in rows]
    return paginated_or_list(items, total, skip, limit, paginated)


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    appointment = await booking.admitted_appointment(db,current_user,appointment_id)
    return await booking.snapshot(db,appointment,actor=current_user)


@router.put("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: UUID,
    data: AppointmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    await booking.locks(db,current_user.tenant_id)
    apt=await booking.admitted_appointment(db,current_user,appointment_id,write=True)
    if current_user.role not in booking.STAFF: raise HTTPException(404,'Appointment not found')
    svc=await db.get(Service,apt.service_id)
    if apt.booking_payment_version == 1:
        allowed_advances={(AppointmentStatus.CONFIRMED,AppointmentStatus.IN_PROGRESS),(AppointmentStatus.IN_PROGRESS,AppointmentStatus.COMPLETED)}
        if data.status is not None and data.status != apt.status and (apt.status,data.status) not in allowed_advances:
            booking.fail('booking_status_transition_unavailable','Only verified reservations can advance through shop service. Use the separate cancellation action.')
        if data.status and data.status in {AppointmentStatus.CONFIRMED,AppointmentStatus.IN_PROGRESS,AppointmentStatus.COMPLETED}:
            receipt=await db.scalar(select(booking.BookingReceipt).where(booking.BookingReceipt.id==apt.confirmed_receipt_id,booking.BookingReceipt.tenant_id==apt.tenant_id,booking.BookingReceipt.appointment_id==apt.id))
            if not receipt or receipt.amount_received_minor-receipt.refunded_amount_minor != int(Decimal(apt.price)*100) or apt.booking_payment_state!='paid':
                booking.fail('booking_verified_payment_required','Verified full payment is required before confirming this reservation.')
        if data.scheduled_at is not None:
            booking.fail('booking_snapshot_immutable','A prepaid reservation cannot be changed through this action.')
        if data.status==AppointmentStatus.CANCELLED:
            booking.fail('booking_cancel_required','Use the reservation cancellation action.')
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(apt, field, value)
    
    await db.commit()
    await db.refresh(apt)
    
    return AppointmentResponse(
        id=str(apt.id),
        confirmation_number=apt.confirmation_number,
        customer_id=str(apt.customer_id),
        vehicle_id=str(apt.vehicle_id) if apt.vehicle_id else None,
        service_id=str(apt.service_id),
        service_name=svc.name,
        scheduled_at=apt.scheduled_at,
        duration_minutes=apt.duration_minutes,
        status=apt.status.value,
        price=str(apt.price),
        customer_notes=apt.customer_notes,
        paid_at=apt.paid_at,
        created_at=apt.created_at,
    )


@router.post("/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cancel an appointment"""
    
    await booking.locks(db,current_user.tenant_id)
    apt=await booking.admitted_appointment(db,current_user,appointment_id,write=True)
    if apt.booking_payment_version==1:
        live=await db.scalar(select(booking.BookingPaymentAttempt.id).where(booking.BookingPaymentAttempt.appointment_id==apt.id,booking.BookingPaymentAttempt.state.in_(booking.LIVE)))
        if live:booking.fail('booking_payment_pending','Payment verification is pending. Contact the shop before cancelling.')
        if apt.booking_payment_state=='unpaid_hold':apt.booking_payment_state='expired_unpaid'
        apt.booking_version+=1
    # Can only cancel pending or confirmed
    if apt.status not in [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]:
        raise HTTPException(status_code=400, detail="Cannot cancel appointment in current status")
    
    apt.status = AppointmentStatus.CANCELLED
    await db.commit()
    
    return {"status": "cancelled", "confirmation_number": apt.confirmation_number}


@router.get("/available-slots/{service_id}")
async def get_available_slots(
    service_id: UUID,
    date_str: date = Query(..., alias="date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get available time slots for a service on a given date"""
    
    result = await db.execute(select(Service).where(
        Service.id == service_id,
        Service.tenant_id == current_user.tenant_id,
        Service.is_active.is_(True),
        Service.deleted_at.is_(None),
    ))
    service = result.scalar_one_or_none()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    if service.duration_minutes<=0:
        booking.fail("booking_service_unavailable","This service duration must be reviewed before reserving.")
    
    result = await db.execute(select(Tenant.timezone).where(Tenant.id == service.tenant_id))
    timezone_name = result.scalar_one_or_none()
    try:
        shop_zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise HTTPException(status_code=409, detail="Shop timezone is unavailable")
    start_of_day = datetime.combine(date_str, datetime.min.time(), tzinfo=shop_zone).astimezone(timezone.utc)
    end_of_day = datetime.combine(date_str + timedelta(days=1), datetime.min.time(), tzinfo=shop_zone).astimezone(timezone.utc)
    
    result = await db.execute(
        select(Appointment).where(
            and_(
                Appointment.tenant_id == service.tenant_id,
                Appointment.deleted_at.is_(None),
                # Include earlier appointments that may extend into this shop day.
                Appointment.scheduled_at < end_of_day,
                or_(Appointment.status.in_([AppointmentStatus.CONFIRMED, AppointmentStatus.IN_PROGRESS]), (Appointment.booking_payment_version == 1) & (Appointment.status == AppointmentStatus.PENDING)),
            )
        )
    )
    existing = []
    for appointment in result.scalars().all():
        if getattr(appointment,'status',AppointmentStatus.CONFIRMED) == AppointmentStatus.PENDING and not (appointment.booking_payment_state == 'payment_processing' or (appointment.booking_payment_state == 'unpaid_hold' and appointment.hold_expires_at and booking.utc(appointment.hold_expires_at)>booking.now())):
            continue
        # Naive legacy/test values follow the database UTC convention.
        starts_at = appointment.scheduled_at.replace(tzinfo=appointment.scheduled_at.tzinfo or timezone.utc).astimezone(timezone.utc)
        ends_at = starts_at + timedelta(minutes=appointment.duration_minutes)
        if ends_at > start_of_day:
            existing.append((starts_at, ends_at))
    
    # Generate time slots (8am - 5pm, every 30 min)
    slots = []
    current_time = datetime.combine(date_str, datetime.strptime("08:00", "%H:%M").time(), tzinfo=shop_zone)
    end_time = datetime.combine(date_str, datetime.strptime("17:00", "%H:%M").time(), tzinfo=shop_zone)
    
    while current_time < end_time:
        # Check if slot conflicts with existing appointments
        slot_start = current_time.astimezone(timezone.utc)
        slot_end = slot_start + timedelta(minutes=service.duration_minutes)
        available = True
        
        for apt_start, apt_end in existing:
            # Adjacent appointments do not overlap.
            if not (slot_end <= apt_start or slot_start >= apt_end):
                available = False
                break
        
        slots.append(TimeSlot(
            time=current_time.strftime("%H:%M"),
            available=available,
            starts_at=slot_start,
            timezone=timezone_name,
        ))
        
        current_time += timedelta(minutes=30)
    
    return slots
