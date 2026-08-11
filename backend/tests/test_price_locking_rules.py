from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import os

from fastapi import Response, HTTPException
import pytest
from sqlalchemy import select
from starlette.requests import Request

# Twilio client is initialized at import time in app.services.twilio_service.
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import quotes as quotes_endpoint
from app.api.v1.endpoints import repair_orders as repair_orders_endpoint
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.quote import Quote
from app.db.models.notification import Notification, NotificationStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.service import Service
from app.db.models.labor import Labor, LaborLineType
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import DiscountUpdate
from app.services.price_build_service import PriceBuildLockedError, PriceBuildService


def _fake_request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/quotes/portal/create",
        "headers": [],
        "client": ("testclient", 50000),
    })


async def _seed_quote_context(db_session):
    tenant = Tenant(
        id=uuid4(),
        name="Lock Test Garage",
        slug=f"lock-test-{uuid4().hex[:8]}",
        phone="7045550199",
        email="service@locktest.example",
        labor_rate=Decimal("100.00"),
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Taylor",
        last_name="Fleet",
        email=f"taylor-{uuid4().hex[:8]}@example.com",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Kenworth",
        model="T680",
        year=2022,
        vin="1XKAD49X35J654321",
    )
    staff_user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"staff-{uuid4().hex[:8]}@example.com",
        hashed_password="hashed-password",
        first_name="Shop",
        last_name="Admin",
        role=UserRole.GARAGE_ADMIN,
        is_active=True,
        is_verified=True,
    )
    order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.QUOTED,
        description="Brake repair",
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    service = Service(
        id=uuid4(),
        tenant_id=tenant.id,
        name="Brake Inspection",
        duration_minutes=60,
        base_price=Decimal("120.00"),
        is_active=True,
        requires_vehicle=True,
    )
    quote = Quote(
        id=uuid4(),
        tenant_id=tenant.id,
        repair_order_id=order.id,
        quote_number=f"Q-{uuid4().hex[:8]}",
        total_amount=Decimal("120.00"),
        notes=None,
        expires_at=None,
        is_approved=False,
        is_declined=False,
        sent_to_customer=False,
        sent_at=None,
    )
    db_session.add_all([tenant, customer, vehicle, staff_user, order, service, quote])
    await db_session.commit()
    return staff_user, order, service, quote


@pytest.mark.asyncio
async def test_locked_order_rejects_price_build_edits(db_session):
    _, order, service, _ = await _seed_quote_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.lock_order_pricing(db_session, loaded.id, reason="approved")
    locked = await svc.load_order(db_session, order.id)

    with pytest.raises(PriceBuildLockedError):
        await svc.add_flat_service_line(db_session, locked, service.id, quantity=1)


@pytest.mark.asyncio
async def test_quote_sent_lock_allows_quoted_revisions(db_session):
    staff_user, order, service, _ = await _seed_quote_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.lock_order_pricing(db_session, loaded.id, reason="quote_sent")
    locked = await svc.load_order(db_session, order.id)

    summary_before = await repair_orders_endpoint.get_price_build_summary(
        order_id=order.id,
        db=db_session,
        current_user=staff_user,
    )

    result = await svc.add_flat_service_line(db_session, locked, service.id, quantity=1)

    assert summary_before.pricing_locked is False
    assert summary_before.pricing_lock_reason == "quote_sent"
    assert result.order.total_labor_cost == Decimal("100.00")


@pytest.mark.asyncio
async def test_quote_sent_lock_allows_discount_revisions(db_session):
    staff_user, order, service, _ = await _seed_quote_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)
    await svc.lock_order_pricing(db_session, loaded.id, reason="quote_sent")

    summary = await repair_orders_endpoint.update_repair_order_discounts(
        order_id=order.id,
        body=DiscountUpdate(labor_discount_amount=Decimal("25.00")),
        db=db_session,
        current_user=staff_user,
    )

    assert summary.pricing_locked is False
    assert summary.labor_discount_amount == Decimal("25.00")
    assert summary.total_cost == Decimal("75.00")


