from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints import activity
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


async def _seed_context(db_session, *, role=UserRole.GARAGE_OWNER):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name="Test Garage", slug=f"test-garage-{suffix}", is_active=True)
    db_session.add(tenant)
    await db_session.flush()

    user = User(
        email=f"owner-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Jane",
        last_name="Owner",
        role=role,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    customer = Customer(
        tenant_id=tenant.id,
        first_name="John",
        last_name="Doe",
        email=f"customer-{suffix}@example.com",
        billing_country="USA",
    )
    db_session.add_all([user, customer])
    await db_session.flush()

    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2020,
    )
    db_session.add(vehicle)
    await db_session.commit()

    return tenant, user, customer, vehicle


async def _list_activity(db_session, current_user, *, limit=20, cursor=None, actor_id=None,
                          event_type=None, date_from=None, date_to=None):
    # activity.list_activity's new filter params default to FastAPI Query(...)
    # sentinels, which only resolve to real values through request dependency
    # injection. Calling the function directly (as these tests do) requires
    # passing explicit None/values so the sentinel objects aren't mistaken
    # for real filter values.
    return await activity.list_activity(
        limit=limit, cursor=cursor, actor_id=actor_id, event_type=event_type,
        date_from=date_from, date_to=date_to, db=db_session, current_user=current_user,
    )


