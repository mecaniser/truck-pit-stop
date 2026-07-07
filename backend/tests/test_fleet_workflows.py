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
    WorkOrderComplete,
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
        inspection_id=detail.id, body=InspectionComplete(odometer=125000), db=db_session, current_user=user
    )
    assert completed.result == InspectionResult.FAIL


@pytest.mark.asyncio
async def test_complete_inspection_updates_vehicle_mileage(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 100000
    await db_session.commit()
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user
    )
    for item in detail.items:
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=item.id,
            body=InspectionItemUpdate(result=InspectionItemResult.PASS), db=db_session, current_user=user,
        )
    await fleet.complete_inspection(
        inspection_id=detail.id, body=InspectionComplete(odometer=112500), db=db_session, current_user=user
    )
    await db_session.refresh(vehicle)
    assert vehicle.mileage == 112500  # odometer from the inspection refreshes the truck


@pytest.mark.asyncio
async def test_complete_inspection_requires_odometer(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user
    )
    for item in detail.items:
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=item.id,
            body=InspectionItemUpdate(result=InspectionItemResult.PASS), db=db_session, current_user=user,
        )
    with pytest.raises(HTTPException) as exc:
        await fleet.complete_inspection(
            inspection_id=detail.id, body=InspectionComplete(), db=db_session, current_user=user
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_complete_inspection_rejects_backwards_odometer(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 120000
    await db_session.commit()
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user
    )
    for item in detail.items:
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=item.id,
            body=InspectionItemUpdate(result=InspectionItemResult.PASS), db=db_session, current_user=user,
        )
    with pytest.raises(HTTPException) as exc:
        await fleet.complete_inspection(
            inspection_id=detail.id, body=InspectionComplete(odometer=12000), db=db_session, current_user=user
        )
    assert exc.value.status_code == 400
    await db_session.refresh(vehicle)
    assert vehicle.mileage == 120000  # unchanged after a rejected reading


