from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api.v1.endpoints import quotes, repair_orders
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory
from app.db.models.labor import Labor, LaborLineType
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.vehicle import Vehicle
from app.db.base import Base
from app.schemas.repair_order import LaborCreate, PartsUsageCreate


def _request(path: str = "/api/v1/quotes/token/test") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "client": ("testclient", 50000),
        }
    )


def _silence_delivery(monkeypatch):
    delivered: list[dict] = []

    async def _capture_email(**kwargs):
        delivered.append(kwargs)

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(quotes.settings, "PROVIDER_OUTBOX_ENABLED", False)
    monkeypatch.setattr(quotes, "send_email", _capture_email)
    monkeypatch.setattr(quotes, "send_sms", _noop)
    monkeypatch.setattr(quotes, "broadcast_quote_event", _noop)
    monkeypatch.setattr(quotes, "broadcast_repair_order_update", _noop)
    return delivered


async def _seed_authorization(
    db,
    *,
    total: Decimal = Decimal("100.00"),
    auto_approval_threshold: Optional[Decimal] = None,
):
    suffix = uuid4().hex
    tenant = Tenant(
        name="Authorization Shop",
        slug=f"authorization-{suffix}",
        email=f"shop-{suffix}@example.com",
    )
    db.add(tenant)
    await db.flush()

    customer = Customer(
        tenant_id=tenant.id,
        first_name="Casey",
        last_name="Customer",
        email=f"customer-{suffix}@example.com",
        phone="7045550100",
        auto_approval_threshold=auto_approval_threshold,
    )
    db.add(customer)
    await db.flush()

    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2023,
    )
    db.add(vehicle)
    await db.flush()

    roles = {}
    for key, role in (
        ("owner", UserRole.GARAGE_OWNER),
        ("admin", UserRole.GARAGE_ADMIN),
        ("receptionist", UserRole.RECEPTIONIST),
        ("mechanic", UserRole.MECHANIC),
        ("fleet_manager", UserRole.FLEET_MANAGER),
        ("driver", UserRole.DRIVER),
        ("super_admin", UserRole.SUPER_ADMIN),
    ):
        roles[key] = User(
            tenant_id=tenant.id,
            email=f"{key}-{suffix}@example.com",
            hashed_password="hashed-password",
            first_name=key.title(),
            last_name="User",
            role=role,
            is_active=True,
            is_verified=True,
        )
        db.add(roles[key])

    customer_user = User(
        tenant_id=None,
        customer_id=None,
        email=f"portal-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Casey",
        last_name="Customer",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db.add(customer_user)
    await db.flush()
    db.add(
        UserCustomerLink(
            user_id=customer_user.id,
            customer_id=customer.id,
            tenant_id=tenant.id,
        )
    )

    order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{suffix[:10]}",
        status=RepairOrderStatus.QUOTED,
        description="Customer repair",
        is_internal=False,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=total,
        total_cost=total,
    )
    db.add(order)
    await db.flush()
    db.add(
        Labor(
            tenant_id=tenant.id,
            repair_order_id=order.id,
            description="Diagnosis and repair",
            hours=Decimal("1.00"),
            hourly_rate=total,
            total_cost=total,
            line_type=LaborLineType.MANUAL,
        )
    )
    quote = Quote(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        quote_number=f"Q-{suffix[:10]}",
        total_amount=total,
        revision=1,
        authorization_type="initial_estimate",
        previously_authorized_amount=Decimal("0.00"),
        delta_amount=total,
        is_approved=False,
        is_declined=False,
        sent_to_customer=False,
    )
    db.add(quote)
    await db.commit()
    return {
        "tenant": tenant,
        "customer": customer,
        "customer_user": customer_user,
        "vehicle": vehicle,
        "roles": roles,
        "order": order,
        "quote": quote,
    }


async def _set_order_total(db, context, total: Decimal) -> None:
    context["order"].total_labor_cost = total
    context["order"].total_cost = total
    labor = (
        await db.execute(select(Labor).where(Labor.repair_order_id == context["order"].id))
    ).scalar_one()
    labor.hourly_rate = total
    labor.total_cost = total
    await db.commit()


async def _run_role_dependency(endpoint, current_user: User):
    dependency = inspect.signature(endpoint).parameters["current_user"].default.dependency
    return await dependency(current_user=current_user)


