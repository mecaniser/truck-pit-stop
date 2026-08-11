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


async def _database_snapshot(db_session) -> tuple:
    """Freeze every financial/audit surface that a rejected mutation could touch."""
    await db_session.rollback()
    db_session.expire_all()
    snapshot = []
    for model in SNAPSHOT_MODELS:
        rows = (
            await db_session.execute(select(model).order_by(model.id))
        ).scalars().all()
        snapshot.append(
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
    return tuple(snapshot)


async def _add_priced_order(
    db_session,
    *,
    tenant: Tenant,
    suffix: str,
    deleted: bool,
) -> tuple[RepairOrder, Labor, PartsUsage]:
    customer = Customer(
        tenant_id=tenant.id,
        first_name="Tenant",
        last_name="Boundary",
        email=f"customer-{suffix}@example.com",
    )
    db_session.add(customer)
    await db_session.flush()
    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2024,
    )
    inventory = Inventory(
        tenant_id=tenant.id,
        sku=f"PART-{suffix}",
        name=f"Boundary part {suffix}",
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
        order_number=f"RO-{suffix}",
        status=RepairOrderStatus.QUOTED,
        total_labor_cost=Decimal("100.00"),
        total_parts_cost=Decimal("20.00"),
        labor_discount_amount=Decimal("5.00"),
        order_discount_amount=Decimal("3.00"),
        total_cost=Decimal("112.00"),
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    db_session.add(order)
    await db_session.flush()
    labor = Labor(
        tenant_id=tenant.id,
        repair_order_id=order.id,
        description="Existing diagnostic",
        hours=Decimal("1.00"),
        hourly_rate=Decimal("100.00"),
        total_cost=Decimal("100.00"),
        line_type=LaborLineType.MANUAL,
        auto_recalc_enabled=False,
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
    db_session.add_all(
        [
            RepairOrderHistoryEvent(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                event_type="seed_boundary",
                label="Existing history",
                detail="Must remain unchanged",
                entity_id=labor.id,
            ),
            Quote(
                tenant_id=tenant.id,
                repair_order_id=order.id,
                quote_number=f"Q-{suffix}",
                total_amount=Decimal("112.00"),
                revision=1,
                authorization_type="initial_estimate",
                previously_authorized_amount=Decimal("0.00"),
                delta_amount=Decimal("112.00"),
                sent_to_customer=False,
                is_approved=False,
                is_declined=False,
            ),
            ProviderOutboxEvent(
                tenant_id=tenant.id,
                event_type="boundary.seed",
                aggregate_type="repair_order",
                aggregate_id=order.id,
                payload={"repair_order_id": str(order.id)},
                idempotency_key=f"boundary:{order.id}",
                status="pending",
                attempt_count=0,
                available_at=datetime.now(timezone.utc),
            ),
        ]
    )
    return order, labor, part


def _mutation_requests(
    order_id: UUID,
    labor_id: UUID,
    part_id: UUID,
) -> tuple[tuple[str, str, dict | None], ...]:
    base = f"/api/v1/repair-orders/{order_id}"
    return (
        ("patch", f"{base}/price-build/lines/{labor_id}", {"description": "Changed"}),
        ("delete", f"{base}/price-build/lines/{labor_id}", None),
        ("post", f"{base}/price-build/recalculate", None),
        (
            "post",
            f"{base}/price-build/sublet",
            {
                "description": "Foreign sublet",
                "vendor_name": "Foreign vendor",
                "vendor_cost": "50.00",
                "charge_to_customer": "75.00",
            },
        ),
        ("post", f"{base}/parts/pricing-mode", {"mode": "list"}),
        ("patch", f"{base}/discounts", {"labor_discount_amount": "1.00"}),
        ("delete", f"{base}/parts/{part_id}", None),
        ("put", f"{base}/labor/{labor_id}", {"description": "Changed"}),
        ("delete", f"{base}/labor/{labor_id}", None),
        ("patch", f"{base}/parts/{part_id}", {"quantity": "2.00"}),
    )


def _assert_generic_order_not_found(response) -> None:
    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == {"detail", "error", "correlation_id"}
    assert payload["detail"] == "Repair order not found"
    assert payload["error"] == payload["detail"]
    UUID(payload["correlation_id"])


@pytest.mark.asyncio
async def test_price_mutations_hide_foreign_missing_and_deleted_orders_without_writes(
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
    order_tenant = Tenant(name="Order tenant", slug=f"order-{suffix}")
    actor_tenant = Tenant(name="Actor tenant", slug=f"actor-{suffix}")
    db_session.add_all([order_tenant, actor_tenant])
    await db_session.flush()
    actor = User(
        tenant_id=actor_tenant.id,
        email=f"owner-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Actor",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(actor)
    await db_session.flush()
    foreign_order, foreign_labor, foreign_part = await _add_priced_order(
        db_session,
        tenant=order_tenant,
        suffix=f"FOREIGN-{suffix}",
        deleted=False,
    )
    deleted_order, deleted_labor, deleted_part = await _add_priced_order(
        db_session,
        tenant=actor_tenant,
        suffix=f"DELETED-{suffix}",
        deleted=True,
    )
    await db_session.commit()

    token = create_access_token({"sub": str(actor.id)})
    headers = {"Authorization": f"Bearer {token}"}
    missing_id = uuid4()
    cases = (
        (foreign_order.id, foreign_labor.id, foreign_part.id),
        (deleted_order.id, deleted_labor.id, deleted_part.id),
        (missing_id, uuid4(), uuid4()),
    )
    baseline = await _database_snapshot(db_session)

    for order_id, labor_id, part_id in cases:
        for method, path, payload in _mutation_requests(order_id, labor_id, part_id):
            request_kwargs = {"headers": headers}
            if payload is not None:
                request_kwargs["json"] = payload
            response = await client.request(method, path, **request_kwargs)
            _assert_generic_order_not_found(response)
            assert await _database_snapshot(db_session) == baseline

    # Adjacent price-builder reads use the same tenant-scoped entry point.
    for order_id, _, _ in cases:
        summary = await client.get(
            f"/api/v1/repair-orders/{order_id}/price-build",
            headers=headers,
        )
        search = await client.post(
            f"/api/v1/repair-orders/{order_id}/price-build/repair-ops/search",
            json={"query": "diagnostic"},
            headers=headers,
        )
        _assert_generic_order_not_found(summary)
        _assert_generic_order_not_found(search)
        assert await _database_snapshot(db_session) == baseline

    assert websocket_events == []