@pytest.mark.asyncio
async def test_complete_inspection_rejects_pending_items(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user
    )
    with pytest.raises(HTTPException) as exc:
        await fleet.complete_inspection(
            inspection_id=detail.id, body=InspectionComplete(odometer=125000), db=db_session, current_user=user
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
        inspection_id=detail.id, body=InspectionComplete(odometer=125000), db=db_session, current_user=user
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
async def test_delete_incident_without_repair(db_session):
    from sqlalchemy import select
    from app.db.models.fleet import FleetIncident

    _, vehicle, user = await _seed_fleet(db_session)
    incident = await fleet.create_incident(
        body=IncidentCreate(
            vehicle_id=vehicle.id, occurred_at=datetime.now(timezone.utc),
            description="Mistaken entry",
        ),
        db=db_session, current_user=user,
    )
    inc_id = incident.id
    await fleet.delete_incident(incident_id=inc_id, db=db_session, current_user=user)
    assert (await db_session.execute(select(FleetIncident).where(FleetIncident.id == inc_id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_incident_blocked_when_repair_linked(db_session):
    from sqlalchemy import select
    from app.db.models.fleet import FleetIncident

    _, vehicle, user = await _seed_fleet(db_session)
    incident = await fleet.create_incident(
        body=IncidentCreate(
            vehicle_id=vehicle.id, occurred_at=datetime.now(timezone.utc),
            description="Blowout", severity=IncidentSeverity.HIGH,
        ),
        db=db_session, current_user=user,
    )
    await fleet.create_repair_for_incident(incident_id=incident.id, db=db_session, current_user=user)

    with pytest.raises(HTTPException) as exc:
        await fleet.delete_incident(incident_id=incident.id, db=db_session, current_user=user)
    assert exc.value.status_code == 400
    # Incident is untouched.
    assert (await db_session.execute(select(FleetIncident).where(FleetIncident.id == incident.id))).scalar_one_or_none() is not None


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
async def test_internal_wo_captures_mileage_in_and_out(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 305000
    await db_session.commit()

    truck = await fleet.new_work_order(
        vehicle_id=vehicle.id, body=WorkOrderCreate(description="Brake chamber"),
        db=db_session, current_user=user,
    )
    ro = (await db_session.execute(
        __import__("sqlalchemy").select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id)
    )).scalar_one()
    # mileage-in auto-captured from the truck's odometer at creation.
    assert ro.mileage_in == 305000

    # Take it through start -> complete; mileage-out auto-captures from the vehicle.
    await fleet.start_work_order(ro_id=ro.id, db=db_session, current_user=user)
    await fleet.complete_work_order(ro_id=ro.id, body=None, db=db_session, current_user=user)
    await db_session.refresh(ro)
    assert ro.mileage_out == 305000
    assert ro.status == RepairOrderStatus.COMPLETED


@pytest.mark.asyncio
async def test_internal_wo_complete_manual_mileage_out_overrides(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 305000
    await db_session.commit()

    await fleet.new_work_order(
        vehicle_id=vehicle.id, body=WorkOrderCreate(description="Brake chamber"),
        db=db_session, current_user=user,
    )
    ro = (await db_session.execute(
        __import__("sqlalchemy").select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id)
    )).scalar_one()
    await fleet.start_work_order(ro_id=ro.id, db=db_session, current_user=user)
    # Manual reading provided at completion takes precedence over the odometer.
    await fleet.complete_work_order(
        ro_id=ro.id, body=WorkOrderComplete(mileage_out=305150), db=db_session, current_user=user,
    )
    await db_session.refresh(ro)
    assert ro.mileage_out == 305150


@pytest.mark.asyncio
async def test_delete_completed_internal_wo_keeps_invoice_intact(db_session):
    """A completed internal WO has an internal invoice (FK to the RO). Deleting
    the RO is a soft delete, so the invoice is untouched and never at risk of
    an FK error."""
    from sqlalchemy import select
    from app.api.v1.endpoints import repair_orders as ro_ep
    from app.db.models.invoice import Invoice

    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 200000
    await db_session.commit()

    await fleet.new_work_order(
        vehicle_id=vehicle.id, body=WorkOrderCreate(description="Radiator"),
        db=db_session, current_user=user,
    )
    ro = (await db_session.execute(select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id))).scalar_one()
    await fleet.start_work_order(ro_id=ro.id, db=db_session, current_user=user)
    await fleet.complete_work_order(ro_id=ro.id, body=WorkOrderComplete(mileage_out=200050), db=db_session, current_user=user)

    ro_id = ro.id
    assert (await db_session.execute(select(Invoice).where(Invoice.repair_order_id == ro_id))).scalar_one_or_none() is not None

    # Deleting the completed internal RO must succeed (no FK error). It's a
    # soft delete, so both the RO and its internal invoice survive, hidden.
    await ro_ep.delete_repair_order(order_id=ro_id, db=db_session, current_user=user)

    stored = (await db_session.execute(select(RepairOrder).where(RepairOrder.id == ro_id))).scalar_one()
    assert stored.deleted_at is not None
    assert (await db_session.execute(select(Invoice).where(Invoice.repair_order_id == ro_id))).scalar_one_or_none() is not None


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


@pytest.mark.asyncio
async def test_dashboard_stats_reports_internal_costs_separately_from_revenue(db_session):
    import sqlalchemy
    from app.api.v1.endpoints import dashboard

    _, vehicle, user = await _seed_fleet(db_session)
    await fleet.new_work_order(vehicle_id=vehicle.id, body=WorkOrderCreate(description="Brakes"),
                               db=db_session, current_user=user)
    ro = (await db_session.execute(
        sqlalchemy.select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id)
    )).scalar_one()
    await fleet.start_work_order(ro_id=ro.id, db=db_session, current_user=user)
    await fleet.complete_work_order(ro_id=ro.id, db=db_session, current_user=user)

    stats = await dashboard.get_dashboard_stats(db=db_session, current_user=user)

    # No parts/labor were added, so the internal invoice's cost-basis total is zero.
    expected_total = "0.00"
    assert stats.internal_costs.total_internal_invoices == 1
    assert stats.internal_costs.this_month == expected_total
    assert stats.internal_costs.this_week == expected_total
    assert stats.internal_costs.today == expected_total

    # Internal invoices have no Payment row, so they must never inflate
    # customer-facing revenue.
    assert stats.revenue.this_month == "0.00"


@pytest.mark.asyncio
async def test_pm_due_by_date(db_session):
    from datetime import date, timedelta
    from app.schemas.fleet import SchedulePMRequest
    _, vehicle, user = await _seed_fleet(db_session)

    # Plenty of mileage left, but PM date is within the window -> "pm".
    vehicle.mileage = 1000
    vehicle.next_pm_miles = 26000  # 25k miles out
    await db_session.commit()
    await fleet.schedule_pm(vehicle_id=vehicle.id,
                            body=SchedulePMRequest(due_date=date.today() + timedelta(days=5)),
                            db=db_session, current_user=user)
    board = await fleet.fleet_board(db=db_session, current_user=user)
    bt = next(t for t in board.trucks if t.id == vehicle.id)
    assert bt.status == "pm"
    assert bt.pm_days_remaining == 5


@pytest.mark.asyncio
async def test_schedule_pm_can_create_work_order(db_session):
    from datetime import date, timedelta
    from app.schemas.fleet import SchedulePMRequest
    _, vehicle, user = await _seed_fleet(db_session)
    truck = await fleet.schedule_pm(
        vehicle_id=vehicle.id,
        body=SchedulePMRequest(due_date=date.today() + timedelta(days=30), create_work_order=True),
        db=db_session, current_user=user,
    )
    assert truck.open_work_order_count == 1
    await db_session.refresh(vehicle)
    assert vehicle.pm_due_date == date.today() + timedelta(days=30)


@pytest.mark.asyncio
async def test_completing_pm_rolls_date_and_mileage_forward(db_session):
    import sqlalchemy
    from datetime import date, timedelta
    from app.schemas.fleet import SchedulePMRequest
    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 100000
    vehicle.pm_interval_miles = 25000
    vehicle.pm_interval_days = 180
    await db_session.commit()
    await fleet.schedule_pm(vehicle_id=vehicle.id,
                            body=SchedulePMRequest(due_date=date.today(), create_work_order=True),
                            db=db_session, current_user=user)
    ro = (await db_session.execute(
        sqlalchemy.select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id)
    )).scalar_one()
    await fleet.start_work_order(ro_id=ro.id, db=db_session, current_user=user)
    await fleet.complete_work_order(ro_id=ro.id, db=db_session, current_user=user)

    await db_session.refresh(vehicle)
    assert vehicle.next_pm_miles == 100000 + 25000
    # The due date is now projected from the mileage target (not a flat
    # pm_interval_days span): 25,000 mi remaining at 600 mi/day = 42 days.
    import math
    from app.services.internal_fleet import PM_AVG_MILES_PER_DAY
    expected_days = math.ceil(25000 / PM_AVG_MILES_PER_DAY)
    assert vehicle.pm_due_date == date.today() + timedelta(days=expected_days)


@pytest.mark.asyncio
async def test_schedule_pm_projects_due_date_from_mileage(db_session):
    """Rescheduling with a mileage target but no date projects the date from the
    remaining miles (so date & odometer agree). An explicit date is honored."""
    import math
    from datetime import date, timedelta
    from app.schemas.fleet import SchedulePMRequest
    from app.services.internal_fleet import PM_AVG_MILES_PER_DAY
    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 149075
    await db_session.commit()

    # No due_date given -> projected from 1,927 mi remaining at 600 mi/day.
    await fleet.schedule_pm(vehicle_id=vehicle.id,
                            body=SchedulePMRequest(next_pm_miles=151002),
                            db=db_session, current_user=user)
    await db_session.refresh(vehicle)
    expected = date.today() + timedelta(days=math.ceil((151002 - 149075) / PM_AVG_MILES_PER_DAY))
    assert vehicle.pm_due_date == expected  # ~4 days out, not months

    # An explicit date wins (manager knows the truck will sit idle).
    picked = date.today() + timedelta(days=120)
    await fleet.schedule_pm(vehicle_id=vehicle.id,
                            body=SchedulePMRequest(next_pm_miles=151002, due_date=picked),
                            db=db_session, current_user=user)
    await db_session.refresh(vehicle)
    assert vehicle.pm_due_date == picked


@pytest.mark.asyncio
async def test_manual_status_override_when_idle(db_session):
    from app.schemas.fleet import TruckUpdate
    _, vehicle, user = await _seed_fleet(db_session)

    # No work order, no override -> on the road ("active").
    board = await fleet.fleet_board(db=db_session, current_user=user)
    bt = next(t for t in board.trucks if t.id == vehicle.id)
    assert bt.status == "active"

    # Operator marks it out of service.
    await fleet.update_truck(vehicle_id=vehicle.id, body=TruckUpdate(status_override="out_of_service"),
                             db=db_session, current_user=user)
    board = await fleet.fleet_board(db=db_session, current_user=user)
    bt = next(t for t in board.trucks if t.id == vehicle.id)
    assert bt.status == "out_of_service"
    assert bt.status_override == "out_of_service"

    # An open work order wins over the manual status.
    await fleet.new_work_order(vehicle_id=vehicle.id, body=WorkOrderCreate(description="Brakes"),
                               db=db_session, current_user=user)
    board = await fleet.fleet_board(db=db_session, current_user=user)
    bt = next(t for t in board.trucks if t.id == vehicle.id)
    assert bt.status == "draft"  # fresh work order

    # 'auto' clears the override.
    await fleet.update_truck(vehicle_id=vehicle.id, body=TruckUpdate(status_override="auto"),
                             db=db_session, current_user=user)
    await db_session.refresh(vehicle)
    assert vehicle.status_override is None


@pytest.mark.asyncio
async def test_invalid_status_override_rejected(db_session):
    from app.schemas.fleet import TruckUpdate
    _, vehicle, user = await _seed_fleet(db_session)
    with pytest.raises(HTTPException) as exc:
        await fleet.update_truck(vehicle_id=vehicle.id, body=TruckUpdate(status_override="flying"),
                                 db=db_session, current_user=user)
    assert exc.value.status_code == 400


# --- Weekly inspection compliance (missed-inspection recording) ---

async def _missed_records(db_session, vehicle_id):
    from sqlalchemy import select as _select, and_ as _and
    from app.db.models.fleet import FleetInspection
    rows = (await db_session.execute(
        _select(FleetInspection).where(_and(
            FleetInspection.vehicle_id == vehicle_id,
            FleetInspection.status == InspectionStatus.MISSED,
        ))
    )).scalars().all()
    return rows


@pytest.mark.asyncio
async def test_compliance_records_missed_for_uninspected_truck(db_session):
    from app.tasks.fleet_inspection_compliance import record_missed_inspections
    _, vehicle, _ = await _seed_fleet(db_session)
    missed_by_tenant = await record_missed_inspections(db_session)
    assert vehicle.tenant_id in missed_by_tenant
    rows = await _missed_records(db_session, vehicle.id)
    assert len(rows) == 1
    assert rows[0].result == InspectionResult.FAIL


@pytest.mark.asyncio
async def test_compliance_skips_recently_inspected_truck(db_session):
    from app.tasks.fleet_inspection_compliance import record_missed_inspections
    from app.db.models.fleet import FleetInspection
    _, vehicle, _ = await _seed_fleet(db_session)
    db_session.add(FleetInspection(
        id=uuid4(), tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
        status=InspectionStatus.COMPLETED, result=InspectionResult.PASS,
        scheduled_for=datetime.now(timezone.utc).date(),
        performed_at=datetime.now(timezone.utc) - timedelta(days=2),
    ))
    await db_session.commit()
    await record_missed_inspections(db_session)
    assert await _missed_records(db_session, vehicle.id) == []


@pytest.mark.asyncio
async def test_compliance_is_idempotent_within_the_week(db_session):
    from app.tasks.fleet_inspection_compliance import record_missed_inspections
    _, vehicle, _ = await _seed_fleet(db_session)
    await record_missed_inspections(db_session)
    await record_missed_inspections(db_session)
    assert len(await _missed_records(db_session, vehicle.id)) == 1


@pytest.mark.asyncio
async def test_compliance_skips_out_of_service_truck(db_session):
    from app.tasks.fleet_inspection_compliance import record_missed_inspections
    _, vehicle, _ = await _seed_fleet(db_session)
    vehicle.status_override = "out_of_service"
    await db_session.commit()
    await record_missed_inspections(db_session)
    assert await _missed_records(db_session, vehicle.id) == []


@pytest.mark.asyncio
async def test_delete_inspection_owner_only(db_session):
    from fastapi import HTTPException
    from sqlalchemy import select, func
    from app.db.models.fleet import FleetInspection, FleetInspectionItem
    tenant, vehicle, fm = await _seed_fleet(db_session)  # fm is a fleet_manager
    owner = User(id=uuid4(), tenant_id=tenant.id, email=f"own-{uuid4().hex[:6]}@example.com",
                 hashed_password="x", first_name="O", last_name="W",
                 role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True)
    admin_user = User(id=uuid4(), tenant_id=tenant.id, email=f"adm-{uuid4().hex[:6]}@example.com",
                      hashed_password="x", first_name="A", last_name="D",
                      role=UserRole.GARAGE_ADMIN, is_active=True, is_verified=True)
    db_session.add_all([owner, admin_user])
    await db_session.commit()

    insp = await fleet.create_inspection(body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=fm)

    # Fleet manager and garage admin are blocked from the owner-only guard.
    for blocked in (fm, admin_user):
        with pytest.raises(HTTPException) as exc:
            fleet.require_garage_owner_only(current_user=blocked)
        assert exc.value.status_code == 403

    # Owner deletes; inspection and its checklist items are gone.
    await fleet.delete_inspection(inspection_id=insp.id, db=db_session, current_user=owner)
    gone = (await db_session.execute(select(FleetInspection).where(FleetInspection.id == insp.id))).scalar_one_or_none()
    items = (await db_session.execute(select(func.count(FleetInspectionItem.id)).where(FleetInspectionItem.inspection_id == insp.id))).scalar()
    assert gone is None and items == 0


@pytest.mark.asyncio
async def test_inspection_flags_and_work_order_clears_warning_lights(db_session):
    import sqlalchemy
    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 100000
    await db_session.commit()

    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user)
    # Everything OK except the Check Engine warning light is on (FAIL).
    for item in detail.items:
        res = InspectionItemResult.PASS
        if item.is_warning_light and item.label == "Check engine (MIL)":
            res = InspectionItemResult.FAIL
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=item.id,
            body=InspectionItemUpdate(result=res), db=db_session, current_user=user)
    await fleet.complete_inspection(
        inspection_id=detail.id, body=InspectionComplete(odometer=101000),
        db=db_session, current_user=user)

    await db_session.refresh(vehicle)
    assert vehicle.active_warning_lights == "Check engine (MIL)"
    board = await fleet.fleet_board(db=db_session, current_user=user)
    bt = next(t for t in board.trucks if t.id == vehicle.id)
    assert bt.warning_lights == ["Check engine (MIL)"]

    # Completing a work order clears the warning lights.
    await fleet.new_work_order(vehicle_id=vehicle.id, body=WorkOrderCreate(description="Fix MIL"),
                               db=db_session, current_user=user)
    ro = (await db_session.execute(
        sqlalchemy.select(RepairOrder).where(RepairOrder.vehicle_id == vehicle.id)
    )).scalars().first()
    await fleet.start_work_order(ro_id=ro.id, db=db_session, current_user=user)
    await fleet.complete_work_order(ro_id=ro.id, db=db_session, current_user=user)
    await db_session.refresh(vehicle)
    assert vehicle.active_warning_lights is None


