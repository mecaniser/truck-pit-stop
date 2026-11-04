"""Versioned date-only requests and audited exact repair intake links."""
from datetime import date
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, text
from app.db.models.booking_fulfillment import VisitRequestEvent, BookingRepairOrderLink
from app.db.models.visit_request import VisitRequest
from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.service import Service
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.invoice import Invoice, InvoiceStatus
from app.services import booking_payments as booking
from app.services.financial_transaction_lock import lock_tenant_financials


def staff(actor):
    if not actor.tenant_id or actor.role not in booking.STAFF:
        raise HTTPException(404, 'Visit request not found')


def actor_name(actor):
    return ' '.join(filter(None, [getattr(actor, 'first_name', None), getattr(actor, 'last_name', None)])).strip() or getattr(actor, 'email', None) or str(actor.id)


async def request_dto(db, row, actor):
    service = await db.scalar(select(Service).where(Service.id == row.service_id, Service.tenant_id == row.tenant_id))
    vehicle = await db.scalar(select(Vehicle).where(Vehicle.id == row.vehicle_id, Vehicle.tenant_id == row.tenant_id)) if row.vehicle_id else None
    result = {
        'id': str(row.id), 'booking_kind': 'request', 'request_reference': row.request_reference,
        'status': row.status, 'version': row.version, 'preferred_date': row.preferred_date,
        'accepted_arrival_date': row.accepted_arrival_date, 'customer_notes': row.customer_notes,
        'service_id': str(row.service_id), 'service_name': service.name if service else None,
        'service': {'id': str(service.id), 'name': service.name} if service else None,
        'vehicle_id': str(row.vehicle_id) if row.vehicle_id else None,
        'vehicle': {key: getattr(vehicle, key) for key in ('unit_number', 'year', 'make', 'model', 'license_plate')} | {'id': str(vehicle.id)} if vehicle else None,
        'created_at': row.created_at,
    }
    if actor.role in booking.STAFF:
        customer = await db.scalar(select(Customer).where(Customer.id == row.customer_id, Customer.tenant_id == row.tenant_id))
        result.update({
            'customer': {'id': str(customer.id), 'display_name': ' '.join(filter(None, [customer.first_name, customer.last_name])), 'company_name': customer.company_name, 'email': customer.email, 'phone': customer.phone} if customer else None,
            'internal_review_note': row.internal_review_note, 'reviewed_at': row.reviewed_at,
            'can_review': row.status == 'requested',
            'can_accept': row.status in {'requested','availability_review','accepted'} and bool(service and service.is_active and service.deleted_at is None and customer and customer.deleted_at is None and (not service.requires_vehicle or (vehicle and vehicle.deleted_at is None))),
            'can_decline': row.status in {'requested','availability_review'},
            'can_withdraw': row.status in {'requested','availability_review','accepted'},
            'can_fulfill': row.status == 'accepted',
        })
    if row.fulfilled_repair_order_id:
        order=await db.scalar(select(RepairOrder).where(RepairOrder.id==row.fulfilled_repair_order_id,RepairOrder.tenant_id==row.tenant_id,RepairOrder.customer_id==row.customer_id,RepairOrder.deleted_at.is_(None)))
        if order:result['fulfilled_repair_order_id']=str(order.id)
    return result


async def request_lock(db,tenant_id,request_key):
    if db.get_bind().dialect.name=='postgresql':
        number=int(booking.digest({'visit_request_key':request_key,'tenant':tenant_id})[:15],16)
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':number})


