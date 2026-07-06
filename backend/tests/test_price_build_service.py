from __future__ import annotations

from datetime import datetime, timezone
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
async def test_custom_operation_preserves_user_entered_acronyms(db_session):
    _, _, _, order, _ = await _seed_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)

    candidates, _ = await svc.search_repair_operations(db_session, loaded, "DPF Cleaning")

    assert candidates[0].operation_id == "custom:dpf-cleaning"
    assert candidates[0].name == "DPF Cleaning"


@pytest.mark.asyncio
async def test_custom_operation_is_not_learned_until_hours_are_entered(db_session):
    tenant, _, _, order, _ = await _seed_context(db_session)
    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)

    created = await svc.add_repair_operation_line(
        db_session,
        loaded,
        operation_id="custom:tire-replacement",
        name="Tire Replacement",
        description="New custom repair operation. Save hours once and the system will reuse them next time.",
        estimated_hours=Decimal("0.00"),
    )

    first_line = next(li for li in created.order.labor_items if li.provider_operation_id == "custom:tire-replacement")
    assert Decimal(str(first_line.hours)) == Decimal("0.00")

    memory_rows = await db_session.execute(select(LaborOperationMemory))
    assert memory_rows.scalars().all() == []

    same_loaded = await svc.load_order(db_session, order.id)
    candidates, warnings = await svc.search_repair_operations(db_session, same_loaded, "tire replacement")
    assert len(candidates) == 1
    assert candidates[0].provider == "internal_library"
    assert candidates[0].operation_id == "custom:tire-replacement"
    assert candidates[0].estimated_hours == Decimal("0.00")
    assert warnings
    assert warnings[0].code == "no_saved_match"

    await svc.update_line(
        db_session,
        created.order,
        line_id=first_line.id,
        hours=Decimal("2.50"),
    )

    stored_rows = await db_session.execute(select(LaborOperationMemory))
    stored = stored_rows.scalars().all()
    assert len(stored) == 1
    assert stored[0].provider_operation_id == "custom:tire-replacement"
    assert Decimal(str(stored[0].normalized_hours)) == Decimal("2.50")

    learned_candidates, learned_warnings = await svc.search_repair_operations(db_session, same_loaded, "tire replacement")
    assert learned_candidates
    assert learned_candidates[0].provider == "internal_memory"
    assert learned_candidates[0].estimated_hours == Decimal("2.50")
    assert learned_warnings
    assert learned_warnings[0].code == "internal_memory_hit"


