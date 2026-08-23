from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.recommended_service import (
    RecommendedService,
    RecommendedServicePriority,
)
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.db.models.vehicle import Vehicle


SNAPSHOT_MODELS = (RepairOrder, RecommendedService, ProviderOutboxEvent)


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
) -> tuple[RepairOrder, RecommendedService, Customer]:
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
        status=RepairOrderStatus.IN_PROGRESS,
        description=f"Private order {suffix}",
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    db_session.add(order)
    await db_session.flush()
    service = RecommendedService(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        description=f"Private recommended service {suffix}",
        priority=RecommendedServicePriority.SOON,
        notes="Private recommendation notes",
        is_resolved=False,
    )
    db_session.add(service)
    await db_session.flush()
    db_session.add(
        ProviderOutboxEvent(
            tenant_id=tenant.id,
            event_type="boundary.seed",
            aggregate_type="repair_order",
            aggregate_id=order.id,
            payload={"private": suffix},
            idempotency_key=f"recommended-boundary:{order.id}",
            status="pending",
            attempt_count=0,
            available_at=datetime.now(timezone.utc),
        )
    )
    return order, service, customer


def _requests(
    order_id: UUID,
    service_id: UUID,
) -> tuple[tuple[str, str, dict | None], ...]:
    base = f"/api/v1/repair-orders/{order_id}/recommended-services"
    return (
        ("get", base, None),
        (
            "post",
            base,
            {
                "description": "Attempted private recommendation",
                "priority": "soon",
            },
        ),
        (
            "patch",
            f"{base}/{service_id}",
            {"description": "Attempted private update"},
        ),
        ("delete", f"{base}/{service_id}", None),
    )


async def _send_requests(client, headers, order_id, service_id):
    responses = []
    for method, path, payload in _requests(order_id, service_id):
        kwargs = {"headers": headers}
        if payload is not None:
            kwargs["json"] = payload
        responses.append(await client.request(method, path, **kwargs))
    return responses


def _assert_generic_not_found(response) -> None:
    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == {"detail", "error", "correlation_id"}
    assert payload["detail"] == payload["error"] == "Repair order not found"
    assert "private" not in response.text.lower()


@pytest.mark.asyncio
async def test_recommended_service_family_hides_foreign_missing_and_deleted_orders(
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
    foreign_tenant = Tenant(name="Foreign tenant", slug=f"foreign-{suffix}")
    actor_tenant = Tenant(name="Actor tenant", slug=f"actor-{suffix}")
    db_session.add_all([foreign_tenant, actor_tenant])
    await db_session.flush()
    owner = User(
        tenant_id=actor_tenant.id,
        email=f"owner-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Actor",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    assigned_mechanic = User(
        tenant_id=actor_tenant.id,
        email=f"assigned-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Assigned",
        last_name="Mechanic",
        role=UserRole.MECHANIC,
        is_active=True,
        is_verified=True,
    )
    unassigned_mechanic = User(
        tenant_id=actor_tenant.id,
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
    foreign_order, foreign_service, _ = await _add_order(
        db_session,
        tenant=foreign_tenant,
        suffix=f"FOREIGN-{suffix}",
    )
    same_order, same_service, same_customer = await _add_order(
        db_session,
        tenant=actor_tenant,
        suffix=f"SAME-{suffix}",
        assigned_mechanic_id=assigned_mechanic.id,
    )
    deleted_order, deleted_service, _ = await _add_order(
        db_session,
        tenant=actor_tenant,
        suffix=f"DELETED-{suffix}",
        deleted=True,
    )
    db_session.add(
        UserCustomerLink(
            user_id=linked_customer.id,
            customer_id=same_customer.id,
            tenant_id=actor_tenant.id,
        )
    )
    await db_session.commit()

    owner_id = owner.id
    assigned_mechanic_id = assigned_mechanic.id
    unassigned_mechanic_id = unassigned_mechanic.id
    linked_customer_id = linked_customer.id
    foreign_target = (foreign_order.id, foreign_service.id)
    same_target = (same_order.id, same_service.id)
    deleted_target = (deleted_order.id, deleted_service.id)

    owner_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(owner_id)})}"
    }
    baseline = await _snapshot(db_session)
    not_found_cases = (
        foreign_target,
        deleted_target,
        (uuid4(), uuid4()),
    )
    for order_id, service_id in not_found_cases:
        responses = await _send_requests(
            client,
            owner_headers,
            order_id,
            service_id,
        )
        for response in responses:
            _assert_generic_not_found(response)
        assert await _snapshot(db_session) == baseline

    unassigned_headers = {
        "Authorization": (
            f"Bearer {create_access_token({'sub': str(unassigned_mechanic_id)})}"
        )
    }
    unassigned_responses = await _send_requests(
        client,
        unassigned_headers,
        *same_target,
    )
    assert [response.status_code for response in unassigned_responses] == [403] * 4
    assert await _snapshot(db_session) == baseline

    linked_headers = {
        "Authorization": (
            f"Bearer {create_access_token({'sub': str(linked_customer_id)})}"
        )
    }
    linked_responses = await _send_requests(
        client,
        linked_headers,
        *same_target,
    )
    assert [response.status_code for response in linked_responses] == [403] * 4
    assert await _snapshot(db_session) == baseline

    # Preserve successful staff and assigned-mechanic behavior across the family.
    created = await client.post(
        f"/api/v1/repair-orders/{same_target[0]}/recommended-services",
        json={"description": "Valid staff recommendation", "priority": "soon"},
        headers=owner_headers,
    )
    assert created.status_code == 201
    created_id = created.json()["id"]
    assigned_headers = {
        "Authorization": (
            f"Bearer {create_access_token({'sub': str(assigned_mechanic_id)})}"
        )
    }
    listed = await client.get(
        f"/api/v1/repair-orders/{same_target[0]}/recommended-services",
        headers=assigned_headers,
    )
    assert listed.status_code == 200
    assert created_id in {item["id"] for item in listed.json()}
    updated = await client.patch(
        (
            f"/api/v1/repair-orders/{same_target[0]}/recommended-services/"
            f"{created_id}"
        ),
        json={"description": "Valid assigned mechanic update"},
        headers=assigned_headers,
    )
    assert updated.status_code == 200
    deleted = await client.delete(
        (
            f"/api/v1/repair-orders/{same_target[0]}/recommended-services/"
            f"{created_id}"
        ),
        headers=owner_headers,
    )
    assert deleted.status_code == 204
    assert websocket_events == []
