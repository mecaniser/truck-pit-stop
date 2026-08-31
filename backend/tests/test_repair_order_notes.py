"""Notes accumulate on the order, signed and timed, and never overwrite.

The first attempt was a pair of text columns the panel wrote over: a second
note erased the first, and no note carried an author or a time. These tests pin
the behaviour that replaced it — appended entries, an owner, and a delete route
that cannot reach the part and status events this table exists to preserve.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints import repair_orders
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import RepairOrderNoteCreate


async def _seed(db, *, role: UserRole = UserRole.RECEPTIONIST):
    suffix = uuid4().hex[:8]
    tenant = Tenant(id=uuid4(), name="Note shop", slug=f"note-{suffix}", is_active=True)
    customer = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Pat", last_name="Driver",
        email=f"pat-{suffix}@example.test",
    )
    vehicle = Vehicle(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, make="Volvo", model="VNL")
    user = User(
        id=uuid4(), tenant_id=tenant.id, email=f"staff-{suffix}@example.test",
        hashed_password="x", first_name="Dana", last_name="Front", role=role,
        is_active=True, is_verified=True,
    )
    order = RepairOrder(
        id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, vehicle_id=vehicle.id,
        order_number=f"RO-{suffix}", status=RepairOrderStatus.IN_PROGRESS, is_internal=False,
        total_parts_cost=Decimal("0.00"), total_labor_cost=Decimal("0.00"), total_cost=Decimal("0.00"),
    )
    db.add_all([tenant, customer, vehicle, user, order])
    await db.commit()
    return tenant, user, order


async def _live_notes(db, order):
    result = await db.execute(
        select(RepairOrderHistoryEvent)
        .where(
            RepairOrderHistoryEvent.repair_order_id == order.id,
            RepairOrderHistoryEvent.deleted_at.is_(None),
        )
        .order_by(RepairOrderHistoryEvent.created_at.asc())
    )
    return [e for e in result.scalars().all() if e.event_type in repair_orders.NOTE_EVENT_TYPES]


@pytest.mark.asyncio
async def test_a_second_note_does_not_replace_the_first(db_session):
    """The defect that prompted the rewrite."""
    _, user, order = await _seed(db_session)

    for text in ("Customer approved the axle work by phone.", "Reused core, flagged for the next PM."):
        await repair_orders.add_repair_order_note(
            order_id=order.id, body=RepairOrderNoteCreate(body=text, audience="shop"),
            db=db_session, current_user=user,
        )

    notes = await _live_notes(db_session, order)
    assert [n.detail for n in notes] == [
        "Customer approved the axle work by phone.",
        "Reused core, flagged for the next PM.",
    ]


@pytest.mark.asyncio
async def test_a_note_is_signed_and_timed(db_session):
    _, user, order = await _seed(db_session)

    created = await repair_orders.add_repair_order_note(
        order_id=order.id, body=RepairOrderNoteCreate(body="Torque checked.", audience="shop"),
        db=db_session, current_user=user,
    )

    assert created.actor_name == "Dana Front"
    assert created.actor_user_id == user.id
    assert created.created_at is not None


@pytest.mark.asyncio
async def test_the_audience_is_recorded_on_the_note(db_session):
    _, user, order = await _seed(db_session)

    for audience, expected in (("customer", "note_customer"), ("shop", "note_shop")):
        created = await repair_orders.add_repair_order_note(
            order_id=order.id, body=RepairOrderNoteCreate(body=f"{audience} note", audience=audience),
            db=db_session, current_user=user,
        )
        assert created.event_type == expected


@pytest.mark.asyncio
async def test_a_blank_note_is_rejected(db_session):
    with pytest.raises(ValueError):
        RepairOrderNoteCreate(body="   ", audience="shop")


@pytest.mark.asyncio
async def test_you_may_delete_your_own_note(db_session):
    _, user, order = await _seed(db_session)
    created = await repair_orders.add_repair_order_note(
        order_id=order.id, body=RepairOrderNoteCreate(body="Mine to remove.", audience="shop"),
        db=db_session, current_user=user,
    )

    await repair_orders.delete_repair_order_note(
        order_id=order.id, note_id=created.id, db=db_session, current_user=user,
    )

    assert await _live_notes(db_session, order) == []


@pytest.mark.asyncio
async def test_you_may_not_delete_someone_elses_note(db_session):
    tenant, author, order = await _seed(db_session)
    created = await repair_orders.add_repair_order_note(
        order_id=order.id, body=RepairOrderNoteCreate(body="Not yours.", audience="shop"),
        db=db_session, current_user=author,
    )
    other = User(
        id=uuid4(), tenant_id=tenant.id, email=f"other-{uuid4().hex[:8]}@example.test",
        hashed_password="x", first_name="Sam", last_name="Second", role=UserRole.RECEPTIONIST,
        is_active=True, is_verified=True,
    )
    db_session.add(other)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await repair_orders.delete_repair_order_note(
            order_id=order.id, note_id=created.id, db=db_session, current_user=other,
        )
    assert exc.value.status_code == 403
    assert len(await _live_notes(db_session, order)) == 1


@pytest.mark.asyncio
async def test_an_owner_may_remove_anyones_note(db_session):
    tenant, author, order = await _seed(db_session)
    created = await repair_orders.add_repair_order_note(
        order_id=order.id, body=RepairOrderNoteCreate(body="Should not have been written.", audience="customer"),
        db=db_session, current_user=author,
    )
    owner = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{uuid4().hex[:8]}@example.test",
        hashed_password="x", first_name="Owner", last_name="One", role=UserRole.GARAGE_OWNER,
        is_active=True, is_verified=True,
    )
    db_session.add(owner)
    await db_session.commit()

    await repair_orders.delete_repair_order_note(
        order_id=order.id, note_id=created.id, db=db_session, current_user=owner,
    )
    assert await _live_notes(db_session, order) == []


@pytest.mark.asyncio
async def test_the_note_route_cannot_delete_a_part_or_status_event(db_session):
    """The reason this route filters on event_type.

    Notes share a table with the order's audit trail. Without the filter, an
    owner could erase a part or status event through the notes endpoint — the
    exact thing a durable history exists to prevent.
    """
    tenant, user, order = await _seed(db_session, role=UserRole.GARAGE_OWNER)
    audit = RepairOrderHistoryEvent(
        id=uuid4(), tenant_id=tenant.id, repair_order_id=order.id,
        created_at=datetime.now(timezone.utc), event_type="part_added",
        label="Part added", detail="Brake pads · 2 ea", actor_name="Dana Front",
        actor_user_id=user.id,
    )
    db_session.add(audit)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await repair_orders.delete_repair_order_note(
            order_id=order.id, note_id=audit.id, db=db_session, current_user=user,
        )
    assert exc.value.status_code == 404

    still_there = (await db_session.execute(
        select(RepairOrderHistoryEvent).where(RepairOrderHistoryEvent.id == audit.id)
    )).scalar_one()
    assert still_there.deleted_at is None


@pytest.mark.asyncio
async def test_a_note_cannot_be_added_to_another_tenants_order(db_session):
    _, _, order = await _seed(db_session)
    _, outsider, _ = await _seed(db_session)

    with pytest.raises(HTTPException) as exc:
        await repair_orders.add_repair_order_note(
            order_id=order.id, body=RepairOrderNoteCreate(body="Not my shop.", audience="shop"),
            db=db_session, current_user=outsider,
        )
    assert exc.value.status_code in (403, 404)
