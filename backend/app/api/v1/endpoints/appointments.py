from typing import List, Optional
from uuid import UUID
from datetime import datetime, date, timedelta
import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel
from decimal import Decimal

from app.core.dependencies import get_db, get_current_active_user
from app.db.models.user import User, UserRole
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.service import Service
from app.db.models.appointment import Appointment, AppointmentStatus
from app.services.stripe_service import create_payment_intent

router = APIRouter()


# Schemas
class AppointmentCreate(BaseModel):
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


class PaymentIntentResponse(BaseModel):
    client_secret: str
    appointment_id: str


class TimeSlot(BaseModel):
    time: str
    available: bool


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
):
    """Create a new appointment (customer or staff)"""
    
    # Determine customer_id
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id:
            raise HTTPException(status_code=400, detail="Customer profile not found")
        customer_id = current_user.customer_id
        
        # Get tenant from customer
        result = await db.execute(select(Customer).where(Customer.id == customer_id))
        customer = result.scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        tenant_id = customer.tenant_id
    else:
        # Staff creating appointment - would need customer_id in request
        raise HTTPException(status_code=400, detail="Staff appointment creation not yet implemented")
    
    # Get service
    result = await db.execute(select(Service).where(Service.id == data.service_id))
    service = result.scalar_one_or_none()
    if not service or not service.is_active:
        raise HTTPException(status_code=404, detail="Service not found or inactive")
    
    if service.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Service not available")
    
    # Validate vehicle if required
    if service.requires_vehicle:
        if not data.vehicle_id:
            raise HTTPException(status_code=400, detail="Vehicle is required for this service")
        
        result = await db.execute(
            select(Vehicle).where(
                and_(Vehicle.id == data.vehicle_id, Vehicle.customer_id == customer_id)
            )
        )
        vehicle = result.scalar_one_or_none()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")
    
    # Generate confirmation number
    confirmation_number = generate_confirmation_number()
    
    # Create appointment
    appointment = Appointment(
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=data.vehicle_id,
        service_id=data.service_id,
        scheduled_at=data.scheduled_at,
        duration_minutes=service.duration_minutes,
        status=AppointmentStatus.PENDING,
        price=service.base_price,
        customer_notes=data.customer_notes,
        confirmation_number=confirmation_number,
    )
    
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    
    return AppointmentResponse(
        id=str(appointment.id),
        confirmation_number=appointment.confirmation_number,
        customer_id=str(appointment.customer_id),
        vehicle_id=str(appointment.vehicle_id) if appointment.vehicle_id else None,
        service_id=str(appointment.service_id),
        service_name=service.name,
        scheduled_at=appointment.scheduled_at,
        duration_minutes=appointment.duration_minutes,
        status=appointment.status.value,
        price=str(appointment.price),
        customer_notes=appointment.customer_notes,
        paid_at=appointment.paid_at,
        created_at=appointment.created_at,
    )


@router.post("/{appointment_id}/payment-intent", response_model=PaymentIntentResponse)
async def create_appointment_payment(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a Stripe payment intent for an appointment"""
    
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Verify ownership
    if current_user.role == UserRole.CUSTOMER:
        if appointment.customer_id != current_user.customer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    if appointment.status != AppointmentStatus.PENDING:
        raise HTTPException(status_code=400, detail="Appointment is not pending payment")
    
    # Create Stripe payment intent
    payment_intent = create_payment_intent(
        amount=appointment.price,
        metadata={
            "appointment_id": str(appointment.id),
            "confirmation_number": appointment.confirmation_number,
        }
    )
    
    # Store payment intent ID
    appointment.stripe_payment_intent_id = payment_intent.id
    await db.commit()
    
    return PaymentIntentResponse(
        client_secret=payment_intent.client_secret,
        appointment_id=str(appointment.id),
    )


@router.post("/{appointment_id}/confirm-payment")
async def confirm_appointment_payment(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Confirm payment was successful and update appointment status"""
    
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    if current_user.role == UserRole.CUSTOMER:
        if appointment.customer_id != current_user.customer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Update status
    appointment.status = AppointmentStatus.CONFIRMED
    appointment.paid_at = datetime.utcnow()
    await db.commit()
    
    return {"status": "confirmed", "confirmation_number": appointment.confirmation_number}


@router.get("", response_model=List[AppointmentResponse])
async def list_appointments(
    status_filter: Optional[AppointmentStatus] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List appointments (filtered by user role)"""
    
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id:
            return []
        query = select(Appointment, Service).join(Service).where(
            Appointment.customer_id == current_user.customer_id
        )
    else:
        if not current_user.tenant_id:
            return []
        query = select(Appointment, Service).join(Service).where(
            Appointment.tenant_id == current_user.tenant_id
        )
    
    if status_filter:
        query = query.where(Appointment.status == status_filter)
    
    if from_date:
        query = query.where(func.date(Appointment.scheduled_at) >= from_date)
    
    if to_date:
        query = query.where(func.date(Appointment.scheduled_at) <= to_date)
    
    query = query.order_by(Appointment.scheduled_at.desc())
    
    result = await db.execute(query)
    rows = result.all()
    
    return [
        AppointmentResponse(
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
        for apt, svc in rows
    ]


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Appointment, Service)
        .join(Service)
        .where(Appointment.id == appointment_id)
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    apt, svc = row
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if apt.customer_id != current_user.customer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user.tenant_id != apt.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
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


@router.put("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: UUID,
    data: AppointmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Appointment, Service)
        .join(Service)
        .where(Appointment.id == appointment_id)
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    apt, svc = row
    
    # Staff only for updates
    if current_user.role == UserRole.CUSTOMER:
        raise HTTPException(status_code=403, detail="Customers cannot update appointments directly")
    
    if current_user.tenant_id != apt.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
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
    
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    apt = result.scalar_one_or_none()
    
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Check access
    if current_user.role == UserRole.CUSTOMER:
        if apt.customer_id != current_user.customer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user.tenant_id != apt.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
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
    
    result = await db.execute(select(Service).where(Service.id == service_id))
    service = result.scalar_one_or_none()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Get existing appointments for this day
    start_of_day = datetime.combine(date_str, datetime.min.time())
    end_of_day = datetime.combine(date_str, datetime.max.time())
    
    result = await db.execute(
        select(Appointment).where(
            and_(
                Appointment.tenant_id == service.tenant_id,
                Appointment.scheduled_at >= start_of_day,
                Appointment.scheduled_at <= end_of_day,
                Appointment.status.in_([AppointmentStatus.CONFIRMED, AppointmentStatus.IN_PROGRESS]),
            )
        )
    )
    existing = result.scalars().all()
    
    # Generate time slots (8am - 5pm, every 30 min)
    slots = []
    current_time = datetime.combine(date_str, datetime.strptime("08:00", "%H:%M").time())
    end_time = datetime.combine(date_str, datetime.strptime("17:00", "%H:%M").time())
    
    while current_time < end_time:
        # Check if slot conflicts with existing appointments
        slot_end = current_time + timedelta(minutes=service.duration_minutes)
        available = True
        
        for apt in existing:
            apt_end = apt.scheduled_at + timedelta(minutes=apt.duration_minutes)
            # Check for overlap
            if not (slot_end <= apt.scheduled_at or current_time >= apt_end):
                available = False
                break
        
        slots.append(TimeSlot(
            time=current_time.strftime("%H:%M"),
            available=available,
        ))
        
        current_time += timedelta(minutes=30)
    
    return slots
