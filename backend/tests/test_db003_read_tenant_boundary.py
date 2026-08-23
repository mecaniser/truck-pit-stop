from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor, LaborLineType
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.vehicle import Vehicle


SNAPSHOT_MODELS = (
    RepairOrder,
    Labor,
    PartsUsage,
    Inventory,
    RepairOrderHistoryEvent,
    Quote,
    ProviderOutboxEvent,
)


async def _snapshot(db_session) -> tuple:
    await db_session.rollback()
    db_session.expire_all()
    frozen = []
    for model in SNAPSHOT_MODELS:
        rows = (
            await db_session.execute(select(model).order_by(model.id))
        ).scalars().all()
        frozen.append(
            (
                model.__tablename__,
                tuple(
                    tuple(
                        (column.name, repr(getattr(row, column.name)))
                        for column in model.__table__.columns
                    )
                    for row in rows
                ),
            )
        )
    return tuple(frozen)


async def _add_order(
    db_session,
    *,
    tenant: Tenant,
    suffix: str,
    assigned_mechanic_id: UUID | None = None,
    deleted: bool = False,
) -> RepairOrder:
    customer = Customer(
        tenant_id=tenant.id,
        first_name=f"Private-{suffix}",
        last_name="Customer",
        email=f"private-{suffix}@example.com",
    )
    db_session.add(customer)
    await db_session.flush()
    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Private Freightliner",
        model="Cascadia",
        year=2024,
    )
    inventory = Inventory(
        tenant_id=tenant.id,
        sku=f"PRIVATE-{suffix}",
        name=f"Private part {suffix}",
        stock_quantity=5,
        cost=Decimal("10.00"),
        selling_price=Decimal("20.00"),
    )
    db_session.add_all([vehicle, inventory])
    await db_session.flush()
    order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        assigned_mechanic_id=assigned_mechanic_id,
        order_number=f"PRIVATE-RO-{suffix}",
        status=RepairOrderStatus.QUOTED,
        total_labor_cost=Decimal("100.00"),
        total_parts_cost=Decimal("20.00"),
        total_cost=Decimal("120.00"),
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    db_session.add(order)
    await db_session.flush()
    labor = Labor(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        description=f"Private labor {suffix}",
        hours=Decimal("1.00"),
        hourly_rate=Decimal("100.00"),
        total_cost=Decimal("100.00"),
        line_type=LaborLineType.MANUAL,
    )
    part = PartsUsage(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        inventory_id=inventory.id,
        quantity=Decimal("1.00"),
        unit_cost=Decimal("10.00"),
        unit_price=Decimal("20.00"),
        list_price=Decimal("20.00"),
        total_price=Decimal("20.00"),
        stock_reserved_packages=1,
        stock_shortage_override=False,
    )
    db_session.add_all([labor, part])
    await db_session.flush()
    quote = Quote(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        quote_number=f"PRIVATE-Q-{suffix}",
        total_amount=Decimal("120.00"),
        revision=1,
        authorization_type="initial_estimate",
        previously_authorized_amount=Decimal("0.00"),
        delta_amount=Decimal("120.00"),
        sent_to_customer=True,
        is_approved=False,
        is_declined=False,
    )
    db_session.add(quote)
    await db_session.flush()
    db_session.add_all(
        [
            RepairOrderHistoryEvent(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                event_type="authorization_published",
                label=f"Private history {suffix}",
                detail='{"private":"must-not-leak"}',
                entity_id=quote.id,
            ),
            ProviderOutboxEvent(
                tenant_id=tenant.id,
                event_type="boundary.seed",
                aggregate_type="repair_order",
                aggregate_id=order.id,
                payload={"private": suffix},
                idempotency_key=f"read-boundary:{order.id}",
                status="pending",
                attempt_count=0,
                available_at=datetime.now(timezone.utc),
            ),
        ]
    )
    return order


def _read_paths(order_id) -> tuple[str, ...]:
    base = f"/api/v1/repair-orders/{order_id}"
    return (
        f"{base}/parts",
        f"{base}/parts/suggestions",
        f"{base}/labor",
        f"/api/v1/quotes/repair-order/{order_id}/history",
    )


def _draft_price_read_paths(order_id) -> tuple[str, ...]:
    base = f"/api/v1/repair-orders/{order_id}"
    return (
        f"{base}/parts",
        f"{base}/parts/suggestions",
        f"{base}/labor",
    )


def _assert_generic_not_found(response) -> None:
    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == {"detail", "error", "correlation_id"}
    assert payload["detail"] == payload["error"] == "Repair order not found"
    assert "private" not in response.text.lower()