@pytest.mark.asyncio
async def test_mechanic_role_is_additive_only_at_the_api_boundary(db_session):
    context = await _seed_authorization(db_session)
    mechanic = context["roles"]["mechanic"]

    for endpoint in (
        repair_orders.add_price_build_flat_service,
        repair_orders.apply_price_build_repair_operation,
        repair_orders.add_parts_to_repair_order,
        repair_orders.add_labor_to_repair_order,
    ):
        assert await _run_role_dependency(endpoint, mechanic) is mechanic

    for endpoint in (
        repair_orders.update_price_build_line,
        repair_orders.delete_price_build_line,
        repair_orders.recalculate_price_build,
        repair_orders.add_sublet_to_price_build,
        repair_orders.update_parts_quantity,
        repair_orders.set_parts_pricing_mode,
        repair_orders.update_repair_order_discounts,
        repair_orders.remove_parts_from_repair_order,
        repair_orders.update_repair_order_labor,
        repair_orders.remove_labor_from_repair_order,
        repair_orders.approve_completion,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _run_role_dependency(endpoint, mechanic)
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_assigned_mechanic_adds_shop_priced_delta_for_staff_publication(
    db_session,
    monkeypatch,
):
    context = await _seed_authorization(db_session)
    mechanic = context["roles"]["mechanic"]
    context["tenant"].labor_rate = Decimal("100.00")
    context["order"].assigned_mechanic_id = mechanic.id
    context["order"].status = RepairOrderStatus.IN_PROGRESS
    context["quote"].sent_to_customer = True
    context["quote"].sent_at = datetime.now(timezone.utc)
    context["quote"].is_approved = True
    context["quote"].authorization_type = "initial_estimate"
    context["quote"].previously_authorized_amount = Decimal("0.00")
    context["quote"].delta_amount = Decimal("100.00")
    inventory = Inventory(
        tenant_id=context["tenant"].id,
        sku=f"DB003-{uuid4().hex[:8]}",
        name="DEF pressure sensor",
        stock_quantity=3,
        on_order_quantity=0,
        reorder_level=0,
        cost=Decimal("25.00"),
        selling_price=Decimal("50.00"),
    )
    db_session.add(inventory)
    await db_session.commit()

    labor = await repair_orders.add_labor_to_repair_order(
        order_id=context["order"].id,
        body=LaborCreate(
            description="Trace DEF pressure fault",
            hours=Decimal("0.50"),
            hourly_rate=Decimal("999.00"),
        ),
        db=db_session,
        current_user=mechanic,
    )
    part = await repair_orders.add_parts_to_repair_order(
        order_id=context["order"].id,
        body=PartsUsageCreate(inventory_id=inventory.id, quantity=Decimal("1.00")),
        db=db_session,
        current_user=mechanic,
    )
    revision = await quotes.create_quote(
        body=quotes.QuoteCreate(repair_order_id=context["order"].id),
        db=db_session,
        current_user=mechanic,
    )

    assert labor.mechanic_id == mechanic.id
    assert labor.hourly_rate == Decimal("100.00")
    assert labor.total_cost == Decimal("50.00")
    assert part.unit_price == Decimal("50.00")
    assert revision.authorization_type == "additional_work"
    assert revision.previously_authorized_amount == Decimal("100.00")
    assert revision.delta_amount == Decimal("100.00")
    assert revision.total_amount == Decimal("200.00")

    with pytest.raises(HTTPException) as publish_error:
        await quotes.send_quote_to_customer(
            quote_id=revision.id,
            db=db_session,
            current_user=mechanic,
        )
    assert publish_error.value.status_code == 403

    with pytest.raises(HTTPException) as decision_error:
        await quotes.approve_quote(
            quote_id=revision.id,
            db=db_session,
            current_user=mechanic,
        )
    assert decision_error.value.status_code == 404

    _silence_delivery(monkeypatch)
    published = await quotes.send_quote_to_customer(
        quote_id=revision.id,
        db=db_session,
        current_user=context["roles"]["admin"],
    )
    assert published.sent_to_customer is True
    persisted_revision = await db_session.get(Quote, revision.id)
    assert persisted_revision.line_items_snapshot["labor_total"] == "150.00"
    assert persisted_revision.line_items_snapshot["parts_total"] == "50.00"
    assert persisted_revision.line_items_snapshot["repair_total"] == "200.00"


@pytest.mark.asyncio
async def test_mechanic_pricing_requires_assignment_and_tenant_match(db_session):
    context = await _seed_authorization(db_session)
    other = await _seed_authorization(db_session)
    mechanic = context["roles"]["mechanic"]
    order_id = context["order"].id
    mechanic_id = mechanic.id
    other_mechanic_id = other["roles"]["mechanic"].id
    context["order"].assigned_mechanic_id = uuid4()
    await db_session.commit()

    with pytest.raises(HTTPException) as unassigned_labor:
        await repair_orders.add_labor_to_repair_order(
            order_id=order_id,
            body=LaborCreate(
                description="Unauthorized line",
                hours=Decimal("1.00"),
                hourly_rate=Decimal("100.00"),
            ),
            db=db_session,
            current_user=mechanic,
        )
    assert unassigned_labor.value.status_code == 403
    await db_session.rollback()
    mechanic = await db_session.get(User, mechanic_id)

    with pytest.raises(HTTPException) as unassigned_quote:
        await quotes.create_quote(
            body=quotes.QuoteCreate(repair_order_id=order_id),
            db=db_session,
            current_user=mechanic,
        )
    assert unassigned_quote.value.status_code == 403
    await db_session.rollback()
    other_mechanic = await db_session.get(User, other_mechanic_id)

    with pytest.raises(HTTPException) as cross_tenant_labor:
        await repair_orders.add_labor_to_repair_order(
            order_id=order_id,
            body=LaborCreate(
                description="Cross-tenant line",
                hours=Decimal("1.00"),
                hourly_rate=Decimal("100.00"),
            ),
            db=db_session,
            current_user=other_mechanic,
        )
    assert cross_tenant_labor.value.status_code == 403
    await db_session.rollback()
    other_mechanic = await db_session.get(User, other_mechanic_id)

    with pytest.raises(HTTPException) as cross_tenant_quote:
        await quotes.create_quote(
            body=quotes.QuoteCreate(repair_order_id=order_id),
            db=db_session,
            current_user=other_mechanic,
        )
    assert cross_tenant_quote.value.status_code == 404

    added_lines = (
        await db_session.execute(
            select(Labor).where(
                Labor.repair_order_id == order_id,
                Labor.description.in_(("Unauthorized line", "Cross-tenant line")),
            )
        )
    ).scalars().all()
    assert added_lines == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role_key", ["owner", "admin", "receptionist"])
async def test_only_financial_staff_roles_can_publish(db_session, monkeypatch, role_key):
    context = await _seed_authorization(db_session)
    delivered = _silence_delivery(monkeypatch)

    response = await quotes.send_quote_to_customer(
        quote_id=context["quote"].id,
        db=db_session,
        current_user=context["roles"][role_key],
    )

    assert response.sent_to_customer is True
    persisted = await db_session.get(Quote, response.id)
    assert persisted.sent_by_user_id == context["roles"][role_key].id
    assert len(delivered) == 1
    events = (
        await db_session.execute(
            select(RepairOrderHistoryEvent).where(
                RepairOrderHistoryEvent.repair_order_id == context["order"].id
            ).order_by(RepairOrderHistoryEvent.created_at.asc())
        )
    ).scalars().all()
    assert [event.event_type for event in events] == ["authorization_published"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_key",
    ["mechanic", "fleet_manager", "driver", "super_admin", "customer"],
)
async def test_non_financial_roles_cannot_publish(db_session, monkeypatch, role_key):
    context = await _seed_authorization(db_session)
    delivered = _silence_delivery(monkeypatch)
    current_user = (
        context["customer_user"]
        if role_key == "customer"
        else context["roles"][role_key]
    )

    with pytest.raises(HTTPException) as exc_info:
        await quotes.send_quote_to_customer(
            quote_id=context["quote"].id,
            db=db_session,
            current_user=current_user,
        )

    assert exc_info.value.status_code == 403
    persisted = await db_session.get(Quote, context["quote"].id)
    assert persisted.sent_to_customer is False
    assert persisted.approval_token is None
    assert delivered == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_key",
    ["owner", "admin", "receptionist", "mechanic", "fleet_manager", "driver", "super_admin"],
)
@pytest.mark.parametrize("decision", ["approve", "decline"])
async def test_ordinary_staff_cannot_record_customer_decisions(
    db_session,
    monkeypatch,
    role_key,
    decision,
):
    context = await _seed_authorization(db_session)
    _silence_delivery(monkeypatch)
    await quotes.send_quote_to_customer(
        quote_id=context["quote"].id,
        db=db_session,
        current_user=context["roles"]["admin"],
    )

    with pytest.raises(HTTPException) as exc_info:
        if decision == "approve":
            await quotes.approve_quote(
                quote_id=context["quote"].id,
                db=db_session,
                current_user=context["roles"][role_key],
            )
        else:
            await quotes.decline_quote(
                quote_id=context["quote"].id,
                body=quotes.DeclineQuoteRequest(notes="Staff cannot decide"),
                db=db_session,
                current_user=context["roles"][role_key],
            )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_linked_customer_can_approve_and_view_ordered_history(db_session, monkeypatch):
    context = await _seed_authorization(db_session)
    _silence_delivery(monkeypatch)
    await quotes.send_quote_to_customer(
        quote_id=context["quote"].id,
        db=db_session,
        current_user=context["roles"]["admin"],
    )

    response = await quotes.approve_quote(
        quote_id=context["quote"].id,
        db=db_session,
        current_user=context["customer_user"],
    )
    history = await quotes.get_authorization_history(
        repair_order_id=context["order"].id,
        db=db_session,
        current_user=context["customer_user"],
    )

    assert response.is_approved is True
    assert [revision.revision for revision in history.revisions] == [1]
    assert [event.event_type for event in history.events] == [
        "authorization_published",
        "authorization_customer_approved",
    ]
    decision_detail = json.loads(history.events[-1].detail)
    assert decision_detail == {
        "authorization_type": "initial_estimate",
        "delta_amount": "100.00",
        "occurred_at": decision_detail["occurred_at"],
        "previous_amount": "0.00",
        "resulting_total": "100.00",
        "source": "customer_portal",
        "revision": 1,
    }
    assert "token" not in history.events[-1].detail.lower()


