from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.customer import Customer
from app.db.models.labor import LaborLineType
from app.db.models.motor_operation_cache import MotorOperationCache
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.service import Service
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.services.price_build_service import PriceBuildService


async def _seed_context(db_session):
    tenant = Tenant(
        id=uuid4(),
        name="Test Garage",
        slug=f"test-garage-{uuid4().hex[:8]}",
        labor_rate=Decimal("100.00"),
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Alex",
        last_name="Driver",
        email=f"alex-{uuid4().hex[:8]}@example.com",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2021,
        vin="3AKJHHDR8LSLA7890",
    )
    order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.DRAFT,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    service = Service(
        id=uuid4(),
        tenant_id=tenant.id,
        name="DOT Inspection",
        description="Annual DOT inspection",
        duration_minutes=60,
        base_price=Decimal("149.00"),
        is_active=True,
        requires_vehicle=True,
    )

    db_session.add_all([tenant, customer, vehicle, order, service])
    await db_session.commit()
    return tenant, customer, vehicle, order, service


@pytest.mark.asyncio
async def test_add_flat_service_line_recomputes_totals(db_session):
    _, _, _, order, service = await _seed_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)

    result = await svc.add_flat_service_line(db_session, loaded, service.id, quantity=2)

    assert result.order.total_parts_cost == Decimal("0.00")
    assert result.order.total_labor_cost == Decimal("298.00")
    assert result.order.total_cost == Decimal("298.00")
    assert len(result.order.labor_items) == 1
    assert result.order.labor_items[0].line_type == LaborLineType.FLAT_SERVICE
    assert result.order.labor_items[0].source_service_id == service.id


@pytest.mark.asyncio
async def test_add_repair_operation_and_override_line(db_session, monkeypatch):
    _, _, _, order, _ = await _seed_context(db_session)
    monkeypatch.setattr("app.services.price_build_service.settings.MOTOR_ENABLED", False)

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    result = await svc.add_repair_operation_line(
        db_session,
        loaded,
        operation_id="egr-replacement",
    )

    repair_lines = [li for li in result.order.labor_items if li.line_type == LaborLineType.REPAIR_OPERATION]
    assert len(repair_lines) == 1
    line = repair_lines[0]
    assert line.provider == "motor"
    assert line.provider_operation_id == "egr-replacement"
    assert Decimal(str(line.hours)) > Decimal("0.00")

    updated = await svc.update_line(
        db_session,
        result.order,
        line_id=line.id,
        hours=Decimal("3.00"),
        hourly_rate=Decimal("150.00"),
    )
    refreshed = await svc.load_order(db_session, order.id)
    assert updated.order.total_labor_cost >= Decimal("450.00")
    assert refreshed.total_cost == refreshed.total_labor_cost + refreshed.total_parts_cost


@pytest.mark.asyncio
async def test_search_repair_operations_uses_cache(db_session, monkeypatch):
    _, _, _, order, _ = await _seed_context(db_session)
    monkeypatch.setattr("app.services.price_build_service.settings.MOTOR_ENABLED", False)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)

    first, _ = await svc.search_repair_operations(db_session, loaded, "brake")
    second, _ = await svc.search_repair_operations(db_session, loaded, "brake")

    assert first
    assert second
    assert first[0].operation_id == second[0].operation_id

    cache_rows = await db_session.execute(select(MotorOperationCache))
    assert len(cache_rows.scalars().all()) >= 1
