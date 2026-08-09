from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.customer import Customer
from app.db.models.fleet import FleetIncident, FleetInspection, IncidentSeverity, IncidentStatus, InspectionStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_merge import VehicleMergeRecord, VehicleSourceAlias
from app.db.models.vehicle_relationship import FleetMembership, VehicleCustomerRelationship
from app.services.vehicle_merge import VehicleMergeError, merge_vehicles


@pytest.mark.asyncio
async def test_vehicle_merge_moves_history_but_preserves_historical_customer(db_session):
    tenant = Tenant(id=uuid4(), name="Merge Garage", slug=f"merge-{uuid4().hex[:8]}", labor_rate=Decimal("125"))
    owner = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Elis", last_name="Logistics",
        company_name="ELIS LOGISTICS LLC", email=f"elis-{uuid4().hex[:6]}@example.com",
    )
    imported_customer = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Imported", last_name="Account",
        company_name="Easy Truck Shop account", email=f"ets-{uuid4().hex[:6]}@example.com",
    )
    authority = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="77", last_name="Cargo",
        company_name="77 CARGO LLC", email=f"77-{uuid4().hex[:6]}@example.com", fleet_enabled=True,
    )
    user = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{uuid4().hex[:6]}@example.com",
        hashed_password="x", first_name="Garage", last_name="Owner", role=UserRole.GARAGE_OWNER,
        is_active=True, is_verified=True,
    )
    db_session.add_all([tenant, owner, imported_customer, authority, user])
    await db_session.flush()

    vin = "4V4WC9EG9LN250022"
    canonical = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=owner.id, vin=vin,
        make="VOLVO TRUCK", model="VNR", year=2020, unit_number="603", mileage=598_458,
    )
    duplicate = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=imported_customer.id,
        vin="4v4wc9eg9ln250022", make="Volvo", model="VNR", year=2020,
        mileage=621_565, source="easy_truck_shop_import", ets_external_id="97052",
    )
    db_session.add_all([canonical, duplicate])
    await db_session.flush()

    order = RepairOrder(
        id=uuid4(), tenant_id=tenant.id, customer_id=imported_customer.id,
        vehicle_id=duplicate.id, order_number=f"ETS-{uuid4().hex[:8]}",
        status=RepairOrderStatus.COMPLETED, source="easy_truck_shop_import",
    )
    inspection = FleetInspection(
        id=uuid4(), tenant_id=tenant.id, vehicle_id=duplicate.id,
        status=InspectionStatus.SCHEDULED, scheduled_for=date.today(),
    )
    incident = FleetIncident(
        id=uuid4(), tenant_id=tenant.id, vehicle_id=duplicate.id,
        occurred_at=datetime.now(timezone.utc), severity=IncidentSeverity.MEDIUM,
        status=IncidentStatus.OPEN, description="Roadside tire failure",
    )
    canonical_owner = VehicleCustomerRelationship(
        id=uuid4(), tenant_id=tenant.id, vehicle_id=canonical.id, customer_id=owner.id,
        relationship_type="owner", is_primary=True,
    )
    duplicate_owner = VehicleCustomerRelationship(
        id=uuid4(), tenant_id=tenant.id, vehicle_id=duplicate.id, customer_id=imported_customer.id,
        relationship_type="owner", is_primary=True,
    )
    canonical_membership = FleetMembership(
        id=uuid4(), tenant_id=tenant.id, vehicle_id=canonical.id, fleet_customer_id=authority.id,
    )
    duplicate_membership = FleetMembership(
        id=uuid4(), tenant_id=tenant.id, vehicle_id=duplicate.id, fleet_customer_id=imported_customer.id,
    )
    db_session.add_all([
        order, inspection, incident, canonical_owner, duplicate_owner,
        canonical_membership, duplicate_membership,
    ])
    await db_session.commit()

    kept, record, moved = await merge_vehicles(
        db_session,
        tenant_id=tenant.id,
        canonical_id=canonical.id,
        duplicate_id=duplicate.id,
        merged_by_user_id=user.id,
        confirm_vin=vin,
    )
    await db_session.commit()

    assert kept.id == canonical.id
    assert kept.customer_id == owner.id
    assert kept.mileage == 621_565
    assert kept.ets_external_id == "97052"
    assert moved["repair_orders"] == 1
    assert moved["inspections"] == 1
    assert moved["incidents"] == 1

    await db_session.refresh(order)
    await db_session.refresh(inspection)
    await db_session.refresh(incident)
    await db_session.refresh(duplicate)
    await db_session.refresh(duplicate_owner)
    await db_session.refresh(duplicate_membership)
    assert order.vehicle_id == canonical.id
    assert order.customer_id == imported_customer.id  # historical billing context remains intact
    assert inspection.vehicle_id == canonical.id
    assert incident.vehicle_id == canonical.id
    assert duplicate.deleted_at is not None
    assert duplicate_owner.vehicle_id == canonical.id
    assert duplicate_owner.is_primary is False
    assert duplicate_owner.effective_to is not None
    assert duplicate_membership.vehicle_id == canonical.id
    assert duplicate_membership.effective_to is not None

    alias = (await db_session.execute(select(VehicleSourceAlias).where(
        VehicleSourceAlias.source == "easy_truck_shop_import",
        VehicleSourceAlias.external_id == "97052",
    ))).scalar_one()
    assert alias.vehicle_id == canonical.id
    assert (await db_session.execute(select(VehicleMergeRecord).where(
        VehicleMergeRecord.id == record.id
    ))).scalar_one().duplicate_vehicle_id == duplicate.id


@pytest.mark.asyncio
async def test_vehicle_merge_rejects_different_vins(db_session):
    tenant = Tenant(id=uuid4(), name="Merge Guard", slug=f"guard-{uuid4().hex[:8]}", labor_rate=Decimal("125"))
    customer = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Safe", last_name="Fleet",
        company_name="Safe Fleet", email=f"safe-{uuid4().hex[:6]}@example.com",
    )
    user = User(
        id=uuid4(), tenant_id=tenant.id, email=f"guard-{uuid4().hex[:6]}@example.com",
        hashed_password="x", first_name="Garage", last_name="Owner", role=UserRole.GARAGE_OWNER,
        is_active=True, is_verified=True,
    )
    one = Vehicle(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, vin="1M1AW07Y1FM123456", make="Mack", model="One")
    two = Vehicle(id=uuid4(), tenant_id=tenant.id, customer_id=customer.id, vin="1M1AW07Y1FM654321", make="Mack", model="Two")
    db_session.add_all([tenant, customer, user, one, two])
    await db_session.commit()

    with pytest.raises(VehicleMergeError, match="same complete 17-character VIN"):
        await merge_vehicles(
            db_session,
            tenant_id=tenant.id,
            canonical_id=one.id,
            duplicate_id=two.id,
            merged_by_user_id=user.id,
            confirm_vin=one.vin,
        )
