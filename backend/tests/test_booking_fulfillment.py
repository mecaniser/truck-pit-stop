import json
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID,uuid4
import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select,func
from app.db.models.user import User,UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.repair_order import RepairOrder,RepairOrderStatus
from app.db.models.invoice import Invoice,InvoiceStatus
from app.db.models.visit_request import VisitRequest
from app.db.models.booking_fulfillment import VisitRequestEvent,BookingRepairOrderLink
from app.db.models.appointment import Appointment
from app.db.models.booking_payment import BookingReceipt,BookingPaymentAttempt
from app.api.v1.endpoints.visit_requests import create_visit_request,VisitRequestCreate,VisitReviewBody,VisitAcceptBody,VisitWithdrawBody,VisitFulfillBody,list_visit_requests
from app.api.v1.endpoints.appointments import BookingAttemptCreate,BookingRepairOrderLinkBody
from app.services import booking_fulfillment as fulfillment,booking_payments as booking
from test_verified_booking_flow import setup_booking,result

@pytest_asyncio.fixture
async def staff_user(db_session,setup_booking):
    actor=User(id=uuid4(),tenant_id=setup_booking[0].id,role=UserRole.GARAGE_OWNER,first_name='Synthetic',last_name='Staff',email=f'{uuid4()}@example.test',is_active=True)
    db_session.add(actor);await db_session.commit()
    return actor

async def request(db,setup,**extra):
    raw=await create_visit_request(VisitRequestCreate(service_id=setup[2].id,**extra),db,setup[3],f'request-{uuid4()}')
    return await db.get(VisitRequest,UUID(raw['id']))

async def vehicle_order(db,setup,*,customer_id=None,vehicle=None,status=RepairOrderStatus.DRAFT,source=None):
    if vehicle is None:
        vehicle=Vehicle(tenant_id=setup[0].id,customer_id=setup[1].id,make='Volvo',model='VNL',year=2022,unit_number='1047',vin='DUPLICATE-VIN')
        db.add(vehicle);await db.flush()
    order=RepairOrder(tenant_id=setup[0].id,customer_id=customer_id or setup[1].id,vehicle_id=vehicle.id,status=status,source=source,order_number=f'RO-{uuid4()}',is_internal=False)
    db.add(order);await db.commit()
    return vehicle,order

async def paid(db,setup,monkeypatch):
    apt=await booking.reserve(db,setup[3],setup[4],f'hold-{uuid4()}')
    async def create(session,binding,**kwargs):
        attempt=await session.scalar(select(BookingPaymentAttempt).where(BookingPaymentAttempt.appointment_id==apt.id))
        return result(apt,attempt,provider_id=f'charge-{apt.id}')
    monkeypatch.setattr(booking.provider,'create_booking_payment',AsyncMock(side_effect=create))
    await booking.start_attempt(db,setup[3],apt.id,BookingAttemptCreate(expected_version=1,price_snapshot_sha256=apt.price_snapshot_sha256,quickbooks_token='opaque-fixture'),f'payment-{uuid4()}')
    return apt

@pytest.mark.asyncio
async def test_date_only_acceptance_is_versioned_audited_and_has_no_financial_or_slot_effect(db_session,setup_booking,staff_user):
    row=await request(db_session,setup_booking)
    response=await fulfillment.request_action(db_session,staff_user,row.id,'accept',VisitAcceptBody(expected_version=1,arrival_date=booking.now().date()+timedelta(days=1),internal_note='Staff-only review'),'accept-date-key')
    assert response['request']['status']=='accepted' and response['request']['version']==2
    assert response['request']['internal_review_note']=='Staff-only review'
    assert await db_session.scalar(select(func.count(Appointment.id)))==0
    assert await db_session.scalar(select(func.count(BookingPaymentAttempt.id)))==0
    assert await db_session.scalar(select(func.count(BookingReceipt.id)))==0
    event=await db_session.scalar(select(VisitRequestEvent));assert event.actor_user_id==staff_user.id and event.after_status=='accepted'
    customer=await fulfillment.request_dto(db_session,row,setup_booking[3])
    assert customer['status']=='accepted' and customer['accepted_arrival_date']==response['request']['accepted_arrival_date']
    assert not any(key in customer for key in ['internal_review_note','customer','reviewed_at','can_review'])

