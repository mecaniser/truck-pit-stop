"""Voiding an order the financial-record guard protects.

An invoiced or paid order is kept as a financial record and cannot be cancelled
or deleted. That rule is right, and it also traps a test transaction that was
never real — there was no way to retire one at all.

The override does not delete: it voids. The invoice is cancelled with a reason,
the order is marked cancelled, and both rows stay exactly where they were,
visibly void and attributable. These tests pin that, and pin the two things
that keep it from becoming the ordinary way to work: a password, and a refusal
to touch an invoice the accounting system already holds.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.payment_step_up import PaymentStepUpScope
from app.core.security import create_access_token, get_password_hash
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle

PASSWORD = "Local-dev-force-void-42!"


async def _shop(db_session, suffix: str, *, role: UserRole = UserRole.GARAGE_OWNER,
                status: RepairOrderStatus = RepairOrderStatus.PAID,
                invoice_status: InvoiceStatus = InvoiceStatus.PAID,
                quickbooks_invoice_id: str | None = None):
    tenant = Tenant(id=uuid4(), name=f"Void Garage {suffix}", slug=f"void-{suffix}", is_active=True)
    customer = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Pat", last_name="Driver",
        email=f"pat-{suffix}@example.test",
    )
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, make="Volvo", model="VNL")
    user = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{suffix}@example.test",
        hashed_password=get_password_hash(PASSWORD), first_name="Owner", last_name="One",
        role=role, is_active=True, is_verified=True,
    )
    order = RepairOrder(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        order_number=f"RO-{suffix}", status=status, is_internal=False,
        total_parts_cost=Decimal("0.00"), total_labor_cost=Decimal("14.14"), total_cost=Decimal("14.14"),
    )
    invoice = Invoice(
        id=uuid4(), tenant_id=tenant.id, repair_order_id=order.id,
        invoice_number=f"INV-{suffix}", status=invoice_status,
        subtotal=Decimal("14.14"), tax_amount=Decimal("0.00"), total_amount=Decimal("14.14"),
        quickbooks_invoice_id=quickbooks_invoice_id,
    )
    db_session.add_all([tenant, customer, vehicle, user, order, invoice])
    await db_session.commit()
    return tenant, user, order, invoice, create_access_token({"sub": str(user.id)})


async def _grant(client, token: str, password: str = PASSWORD):
    response = await client.post(
        "/api/v1/auth/step-up-grants",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": password, "scope": PaymentStepUpScope.REPAIR_ORDER_FORCE_VOID.value},
    )
    return response


async def _force_void(client, token, order, *, grant_token=None, reason="Test transaction, never real"):
    headers = {"Authorization": f"Bearer {token}"}
    if grant_token:
        headers["X-Step-Up-Authorization"] = grant_token
    return await client.post(
        f"/api/v1/repair-orders/{order.id}/force-void",
        headers=headers, json={"reason": reason},
    )


@pytest.mark.asyncio
async def test_a_paid_order_can_be_voided_with_a_password(client, db_session):
    _t, _u, order, invoice, token = await _shop(db_session, "paid")

    grant = await _grant(client, token)
    assert grant.status_code == 200, grant.text
    response = await _force_void(client, token, order, grant_token=grant.json()["grant_token"])

    assert response.status_code == 200, response.text
    await db_session.refresh(order)
    await db_session.refresh(invoice)
    assert order.status == RepairOrderStatus.CANCELLED
    assert invoice.status == InvoiceStatus.CANCELLED
    assert invoice.void_reason == "Test transaction, never real"
    assert invoice.voided_at is not None


@pytest.mark.asyncio
async def test_the_record_survives_the_void(client, db_session):
    """It voids; it does not delete. The evidence has to outlive the amount."""
    _t, _u, order, invoice, token = await _shop(db_session, "survives")
    grant = await _grant(client, token)
    await _force_void(client, token, order, grant_token=grant.json()["grant_token"])

    still_there = (await db_session.execute(
        select(RepairOrder).where(RepairOrder.id == order.id)
    )).scalar_one()
    assert still_there.deleted_at is None
    assert (await db_session.execute(
        select(Invoice).where(Invoice.id == invoice.id)
    )).scalar_one() is not None

    events = (await db_session.execute(
        select(RepairOrderHistoryEvent).where(
            RepairOrderHistoryEvent.repair_order_id == order.id,
            RepairOrderHistoryEvent.event_type == "order_force_voided",
        )
    )).scalars().all()
    assert len(events) == 1
    assert events[0].actor_name == "Owner One"
    assert "Test transaction, never real" in (events[0].detail or "")


@pytest.mark.asyncio
async def test_without_a_password_grant_it_is_refused(client, db_session):
    """A session alone is not enough — this is the whole point of the gate."""
    _t, _u, order, invoice, token = await _shop(db_session, "no-grant")

    response = await _force_void(client, token, order)

    assert response.status_code == 428
    assert response.json()["detail"]["code"] == "STEP_UP_REQUIRED"
    await db_session.refresh(order)
    assert order.status == RepairOrderStatus.PAID


@pytest.mark.asyncio
async def test_a_wrong_password_yields_no_grant(client, db_session):
    _t, _u, _order, _invoice, token = await _shop(db_session, "wrong-pw")

    response = await _grant(client, token, password="not-the-password")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_grant_is_one_time(client, db_session):
    """One password, one void — a reused grant must not void a second order."""
    _t, _u, order, _invoice, token = await _shop(db_session, "one-time")
    grant = await _grant(client, token)
    raw = grant.json()["grant_token"]
    assert grant.json()["one_time"] is True

    first = await _force_void(client, token, order, grant_token=raw)
    assert first.status_code == 200

    _t2, _u2, order2, _i2, _tok2 = await _shop(db_session, "one-time-second")
    # Same shop's grant, reused. The second call must not be authorised.
    replay = await _force_void(client, token, order2, grant_token=raw)
    assert replay.status_code in (403, 409, 428)


@pytest.mark.asyncio
async def test_an_invoice_already_in_quickbooks_is_refused(client, db_session):
    """Voiding here would leave the accounting system holding a document the
    shop no longer has. The two ledgers must not disagree."""
    _t, _u, order, invoice, token = await _shop(
        db_session, "qb-synced", quickbooks_invoice_id="QB-1234",
    )
    grant = await _grant(client, token)

    response = await _force_void(client, token, order, grant_token=grant.json()["grant_token"])

    assert response.status_code == 409
    assert "QuickBooks" in response.json()["detail"]
    await db_session.refresh(order)
    await db_session.refresh(invoice)
    assert order.status == RepairOrderStatus.PAID
    assert invoice.status == InvoiceStatus.PAID


@pytest.mark.asyncio
async def test_an_ordinary_order_must_use_the_ordinary_path(client, db_session):
    """The override is for the guard it overrides, not a second cancel button."""
    _t, _u, order, _invoice, token = await _shop(
        db_session, "not-protected",
        status=RepairOrderStatus.IN_PROGRESS, invoice_status=InvoiceStatus.DRAFT,
    )
    grant = await _grant(client, token)

    response = await _force_void(client, token, order, grant_token=grant.json()["grant_token"])

    assert response.status_code == 409
    assert "ordinary way" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_receptionist_cannot_get_a_grant_for_this_scope(client, db_session):
    _t, _u, _order, _invoice, token = await _shop(
        db_session, "receptionist", role=UserRole.RECEPTIONIST,
    )

    response = await _grant(client, token)

    assert response.status_code == 403