@pytest.mark.asyncio
async def test_initial_threshold_never_auto_approves_additional_work(db_session, monkeypatch):
    context = await _seed_authorization(
        db_session,
        auto_approval_threshold=Decimal("1000.00"),
    )
    _silence_delivery(monkeypatch)

    initial = await quotes.send_quote_to_customer(
        quote_id=context["quote"].id,
        db=db_session,
        current_user=context["roles"]["admin"],
    )
    assert initial.is_approved is True

    await _set_order_total(db_session, context, Decimal("125.00"))
    additional = await quotes.create_quote(
        body=quotes.QuoteCreate(repair_order_id=context["order"].id),
        db=db_session,
        current_user=context["roles"]["admin"],
    )
    published = await quotes.send_quote_to_customer(
        quote_id=additional.id,
        db=db_session,
        current_user=context["roles"]["receptionist"],
    )

    assert additional.authorization_type == "additional_work"
    assert published.previously_authorized_amount == Decimal("100.00")
    assert published.delta_amount == Decimal("25.00")
    assert published.is_approved is False
    history = await quotes.get_authorization_history(
        repair_order_id=context["order"].id,
        db=db_session,
        current_user=context["customer_user"],
    )
    assert [revision.revision for revision in history.revisions] == [1, 2]
    assert [event.event_type for event in history.events] == [
        "authorization_published",
        "authorization_threshold_approved",
        "authorization_published",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("candidate_total", "creates_revision"),
    [
        (Decimal("100.00"), False),
        (Decimal("100.005"), False),
        (Decimal("100.006"), True),
    ],
)
async def test_currency_rounded_positive_delta_boundary(
    db_session,
    monkeypatch,
    candidate_total,
    creates_revision,
):
    context = await _seed_authorization(db_session)
    context["quote"].sent_to_customer = True
    context["quote"].sent_at = datetime.now(timezone.utc)
    context["quote"].is_approved = True
    await db_session.commit()
    monkeypatch.setattr(quotes, "get_order_total", lambda _order: candidate_total)

    if not creates_revision:
        with pytest.raises(HTTPException) as exc_info:
            await quotes.create_quote(
                body=quotes.QuoteCreate(repair_order_id=context["order"].id),
                db=db_session,
                current_user=context["roles"]["admin"],
            )
        assert exc_info.value.status_code == 400
    else:
        revision = await quotes.create_quote(
            body=quotes.QuoteCreate(repair_order_id=context["order"].id),
            db=db_session,
            current_user=context["roles"]["admin"],
        )
        assert revision.revision == 2
        assert revision.delta_amount == Decimal("0.01")


