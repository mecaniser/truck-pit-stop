from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.v1.endpoints import dashboard, repair_orders
from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_read_model import RepairOrderReadModel
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


def _headers(user: User, tenant: Tenant) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id)}, tenant_id=str(tenant.id))
    return {"Authorization": f"Bearer {token}"}


async def _seed_shop(db_session, *, count: int = 55, total: Decimal = Decimal("12.34")):
    suffix = uuid4().hex
    tenant = Tenant(name="Value Shop", slug=f"value-{suffix}", timezone="America/New_York", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    owner = User(
        tenant_id=tenant.id,
        email=f"value-owner-{suffix}@example.test",
        hashed_password="x",
        first_name="Value",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    customer = Customer(
        tenant_id=tenant.id,
        first_name="Avery",
        last_name="Operator",
        company_name="Acme Hauling",
        email=f"value-customer-{suffix}@example.test",
    )
    db_session.add_all([owner, customer])
    await db_session.flush()
    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2024,
        unit_number="FLOOR-9",
    )
    db_session.add(vehicle)
    await db_session.flush()
    orders: list[RepairOrder] = []
    for index in range(count):
        order = RepairOrder(
            tenant_id=tenant.id,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            order_number=f"VALUE-{suffix[:6]}-{index:03d}",
            description="Brake service",
            status=RepairOrderStatus.IN_PROGRESS,
            total_parts_cost=Decimal("10.00"),
            total_labor_cost=Decimal("5.00"),
            labor_discount_amount=Decimal("1.00"),
            order_discount_amount=Decimal("1.66"),
            total_cost=total,
        )
        orders.append(order)
        db_session.add(order)
    await db_session.flush()
    for order in orders:
        db_session.add(
            RepairOrderReadModel(
                repair_order_id=order.id,
                tenant_id=tenant.id,
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                status=order.status.value,
                is_internal=False,
                is_deleted=False,
                created_at=order.created_at,
                search_document=f"{order.order_number} Acme Hauling Brake service Freightliner Cascadia FLOOR-9",
                search_compact=f"{order.order_number}AcmeHaulingFLOOR9".replace("-", ""),
                payload={},
            )
        )
    await db_session.commit()
    return tenant, owner, customer, vehicle, orders


def test_shop_work_row_uses_canonical_net_total_not_gross_subtotal():
    order = RepairOrder(
        total_parts_cost=Decimal("100.00"),
        total_labor_cost=Decimal("50.00"),
        labor_discount_amount=Decimal("10.00"),
        order_discount_amount=Decimal("15.00"),
        total_cost=Decimal("125.00"),
    )

    assert dashboard.get_effective_total(order) == Decimal("125.00")


@pytest.mark.asyncio
async def test_shop_work_summary_is_search_scoped_and_not_limited_to_fifty(client, db_session):
    tenant, owner, *_ = await _seed_shop(db_session)

    response = await client.get(
        "/api/v1/dashboard/daily-workset/value-summary",
        params={"lane": "on_floor", "search": "Acme Hauling"},
        headers=_headers(owner, tenant),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "order_count": 55,
        "order_value": "678.70",
        "currency": "USD",
        "amount_basis": "repair_order_net",
        "lane": "on_floor",
        "timezone": "America/New_York",
        "business_date": response.json()["business_date"],
    }


@pytest.mark.asyncio
async def test_repair_order_summary_matches_full_search_and_status_scope(client, db_session):
    tenant, owner, *_ = await _seed_shop(db_session)

    response = await client.get(
        "/api/v1/repair-orders/value-summary",
        params={"status": "in_progress", "search": "Acme Hauling"},
        headers=_headers(owner, tenant),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "order_count": 55,
        "order_value": "678.70",
        "currency": "USD",
        "amount_basis": "repair_order_net",
    }


@pytest.mark.asyncio
async def test_repair_order_summary_does_not_cross_tenants(client, db_session):
    tenant, owner, *_ = await _seed_shop(db_session, count=2, total=Decimal("20.00"))
    await _seed_shop(db_session, count=3, total=Decimal("999.00"))

    response = await client.get(
        "/api/v1/repair-orders/value-summary",
        headers=_headers(owner, tenant),
    )

    assert response.status_code == 200, response.text
    assert response.json()["order_count"] == 2
    assert response.json()["order_value"] == "40.00"


@pytest.mark.asyncio
async def test_shop_work_summary_matches_every_lane_and_distinct_all_union(client, db_session):
    tenant, owner, _, _, orders = await _seed_shop(db_session, count=5)
    statuses_and_values = [
        (RepairOrderStatus.DRAFT, Decimal("10.00")),
        (RepairOrderStatus.IN_PROGRESS, Decimal("20.00")),
        (RepairOrderStatus.COMPLETED, Decimal("30.00")),
        (RepairOrderStatus.PAID, Decimal("40.00")),
        (RepairOrderStatus.COMPLETED, Decimal("50.00")),
    ]
    for order, (status, value) in zip(orders, statuses_and_values, strict=True):
        order.status = status
        order.total_cost = value
    db_session.add_all([
        Invoice(
            tenant_id=tenant.id,
            repair_order_id=orders[3].id,
            invoice_number=f"VALUE-PAID-{uuid4().hex}",
            status=InvoiceStatus.PAID,
            subtotal=Decimal("40.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("40.00"),
            paid_at=datetime.now(timezone.utc),
        ),
        Invoice(
            tenant_id=tenant.id,
            repair_order_id=orders[4].id,
            invoice_number=f"VALUE-ZELLE-{uuid4().hex}",
            status=InvoiceStatus.SENT,
            subtotal=Decimal("50.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("50.00"),
            zelle_pending_submitted_at=datetime.now(timezone.utc),
        ),
    ])
    await db_session.commit()

    expected = {
        "needs_action": (2, "60.00"),
        "on_floor": (1, "20.00"),
        "ready_to_close": (1, "30.00"),
        "closed_today": (1, "40.00"),
        "all": (5, "150.00"),
    }
    for lane, (count, value) in expected.items():
        response = await client.get(
            "/api/v1/dashboard/daily-workset/value-summary",
            params={"lane": lane},
            headers=_headers(owner, tenant),
        )
        assert response.status_code == 200, (lane, response.text)
        assert response.json()["order_count"] == count, lane
        assert response.json()["order_value"] == value, lane


@pytest.mark.asyncio
async def test_repair_order_summary_projection_and_legacy_fallback_are_identical(client, db_session):
    tenant, owner, _, _, orders = await _seed_shop(db_session, count=3, total=Decimal("18.25"))
    headers = _headers(owner, tenant)

    projected = await client.get("/api/v1/repair-orders/value-summary", headers=headers)
    await db_session.execute(
        delete(RepairOrderReadModel).where(RepairOrderReadModel.repair_order_id == orders[-1].id)
    )
    await db_session.commit()
    fallback = await client.get("/api/v1/repair-orders/value-summary", headers=headers)

    assert projected.status_code == fallback.status_code == 200
    assert projected.json() == fallback.json() == {
        "order_count": 3,
        "order_value": "54.75",
        "currency": "USD",
        "amount_basis": "repair_order_net",
    }


@pytest.mark.asyncio
async def test_customer_principal_cannot_access_shop_repair_order_summary(client, db_session):
    tenant, _, customer, *_ = await _seed_shop(db_session, count=2)
    customer_user = User(
        tenant_id=tenant.id,
        customer_id=customer.id,
        email=f"value-customer-user-{uuid4().hex}@example.test",
        hashed_password="x",
        first_name="Customer",
        last_name="Viewer",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(customer_user)
    await db_session.commit()

    response = await client.get(
        "/api/v1/repair-orders/value-summary",
        headers=_headers(customer_user, tenant),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Shop access denied"


@pytest.mark.asyncio
async def test_driver_principal_is_denied_before_repair_order_summary_queries():
    driver = User(
        id=uuid4(),
        tenant_id=uuid4(),
        email=f"value-driver-{uuid4().hex}@example.test",
        hashed_password="x",
        first_name="Driver",
        last_name="Viewer",
        role=UserRole.DRIVER,
        is_active=True,
        is_verified=True,
    )
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await repair_orders.repair_order_value_summary(
            customer_id=None,
            vehicle_id=None,
            status=None,
            search=None,
            deleted=False,
            db=db,
            current_user=driver,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Shop access denied"
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_fleet_manager_summary_includes_only_internal_orders(client, db_session):
    tenant, _, _, _, orders = await _seed_shop(db_session, count=2, total=Decimal("25.00"))
    orders[0].is_internal = True
    projection = await db_session.get(RepairOrderReadModel, orders[0].id)
    assert projection is not None
    projection.is_internal = True
    fleet_manager = User(
        tenant_id=tenant.id,
        email=f"value-fleet-{uuid4().hex}@example.test",
        hashed_password="x",
        first_name="Fleet",
        last_name="Manager",
        role=UserRole.FLEET_MANAGER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(fleet_manager)
    await db_session.commit()

    response = await client.get(
        "/api/v1/repair-orders/value-summary",
        headers=_headers(fleet_manager, tenant),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "order_count": 1,
        "order_value": "25.00",
        "currency": "USD",
        "amount_basis": "repair_order_net",
    }


@pytest.mark.asyncio
async def test_repair_order_summary_foreign_vehicle_filter_is_empty(client, db_session):
    tenant, owner, *_ = await _seed_shop(db_session, count=2, total=Decimal("20.00"))
    _, _, _, foreign_vehicle, _ = await _seed_shop(db_session, count=1, total=Decimal("999.00"))

    response = await client.get(
        "/api/v1/repair-orders/value-summary",
        params={"vehicle_id": str(foreign_vehicle.id)},
        headers=_headers(owner, tenant),
    )

    assert response.status_code == 200, response.text
    assert response.json()["order_count"] == 0
    assert response.json()["order_value"] == "0.00"


@pytest.mark.asyncio
async def test_shop_work_summary_denies_nonstaff_principal(client, db_session):
    tenant, _, customer, *_ = await _seed_shop(db_session, count=1)
    customer_user = User(
        tenant_id=tenant.id,
        customer_id=customer.id,
        email=f"value-denied-{uuid4().hex}@example.test",
        hashed_password="x",
        first_name="Denied",
        last_name="Customer",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(customer_user)
    await db_session.commit()

    response = await client.get(
        "/api/v1/dashboard/daily-workset/value-summary",
        headers=_headers(customer_user, tenant),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Shop access denied"


def test_shop_work_row_floors_negative_persisted_total():
    assert dashboard.get_effective_total(RepairOrder(total_cost=Decimal("-0.01"))) == Decimal("0.00")


@pytest.mark.asyncio
async def test_invalid_daily_lane_is_rejected(client, db_session):
    tenant, owner, *_ = await _seed_shop(db_session, count=0)

    response = await client.get(
        "/api/v1/dashboard/daily-workset/value-summary",
        params={"lane": "somewhere_else"},
        headers=_headers(owner, tenant),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_repair_order_status_is_rejected(client, db_session):
    tenant, owner, *_ = await _seed_shop(db_session, count=0)

    response = await client.get(
        "/api/v1/repair-orders/value-summary",
        params={"status": "not_a_status"},
        headers=_headers(owner, tenant),
    )

    assert response.status_code == 422