@pytest.mark.asyncio
async def test_legacy_price_reads_hide_foreign_missing_and_deleted_orders(
    client,
    db_session,
    monkeypatch,
):
    from app.api.v1.endpoints import quotes, repair_orders

    websocket_events: list[dict] = []

    async def _capture_websocket(**event):
        websocket_events.append(event)

    monkeypatch.setattr(
        repair_orders,
        "broadcast_repair_order_update",
        _capture_websocket,
    )
    monkeypatch.setattr(quotes, "broadcast_quote_event", _capture_websocket)
    monkeypatch.setattr(
        quotes,
        "broadcast_repair_order_update",
        _capture_websocket,
    )

    suffix = uuid4().hex[:10]
    foreign_tenant = Tenant(name="Foreign tenant", slug=f"foreign-{suffix}")
    actor_tenant = Tenant(name="Actor tenant", slug=f"actor-{suffix}")
    db_session.add_all([foreign_tenant, actor_tenant])
    await db_session.flush()
    actor = User(
        tenant_id=actor_tenant.id,
        email=f"fleet-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Restricted",
        last_name="Fleet manager",
        role=UserRole.FLEET_MANAGER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(actor)
    await db_session.flush()
    foreign_order = await _add_order(
        db_session,
        tenant=foreign_tenant,
        suffix=f"FOREIGN-{suffix}",
    )
    same_tenant_order = await _add_order(
        db_session,
        tenant=actor_tenant,
        suffix=f"SAME-{suffix}",
    )
    deleted_order = await _add_order(
        db_session,
        tenant=actor_tenant,
        suffix=f"DELETED-{suffix}",
        deleted=True,
    )
    await db_session.commit()

    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(actor.id)})}"
    }
    baseline = await _snapshot(db_session)

    for order_id in (foreign_order.id, deleted_order.id, uuid4()):
        responses = [
            await client.get(path, headers=headers)
            for path in _read_paths(order_id)
        ]
        for response in responses:
            _assert_generic_not_found(response)
        assert [set(response.json()) for response in responses] == [
            {"detail", "error", "correlation_id"}
        ] * 4
        assert await _snapshot(db_session) == baseline

    # Existing same-tenant restricted-role decisions remain forbidden rather
    # than being flattened into the cross-tenant not-found boundary.
    same_tenant_responses = [
        await client.get(path, headers=headers)
        for path in _read_paths(same_tenant_order.id)
    ]
    assert [response.status_code for response in same_tenant_responses] == [
        403,
        403,
        403,
        403,
    ]
    assert await _snapshot(db_session) == baseline
    assert websocket_events == []


@pytest.mark.asyncio
async def test_draft_price_reads_require_staff_or_assigned_mechanic(
    client,
    db_session,
    monkeypatch,
):
    from app.api.v1.endpoints import repair_orders

    websocket_events: list[dict] = []

    async def _capture_websocket(**event):
        websocket_events.append(event)

    monkeypatch.setattr(
        repair_orders,
        "broadcast_repair_order_update",
        _capture_websocket,
    )

    suffix = uuid4().hex[:10]
    tenant = Tenant(name="Price boundary tenant", slug=f"price-boundary-{suffix}")
    db_session.add(tenant)
    await db_session.flush()
    owner = User(
        tenant_id=tenant.id,
        email=f"owner-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Shop",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    assigned_mechanic = User(
        tenant_id=tenant.id,
        email=f"assigned-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Assigned",
        last_name="Mechanic",
        role=UserRole.MECHANIC,
        is_active=True,
        is_verified=True,
    )
    unassigned_mechanic = User(
        tenant_id=tenant.id,
        email=f"unassigned-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Unassigned",
        last_name="Mechanic",
        role=UserRole.MECHANIC,
        is_active=True,
        is_verified=True,
    )
    linked_customer = User(
        tenant_id=None,
        customer_id=None,
        email=f"linked-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Linked",
        last_name="Customer",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all(
        [owner, assigned_mechanic, unassigned_mechanic, linked_customer]
    )
    await db_session.flush()
    order = await _add_order(
        db_session,
        tenant=tenant,
        suffix=f"DRAFT-{suffix}",
        assigned_mechanic_id=assigned_mechanic.id,
    )
    linked_order = await _add_order(
        db_session,
        tenant=tenant,
        suffix=f"LINKED-DRAFT-{suffix}",
        assigned_mechanic_id=assigned_mechanic.id,
    )
    direct_customer = User(
        tenant_id=tenant.id,
        customer_id=order.customer_id,
        email=f"direct-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Direct",
        last_name="Customer",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(direct_customer)
    await db_session.flush()
    db_session.add(
        UserCustomerLink(
            user_id=linked_customer.id,
            customer_id=linked_order.customer_id,
            tenant_id=tenant.id,
        )
    )
    await db_session.commit()

    tenant_id = tenant.id
    order_id = order.id
    linked_order_id = linked_order.id
    owner_id = owner.id
    assigned_mechanic_id = assigned_mechanic.id
    unassigned_mechanic_id = unassigned_mechanic.id
    direct_customer_id = direct_customer.id
    linked_customer_id = linked_customer.id
    baseline = await _snapshot(db_session)

    def _headers(user_id, **claims):
        return {
            "Authorization": (
                "Bearer "
                + create_access_token({"sub": str(user_id), **claims})
            )
        }

    customer_cases = (
        (_headers(direct_customer_id), order_id),
        (_headers(linked_customer_id, tid=str(tenant_id)), linked_order_id),
    )
    private_markers = ("private", "20.0", "100.0", "120.0")
    for headers, customer_order_id in customer_cases:
        responses = [
            await client.get(path, headers=headers)
            for path in _draft_price_read_paths(customer_order_id)
        ]
        assert [response.status_code for response in responses] == [403] * 3
        for response in responses:
            assert response.json()["detail"] == "Insufficient permissions"
            assert all(marker not in response.text.lower() for marker in private_markers)
        assert await _snapshot(db_session) == baseline

    unassigned_responses = [
        await client.get(path, headers=_headers(unassigned_mechanic_id))
        for path in _draft_price_read_paths(order_id)
    ]
    assert [response.status_code for response in unassigned_responses] == [403] * 3
    assert await _snapshot(db_session) == baseline

    for actor_id in (owner_id, assigned_mechanic_id):
        responses = [
            await client.get(path, headers=_headers(actor_id))
            for path in _draft_price_read_paths(order_id)
        ]
        assert [response.status_code for response in responses] == [200] * 3

    assert await _snapshot(db_session) == baseline
    assert websocket_events == []
