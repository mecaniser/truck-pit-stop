from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.customer import Customer
from app.db.models.labor import Labor, LaborLineType
from app.db.models.labor_operation_memory import LaborOperationMemory
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
        nhtsa_make="FREIGHTLINER",
        nhtsa_model="CASCADIA",
        nhtsa_model_year=2021,
        nhtsa_vehicle_type="TRUCK",
        nhtsa_body_class="Truck-Tractor",
        nhtsa_drive_type="6x4",
        nhtsa_fuel_type="Diesel",
        nhtsa_engine_cylinders=6,
        nhtsa_engine_displacement_l=14.8,
        nhtsa_gvwr="Class 8",
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


async def _create_matching_order(db_session, tenant: Tenant):
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Taylor",
        last_name="Fleet",
        email=f"taylor-{uuid4().hex[:8]}@example.com",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2021,
        vin="1FUJHHDR8LSLA9999",
        nhtsa_make="FREIGHTLINER",
        nhtsa_model="CASCADIA",
        nhtsa_model_year=2021,
        nhtsa_vehicle_type="TRUCK",
        nhtsa_body_class="Truck-Tractor",
        nhtsa_drive_type="6x4",
        nhtsa_fuel_type="Diesel",
        nhtsa_engine_cylinders=6,
        nhtsa_engine_displacement_l=14.8,
        nhtsa_gvwr="Class 8",
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
    db_session.add_all([customer, vehicle, order])
    await db_session.commit()
    return customer, vehicle, order


@pytest.mark.asyncio
async def test_add_flat_service_line_recomputes_totals(db_session):
    _, _, _, order, service = await _seed_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)

    result = await svc.add_flat_service_line(db_session, loaded, service.id, quantity=2)

    assert result.order.total_parts_cost == Decimal("0.00")
    assert result.order.total_labor_cost == Decimal("200.00")
    assert result.order.total_cost == Decimal("200.00")
    assert len(result.order.labor_items) == 1
    assert result.order.labor_items[0].line_type == LaborLineType.MANUAL
    assert result.order.labor_items[0].source_service_id == service.id


@pytest.mark.asyncio
async def test_add_repair_operation_and_override_line(db_session):
    _, _, _, order, _ = await _seed_context(db_session)

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
    assert line.provider == "internal_library"
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
    refreshed_line = next(li for li in refreshed.labor_items if li.id == line.id)
    assert updated.order.total_labor_cost == Decimal("300.00")
    assert Decimal(str(refreshed_line.hours)) == Decimal("3.00")
    assert Decimal(str(refreshed_line.hourly_rate)) == Decimal("100.00")
    assert refreshed.total_cost == refreshed.total_labor_cost + refreshed.total_parts_cost


@pytest.mark.asyncio
async def test_search_repair_operations_returns_library_candidates(db_session):
    _, _, _, order, _ = await _seed_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)

    candidates, warnings = await svc.search_repair_operations(db_session, loaded, "brake")

    assert candidates
    assert candidates[0].operation_id == "brake-change"
    assert candidates[0].provider == "internal_library"
    assert warnings == []


@pytest.mark.asyncio
async def test_search_repair_operations_returns_custom_candidate_when_no_match(db_session):
    _, _, _, order, _ = await _seed_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)

    candidates, warnings = await svc.search_repair_operations(db_session, loaded, "king pin bushing")

    assert len(candidates) == 1
    assert candidates[0].operation_id == "custom:king-pin-bushing"
    assert candidates[0].provider == "internal_library"
    assert candidates[0].estimated_hours == Decimal("0.00")
    assert warnings
    assert warnings[0].code == "no_saved_match"


