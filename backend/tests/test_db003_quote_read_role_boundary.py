from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models.customer import Customer
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
    Quote,
    RepairOrderHistoryEvent,
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
) -> tuple[RepairOrder, Customer]:
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
    db_session.add(vehicle)
    await db_session.flush()
    order = RepairOrder(
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        assigned_mechanic_id=assigned_mechanic_id,
        order_number=f"PRIVATE-RO-{suffix}",
        status=RepairOrderStatus.QUOTED,
        total_labor_cost=Decimal("100.00"),
        total_parts_cost=Decimal("0.00"),
        total_cost=Decimal("100.00"),
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    db_session.add(order)
    await db_session.flush()
    return order, customer


def _headers(user_id: UUID, *, tenant_id: UUID | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token({'sub': str(user_id)}, tenant_id=str(tenant_id) if tenant_id else None)}"
    }


@pytest.mark.asyncio
async def test_draft_quote_read_enforces_complete_role_and_tenant_matrix(
    client,
    db_session,
    monkeypatch,
):
    from app.api.v1.endpoints import quotes

    websocket_events: list[dict] = []

    async def _capture_websocket(**event):
        websocket_events.append(event)

    monkeypatch.setattr(quotes, "broadcast_quote_event", _capture_websocket)
    monkeypatch.setattr(
        quotes,
        "broadcast_repair_order_update",
        _capture_websocket,
    )

    suffix = uuid4().hex[:10]
    tenant = Tenant(name="Quote role tenant", slug=f"quote-role-{suffix}")
    foreign_tenant = Tenant(
        name="Foreign quote tenant",
        slug=f"foreign-quote-role-{suffix}",
    )
    db_session.add_all([tenant, foreign_tenant])
    await db_session.flush()

    users = {
        role: User(
            tenant_id=tenant.id,
            email=f"{role.value}-{suffix}@example.com",
            hashed_password="hashed-password",
            first_name=role.value,
            last_name="Actor",
            role=role,
            is_active=True,
            is_verified=True,
        )
        for role in (
            UserRole.GARAGE_OWNER,
            UserRole.GARAGE_ADMIN,
            UserRole.RECEPTIONIST,
            UserRole.FLEET_MANAGER,
            UserRole.DRIVER,
            UserRole.SUPER_ADMIN,
        )
    }
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
        [*users.values(), assigned_mechanic, unassigned_mechanic, linked_customer]
    )
    await db_session.flush()

    order, customer = await _add_order(
        db_session,
        tenant=tenant,
        suffix=f"SAME-{suffix}",
        assigned_mechanic_id=assigned_mechanic.id,
    )
    direct_customer = User(
        tenant_id=tenant.id,
        customer_id=customer.id,
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
            customer_id=customer.id,
            tenant_id=tenant.id,
        )
    )
    sent_quote = Quote(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        quote_number=f"PRIVATE-SENT-{suffix}",
        total_amount=Decimal("90.00"),
        revision=1,
        authorization_type="initial_estimate",
        previously_authorized_amount=Decimal("0.00"),
        delta_amount=Decimal("90.00"),
        sent_to_customer=True,
        sent_at=datetime.now(timezone.utc),
        approval_token=f"published-{uuid4().hex}",
    )
    draft_quote = Quote(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        quote_number=f"PRIVATE-DRAFT-{suffix}",
        total_amount=Decimal("100.00"),
        revision=2,
        authorization_type="additional_work",
        previously_authorized_amount=Decimal("90.00"),
        delta_amount=Decimal("10.00"),
        sent_to_customer=False,
    )
    db_session.add_all([sent_quote, draft_quote])

    foreign_order, _ = await _add_order(
        db_session,
        tenant=foreign_tenant,
        suffix=f"FOREIGN-{suffix}",
    )
    deleted_order, _ = await _add_order(
        db_session,
        tenant=tenant,
        suffix=f"DELETED-{suffix}",
        deleted=True,
    )
    db_session.add(
        ProviderOutboxEvent(
            tenant_id=tenant.id,
            event_type="boundary.seed",
            aggregate_type="repair_order",
            aggregate_id=order.id,
            payload={"private": suffix},
            idempotency_key=f"quote-role-boundary:{order.id}",
            status="pending",
            attempt_count=0,
            available_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    tenant_id = tenant.id
    order_id = order.id
    foreign_order_id = foreign_order.id
    deleted_order_id = deleted_order.id
    sent_quote_id = sent_quote.id
    sent_quote_number = sent_quote.quote_number
    draft_quote_id = draft_quote.id
    draft_quote_number = draft_quote.quote_number
    allowed_ids = (
        users[UserRole.GARAGE_OWNER].id,
        users[UserRole.GARAGE_ADMIN].id,
        users[UserRole.RECEPTIONIST].id,
        assigned_mechanic.id,
    )
    denied_cases = (
        (users[UserRole.FLEET_MANAGER].id, "Insufficient permissions"),
        (users[UserRole.DRIVER].id, "Insufficient permissions"),
        (users[UserRole.SUPER_ADMIN].id, "Insufficient permissions"),
        (unassigned_mechanic.id, "Access denied"),
        (direct_customer.id, "Insufficient permissions"),
        (linked_customer.id, "Insufficient permissions"),
    )
    direct_customer_id = direct_customer.id
    linked_customer_id = linked_customer.id
    owner_id = users[UserRole.GARAGE_OWNER].id
    baseline = await _snapshot(db_session)

    draft_url = f"/api/v1/quotes?repair_order_id={order_id}"
    for actor_id in allowed_ids:
        response = await client.get(draft_url, headers=_headers(actor_id))
        assert response.status_code == 200
        assert response.json()["id"] == str(draft_quote_id)
        assert response.json()["quote_number"] == draft_quote_number
        assert response.json()["total_amount"] == "100.00"

    for actor_id, expected_detail in denied_cases:
        response = await client.get(draft_url, headers=_headers(actor_id))
        assert response.status_code == 403
        payload = response.json()
        assert set(payload) == {"detail", "error", "correlation_id"}
        assert payload["detail"] == payload["error"] == expected_detail
        assert draft_quote_number not in response.text
        assert "100.00" not in response.text

    owner_headers = _headers(owner_id)
    for hidden_order_id in (foreign_order_id, deleted_order_id, uuid4()):
        response = await client.get(
            f"/api/v1/quotes?repair_order_id={hidden_order_id}",
            headers=owner_headers,
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Repair order not found"
        assert "private" not in response.text.lower()

    history_url = f"/api/v1/quotes/repair-order/{order_id}/history"
    for customer_id, selected_tenant_id in (
        (direct_customer_id, None),
        (linked_customer_id, tenant_id),
    ):
        response = await client.get(
            history_url,
            headers=_headers(customer_id, tenant_id=selected_tenant_id),
        )
        assert response.status_code == 200
        revisions = response.json()["revisions"]
        assert [revision["id"] for revision in revisions] == [str(sent_quote_id)]
        assert revisions[0]["quote_number"] == sent_quote_number
        assert draft_quote_number not in response.text
        assert "100.00" not in response.text

    assert await _snapshot(db_session) == baseline
    assert websocket_events == []