@pytest.mark.asyncio
async def test_zero_hour_memory_rows_are_ignored_for_known_operations(db_session):
    tenant, _, _, order, _ = await _seed_context(db_session)
    db_session.add(
        LaborOperationMemory(
            tenant_id=tenant.id,
            vehicle_signature=(
                "year:2021|make:freightliner|model:cascadia|vehicle_type:truck|"
                "body_class:truck-tractor|drive_type:6x4|fuel_type:diesel|"
                "engine_cylinders:6|engine_displacement_l:14.8|gvwr:class 8"
            ),
            operation_key="operation:brake-change",
            operation_name="Brake Change",
            operation_description="Bad zero-hour seed row",
            provider_operation_id="brake-change",
            source_provider="internal_memory",
            normalized_hours=Decimal("0.00"),
            usage_count=1,
            last_used_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)

    candidates, warnings = await svc.search_repair_operations(db_session, loaded, "brake")

    assert candidates
    assert candidates[0].provider == "internal_library"
    assert candidates[0].operation_id == "brake-change"
    assert candidates[0].estimated_hours == Decimal("2.50")
    assert warnings == []

    result = await svc.add_repair_operation_line(
        db_session,
        loaded,
        operation_id="brake-change",
    )

    line = next(li for li in result.order.labor_items if li.provider_operation_id == "brake-change")
    assert Decimal(str(line.hours)) == Decimal("2.50")

    refreshed = await svc.recalculate_order(db_session, result.order)
    refreshed_line = next(li for li in refreshed.order.labor_items if li.provider_operation_id == "brake-change")
    assert Decimal(str(refreshed_line.hours)) == Decimal("2.50")


@pytest.mark.asyncio
async def test_manual_labor_book_time_matches_by_application_signature(db_session):
    tenant, _, _, order, _ = await _seed_context(db_session)
    db_session.add(
        LaborOperationMemory(
            tenant_id=tenant.id,
            vehicle_signature="year:2021|make:freightliner|model:cascadia",
            component_signature="engine:detroit dd15",
            operation_key="custom:water-pump-replacement:detroit-dd15-freightliner-cascadia-2021",
            operation_name="Water Pump Replacement",
            operation_description="Manual book time from motor information system",
            vehicle_year=2021,
            vehicle_make="Freightliner",
            vehicle_model="Cascadia",
            engine="Detroit DD15",
            provider_operation_id="custom:water-pump-replacement:detroit-dd15-freightliner-cascadia-2021",
            source_provider="manual_book_time",
            normalized_hours=Decimal("8.00"),
            usage_count=1,
            last_used_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)

    candidates, warnings = await svc.search_repair_operations(db_session, loaded, "water pump")

    assert candidates
    assert candidates[0].name == "Water Pump Replacement"
    assert candidates[0].provider == "internal_memory"
    assert candidates[0].estimated_hours == Decimal("8.00")
    assert warnings and warnings[0].code == "internal_memory_hit"


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


@pytest.mark.asyncio
async def test_component_memory_hit_on_different_model_same_engine(db_session):
    """Memory learned on one truck model surfaces on a different model with the same engine."""
    tenant, _, _, order, _ = await _seed_context(db_session)  # Freightliner Cascadia, 6-cyl diesel 14.8L

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    created = await svc.add_repair_operation_line(
        db_session, loaded, operation_id="egr-replacement", name="EGR Replacement",
    )
    first_line = next(li for li in created.order.labor_items if li.provider_operation_id == "egr-replacement")
    await svc.update_line(db_session, created.order, line_id=first_line.id, hours=Decimal("6.50"))

    # Different make/model but identical engine: fuel=Diesel, cylinders=6, displacement=14.8L
    customer2 = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="Sam",
        last_name="Fleet",
        email=f"sam-{uuid4().hex[:8]}@example.com",
    )
    vehicle2 = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer2.id,
        make="Kenworth",
        model="T680",
        year=2022,
        nhtsa_make="KENWORTH",
        nhtsa_model="T680",
        nhtsa_model_year=2022,
        nhtsa_vehicle_type="TRUCK",
        nhtsa_body_class="Truck-Tractor",
        nhtsa_drive_type="6x2",
        nhtsa_fuel_type="Diesel",
        nhtsa_engine_cylinders=6,
        nhtsa_engine_displacement_l=14.8,
        nhtsa_gvwr="Class 8",
    )
    order2 = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer2.id,
        vehicle_id=vehicle2.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.DRAFT,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    db_session.add_all([customer2, vehicle2, order2])
    await db_session.commit()

    loaded2 = await svc.load_order(db_session, order2.id)
    candidates, warnings = await svc.search_repair_operations(db_session, loaded2, "egr")

    assert candidates
    assert candidates[0].provider == "internal_memory"
    assert candidates[0].estimated_hours == Decimal("6.50")
    assert warnings
    assert warnings[0].code == "component_memory_hit"