@pytest.mark.asyncio
async def test_decline_preserves_latest_approved_baseline(db_session, monkeypatch):
    context = await _seed_authorization(db_session)
    _silence_delivery(monkeypatch)
    initial = await quotes.send_quote_to_customer(
        quote_id=context["quote"].id,
        db=db_session,
        current_user=context["roles"]["admin"],
    )
    await quotes.approve_quote_by_token(
        request=_request(),
        token=(await db_session.get(Quote, initial.id)).approval_token,
        db=db_session,
    )

    await _set_order_total(db_session, context, Decimal("150.00"))
    second = await quotes.create_quote(
        body=quotes.QuoteCreate(repair_order_id=context["order"].id),
        db=db_session,
        current_user=context["roles"]["admin"],
    )
    await quotes.send_quote_to_customer(
        quote_id=second.id,
        db=db_session,
        current_user=context["roles"]["admin"],
    )
    await quotes.decline_quote(
        quote_id=second.id,
        body=quotes.DeclineQuoteRequest(notes="Defer this work"),
        db=db_session,
        current_user=context["customer_user"],
    )

    await _set_order_total(db_session, context, Decimal("125.00"))
    third = await quotes.create_quote(
        body=quotes.QuoteCreate(repair_order_id=context["order"].id),
        db=db_session,
        current_user=context["roles"]["admin"],
    )

    first_persisted = await db_session.get(Quote, initial.id)
    second_persisted = await db_session.get(Quote, second.id)
    assert first_persisted.is_approved is True
    assert second_persisted.is_declined is True
    assert third.revision == 3
    assert third.previously_authorized_amount == Decimal("100.00")
    assert third.delta_amount == Decimal("25.00")