async def request_action(db, actor, identity, action, body, request_key):
    request_key = booking.key(request_key)
    if action == 'withdraw' and actor.role == UserRole.CUSTOMER:
        if not actor.tenant_id or not actor.customer_id:raise HTTPException(404,'Visit request not found')
    else:staff(actor)
    fingerprint = booking.digest({'request_id': identity, 'action': action, **body.model_dump()})
    if action=='fulfill':await lock_tenant_financials(db,actor.tenant_id)
    await request_lock(db, actor.tenant_id, request_key)
    filters = [VisitRequest.id == identity, VisitRequest.tenant_id == actor.tenant_id, VisitRequest.deleted_at.is_(None)]
    if actor.role == UserRole.CUSTOMER:
        filters.append(VisitRequest.customer_id == actor.customer_id)
    row = await db.scalar(select(VisitRequest).where(*filters).with_for_update().execution_options(populate_existing=True))
    if not row:
        raise HTTPException(404, 'Visit request not found')
    replay = await db.scalar(select(VisitRequestEvent).where(VisitRequestEvent.tenant_id == actor.tenant_id, VisitRequestEvent.idempotency_key == request_key))
    if replay:
        if replay.request_id != identity or replay.request_sha256 != fingerprint:
            booking.fail('idempotency_conflict', 'This key belongs to a different visit action.')
        return await request_dto(db, row, actor)
    if body.expected_version != row.version:
        booking.fail('visit_request_version_conflict', 'This request changed. Refresh before reviewing it.')
    before = row.status
    internal_note = getattr(body, 'internal_note', None)
    arrival = getattr(body, 'arrival_date', None)
    if action == 'review':
        if before != 'requested': booking.fail('visit_request_action_unavailable', 'This request cannot be moved to review.')
        after = 'availability_review'
    elif action == 'accept':
        if before not in {'requested', 'availability_review', 'accepted'}: booking.fail('visit_request_action_unavailable', 'This request cannot be accepted.')
        service=await db.scalar(select(Service).where(Service.id==row.service_id,Service.tenant_id==row.tenant_id,Service.is_active.is_(True),Service.deleted_at.is_(None)))
        customer=await db.scalar(select(Customer.id).where(Customer.id==row.customer_id,Customer.tenant_id==row.tenant_id,Customer.deleted_at.is_(None)))
        if not service or not customer:booking.fail('visit_request_acceptance_unavailable','This request needs shop review before an arrival date can be accepted.')
        if row.vehicle_id:
            active_vehicle=await db.scalar(select(Vehicle.id).where(Vehicle.id==row.vehicle_id,Vehicle.tenant_id==row.tenant_id,Vehicle.deleted_at.is_(None)))
            if not active_vehicle:booking.fail('visit_request_acceptance_unavailable','This vehicle needs shop review before an arrival date can be accepted.')
        elif service.requires_vehicle:booking.fail('visit_request_acceptance_unavailable','This request requires a registered vehicle before acceptance.')
        tenant = await db.get(Tenant, row.tenant_id)
        try: today = booking.now().astimezone(ZoneInfo(tenant.timezone)).date()
        except Exception: booking.fail('visit_request_timezone_unavailable', 'The shop date is unavailable.')
        if not isinstance(arrival, date) or arrival < today:
            booking.fail('visit_request_arrival_date_invalid', 'Choose today or a future arrival date at the shop.', 422)
        if before == 'accepted' and (arrival == row.accepted_arrival_date or not internal_note or len(internal_note.strip()) < 3):
            booking.fail('visit_request_amendment_reason_required', 'Changing an accepted arrival date requires a new date and a review reason.', 422)
        after = 'accepted'
    elif action == 'decline':
        if before not in {'requested', 'availability_review'}: booking.fail('visit_request_action_unavailable', 'This request cannot be declined.')
        after = 'declined'
    elif action == 'withdraw':
        if actor.role in booking.STAFF and (not getattr(body,'reason',None) or len(body.reason.strip())<3):booking.fail('visit_request_reason_required','Enter a withdrawal review reason.',422)
        if before not in {'requested', 'availability_review', 'accepted'}: booking.fail('visit_request_action_unavailable', 'This request cannot be withdrawn.')
        after = 'withdrawn'
    elif action=='fulfill':
        if before!='accepted':booking.fail('visit_request_action_unavailable','Only an accepted visit can be checked in.')
        order,vehicle=await exact_order(db,actor,row.customer_id,row.vehicle_id,body.repair_order_id,getattr(body,'expected_vehicle_id',None))
        if not body.reason or len(body.reason.strip())<3:booking.fail('visit_request_reason_required','Enter an intake review reason.',422)
        after='fulfilled'
        internal_note=body.reason.strip()
    else:
        booking.fail('visit_request_action_unavailable', 'This action is unavailable.')
    # Append audit before the row update so the DB can require matching evidence.
    event=VisitRequestEvent(id=uuid4(),tenant_id=row.tenant_id,request_id=row.id,request_version=row.version+1,
        actor_user_id=actor.id,actor_name_snapshot=actor_name(actor),event_type='accept_amended' if action=='accept' and before=='accepted' else action,
        before_status=before,after_status=after,arrival_date=arrival if action=='accept' else row.accepted_arrival_date,
        internal_note=internal_note or getattr(body,'reason',None),occurred_at=booking.now(),idempotency_key=request_key,request_sha256=fingerprint,
        repair_order_id=order.id if action=='fulfill' else None,reviewed_vehicle_id=vehicle.id if action=='fulfill' else None)
    db.add(event)
    await db.flush()
    row.status=after
    row.version+=1
    if action=='accept':row.accepted_arrival_date=arrival
    if action=='fulfill':row.fulfilled_repair_order_id=order.id
    if actor.role in booking.STAFF:
        row.reviewed_by_user_id=actor.id
        row.reviewed_at=booking.now()
        row.internal_review_note=internal_note or getattr(body,'reason',None)
    await db.commit()
    return {'request':await request_dto(db,row,actor)}