@pytest.mark.asyncio
async def test_replay_precedes_version_check_changed_payload_conflicts_and_closed_request_stays_closed(db_session,setup_booking,staff_user):
    row=await request(db_session,setup_booking)
    body=VisitReviewBody(expected_version=1,internal_note='Review')
    await fulfillment.request_action(db_session,staff_user,row.id,'review',body,'review-replay-key')
    await fulfillment.request_action(db_session,staff_user,row.id,'review',body,'review-replay-key')
    assert row.version==2 and await db_session.scalar(select(func.count(VisitRequestEvent.id)))==1
    with pytest.raises(HTTPException) as error:await fulfillment.request_action(db_session,staff_user,row.id,'review',body.model_copy(update={'internal_note':'Changed'}),'review-replay-key')
    assert error.value.detail['code']=='idempotency_conflict'
    with pytest.raises(HTTPException) as error:await fulfillment.request_action(db_session,staff_user,row.id,'decline',body,'stale-decline-key')
    assert error.value.detail['code']=='visit_request_version_conflict'
    await fulfillment.request_action(db_session,staff_user,row.id,'decline',VisitReviewBody(expected_version=2),'decline-close-key')
    with pytest.raises(HTTPException):await fulfillment.request_action(db_session,staff_user,row.id,'review',VisitReviewBody(expected_version=3),'reopen-review-key')
    assert row.status=='declined'

@pytest.mark.asyncio
async def test_shop_calendar_boundary_and_explicit_accepted_amendment(db_session,setup_booking,staff_user,monkeypatch):
    row=await request(db_session,setup_booking)
    monkeypatch.setattr(booking,'now',lambda:datetime(2030,1,2,1,tzinfo=timezone.utc))  # still Jan1 at shop
    await fulfillment.request_action(db_session,staff_user,row.id,'accept',VisitAcceptBody(expected_version=1,arrival_date=date(2030,1,1)),'calendar-accept-key')
    assert row.accepted_arrival_date==date(2030,1,1)
    with pytest.raises(HTTPException):await fulfillment.request_action(db_session,staff_user,row.id,'accept',VisitAcceptBody(expected_version=2,arrival_date=date(2030,1,2)),'silent-date-key')
    await fulfillment.request_action(db_session,staff_user,row.id,'accept',VisitAcceptBody(expected_version=2,arrival_date=date(2030,1,2),internal_note='Customer requested another arrival date'),'amended-date-key')
    assert row.version==3 and row.accepted_arrival_date==date(2030,1,2)

@pytest.mark.asyncio
async def test_existing_inactive_service_remains_readable_but_not_acceptible(db_session,setup_booking,staff_user):
    row=await request(db_session,setup_booking)
    setup_booking[2].is_active=False;await db_session.commit()
    view=await fulfillment.request_dto(db_session,row,staff_user)
    assert view['service']['name']=='Synthetic Oil Change' and view['can_accept'] is False
    with pytest.raises(HTTPException):await fulfillment.request_action(db_session,staff_user,row.id,'accept',VisitAcceptBody(expected_version=1,arrival_date=booking.now().date()),'inactive-accept-key')
    await fulfillment.request_action(db_session,staff_user,row.id,'decline',VisitReviewBody(expected_version=1),'inactive-decline-key')
    assert row.status=='declined'

@pytest.mark.asyncio
@pytest.mark.parametrize('role',[UserRole.MECHANIC,UserRole.FLEET_MANAGER,UserRole.DRIVER,UserRole.SUPER_ADMIN,UserRole.CUSTOMER])
async def test_nonstaff_cannot_review(db_session,setup_booking,role):
    row=await request(db_session,setup_booking)
    actor=SimpleNamespace(id=uuid4(),role=role,tenant_id=row.tenant_id,customer_id=row.customer_id)
    with pytest.raises(HTTPException) as error:await fulfillment.request_action(db_session,actor,row.id,'review',VisitReviewBody(expected_version=1),'unauthorized-review-key')
    assert error.value.status_code==404 and row.version==1

@pytest.mark.asyncio
async def test_foreign_staff_customer_and_staff_withdrawal_rules(db_session,setup_booking,staff_user):
    row=await request(db_session,setup_booking)
    foreign=SimpleNamespace(id=staff_user.id,role=staff_user.role,tenant_id=uuid4(),customer_id=None)
    with pytest.raises(HTTPException) as error:await fulfillment.request_action(db_session,foreign,row.id,'review',VisitReviewBody(expected_version=1),'foreign-review-key')
    assert error.value.status_code==404
    with pytest.raises(HTTPException):await fulfillment.request_action(db_session,staff_user,row.id,'withdraw',VisitWithdrawBody(expected_version=1),'staff-withdraw-no-reason')
    await fulfillment.request_action(db_session,staff_user,row.id,'withdraw',VisitWithdrawBody(expected_version=1,reason='Requested by customer'),'staff-withdraw-reason')
    assert row.status=='withdrawn' and row.version==2