@pytest.mark.asyncio
async def test_duplicate_send_is_one_publication_and_one_delivery(db_session, monkeypatch):
    context = await _seed_authorization(db_session)
    delivered = _silence_delivery(monkeypatch)
    await quotes.send_quote_to_customer(
        quote_id=context["quote"].id,
        db=db_session,
        current_user=context["roles"]["admin"],
    )

    with pytest.raises(HTTPException) as exc_info:
        await quotes.send_quote_to_customer(
            quote_id=context["quote"].id,
            db=db_session,
            current_user=context["roles"]["owner"],
        )

    assert exc_info.value.status_code == 409
    assert len(delivered) == 1
    publication_count = (
        await db_session.execute(
            select(RepairOrderHistoryEvent).where(
                RepairOrderHistoryEvent.repair_order_id == context["order"].id,
                RepairOrderHistoryEvent.event_type == "authorization_published",
            )
        )
    ).scalars().all()
    assert len(publication_count) == 1


@pytest.mark.asyncio
async def test_competing_send_compare_and_swap_allows_one_winner(
    _db_engine,
    monkeypatch,
    tmp_path,
):
    database_path = tmp_path / "competing-publication.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 30},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as seed_db:
            context = await _seed_authorization(seed_db)
            quote_id = context["quote"].id
            admin_id = context["roles"]["admin"].id
            owner_id = context["roles"]["owner"].id
        delivered = _silence_delivery(monkeypatch)

        async def _send(user_id):
            async with factory() as db:
                user = await db.get(User, user_id)
                try:
                    response = await quotes.send_quote_to_customer(
                        quote_id=quote_id,
                        db=db,
                        current_user=user,
                    )
                    return response.sent_to_customer
                except HTTPException as exc:
                    await db.rollback()
                    return exc.status_code

        outcomes = await asyncio.gather(_send(admin_id), _send(owner_id))

        assert set(outcomes) == {True, 409}
        assert len(delivered) == 1
        async with factory() as verify_db:
            persisted = await verify_db.get(Quote, quote_id)
            publications = (
                await verify_db.execute(
                    select(RepairOrderHistoryEvent).where(
                        RepairOrderHistoryEvent.repair_order_id == persisted.repair_order_id,
                        RepairOrderHistoryEvent.event_type == "authorization_published",
                    )
                )
            ).scalars().all()
        assert persisted.sent_to_customer is True
        assert len(publications) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expired_and_superseded_magic_links_are_not_found(db_session, monkeypatch):
    context = await _seed_authorization(db_session)
    _silence_delivery(monkeypatch)
    sent = await quotes.send_quote_to_customer(
        quote_id=context["quote"].id,
        db=db_session,
        current_user=context["roles"]["admin"],
    )
    persisted = await db_session.get(Quote, sent.id)
    token = persisted.approval_token
    persisted.sent_at = datetime.now(timezone.utc) - timedelta(days=8)
    await db_session.commit()

    with pytest.raises(HTTPException) as expired:
        await quotes.approve_quote_by_token(request=_request(), token=token, db=db_session)
    assert expired.value.status_code == 404

    persisted.sent_at = datetime.now(timezone.utc)
    await _set_order_total(db_session, context, Decimal("125.00"))
    await quotes.create_quote(
        body=quotes.QuoteCreate(repair_order_id=context["order"].id),
        db=db_session,
        current_user=context["roles"]["admin"],
    )
    with pytest.raises(HTTPException) as superseded:
        await quotes.approve_quote_by_token(request=_request(), token=token, db=db_session)
    assert superseded.value.status_code == 404