@pytest.mark.asyncio
async def test_delete_inspection_clears_warning_lights(db_session):
    _, vehicle, owner = await _seed_fleet(db_session, role=UserRole.GARAGE_OWNER)
    vehicle.mileage = 100000
    await db_session.commit()
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=owner)
    for item in detail.items:
        res = InspectionItemResult.PASS
        if item.is_warning_light and item.label == "Check engine (MIL)":
            res = InspectionItemResult.FAIL
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=item.id,
            body=InspectionItemUpdate(result=res), db=db_session, current_user=owner)
    await fleet.complete_inspection(
        inspection_id=detail.id, body=InspectionComplete(odometer=101000),
        db=db_session, current_user=owner)
    await db_session.refresh(vehicle)
    assert vehicle.active_warning_lights == "Check engine (MIL)"

    # Deleting the inspection re-derives lights (nothing left -> cleared).
    await fleet.delete_inspection(inspection_id=detail.id, db=db_session, current_user=owner)
    await db_session.refresh(vehicle)
    assert vehicle.active_warning_lights is None


async def _complete_with_one_fail(db_session, vehicle, user, fail_label="Check engine (MIL)"):
    """Create + complete an inspection with a single FAILED item; return detail."""
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user)
    for item in detail.items:
        res = InspectionItemResult.FAIL if item.label == fail_label else InspectionItemResult.PASS
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=item.id,
            body=InspectionItemUpdate(result=res), db=db_session, current_user=user)
    await fleet.complete_inspection(
        inspection_id=detail.id, body=InspectionComplete(odometer=101000),
        db=db_session, current_user=user)
    return detail