@pytest.mark.asyncio
async def test_quote_send_does_not_lock_live_order_pricing(db_session, monkeypatch):
    staff_user, order, service, quote = await _seed_quote_context(db_session)

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)
    await quotes_endpoint.update_quote(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    async def _noop_email(**_kwargs):
        return None

    async def _noop_sms(*_args, **_kwargs):
        return None

    async def _noop_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(quotes_endpoint, "send_email", _noop_email)
    monkeypatch.setattr(quotes_endpoint, "send_sms", _noop_sms)
    monkeypatch.setattr(quotes_endpoint, "broadcast_quote_event", _noop_broadcast)
    monkeypatch.setattr(quotes_endpoint, "broadcast_repair_order_update", _noop_broadcast)

    response = await quotes_endpoint.send_quote_to_customer(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    assert response.sent_to_customer is True
    assert response.sent_at is not None
    sent_quote = (await db_session.execute(select(Quote).where(Quote.id == quote.id))).scalar_one()
    assert sent_quote.line_items_snapshot["repair_total"] == "100.00"
    assert sent_quote.line_items_snapshot["labor_total"] == "100.00"

    order_id = order.id
    db_session.expire_all()
    refreshed_order = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order_id))).scalar_one()
    assert refreshed_order.pricing_locked_at is None
    assert refreshed_order.pricing_lock_reason is None


@pytest.mark.asyncio
async def test_approved_estimate_creates_incremental_authorization_revision(db_session):
    staff_user, order, _service, quote = await _seed_quote_context(db_session)
    quote.is_approved = True
    quote.sent_to_customer = True
    quote.revision = 1
    quote.authorization_type = "initial_estimate"
    quote.previously_authorized_amount = Decimal("0.00")
    quote.delta_amount = Decimal("120.00")
    order.total_labor_cost = Decimal("170.00")
    order.total_cost = Decimal("170.00")
    await db_session.commit()

    created = await quotes_endpoint.create_quote(
        body=quotes_endpoint.QuoteCreate(repair_order_id=order.id),
        db=db_session,
        current_user=staff_user,
    )

    assert created.revision == 2
    assert created.authorization_type == "additional_work"
    assert created.previously_authorized_amount == Decimal("120.00")
    assert created.delta_amount == Decimal("50.00")
    assert created.total_amount == Decimal("170.00")

    original = (await db_session.execute(select(Quote).where(Quote.id == quote.id))).scalar_one()
    assert original.is_approved is True


@pytest.mark.asyncio
async def test_quote_send_rejects_stale_draft_without_rewriting(db_session):
    staff_user, _order, _service, quote = await _seed_quote_context(db_session)
    # Order needs a work line so the send passes the empty-order guard.
    db_session.add(Labor(
        id=uuid4(),
        tenant_id=_order.tenant_id,
        repair_order_id=_order.id,
        description="Brake Inspection",
        hours=Decimal("1.00"),
        hourly_rate=Decimal("120.00"),
        total_cost=Decimal("120.00"),
        line_type=LaborLineType.MANUAL,
    ))
    await db_session.commit()
    quote_id = quote.id
    with pytest.raises(HTTPException) as exc_info:
        await quotes_endpoint.send_quote_to_customer(
            quote_id=quote_id,
            db=db_session,
            current_user=staff_user,
        )

    assert exc_info.value.status_code == 409
    await db_session.rollback()
    persisted = await db_session.get(Quote, quote_id)
    assert persisted.sent_to_customer is False
    assert persisted.approval_token is None
    assert persisted.total_amount == Decimal("120.00")