async def exact_order(db,actor,customer_id,vehicle_id,order_id,expected_vehicle_id):
    order=await db.scalar(select(RepairOrder).where(RepairOrder.id==order_id,RepairOrder.tenant_id==actor.tenant_id).with_for_update().execution_options(populate_existing=True))
    if not order or order.deleted_at is not None:raise HTTPException(404,'Repair order not found')
    if order.customer_id!=customer_id:booking.fail('booking_payer_mismatch','The repair order must have the same customer as the visit.')
    if order.status in {RepairOrderStatus.CANCELLED,RepairOrderStatus.INVOICED,RepairOrderStatus.PAID} or order.is_internal or order.source not in (None,'','native'):booking.fail('booking_link_unavailable','Only an active native customer repair order can be linked.')
    invoices=(await db.scalars(select(Invoice).where(Invoice.tenant_id==actor.tenant_id,Invoice.repair_order_id==order.id).order_by(Invoice.id).with_for_update().execution_options(populate_existing=True))).all()
    if any(invoice.status!=InvoiceStatus.DRAFT or invoice.source or invoice.accounting_policy in {'historical_export_hold','source_collection_hold'} or (invoice.billed_customer_id and invoice.billed_customer_id!=customer_id) for invoice in invoices):booking.fail('booking_invoice_already_issued','Review the existing invoice before linking intake.')
    if vehicle_id is not None and order.vehicle_id!=vehicle_id:booking.fail('booking_vehicle_mismatch','Intake must use the exact visit vehicle.')
    if vehicle_id is None and (not expected_vehicle_id or expected_vehicle_id!=order.vehicle_id):booking.fail('booking_vehicle_review_required','Explicitly choose and review the exact intake vehicle.',422)
    if expected_vehicle_id and expected_vehicle_id!=order.vehicle_id:booking.fail('booking_vehicle_mismatch','The reviewed vehicle does not match intake.')
    vehicle=await db.scalar(select(Vehicle).where(Vehicle.id==order.vehicle_id,Vehicle.tenant_id==actor.tenant_id,Vehicle.deleted_at.is_(None)))
    if not vehicle:raise HTTPException(404,'Vehicle not found')
    if vehicle.customer_id!=customer_id:
        from app.db.models.vehicle_relationship import VehicleCustomerRelationship
        connection=await db.scalar(select(VehicleCustomerRelationship.id).where(VehicleCustomerRelationship.tenant_id==actor.tenant_id,VehicleCustomerRelationship.vehicle_id==vehicle.id,VehicleCustomerRelationship.customer_id==customer_id,VehicleCustomerRelationship.effective_to.is_(None),VehicleCustomerRelationship.deleted_at.is_(None)).limit(1))
        if not connection:booking.fail('booking_vehicle_customer_mismatch','This intake vehicle is not connected to the visit customer.')
    return order,vehicle


async def link_envelope(db,apt):
    from app.services.booking_receipt_application import prepayment_view
    return await prepayment_view(db,apt)