@pytest.mark.asyncio
async def test_vehicleless_fulfillment_requires_explicit_vehicle_and_does_not_change_ro_status(db_session,setup_booking,staff_user):
    row=await request(db_session,setup_booking)
    await fulfillment.request_action(db_session,staff_user,row.id,'accept',VisitAcceptBody(expected_version=1,arrival_date=booking.now().date()),'fulfill-accept-key')
    vehicle,order=await vehicle_order(db_session,setup_booking)
    body=VisitFulfillBody(expected_version=2,repair_order_id=order.id,reason='Physical arrival checked by staff')
    with pytest.raises(HTTPException):await fulfillment.request_action(db_session,staff_user,row.id,'fulfill',body,'unreviewed-truck-key')
    response=await fulfillment.request_action(db_session,staff_user,row.id,'fulfill',body.model_copy(update={'expected_vehicle_id':vehicle.id}),'fulfilled-exact-key')
    assert response['request']['status']=='fulfilled' and row.vehicle_id is None and row.fulfilled_repair_order_id==order.id
    assert order.status==RepairOrderStatus.DRAFT and await db_session.scalar(select(func.count(Appointment.id)))==0

@pytest.mark.asyncio
async def test_paid_appointment_link_is_exact_audited_and_does_not_mutate_receipt(db_session,setup_booking,staff_user,monkeypatch):
    apt=await paid(db_session,setup_booking,monkeypatch)
    vehicle,order=await vehicle_order(db_session,setup_booking)
    receipt=await db_session.scalar(select(BookingReceipt));before=(receipt.amount_received_minor,receipt.refunded_amount_minor,receipt.version)
    body=BookingRepairOrderLinkBody(expected_booking_version=apt.booking_version,repair_order_id=order.id,reason='Verified vehicle and payer',expected_vehicle_id=vehicle.id)
    response=await fulfillment.link_appointment(db_session,staff_user,apt.id,body,'exact-ro-link-key')
    assert response['repair_order_id']==str(order.id) and apt.vehicle_id is None and apt.repair_order_id==order.id
    assert before==(receipt.amount_received_minor,receipt.refunded_amount_minor,receipt.version)
    event=await db_session.scalar(select(BookingRepairOrderLink));assert event.reviewed_vehicle_id==vehicle.id and event.customer_id==apt.customer_id
    await fulfillment.link_appointment(db_session,staff_user,apt.id,body,'exact-ro-link-key')
    assert await db_session.scalar(select(func.count(BookingRepairOrderLink.id)))==1

@pytest.mark.asyncio
@pytest.mark.parametrize('invalid',['unpaid','cancelled_ro','imported_ro','issued_invoice','wrong_customer','wrong_vehicle'])
async def test_booking_link_rejects_unsafe_intake_targets(db_session,setup_booking,staff_user,monkeypatch,invalid):
    apt=await booking.reserve(db_session,setup_booking[3],setup_booking[4],f'hold-{uuid4()}') if invalid=='unpaid' else await paid(db_session,setup_booking,monkeypatch)
    vehicle,order=await vehicle_order(db_session,setup_booking)
    if invalid=='cancelled_ro':order.status=RepairOrderStatus.CANCELLED
    if invalid=='imported_ro':order.source='easy_truck_shop_import'
    if invalid=='wrong_customer':order.customer_id=uuid4()
    if invalid=='issued_invoice':db_session.add(Invoice(tenant_id=apt.tenant_id,repair_order_id=order.id,billed_customer_id=apt.customer_id,invoice_number=f'INV-{uuid4()}',status=InvoiceStatus.SENT,subtotal=120,total_amount=120,accounting_policy='standard'))
    await db_session.commit()
    expected=uuid4() if invalid=='wrong_vehicle' else vehicle.id
    with pytest.raises(HTTPException):await fulfillment.link_appointment(db_session,staff_user,apt.id,BookingRepairOrderLinkBody(expected_booking_version=apt.booking_version,repair_order_id=order.id,reason='Explicit intake review',expected_vehicle_id=expected),f'unsafe-link-{invalid}')
    assert apt.repair_order_id is None and await db_session.scalar(select(func.count(BookingRepairOrderLink.id)))==0

@pytest.mark.parametrize('value',[True,1.0,1.5,'1'])
def test_versions_are_strict_integers(value):
    with pytest.raises(ValidationError):VisitReviewBody(expected_version=value)
    with pytest.raises(ValidationError):BookingRepairOrderLinkBody(expected_booking_version=value,repair_order_id=uuid4(),reason='Review')
