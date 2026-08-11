from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory, PartsUsage
from app.db.models.labor import Labor
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.service import Service, ServicePart
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


@pytest.mark.asyncio
async def test_cross_tenant_mechanic_additive_http_paths_are_generic_404_and_noop(
    client, db_session, monkeypatch
):
    from app.api.v1.endpoints import repair_orders

    websocket_events: list[dict] = []

    async def _capture_websocket(**event):
        websocket_events.append(event)

    monkeypatch.setattr(
        repair_orders, "broadcast_repair_order_update", _capture_websocket
    )
    suffix = uuid4().hex
    owner_tenant = Tenant(
        name="Order tenant",
        slug=f"order-tenant-{suffix}",
        labor_rate=Decimal("100.00"),
    )
    actor_tenant = Tenant(
        name="Actor tenant",
        slug=f"actor-tenant-{suffix}",
        labor_rate=Decimal("120.00"),
    )
    db_session.add_all([owner_tenant, actor_tenant])
    await db_session.flush()

    customer = Customer(
        tenant_id=owner_tenant.id,
        first_name="Tenant",
        last_name="Customer",
        email=f"customer-{suffix}@example.com",
    )
    db_session.add(customer)
    await db_session.flush()
    vehicle = Vehicle(
        tenant_id=owner_tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2024,
    )
    assigned_mechanic = User(
        tenant_id=owner_tenant.id,
        email=f"assigned-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Assigned",
        last_name="Mechanic",
        role=UserRole.MECHANIC,
        is_active=True,
        is_verified=True,
    )
    cross_tenant_mechanic = User(
        tenant_id=actor_tenant.id,
        email=f"cross-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Cross",
        last_name="Mechanic",
        role=UserRole.MECHANIC,
        is_active=True,
        is_verified=True,
    )
    unassigned_mechanic = User(
        tenant_id=owner_tenant.id,
        email=f"unassigned-{suffix}@example.com",
        hashed_password="hashed-password",
        first_name="Unassigned",
        last_name="Mechanic",
        role=UserRole.MECHANIC,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all(
        [vehicle, assigned_mechanic, cross_tenant_mechanic, unassigned_mechanic]
    )
    await db_session.flush()
    order = RepairOrder(
        tenant_id=owner_tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        assigned_mechanic_id=assigned_mechanic.id,
        order_number=f"RO-{suffix[:12]}",
        status=RepairOrderStatus.QUOTED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    deleted_order = RepairOrder(
        tenant_id=owner_tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        assigned_mechanic_id=unassigned_mechanic.id,
        order_number=f"RO-DELETED-{suffix[:8]}",
        status=RepairOrderStatus.QUOTED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
        deleted_at=datetime.now(timezone.utc),
    )
    inventory = Inventory(
        tenant_id=actor_tenant.id,
        sku=f"ACTOR-{suffix[:8]}",
        name="Actor tenant part",
        stock_quantity=5,
        cost=Decimal("10.00"),
        selling_price=Decimal("20.00"),
    )
    service = Service(
        tenant_id=actor_tenant.id,
        name="Actor tenant service",
        duration_minutes=60,
        is_active=True,
    )
    owner_inventory = Inventory(
        tenant_id=owner_tenant.id,
        sku=f"OWNER-{suffix[:8]}",
        name="Owner tenant part",
        stock_quantity=7,
        cost=Decimal("11.00"),
        selling_price=Decimal("21.00"),
    )
    owner_service = Service(
        tenant_id=owner_tenant.id,
        name="Owner tenant service",
        duration_minutes=60,
        is_active=True,
    )
    invalid_bundle_service = Service(
        tenant_id=owner_tenant.id,
        name="Invalid extreme bundle",
        duration_minutes=60,
        is_active=True,
    )
    db_session.add_all(
        [
            order,
            deleted_order,
            inventory,
            service,
            owner_inventory,
            owner_service,
            invalid_bundle_service,
        ]
    )
    await db_session.flush()
    db_session.add(
        ServicePart(
            tenant_id=owner_tenant.id,
            service_id=invalid_bundle_service.id,
            inventory_id=owner_inventory.id,
            quantity=Decimal("9999.99"),
        )
    )
    await db_session.flush()
    quote = Quote(
        tenant_id=owner_tenant.id,
        repair_order_id=order.id,
        quote_number=f"Q-{suffix[:12]}",
        total_amount=Decimal("0.00"),
        revision=1,
        authorization_type="initial_estimate",
        previously_authorized_amount=Decimal("0.00"),
        delta_amount=Decimal("0.00"),
        sent_to_customer=False,
        is_approved=False,
        is_declined=False,
    )
    db_session.add(quote)
    await db_session.commit()
    order_id = order.id
    inventory_id = inventory.id
    owner_inventory_id = owner_inventory.id
    owner_service_id = owner_service.id
    invalid_bundle_service_id = invalid_bundle_service.id
    deleted_order_id = deleted_order.id

    token = create_access_token({"sub": str(cross_tenant_mechanic.id)})
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/repair-orders/{order_id}"
    requests = (
        ("post", f"{base}/labor", {
            "description": "Cross tenant labor",
            "hours": "1.00",
            "hourly_rate": "120.00",
        }),
        ("post", f"{base}/parts", {
            "inventory_id": str(inventory_id),
            "quantity": "1.00",
            "allow_stock_shortage": True,
        }),
        ("post", f"{base}/price-build/flat-service", {
            "service_id": str(service.id),
            "quantity": 1,
        }),
        ("post", f"{base}/price-build/repair-ops/apply", {
            "operation_id": "custom:cross-tenant",
            "name": "Cross tenant operation",
            "estimated_hours": "1.00",
            "auto_recalc_enabled": False,
        }),
    )

    for method, path, payload in requests:
        response = await getattr(client, method)(path, json=payload, headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Repair order not found"

    unassigned_token = create_access_token({"sub": str(unassigned_mechanic.id)})
    unassigned_headers = {"Authorization": f"Bearer {unassigned_token}"}
    unassigned_requests = (
        (f"{base}/labor", {
            "description": "Unassigned labor",
            "hours": "1.00",
            "hourly_rate": "100.00",
        }),
        (f"{base}/parts", {
            "inventory_id": str(owner_inventory_id),
            "quantity": "1.00",
        }),
        (f"{base}/price-build/flat-service", {
            "service_id": str(owner_service_id),
            "quantity": 1,
        }),
        (f"{base}/price-build/repair-ops/apply", {
            "operation_id": "custom:unassigned",
            "name": "Unassigned operation",
            "estimated_hours": "1.00",
            "auto_recalc_enabled": False,
        }),
    )
    for path, payload in unassigned_requests:
        response = await client.post(path, json=payload, headers=unassigned_headers)
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

    def additive_requests(candidate_order_id):
        candidate_base = f"/api/v1/repair-orders/{candidate_order_id}"
        return (
            (f"{candidate_base}/labor", {
                "description": "No-op labor",
                "hours": "1.00",
                "hourly_rate": "100.00",
            }),
            (f"{candidate_base}/parts", {
                "inventory_id": str(owner_inventory_id),
                "quantity": "1.00",
            }),
            (f"{candidate_base}/price-build/flat-service", {
                "service_id": str(owner_service_id),
                "quantity": 1,
            }),
            (f"{candidate_base}/price-build/repair-ops/apply", {
                "operation_id": "custom:not-found",
                "name": "No-op operation",
                "estimated_hours": "1.00",
                "auto_recalc_enabled": False,
            }),
        )

    for candidate_order_id in (deleted_order_id, uuid4()):
        for path, payload in additive_requests(candidate_order_id):
            response = await client.post(
                path, json=payload, headers=unassigned_headers
            )
            assert response.status_code == 404
            assert response.json()["detail"] == "Repair order not found"

    assigned_token = create_access_token({"sub": str(assigned_mechanic.id)})
    assigned_headers = {"Authorization": f"Bearer {assigned_token}"}
    extreme_requests = (
        (f"{base}/parts", {
            "inventory_id": str(owner_inventory_id),
            "quantity": "9999.99",
            "allow_stock_shortage": True,
        }),
        (f"{base}/labor", {
            "description": "Extreme labor",
            "hours": "9999.99",
            "hourly_rate": "100.00",
        }),
        (f"{base}/price-build/repair-ops/apply", {
            "operation_id": "custom:extreme",
            "name": "Extreme operation",
            "estimated_hours": "9999.99",
            "auto_recalc_enabled": False,
        }),
        (f"{base}/price-build/flat-service", {
            "service_id": str(invalid_bundle_service_id),
            "quantity": 1,
        }),
    )
    for path, payload in extreme_requests:
        response = await client.post(path, json=payload, headers=assigned_headers)
        assert response.status_code == 422

    db_session.expire_all()
    persisted_order = await db_session.get(RepairOrder, order_id)
    persisted_inventory = await db_session.get(Inventory, inventory_id)
    persisted_owner_inventory = await db_session.get(Inventory, owner_inventory_id)
    assert persisted_order.total_parts_cost == Decimal("0.00")
    assert persisted_order.total_labor_cost == Decimal("0.00")
    assert persisted_order.total_cost == Decimal("0.00")
    assert persisted_inventory.stock_quantity == 5
    assert persisted_owner_inventory.stock_quantity == 7
    assert await db_session.scalar(
        select(func.count(Labor.id)).where(Labor.repair_order_id == order_id)
    ) == 0
    assert await db_session.scalar(
        select(func.count(PartsUsage.id)).where(PartsUsage.repair_order_id == order_id)
    ) == 0
    assert await db_session.scalar(
        select(func.count(RepairOrderHistoryEvent.id)).where(
            RepairOrderHistoryEvent.repair_order_id == order_id
        )
    ) == 0
    assert await db_session.scalar(
        select(func.count(Quote.id)).where(Quote.repair_order_id == order_id)
    ) == 1
    assert await db_session.scalar(select(func.count(ProviderOutboxEvent.id))) == 0
    assert websocket_events == []