@pytest.mark.asyncio
async def test_create_work_order_from_failed_inspection_links_and_describes(db_session):
    import sqlalchemy
    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 100000
    await db_session.commit()
    detail = await _complete_with_one_fail(db_session, vehicle, user)

    result = await fleet.create_work_order_for_inspection(
        inspection_id=detail.id, db=db_session, current_user=user)

    assert result.repair_order_id is not None
    ro = (await db_session.execute(
        sqlalchemy.select(RepairOrder).where(RepairOrder.id == result.repair_order_id)
    )).scalar_one()
    assert ro.vehicle_id == vehicle.id
    assert ro.is_internal is True
    assert "Check engine (MIL)" in (ro.description or "")

    # A second call is rejected — the work order already exists.
    with pytest.raises(HTTPException) as exc:
        await fleet.create_work_order_for_inspection(
            inspection_id=detail.id, db=db_session, current_user=user)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_work_order_rejects_when_no_failed_items(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 100000
    await db_session.commit()
    detail = await fleet.create_inspection(
        body=InspectionCreate(vehicle_id=vehicle.id), db=db_session, current_user=user)
    for item in detail.items:
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=item.id,
            body=InspectionItemUpdate(result=InspectionItemResult.PASS), db=db_session, current_user=user)
    await fleet.complete_inspection(
        inspection_id=detail.id, body=InspectionComplete(odometer=101000),
        db=db_session, current_user=user)

    with pytest.raises(HTTPException) as exc:
        await fleet.create_work_order_for_inspection(
            inspection_id=detail.id, db=db_session, current_user=user)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_add_service_to_internal_work_order_seeds_internal_labor(db_session):
    from decimal import Decimal
    from app.db.models.service import Service
    from app.db.models.labor import Labor
    from app.schemas.fleet import AddServiceRequest
    import sqlalchemy

    tenant, vehicle, user = await _seed_fleet(db_session)
    tenant.internal_labor_rate = 40
    diagnostic = Service(
        id=uuid4(), tenant_id=tenant.id, name="Diagnostic Scan",
        duration_minutes=30, is_active=True,
    )
    db_session.add(diagnostic)
    await db_session.commit()

    # A non-PM internal work order (as spawned from a failed inspection).
    truck = await fleet.new_work_order(
        vehicle_id=vehicle.id, body=WorkOrderCreate(description="Check engine"),
        db=db_session, current_user=user)
    ro_id = truck.work_order.repair_order_id

    # Catalog exposes the (non-PM) service.
    catalog = await fleet.service_catalog(db=db_session, current_user=user)
    assert any(s.service_id == diagnostic.id for s in catalog)

    await fleet.add_service_to_work_order(
        ro_id=ro_id, body=AddServiceRequest(service_id=diagnostic.id),
        db=db_session, current_user=user)

    labor = (await db_session.execute(
        sqlalchemy.select(Labor).where(Labor.repair_order_id == ro_id)
    )).scalars().all()
    assert len(labor) == 1
    line = labor[0]
    assert line.description == "Diagnostic Scan"
    assert line.source_service_id == diagnostic.id
    assert Decimal(str(line.hours)) == Decimal("0.5")
    assert Decimal(str(line.hourly_rate)) == Decimal("40")
    assert Decimal(str(line.total_cost)) == Decimal("20.00")