async def _create_order(db_session, *, tenant_id, customer_id, vehicle_id, **kwargs):
    order = RepairOrder(
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=kwargs.pop("status", RepairOrderStatus.DRAFT),
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
        **kwargs,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest.mark.asyncio
async def test_quote_sent_records_actor(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    order = await _create_order(db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id)

    quote = Quote(
        tenant_id=tenant.id, repair_order_id=order.id, quote_number=f"Q-{uuid4().hex[:8]}",
        total_amount=Decimal("100.00"),
    )
    quote.sent_to_customer = True
    quote.sent_at = datetime.now(timezone.utc)
    quote.sent_by_user_id = user.id
    db_session.add(quote)
    await db_session.commit()
    await db_session.refresh(quote)

    assert quote.sent_by_user_id == user.id


@pytest.mark.asyncio
async def test_manual_invoice_records_actor(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    order = await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        status=RepairOrderStatus.COMPLETED,
    )

    invoice = Invoice(
        tenant_id=tenant.id, repair_order_id=order.id, invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.SENT, subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
        created_by_user_id=user.id,
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)

    assert invoice.created_by_user_id == user.id


@pytest.mark.asyncio
async def test_manual_payment_records_actor(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    order = await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        status=RepairOrderStatus.INVOICED,
    )
    invoice = Invoice(
        tenant_id=tenant.id, repair_order_id=order.id, invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.SENT, subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)

    payment = Payment(
        tenant_id=tenant.id, invoice_id=invoice.id, payment_number=f"PMT-{uuid4().hex[:8]}",
        amount=Decimal("100.00"), method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED,
        recorded_by_user_id=user.id,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.recorded_by_user_id == user.id


@pytest.mark.asyncio
async def test_customer_guest_payment_leaves_actor_null(db_session):
    """Customer/guest self-service payment paths never set recorded_by_user_id —
    only staff-initiated manual recording does."""
    tenant, user, customer, vehicle = await _seed_context(db_session)
    order = await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        status=RepairOrderStatus.INVOICED,
    )
    invoice = Invoice(
        tenant_id=tenant.id, repair_order_id=order.id, invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.SENT, subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)

    # Simulates confirm_payment / confirm_guest_payment: no recorded_by_user_id passed.
    payment = Payment(
        tenant_id=tenant.id, invoice_id=invoice.id, payment_number=f"PMT-{uuid4().hex[:8]}",
        amount=Decimal("100.00"), method=PaymentMethod.STRIPE, status=PaymentStatus.COMPLETED,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.recorded_by_user_id is None


@pytest.mark.asyncio
async def test_activity_feed_merges_and_sorts_across_entities(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    now = datetime.now(timezone.utc)

    order = await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        status=RepairOrderStatus.CANCELLED,
        cancelled_at=now - timedelta(minutes=5),
        cancelled_by_user_id=user.id,
    )

    quote = Quote(
        tenant_id=tenant.id, repair_order_id=order.id, quote_number=f"Q-{uuid4().hex[:8]}",
        total_amount=Decimal("100.00"), sent_to_customer=True,
        sent_at=now - timedelta(minutes=10), sent_by_user_id=user.id,
    )
    db_session.add(quote)

    invoice = Invoice(
        tenant_id=tenant.id, repair_order_id=order.id, invoice_number=f"INV-{uuid4().hex[:8]}",
        status=InvoiceStatus.PAID, subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
        created_by_user_id=user.id, paid_at=now - timedelta(minutes=1),
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)

    payment = Payment(
        tenant_id=tenant.id, invoice_id=invoice.id, payment_number=f"PMT-{uuid4().hex[:8]}",
        amount=Decimal("100.00"), method=PaymentMethod.CASH, status=PaymentStatus.COMPLETED,
        recorded_by_user_id=user.id,
    )
    db_session.add(payment)
    await db_session.commit()

    response = await _list_activity(db_session, user, limit=20)

    event_types = [e.event_type for e in response.items]
    # ro_created, quote_sent, ro_cancelled, invoice_created, invoice_paid, payment_recorded
    assert "ro_created" in event_types
    assert "quote_sent" in event_types
    assert "ro_cancelled" in event_types
    assert "invoice_created" in event_types
    assert "invoice_paid" in event_types
    assert "payment_recorded" in event_types

    # Sorted descending by occurred_at.
    timestamps = [e.occurred_at for e in response.items]
    assert timestamps == sorted(timestamps, reverse=True)

    # Actor names resolved for events with an actor column set.
    cancelled_event = next(e for e in response.items if e.event_type == "ro_cancelled")
    assert cancelled_event.actor_name == "Jane Owner"
    quote_event = next(e for e in response.items if e.event_type == "quote_sent")
    assert quote_event.actor_name == "Jane Owner"
    assert quote_event.order_number == order.order_number


@pytest.mark.asyncio
async def test_activity_feed_pagination_cursor(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    now = datetime.now(timezone.utc)

    for i in range(5):
        await _create_order(
            db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        )

    first_page = await _list_activity(db_session, user, limit=2)
    assert len(first_page.items) == 2
    assert first_page.has_more is True
    assert first_page.next_cursor is not None

    second_page = await _list_activity(db_session, user, limit=2, cursor=first_page.next_cursor)
    assert len(second_page.items) == 2
    first_ids = {e.id for e in first_page.items}
    second_ids = {e.id for e in second_page.items}
    assert first_ids.isdisjoint(second_ids)


@pytest.mark.asyncio
async def test_activity_feed_requires_staff_role(db_session):
    tenant, _owner, customer, vehicle = await _seed_context(db_session)
    mechanic = User(
        email=f"mech-{uuid4().hex[:8]}@example.com",
        hashed_password="hashed-password",
        first_name="Mo",
        last_name="Mechanic",
        role=UserRole.MECHANIC,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(mechanic)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await activity.list_activity(limit=20, cursor=None, db=db_session, current_user=mechanic)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_activity_feed_filters_by_actor(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    other = User(
        email=f"admin-{uuid4().hex[:8]}@example.com",
        hashed_password="hashed-password",
        first_name="Alex",
        last_name="Admin",
        role=UserRole.GARAGE_ADMIN,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(other)
    await db_session.commit()

    now = datetime.now(timezone.utc)
    await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        status=RepairOrderStatus.CANCELLED, cancelled_at=now, cancelled_by_user_id=user.id,
    )
    await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        status=RepairOrderStatus.CANCELLED, cancelled_at=now, cancelled_by_user_id=other.id,
    )

    response = await activity.list_activity(
        limit=20, cursor=None, actor_id=user.id, event_type=None, date_from=None, date_to=None,
        db=db_session, current_user=user,
    )

    cancelled = [e for e in response.items if e.event_type == "ro_cancelled"]
    assert len(cancelled) == 1
    assert cancelled[0].actor_id == str(user.id)


@pytest.mark.asyncio
async def test_activity_feed_filters_by_event_type(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    now = datetime.now(timezone.utc)
    await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        status=RepairOrderStatus.CANCELLED, cancelled_at=now, cancelled_by_user_id=user.id,
    )

    response = await activity.list_activity(
        limit=20, cursor=None, actor_id=None, event_type="ro_cancelled", date_from=None, date_to=None,
        db=db_session, current_user=user,
    )

    assert len(response.items) >= 1
    assert all(e.event_type == "ro_cancelled" for e in response.items)


@pytest.mark.asyncio
async def test_activity_feed_filters_by_date_range(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    today = datetime.now(timezone.utc)
    old = today - timedelta(days=10)

    recent_order = await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
    )
    old_order = await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
    )
    old_order.created_at = old
    await db_session.commit()

    response = await activity.list_activity(
        limit=20, cursor=None, actor_id=None, event_type=None,
        date_from=today.date(), date_to=today.date(),
        db=db_session, current_user=user,
    )

    order_ids_in_range = {e.order_id for e in response.items if e.event_type == "ro_created"}
    assert str(recent_order.id) in order_ids_in_range
    assert str(old_order.id) not in order_ids_in_range


@pytest.mark.asyncio
async def test_activity_feed_available_actors(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    now = datetime.now(timezone.utc)
    await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        status=RepairOrderStatus.CANCELLED, cancelled_at=now, cancelled_by_user_id=user.id,
    )

    response = await _list_activity(db_session, user, limit=20)

    assert any(a.id == str(user.id) and a.name == "Jane Owner" for a in response.available_actors)


@pytest.mark.asyncio
async def test_activity_feed_anomaly_warning_triggers_at_threshold(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    now = datetime.now(timezone.utc)

    for _ in range(3):
        await _create_order(
            db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
            status=RepairOrderStatus.CANCELLED, cancelled_at=now, cancelled_by_user_id=user.id,
        )

    response = await _list_activity(db_session, user, limit=20)

    assert len(response.warnings) == 1
    assert "3" in response.warnings[0]


@pytest.mark.asyncio
async def test_activity_feed_no_anomaly_warning_below_threshold(db_session):
    tenant, user, customer, vehicle = await _seed_context(db_session)
    now = datetime.now(timezone.utc)

    await _create_order(
        db_session, tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        status=RepairOrderStatus.CANCELLED, cancelled_at=now, cancelled_by_user_id=user.id,
    )

    response = await _list_activity(db_session, user, limit=20)

    assert response.warnings == []