@pytest.mark.asyncio
async def test_vehicle_match_takes_priority_over_component_match(db_session):
    """When both a vehicle-sig and a component-sig row exist, the vehicle-sig hours win."""
    tenant, _, _, order, _ = await _seed_context(db_session)

    svc = PriceBuildService()

    # Save 7.00h on the Cascadia (vehicle-sig match for future Cascadia lookups)
    loaded = await svc.load_order(db_session, order.id)
    created1 = await svc.add_repair_operation_line(
        db_session, loaded, operation_id="egr-replacement", name="EGR Replacement",
    )
    line1 = next(li for li in created1.order.labor_items if li.provider_operation_id == "egr-replacement")
    await svc.update_line(db_session, created1.order, line_id=line1.id, hours=Decimal("7.00"))

    # Save 5.00h on a Kenworth with the same engine (component-sig match only)
    customer2 = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="B",
        last_name="B",
        email=f"b-{uuid4().hex[:8]}@example.com",
    )
    vehicle2 = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer2.id,
        make="Kenworth",
        model="T680",
        year=2022,
        nhtsa_make="KENWORTH",
        nhtsa_model="T680",
        nhtsa_model_year=2022,
        nhtsa_vehicle_type="TRUCK",
        nhtsa_body_class="Truck-Tractor",
        nhtsa_drive_type="6x2",
        nhtsa_fuel_type="Diesel",
        nhtsa_engine_cylinders=6,
        nhtsa_engine_displacement_l=14.8,
        nhtsa_gvwr="Class 8",
    )
    order2 = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer2.id,
        vehicle_id=vehicle2.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.DRAFT,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    db_session.add_all([customer2, vehicle2, order2])
    await db_session.commit()

    loaded2 = await svc.load_order(db_session, order2.id)
    created2 = await svc.add_repair_operation_line(
        db_session, loaded2, operation_id="egr-replacement", name="EGR Replacement",
    )
    line2 = next(li for li in created2.order.labor_items if li.provider_operation_id == "egr-replacement")
    await svc.update_line(db_session, created2.order, line_id=line2.id, hours=Decimal("5.00"))

    # Search on the original Cascadia: should get its own 7.00h, not the Kenworth's 5.00h
    loaded_orig = await svc.load_order(db_session, order.id)
    candidates, warnings = await svc.search_repair_operations(db_session, loaded_orig, "egr")

    assert candidates
    assert candidates[0].estimated_hours == Decimal("7.00")
    assert warnings[0].code == "internal_memory_hit"  # vehicle match, not component


@pytest.mark.asyncio
async def test_component_match_requires_minimum_engine_fields(db_session):
    """A vehicle missing enough engine fields produces no component signature and no component fallback."""
    tenant, _, _, order, _ = await _seed_context(db_session)

    svc = PriceBuildService()
    loaded = await svc.load_order(db_session, order.id)
    created = await svc.add_repair_operation_line(
        db_session, loaded, operation_id="egr-replacement", name="EGR Replacement",
    )
    line = next(li for li in created.order.labor_items if li.provider_operation_id == "egr-replacement")
    await svc.update_line(db_session, created.order, line_id=line.id, hours=Decimal("6.50"))

    # Vehicle with only fuel_type — not enough for a component signature (need ≥2 fields)
    customer2 = Customer(
        id=uuid4(),
        tenant_id=tenant.id,
        first_name="C",
        last_name="C",
        email=f"c-{uuid4().hex[:8]}@example.com",
    )
    vehicle2 = Vehicle(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer2.id,
        make="Peterbilt",
        model="579",
        year=2020,
        nhtsa_make="PETERBILT",
        nhtsa_model="579",
        nhtsa_model_year=2020,
        nhtsa_vehicle_type="TRUCK",
        nhtsa_fuel_type="Diesel",
        nhtsa_engine_cylinders=None,
        nhtsa_engine_displacement_l=None,
        nhtsa_gvwr="Class 8",
    )
    order2 = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer2.id,
        vehicle_id=vehicle2.id,
        order_number=f"RO-{uuid4().hex[:8]}",
        status=RepairOrderStatus.DRAFT,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("0.00"),
        total_cost=Decimal("0.00"),
    )
    db_session.add_all([customer2, vehicle2, order2])
    await db_session.commit()

    loaded2 = await svc.load_order(db_session, order2.id)
    candidates, warnings = await svc.search_repair_operations(db_session, loaded2, "egr")

    # No vehicle sig match, no component sig → falls through to library only
    assert candidates
    assert candidates[0].provider == "internal_library"
    assert warnings == []