@pytest.mark.asyncio
async def test_add_service_rejected_on_pm_work_order(db_session):
    from app.db.models.service import Service
    from app.schemas.fleet import AddServiceRequest, SchedulePMRequest

    tenant, vehicle, user = await _seed_fleet(db_session)
    svc = Service(id=uuid4(), tenant_id=tenant.id, name="Diagnostic", duration_minutes=30, is_active=True)
    db_session.add(svc)
    await db_session.commit()

    # Spawn a PM work order and confirm hand-adding a service is rejected — PM
    # scope is set through the PM picker, not this endpoint.
    truck = await fleet.schedule_pm(
        vehicle_id=vehicle.id, body=SchedulePMRequest(create_work_order=True),
        db=db_session, current_user=user)
    ro_id = truck.pm_work_order.repair_order_id

    with pytest.raises(HTTPException) as exc:
        await fleet.add_service_to_work_order(
            ro_id=ro_id, body=AddServiceRequest(service_id=svc.id),
            db=db_session, current_user=user)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_completed_inspection_items_are_locked(db_session):
    _, vehicle, user = await _seed_fleet(db_session)
    vehicle.mileage = 100000
    await db_session.commit()
    detail = await _complete_with_one_fail(db_session, vehicle, user)

    # Editing an item on a completed inspection is rejected — the record is a
    # point-in-time safety document; re-inspect instead.
    with pytest.raises(HTTPException) as exc:
        await fleet.update_inspection_item(
            inspection_id=detail.id, item_id=detail.items[0].id,
            body=InspectionItemUpdate(result=InspectionItemResult.PASS),
            db=db_session, current_user=user)
    assert exc.value.status_code == 400
