"""Fleet workflows: weekly inspections, incidents, and incident-to-repair spawning."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from uuid import uuid4
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import fleet
from app.db.models.customer import Customer
from app.db.models.fleet import (
    InspectionResult,
    InspectionStatus,
    InspectionItemResult,
    IncidentStatus,
    IncidentSeverity,
    DEFAULT_INSPECTION_CHECKLIST,
)
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.fleet import (
    InspectionCreate,
    InspectionComplete,
    InspectionItemUpdate,
    IncidentCreate,
    IncidentUpdate,
    WorkOrderCreate,
)
from app.services.internal_fleet import ensure_internal_fleet_customer


async def _seed_fleet(db_session, *, role=UserRole.FLEET_MANAGER):
    tenant = Tenant(id=uuid4(), name="Fleet Garage", slug=f"fg-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.commit()

    fleet_customer = await ensure_internal_fleet_customer(db_session, tenant.id)
    await db_session.commit()

    vehicle = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=fleet_customer.id,
        make="Freightliner", model="Cascadia", year=2020, unit_number="T-12",
    )
    user = User(
        id=uuid4(), tenant_id=tenant.id, email=f"u-{uuid4().hex[:8]}@example.com",
        hashed_password="x", first_name="Fleet", last_name="Mgr",
        role=role, is_active=True, is_verified=True,
    )
    db_session.add_all([vehicle, user])
    await db_session.commit()
    return tenant, vehicle, user


@pytest.mark.asyncio
async def test_create_inspection_instantiates_checklist(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user
    )
    assert detail.status == InspectionStatus.SCHEDULED
    assert len(detail.items) == len(DEFAULT_INSPECTION_CHECKLIST)
    assert all(i.result == InspectionItemResult.PENDING for i in detail.items)


@pytest.mark.asyncio
async def test_complete_inspection_all_pass(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user
    )
    for item in detail.items:
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=item.id,
            body=InspectionItemUpdate(result=InspectionItemResult.PASS),
            db=db_session, current_user=user,
        )
    completed = await fleet.complete_inspection(
        inspection_id=detail.id, body=InspectionComplete(odometer=120000),
        db=db_session, current_user=user,
    )
    assert completed.status == InspectionStatus.COMPLETED
    assert completed.result == InspectionResult.PASS
    assert completed.performed_at is not None
    assert completed.inspector_id == user.id


@pytest.mark.asyncio
async def test_complete_inspection_with_failure(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user
    )
    for idx, item in enumerate(detail.items):
        res = InspectionItemResult.FAIL if idx == 0 else InspectionItemResult.PASS
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=item.id,
            body=InspectionItemUpdate(result=res), db=db_session, current_user=user,
        )
    completed = await fleet.complete_inspection(
        inspection_id=detail.id, body=InspectionComplete(), db=db_session, current_user=user
    )
    assert completed.result == InspectionResult.FAIL


@pytest.mark.asyncio
async def test_complete_inspection_rejects_pending_items(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user
    )
    with pytest.raises(HTTPException) as exc:
        await fleet.complete_inspection(
            inspection_id=detail.id, body=InspectionComplete(), db=db_session, current_user=user
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_roster_overdue_then_current(db_session):
    _, vehicle, user = await _seed_fleet(db_session)

    # Never inspected -> overdue.
    roster = await fleet.list_fleet_vehicles(db=db_session, current_user=user)
    assert len(roster) == 1
    assert roster[0].inspection_overdue is True
    assert roster[0].next_inspection_due is None

    # Complete an inspection -> not overdue, next due ~7 days out.
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user
    )
    for item in detail.items:
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=item.id,
            body=InspectionItemUpdate(result=InspectionItemResult.PASS),
            db=db_session, current_user=user,
        )
    await fleet.complete_inspection(
        inspection_id=detail.id, body=InspectionComplete(), db=db_session, current_user=user
    )
    roster = await fleet.list_fleet_vehicles(db=db_session, current_user=user)
    assert roster[0].inspection_overdue is False
    today = datetime.now(timezone.utc).date()
    assert roster[0].next_inspection_due == today + timedelta(days=7)


@pytest.mark.asyncio
async def test_incident_create_and_spawn_internal_repair(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    incident = await fleet.create_incident(
        body=IncidentCreate(
            vehicle_id=vehicle.id,
            occurred_at=datetime.now(timezone.utc),
            location="I-85 mile 42",
            severity=IncidentSeverity.HIGH,
            description="Blowout on front left tire",
        ),
        db=db_session, current_user=user,
    )
    assert incident.status == IncidentStatus.OPEN
    assert incident.repair_order_id is None

    updated = await fleet.create_repair_for_incident(
        incident_id=incident.id, db=db_session, current_user=user
    )
    assert updated.repair_order_id is not None
    assert updated.status == IncidentStatus.IN_PROGRESS

    ro = (await db_session.execute(
        __import__("sqlalchemy").select(RepairOrder).where(RepairOrder.id == updated.repair_order_id)
    )).scalar_one()
    assert ro.is_internal is True
    assert ro.vehicle_id == vehicle.id


@pytest.mark.asyncio
async def test_incident_resolve_sets_resolved_at(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    incident = await fleet.create_incident(
        body=IncidentCreate(
            vehicle_id=vehicle.id, occurred_at=datetime.now(timezone.utc),
            description="Minor fender scrape",
        ),
        db=db_session, current_user=user,
    )
    resolved = await fleet.update_incident(
        incident_id=incident.id,
        body=IncidentUpdate(status=IncidentStatus.RESOLVED, resolution_notes="Buffed out"),
        db=db_session, current_user=user,
    )
    assert resolved.status == IncidentStatus.RESOLVED
    assert resolved.resolved_at is not None


@pytest.mark.asyncio
async def test_fleet_access_denied_for_mechanic(db_session):
    _, _, mechanic = await _seed_fleet(db_session, role=UserRole.MECHANIC)
    with pytest.raises(HTTPException) as exc:
        fleet.require_fleet_access(current_user=mechanic)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_inspection_rejects_non_fleet_vehicle(db_session):
    tenant, _, user = await _seed_fleet(db_session)
    # External (non-fleet) customer + vehicle in the same tenant.
    ext_customer = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Acme", last_name="Co",
        email=f"acme-{uuid4().hex[:6]}@example.com",
    )
    ext_vehicle = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=ext_customer.id,
        make="Volvo", model="VNL", year=2019,
    )
    db_session.add_all([ext_customer, ext_vehicle])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await fleet.create_inspection(
            body=InspectionCreate(vehicle_id=ext_vehicle.id), db=db_session, current_user=user
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_new_work_order_uses_description(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    await fleet.new_work_order(
        vehicle_id=vehicle.id, body=WorkOrderCreate(description="Air leak on front brake chamber"),
        db=db_session, current_user=user,
    )
    ro = (await db_session.execute(
        __import__("sqlalchemy").select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id)
    )).scalar_one()
    assert ro.description == "Air leak on front brake chamber"
    assert ro.is_internal is True and ro.is_pm is False


@pytest.mark.asyncio
async def test_new_work_order_defaults_blank_description(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    await fleet.new_work_order(vehicle_id=vehicle.id, body=WorkOrderCreate(description="   "),
                               db=db_session, current_user=user)
    ro = (await db_session.execute(
        __import__("sqlalchemy").select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id)
    )).scalar_one()
    assert ro.description == "Fleet work order"


@pytest.mark.asyncio
async def test_truck_allows_multiple_open_work_orders(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    await fleet.new_work_order(vehicle_id=vehicle.id, body=WorkOrderCreate(description="First"),
                               db=db_session, current_user=user)
    truck = await fleet.new_work_order(vehicle_id=vehicle.id, body=WorkOrderCreate(description="Second"),
                                       db=db_session, current_user=user)
    # No 409 anymore; the board card reflects the count.
    assert truck.open_work_order_count == 2
    board = await fleet.fleet_board(db=db_session, current_user=user)
    bt = next(t for t in board.trucks if t.id == vehicle.id)
    assert bt.open_work_order_count == 2
    detail = await fleet.truck_detail(vehicle_id=vehicle.id, db=db_session, current_user=user)
    assert len(detail.open_work_orders) == 2


@pytest.mark.asyncio
async def test_list_fleet_mechanics_returns_tenant_mechanics(db_session):
    tenant, _, user = await _seed_fleet(db_session)
    mech = User(
        id=uuid4(), tenant_id=tenant.id, email=f"m-{uuid4().hex[:8]}@example.com",
        hashed_password="x", first_name="Mick", last_name="Wrench",
        role=UserRole.MECHANIC, is_active=True, is_verified=True,
    )
    inactive = User(
        id=uuid4(), tenant_id=tenant.id, email=f"m2-{uuid4().hex[:8]}@example.com",
        hashed_password="x", first_name="Gone", last_name="Away",
        role=UserRole.MECHANIC, is_active=False, is_verified=True,
    )
    db_session.add_all([mech, inactive])
    await db_session.commit()

    options = await fleet.list_fleet_mechanics(db=db_session, current_user=user)
    names = {o.name for o in options}
    assert "Mick Wrench" in names
    assert "Gone Away" not in names  # inactive excluded


@pytest.mark.asyncio
async def test_fleet_settings_returns_internal_labor_rate(db_session):
    tenant, _, user = await _seed_fleet(db_session)
    tenant.internal_labor_rate = 65
    await db_session.commit()
    settings = await fleet.get_fleet_settings(db=db_session, current_user=user)
    assert settings.internal_labor_rate == 65.0


@pytest.mark.asyncio
async def test_fresh_work_order_shows_draft_status(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    await fleet.new_work_order(vehicle_id=vehicle.id, body=WorkOrderCreate(description="Brakes"),
                               db=db_session, current_user=user)
    board = await fleet.fleet_board(db=db_session, current_user=user)
    truck = next(t for t in board.trucks if t.id == vehicle.id)
    assert truck.status == "draft"
    assert truck.work_order is not None and truck.work_order.status == "Draft"


@pytest.mark.asyncio
async def test_fleet_lifecycle_start_and_complete_without_mechanic(db_session):
    import sqlalchemy
    _, vehicle, user = await _seed_fleet(db_session)
    await fleet.new_work_order(vehicle_id=vehicle.id, body=WorkOrderCreate(description="Brakes"),
                               db=db_session, current_user=user)
    ro = (await db_session.execute(
        sqlalchemy.select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id)
    )).scalar_one()
    assert ro.assigned_mechanic_id is None  # mechanic optional

    wo = await fleet.start_work_order(ro_id=ro.id, db=db_session, current_user=user)
    assert wo.status == "In progress"
    await db_session.refresh(ro)
    assert ro.status == RepairOrderStatus.IN_PROGRESS and ro.work_started_at is not None

    await fleet.complete_work_order(ro_id=ro.id, db=db_session, current_user=user)
    await db_session.refresh(ro)
    assert ro.status == RepairOrderStatus.COMPLETED and ro.work_completed_at is not None


@pytest.mark.asyncio
async def test_complete_requires_in_progress(db_session):
    import sqlalchemy
    _, vehicle, user = await _seed_fleet(db_session)
    await fleet.new_work_order(vehicle_id=vehicle.id, body=WorkOrderCreate(description="Brakes"),
                               db=db_session, current_user=user)
    ro = (await db_session.execute(
        sqlalchemy.select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id)
    )).scalar_one()
    with pytest.raises(HTTPException) as exc:
        await fleet.complete_work_order(ro_id=ro.id, db=db_session, current_user=user)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_complete_generates_internal_invoice(db_session):
    import sqlalchemy
    from app.db.models.invoice import Invoice
    _, vehicle, user = await _seed_fleet(db_session)
    await fleet.new_work_order(vehicle_id=vehicle.id, body=WorkOrderCreate(description="Brakes"),
                               db=db_session, current_user=user)
    ro = (await db_session.execute(
        sqlalchemy.select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id)
    )).scalar_one()
    await fleet.start_work_order(ro_id=ro.id, db=db_session, current_user=user)
    await fleet.complete_work_order(ro_id=ro.id, db=db_session, current_user=user)

    inv = (await db_session.execute(
        sqlalchemy.select(Invoice).where(Invoice.repair_order_id == ro.id)
    )).scalar_one()
    assert inv.is_internal is True
    assert inv.tax_amount == 0 and inv.service_fee_amount == 0

    # Idempotent: completing/calling again doesn't create a second invoice.
    await fleet._create_internal_invoice(db_session, ro.tenant_id, ro)
    count = (await db_session.execute(
        sqlalchemy.select(sqlalchemy.func.count(Invoice.id)).where(Invoice.repair_order_id == ro.id)
    )).scalar()
    assert count == 1