async def link_appointment(db, actor, identity, body, request_key):
    staff(actor)
    request_key = booking.key(request_key)
    fingerprint = booking.digest({'appointment_id': identity, **body.model_dump()})
    await lock_tenant_financials(db, actor.tenant_id)
    apt = await booking.admitted_appointment(db, actor, identity, write=True)
    replay = await db.scalar(select(BookingRepairOrderLink).where(BookingRepairOrderLink.tenant_id == actor.tenant_id, BookingRepairOrderLink.idempotency_key == request_key))
    if replay:
        if replay.appointment_id != apt.id or replay.request_sha256 != fingerprint: booking.fail('idempotency_conflict', 'This key belongs to another intake link.')
        return await link_envelope(db, apt)
    if apt.booking_version != body.expected_booking_version: booking.fail('booking_snapshot_changed', 'This reservation changed. Refresh before linking intake.')
    if apt.booking_payment_version != 1 or apt.status.value not in {'confirmed','in_progress','completed'} or apt.booking_payment_state!='paid': booking.fail('booking_link_unavailable', 'This reservation cannot be linked to intake.')
    receipt=await db.scalar(select(booking.BookingReceipt).where(booking.BookingReceipt.id==apt.confirmed_receipt_id,booking.BookingReceipt.tenant_id==apt.tenant_id,booking.BookingReceipt.appointment_id==apt.id).with_for_update().execution_options(populate_existing=True))
    attempt=await db.scalar(select(booking.BookingPaymentAttempt).where(booking.BookingPaymentAttempt.id==receipt.attempt_id,booking.BookingPaymentAttempt.tenant_id==apt.tenant_id,booking.BookingPaymentAttempt.appointment_id==apt.id).execution_options(populate_existing=True)) if receipt else None
    if attempt:booking.validate_attempt_binding(apt,attempt)
    live=await db.scalar(select(booking.BookingPaymentAttempt.id).where(booking.BookingPaymentAttempt.tenant_id==apt.tenant_id,booking.BookingPaymentAttempt.appointment_id==apt.id,booking.BookingPaymentAttempt.state.in_(booking.LIVE)))
    if not receipt or not attempt or live or attempt.state!='succeeded' or not attempt.verified_at or receipt.provider!=attempt.provider or receipt.provider_account_id!=attempt.provider_account_id or receipt.provider_intent_id!=attempt.provider_intent_id or receipt.charge_id!=attempt.provider_charge_id or receipt.currency!='usd' or receipt.amount_received_minor!=attempt.amount_minor or not receipt.proof_sha256 or receipt.verification_basis not in {'server_retrieval','verified_connect_webhook'} or receipt.amount_received_minor-receipt.refunded_amount_minor!=int(apt.price*100):booking.fail('booking_link_unavailable','A verified fully paid reservation is required for this handoff.')
    from app.services.booking_application_accounting import receipt_balances
    from app.services.booking_refund_verification import unresolved_refund_verification
    if await unresolved_refund_verification(db,apt.tenant_id,apt.id):booking.fail('booking_refund_verification_pending','Review existing refund verification before linking intake.')
    balances=await receipt_balances(db,apt.tenant_id,receipt.id)
    if balances['unapplied_minor']!=int(apt.price*100):booking.fail('booking_link_unavailable','This receipt already has an application requiring review.')
    if apt.repair_order_id is not None: booking.fail('booking_link_conflict', 'This reservation already has an intake link.')
    order,vehicle=await exact_order(db,actor,apt.customer_id,apt.vehicle_id,body.repair_order_id,body.expected_vehicle_id)
    if not body.reason or len(body.reason.strip()) < 3: booking.fail('booking_link_reason_required', 'Enter an intake review reason.', 422)
    conflict = await db.scalar(select(BookingRepairOrderLink.id).where(BookingRepairOrderLink.tenant_id == apt.tenant_id, BookingRepairOrderLink.repair_order_id == order.id))
    if conflict: booking.fail('booking_link_conflict', 'This intake already belongs to another reservation.')
    event = BookingRepairOrderLink(id=uuid4(), tenant_id=apt.tenant_id, appointment_id=apt.id, repair_order_id=order.id,
        customer_id=apt.customer_id, reviewed_vehicle_id=order.vehicle_id, actor_user_id=actor.id, actor_name_snapshot=actor_name(actor), reason=body.reason.strip(),
        old_repair_order_id=apt.repair_order_id, occurred_at=booking.now(), idempotency_key=request_key, request_sha256=fingerprint,
        snapshot_sha256=booking.digest({'appointment_id': apt.id, 'price_snapshot': apt.price_snapshot_sha256, 'customer_id': apt.customer_id, 'vehicle_id': order.vehicle_id, 'repair_order_id': order.id}))
    db.add(event)
    await db.flush()
    apt.repair_order_id = order.id
    apt.booking_version += 1
    await db.commit()
    return await link_envelope(db, apt)