@pytest.mark.asyncio
async def test_sent_snapshot_is_immutable(db_session, monkeypatch):
    context = await _seed_authorization(db_session)
    _silence_delivery(monkeypatch)
    await quotes.send_quote_to_customer(
        quote_id=context["quote"].id,
        db=db_session,
        current_user=context["roles"]["admin"],
    )
    snapshot = dict((await db_session.get(Quote, context["quote"].id)).line_items_snapshot)

    for operation in (quotes.update_quote, quotes.delete_quote):
        with pytest.raises(HTTPException) as exc_info:
            await operation(
                quote_id=context["quote"].id,
                db=db_session,
                current_user=context["roles"]["admin"],
            )
        assert exc_info.value.status_code == 409
    persisted = await db_session.get(Quote, context["quote"].id)
    assert persisted.line_items_snapshot == snapshot


@pytest.mark.asyncio
async def test_tenant_and_customer_denials_use_not_found_semantics(db_session, monkeypatch):
    context = await _seed_authorization(db_session)
    other = await _seed_authorization(db_session)
    _silence_delivery(monkeypatch)
    sent = await quotes.send_quote_to_customer(
        quote_id=context["quote"].id,
        db=db_session,
        current_user=context["roles"]["admin"],
    )

    with pytest.raises(HTTPException) as cross_tenant_send:
        await quotes.send_quote_to_customer(
            quote_id=sent.id,
            db=db_session,
            current_user=other["roles"]["admin"],
        )
    assert cross_tenant_send.value.status_code == 404

    with pytest.raises(HTTPException) as cross_tenant_history:
        await quotes.get_authorization_history(
            repair_order_id=context["order"].id,
            db=db_session,
            current_user=other["roles"]["admin"],
        )
    assert cross_tenant_history.value.status_code == 404

    with pytest.raises(HTTPException) as wrong_customer:
        await quotes.approve_quote(
            quote_id=sent.id,
            db=db_session,
            current_user=other["customer_user"],
        )
    assert wrong_customer.value.status_code == 404

    persisted = await db_session.get(Quote, sent.id)
    persisted.tenant_id = other["tenant"].id
    await db_session.commit()
    with pytest.raises(HTTPException) as mismatched_revision:
        await quotes.update_quote(
            quote_id=persisted.id,
            db=db_session,
            current_user=other["roles"]["admin"],
        )
    assert mismatched_revision.value.status_code == 404

    with pytest.raises(HTTPException) as mismatched_token:
        await quotes.approve_quote_by_token(
            request=_request(),
            token=persisted.approval_token,
            db=db_session,
        )
    assert mismatched_token.value.status_code == 404


@pytest.mark.asyncio
async def test_internal_fleet_order_is_excluded(db_session):
    context = await _seed_authorization(db_session)
    context["order"].is_internal = True
    await db_session.commit()

    with pytest.raises(HTTPException) as create_error:
        await quotes.create_quote(
            body=quotes.QuoteCreate(repair_order_id=context["order"].id),
            db=db_session,
            current_user=context["roles"]["admin"],
        )
    assert create_error.value.status_code == 400


@pytest.mark.asyncio
async def test_cross_tenant_manager_cannot_finalize_repair_order(db_session):
    context = await _seed_authorization(db_session)
    other = await _seed_authorization(db_session)
    context["order"].status = RepairOrderStatus.PENDING_REVIEW
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await repair_orders.approve_completion(
            order_id=context["order"].id,
            body=None,
            db=db_session,
            current_user=other["roles"]["admin"],
        )

    assert exc_info.value.status_code == 404
    persisted = await db_session.get(RepairOrder, context["order"].id)
    assert persisted.status == RepairOrderStatus.PENDING_REVIEW