@pytest.mark.asyncio
async def test_quote_send_rejected_when_order_is_empty(db_session):
    """An order with no work lines and no parts cannot have its quote sent.
    The seed order has no labor lines or parts, so it is already empty."""
    staff_user, _order, _service, quote = await _seed_quote_context(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await quotes_endpoint.send_quote_to_customer(
            quote_id=quote.id,
            db=db_session,
            current_user=staff_user,
        )
    assert exc_info.value.status_code == 400
    assert "before sending this quote" in exc_info.value.detail


@pytest.mark.asyncio
async def test_quote_send_uses_discounted_order_total(db_session, monkeypatch):
    staff_user, order, service, quote = await _seed_quote_context(db_session)

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)
    refreshed_order = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    refreshed_order.labor_discount_amount = Decimal("20.00")
    await db_session.commit()
    await quotes_endpoint.update_quote(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    async def _noop_email(**_kwargs):
        return None

    async def _noop_sms(*_args, **_kwargs):
        return None

    async def _noop_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(quotes_endpoint, "send_email", _noop_email)
    monkeypatch.setattr(quotes_endpoint, "send_sms", _noop_sms)
    monkeypatch.setattr(quotes_endpoint, "broadcast_quote_event", _noop_broadcast)
    monkeypatch.setattr(quotes_endpoint, "broadcast_repair_order_update", _noop_broadcast)

    response = await quotes_endpoint.send_quote_to_customer(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    assert response.total_amount == Decimal("80.00")


@pytest.mark.asyncio
async def test_quote_send_email_uses_tenant_branding(db_session, monkeypatch):
    staff_user, order, service, quote = await _seed_quote_context(db_session)

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)
    await quotes_endpoint.update_quote(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    sent_email = {}

    async def _capture_email(**kwargs):
        sent_email.update(kwargs)
        return None

    async def _noop_sms(*_args, **_kwargs):
        return None

    async def _noop_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(quotes_endpoint, "send_email", _capture_email)
    monkeypatch.setattr(quotes_endpoint, "send_sms", _noop_sms)
    monkeypatch.setattr(quotes_endpoint, "broadcast_quote_event", _noop_broadcast)
    monkeypatch.setattr(quotes_endpoint, "broadcast_repair_order_update", _noop_broadcast)

    await quotes_endpoint.send_quote_to_customer(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    assert sent_email["sender_name"] == "Lock Test Garage"
    assert sent_email["subject"].endswith(" - Lock Test Garage")
    assert "Lock Test Garage" in sent_email["body"]
    assert "(704) 555-0199" in sent_email["body"]
    assert "service@locktest.example" in sent_email["body"]
    assert "DieselBridge Network" not in sent_email["subject"]
    assert "DieselBridge Network" not in sent_email["body"]


@pytest.mark.asyncio
async def test_quote_send_queues_email_without_calling_resend(db_session, monkeypatch):
    staff_user, order, service, quote = await _seed_quote_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)
    await quotes_endpoint.update_quote(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    async def _must_not_send_email(**_kwargs):
        raise AssertionError("Resend must not be called from the quote request")

    async def _noop_sms(*_args, **_kwargs):
        return None

    async def _noop_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(quotes_endpoint.settings, "PROVIDER_OUTBOX_ENABLED", True)
    monkeypatch.setattr(quotes_endpoint, "send_email", _must_not_send_email)
    monkeypatch.setattr(quotes_endpoint, "send_sms", _noop_sms)
    monkeypatch.setattr(quotes_endpoint, "broadcast_quote_event", _noop_broadcast)
    monkeypatch.setattr(quotes_endpoint, "broadcast_repair_order_update", _noop_broadcast)

    response = await quotes_endpoint.send_quote_to_customer(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    event = (
        await db_session.execute(
            select(ProviderOutboxEvent).where(ProviderOutboxEvent.aggregate_id == quote.id)
        )
    ).scalar_one()
    notification = await db_session.get(Notification, event.payload["notification_id"])

    assert response.sent_to_customer is True
    assert event.status == ProviderOutboxStatus.PENDING.value
    assert event.idempotency_key == f"quote-email:{quote.id}:revision:{quote.revision}"
    assert quote.approval_token not in event.idempotency_key
    assert notification.status == NotificationStatus.PENDING
    assert notification.recipient_email == order.customer.email
    assert notification.subject.endswith(" - Lock Test Garage")


@pytest.mark.asyncio
async def test_quote_decline_sms_uses_tenant_shop_name(db_session, monkeypatch):
    staff_user, _order, _service, quote = await _seed_quote_context(db_session)
    staff_user.phone = "5558675309"
    quote.sent_to_customer = True
    quote.sent_at = datetime.now(timezone.utc)
    quote.approval_token = f"decline-{uuid4().hex}"
    await db_session.commit()
    sent_sms = []

    async def _capture_sms(*_args, **kwargs):
        sent_sms.append(kwargs.get("body") or _args[3])

    async def _noop_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(quotes_endpoint, "send_sms", _capture_sms)
    monkeypatch.setattr(quotes_endpoint, "broadcast_quote_event", _noop_broadcast)
    monkeypatch.setattr(quotes_endpoint, "broadcast_repair_order_update", _noop_broadcast)

    await quotes_endpoint.decline_quote_by_token(
        request=_fake_request(),
        token=quote.approval_token,
        body=quotes_endpoint.DeclineQuoteRequest(notes="Need approval"),
        db=db_session,
    )

    assert sent_sms
    assert sent_sms[0].endswith(" - Lock Test Garage")
    assert "DieselBridge Network" not in sent_sms[0]


@pytest.mark.asyncio
async def test_quote_send_email_includes_customer_savings(db_session, monkeypatch):
    staff_user, order, service, quote = await _seed_quote_context(db_session)

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    await svc.add_flat_service_line(db_session, loaded, service.id, quantity=1)

    inventory = Inventory(
        id=uuid4(),
        tenant_id=order.tenant_id,
        sku="DISC-PART-001",
        name="Discounted Brake Rotor",
        stock_quantity=4,
        on_order_quantity=0,
        reorder_level=0,
        cost=Decimal("60.00"),
        selling_price=Decimal("100.00"),
    )
    part = PartsUsage(
        id=uuid4(),
        tenant_id=order.tenant_id,
        repair_order_id=order.id,
        inventory_id=inventory.id,
        quantity=Decimal("2.00"),
        unit_cost=Decimal("60.00"),
        unit_price=Decimal("80.00"),
        list_price=Decimal("100.00"),
        total_price=Decimal("160.00"),
    )
    refreshed_order = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == order.id))).scalar_one()
    refreshed_order.labor_discount_amount = Decimal("20.00")
    refreshed_order.order_discount_amount = Decimal("10.00")
    db_session.add_all([inventory, part])
    await db_session.commit()
    await quotes_endpoint.update_quote(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    sent_email = {}

    async def _capture_email(**kwargs):
        sent_email.update(kwargs)
        return None

    async def _noop_sms(*_args, **_kwargs):
        return None

    async def _noop_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(quotes_endpoint, "send_email", _capture_email)
    monkeypatch.setattr(quotes_endpoint, "send_sms", _noop_sms)
    monkeypatch.setattr(quotes_endpoint, "broadcast_quote_event", _noop_broadcast)
    monkeypatch.setattr(quotes_endpoint, "broadcast_repair_order_update", _noop_broadcast)

    await quotes_endpoint.send_quote_to_customer(
        quote_id=quote.id,
        db=db_session,
        current_user=staff_user,
    )

    body = sent_email["body"]
    assert "Customer savings" in body
    assert "Discounted Brake Rotor" in body
    assert "-$40.00" in body
    assert "Labor discount" in body
    assert "-$20.00" in body
    assert "Order discount" in body
    assert "-$10.00" in body
    assert "Total customer savings" in body
    assert "$70.00" in body


@pytest.mark.asyncio
async def test_approved_quote_can_create_customer_portal_account(db_session, monkeypatch):
    _, order, _, quote = await _seed_quote_context(db_session)
    quote.is_approved = True
    quote.approval_token = "approved-token"
    order.status = RepairOrderStatus.APPROVED
    await db_session.commit()

    enrollment_token = "quote-portal-enrollment-token"
    payload = {
        "quote_id": str(quote.id),
        "repair_order_id": str(order.id),
        "customer_id": str(order.customer_id),
        "tenant_id": str(order.tenant_id),
        "email": "taylor@example.com",
        "purpose": "quote_portal_enrollment",
    }

    async def _get_payload(token: str):
        assert token == enrollment_token
        return payload

    async def _is_consumed(_token: str):
        return False

    async def _consume(token: str):
        assert token == enrollment_token
        return payload

    async def _get_token_version(_user_id: str):
        return 0

    monkeypatch.setattr(quotes_endpoint, "get_quote_portal_enrollment_payload", _get_payload)
    monkeypatch.setattr(quotes_endpoint, "is_quote_portal_enrollment_token_consumed", _is_consumed)
    monkeypatch.setattr(quotes_endpoint, "consume_quote_portal_enrollment_token", _consume)
    monkeypatch.setattr(quotes_endpoint, "get_token_version", _get_token_version)

    response = Response()
    result = await quotes_endpoint.create_portal_from_quote_link(
        request=_fake_request(),
        response=response,
        body=quotes_endpoint.QuotePortalCreateRequest(
            token=enrollment_token,
            new_password="StrongPass1!",
        ),
        db=db_session,
    )

    assert result.redirect_to == "/portal"
    assert result.user_exists is False
    assert result.access_token
    assert "access_token=" in response.headers["set-cookie"]

    user = (await db_session.execute(select(User).where(User.customer_id == order.customer_id))).scalar_one()
    assert user.role == UserRole.CUSTOMER
    assert user.email.startswith("taylor-")


@pytest.mark.asyncio
async def test_approved_quote_existing_portal_user_with_link_can_open_portal(db_session, monkeypatch):
    _, order, _, quote = await _seed_quote_context(db_session)
    quote.is_approved = True
    order.status = RepairOrderStatus.APPROVED
    customer = (await db_session.execute(select(Customer).where(Customer.id == order.customer_id))).scalar_one()
    user = User(
        id=uuid4(),
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        email=customer.email,
        hashed_password="hashed-password",
        first_name=customer.first_name,
        last_name=customer.last_name,
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserCustomerLink(user_id=user.id, customer_id=customer.id, tenant_id=customer.tenant_id))
    await db_session.commit()

    enrollment_token = "existing-user-quote-portal-token"
    payload = {
        "quote_id": str(quote.id),
        "repair_order_id": str(order.id),
        "customer_id": str(order.customer_id),
        "tenant_id": str(order.tenant_id),
        "email": customer.email,
        "purpose": "quote_portal_enrollment",
    }

    async def _get_payload(token: str):
        assert token == enrollment_token
        return payload

    async def _is_consumed(_token: str):
        return False

    async def _get_token_version(_user_id: str):
        return 0

    monkeypatch.setattr(quotes_endpoint, "get_quote_portal_enrollment_payload", _get_payload)
    monkeypatch.setattr(quotes_endpoint, "is_quote_portal_enrollment_token_consumed", _is_consumed)
    monkeypatch.setattr(quotes_endpoint, "get_token_version", _get_token_version)

    response = Response()
    result = await quotes_endpoint.create_portal_from_quote_link(
        request=_fake_request(),
        response=response,
        body=quotes_endpoint.QuotePortalCreateRequest(token=enrollment_token),
        db=db_session,
    )

    assert result.redirect_to == "/portal"
    assert result.user_exists is True
    assert result.access_token
    assert "access_token=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_approved_quote_existing_portal_user_relinks_duplicate_customer(db_session, monkeypatch):
    _, order, _, quote = await _seed_quote_context(db_session)
    quote.is_approved = True
    order.status = RepairOrderStatus.APPROVED
    quote_customer = (await db_session.execute(select(Customer).where(Customer.id == order.customer_id))).scalar_one()
    older_customer = Customer(
        id=uuid4(),
        tenant_id=quote_customer.tenant_id,
        first_name=quote_customer.first_name,
        last_name=quote_customer.last_name,
        email=quote_customer.email,
    )
    db_session.add(older_customer)
    await db_session.flush()
    user = User(
        id=uuid4(),
        tenant_id=quote_customer.tenant_id,
        customer_id=older_customer.id,
        email=quote_customer.email,
        hashed_password="hashed-password",
        first_name=quote_customer.first_name,
        last_name=quote_customer.last_name,
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserCustomerLink(user_id=user.id, customer_id=older_customer.id, tenant_id=quote_customer.tenant_id))
    await db_session.commit()

    enrollment_token = "duplicate-customer-quote-portal-token"
    payload = {
        "quote_id": str(quote.id),
        "repair_order_id": str(order.id),
        "customer_id": str(order.customer_id),
        "tenant_id": str(order.tenant_id),
        "email": quote_customer.email,
        "purpose": "quote_portal_enrollment",
    }

    async def _get_payload(token: str):
        assert token == enrollment_token
        return payload

    async def _is_consumed(_token: str):
        return False

    async def _get_token_version(_user_id: str):
        return 0

    monkeypatch.setattr(quotes_endpoint, "get_quote_portal_enrollment_payload", _get_payload)
    monkeypatch.setattr(quotes_endpoint, "is_quote_portal_enrollment_token_consumed", _is_consumed)
    monkeypatch.setattr(quotes_endpoint, "get_token_version", _get_token_version)

    response = Response()
    result = await quotes_endpoint.create_portal_from_quote_link(
        request=_fake_request(),
        response=response,
        body=quotes_endpoint.QuotePortalCreateRequest(token=enrollment_token),
        db=db_session,
    )

    assert result.user_exists is True
    refreshed_link = (
        await db_session.execute(
            select(UserCustomerLink).where(
                UserCustomerLink.user_id == user.id,
                UserCustomerLink.tenant_id == quote_customer.tenant_id,
            )
        )
    ).scalar_one()
    assert refreshed_link.customer_id == quote_customer.id


@pytest.mark.asyncio
async def test_quote_approval_api_creates_portal_account(client, db_session):
    _, order, _, quote = await _seed_quote_context(db_session)
    quote.approval_token = "quote-approval-token"
    quote.sent_to_customer = True
    quote.sent_at = datetime.now(timezone.utc)
    await db_session.commit()

    approve_response = await client.post("/api/v1/quotes/token/quote-approval-token/approve")
    assert approve_response.status_code == 200

    resolve_response = await client.post("/api/v1/quotes/token/quote-approval-token/portal-resolve")
    assert resolve_response.status_code == 200
    enrollment_token = resolve_response.json()["portal_enrollment_token"]

    create_response = await client.post(
        "/api/v1/quotes/portal/create",
        json={
            "token": enrollment_token,
            "new_password": "StrongPass1!",
        },
    )

    assert create_response.status_code == 200
    body = create_response.json()
    assert body["redirect_to"] == "/portal"
    assert body["access_token"]
    assert approve_response.json()["is_approved"] is True