@pytest.mark.asyncio
async def test_recalculate_converts_legacy_flat_service_to_hourly_labor(db_session):
    tenant, _, _, order, service = await _seed_context(db_session)
    db_session.add(
        Labor(
            tenant_id=tenant.id,
            repair_order_id=order.id,
            description=service.name,
            hours=Decimal("2.00"),
            hourly_rate=Decimal("149.00"),
            total_cost=Decimal("298.00"),
            line_type=LaborLineType.FLAT_SERVICE,
            auto_recalc_enabled=True,
            source_service_id=service.id,
        )
    )
    await db_session.commit()

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    result = await svc.recalculate_order(db_session, loaded)

    assert result.order.total_labor_cost == Decimal("200.00")
    assert len(result.order.labor_items) == 1
    line = result.order.labor_items[0]
    assert line.line_type == LaborLineType.MANUAL
    assert Decimal(str(line.hourly_rate)) == Decimal("100.00")
    assert Decimal(str(line.total_cost)) == Decimal("200.00")


@pytest.mark.asyncio
async def test_internal_memory_reuses_saved_operation_across_matching_vehicle_signature(db_session):
    tenant, _, _, order, _ = await _seed_context(db_session)

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    created = await svc.add_repair_operation_line(
        db_session,
        loaded,
        operation_id="egr-replacement",
        name="EGR Replacement",
    )

    first_line = next(li for li in created.order.labor_items if li.provider_operation_id == "egr-replacement")
    await svc.update_line(
        db_session,
        created.order,
        line_id=first_line.id,
        hours=Decimal("7.25"),
    )

    memory_rows = await db_session.execute(select(LaborOperationMemory))
    stored = memory_rows.scalars().all()
    assert len(stored) == 1
    assert stored[0].provider_operation_id == "egr-replacement"
    assert Decimal(str(stored[0].normalized_hours)) == Decimal("7.25")

    _, _, second_order = await _create_matching_order(db_session, tenant)
    second_loaded = await svc.load_order(db_session, second_order.id)

    candidates, warnings = await svc.search_repair_operations(db_session, second_loaded, "egr")

    assert candidates
    assert candidates[0].provider == "internal_memory"
    assert candidates[0].operation_id == "egr-replacement"
    assert candidates[0].estimated_hours == Decimal("7.25")
    assert warnings
    assert warnings[0].code == "internal_memory_hit"

    second_result = await svc.add_repair_operation_line(
        db_session,
        second_loaded,
        operation_id="egr-replacement",
    )

    second_line = next(li for li in second_result.order.labor_items if li.provider_operation_id == "egr-replacement")
    assert Decimal(str(second_line.hours)) == Decimal("7.25")
    assert second_line.total_cost == Decimal("725.00")


@pytest.mark.asyncio
async def test_internal_memory_uses_nhtsa_signature_over_manual_vehicle_text(db_session):
    tenant, _, _, order, _ = await _seed_context(db_session)

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    created = await svc.add_repair_operation_line(
        db_session,
        loaded,
        operation_id="brake-change",
        name="Brake Change",
    )
    first_line = next(li for li in created.order.labor_items if li.provider_operation_id == "brake-change")
    await svc.update_line(
        db_session,
        created.order,
        line_id=first_line.id,
        hours=Decimal("4.25"),
    )

    customer = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Jordan",
        last_name="Dispatch",
        email=f"jordan-{uuid4().hex[:8]}@example.com",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner Trucks",
        model="Cascadia 126",
        year=2021,
        vin="1FUJHHDR8LSLA4567",
        nhtsa_make="FREIGHTLINER",
        nhtsa_model="CASCADIA",
        nhtsa_model_year=2021,
        nhtsa_vehicle_type="TRUCK",
        nhtsa_body_class="Truck-Tractor",
        nhtsa_drive_type="6x4",
        nhtsa_fuel_type="Diesel",
        nhtsa_engine_cylinders=6,
        nhtsa_engine_displacement_l=14.8,
        nhtsa_gvwr="Class 8",
    )
    second_order = RepairOrder(
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
    db_session.add_all([customer, vehicle, second_order])
    await db_session.commit()

    second_loaded = await svc.load_order(db_session, second_order.id)
    candidates, warnings = await svc.search_repair_operations(db_session, second_loaded, "brake")

    assert candidates
    assert candidates[0].provider == "internal_memory"
    assert candidates[0].estimated_hours == Decimal("4.25")
    assert warnings
    assert warnings[0].code == "internal_memory_hit"
