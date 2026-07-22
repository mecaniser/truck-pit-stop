from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints import customers, fleet, vehicles
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership, VehicleCustomerRelationship
from app.schemas.vehicle import VehicleBase, VehicleRelationshipCreate, VehicleUpdate
from app.services.vehicle_identity import (
    ensure_fleet_membership,
    seed_vehicle_account_relationships,
)


@pytest.mark.asyncio
async def test_truck_identity_survives_different_operator_payer_and_owner_transfer(db_session):
    tenant = Tenant(
        id=uuid4(),
        name="Identity Garage",
        slug=f"identity-{uuid4().hex[:8]}",
        labor_rate=Decimal("125.00"),
    )
    owner = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Owner", last_name="One",
        company_name="Owner Trucking LLC", email=f"owner-{uuid4().hex[:6]}@example.com",
    )
    operator = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Dispatch", last_name="Team",
        company_name="77 Cargo", email=f"operator-{uuid4().hex[:6]}@example.com",
        fleet_enabled=True,
    )
    next_owner = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Buyer", last_name="Two",
        company_name="Buyer Transport LLC", email=f"buyer-{uuid4().hex[:6]}@example.com",
    )
    manager = User(
        id=uuid4(), tenant_id=tenant.id, email=f"manager-{uuid4().hex[:6]}@example.com",
        hashed_password="x", first_name="Fleet", last_name="Manager",
        role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    db_session.add_all([tenant, owner, operator, next_owner, manager])
    await db_session.flush()

    truck = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=owner.id,
        vin="1M1AW07Y1FM123456", make="Mack", model="Pinnacle", year=2020,
        unit_number="77-12", mileage=410_000,
    )
    db_session.add(truck)
    await db_session.flush()
    await seed_vehicle_account_relationships(db_session, truck, owner)
    await ensure_fleet_membership(
        db_session,
        tenant_id=tenant.id,
        vehicle_id=truck.id,
        fleet_customer_id=operator.id,
    )
    await db_session.commit()

    order = await fleet._spawn_internal_ro(
        db_session,
        tenant.id,
        truck,
        is_pm=False,
        description="Brake inspection",
        bill_to_customer_id=operator.id,
    )

    assert order.vehicle_id == truck.id
    assert order.customer_id == operator.id
    assert order.is_internal is False
    assert order.is_fleet_work is True

    board = await fleet.fleet_board(db=db_session, current_user=manager)
    assert len(board.trucks) == 1
    card = board.trucks[0]
    assert card.id == truck.id
    assert card.fleet_company_name == "77 Cargo"
    assert card.owner_company_name == "Owner Trucking LLC"
    assert card.work_order is not None

    await vehicles.create_vehicle_relationship(
        vehicle_id=truck.id,
        body=VehicleRelationshipCreate(
            customer_id=next_owner.id,
            relationship_type="owner",
            replace_primary=True,
        ),
        db=db_session,
        current_user=manager,
    )

    await db_session.refresh(truck)
    await db_session.refresh(order)
    assert truck.customer_id == next_owner.id
    assert order.vehicle_id == truck.id
    assert order.customer_id == operator.id

    owner_periods = list((await db_session.execute(
        select(VehicleCustomerRelationship).where(
            VehicleCustomerRelationship.vehicle_id == truck.id,
            VehicleCustomerRelationship.relationship_type == "owner",
        )
    )).scalars().all())
    active_owner = next(row for row in owner_periods if row.effective_to is None)
    previous_owner = next(row for row in owner_periods if row.customer_id == owner.id)
    assert active_owner.customer_id == next_owner.id
    assert previous_owner.effective_to is not None


@pytest.mark.asyncio
async def test_dashboard_vehicle_create_auto_enrolls_fleet_enabled_company(db_session):
    tenant = Tenant(id=uuid4(), name="Fleet Customer Garage", slug=f"fcg-{uuid4().hex[:8]}")
    company = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Fleet", last_name="Contact",
        company_name="77 Cargo", email=f"fleet-{uuid4().hex[:6]}@example.com",
        fleet_enabled=True,
    )
    manager = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{uuid4().hex[:6]}@example.com",
        hashed_password="x", first_name="Shop", last_name="Owner",
        role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    db_session.add_all([tenant, company, manager])
    await db_session.commit()

    truck = await customers.create_customer_vehicle(
        customer_id=company.id,
        vehicle_data=VehicleBase(make="Freightliner", model="Cascadia", unit_number="77-44"),
        db=db_session,
        current_user=manager,
    )

    membership = (await db_session.execute(select(FleetMembership).where(
        FleetMembership.vehicle_id == truck.id,
        FleetMembership.fleet_customer_id == company.id,
        FleetMembership.effective_to.is_(None),
    ))).scalar_one()
    assert membership.vehicle_id == truck.id

    board = await fleet.fleet_board(db=db_session, current_user=manager)
    assert [item.id for item in board.trucks] == [truck.id]


@pytest.mark.asyncio
async def test_duplicate_vin_conflict_identifies_existing_truck(db_session):
    tenant = Tenant(id=uuid4(), name="Conflict Garage", slug=f"conflict-{uuid4().hex[:8]}")
    existing_company = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Dispatch", last_name="One",
        company_name="77 Cargo LLC", email=f"existing-{uuid4().hex[:6]}@example.com",
    )
    editing_company = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Owner", last_name="Two",
        company_name="Owner Trucking LLC", email=f"editing-{uuid4().hex[:6]}@example.com",
    )
    manager = User(
        id=uuid4(), tenant_id=tenant.id, email=f"manager-{uuid4().hex[:6]}@example.com",
        hashed_password="x", first_name="Shop", last_name="Owner",
        role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    existing_truck = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=existing_company.id,
        vin="4V4NC9EH2MN271901", make="Volvo", model="VNL 760", year=2021,
        unit_number="8", license_plate="NC-771",
    )
    editing_truck = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=editing_company.id,
        make="Volvo", model="VNL 760", year=2021,
    )
    db_session.add_all([tenant, existing_company, editing_company, manager, existing_truck, editing_truck])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await customers.update_customer_vehicle(
            customer_id=editing_company.id,
            vehicle_id=editing_truck.id,
            vehicle_data=VehicleUpdate(vin=existing_truck.vin),
            db=db_session,
            current_user=manager,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "duplicate_vin",
        "message": "This VIN is already assigned to an existing truck.",
        "vehicle": {
            "id": str(existing_truck.id),
            "vin": "4V4NC9EH2MN271901",
            "unit_number": "8",
            "year": 2021,
            "make": "Volvo",
            "model": "VNL 760",
            "license_plate": "NC-771",
            "customer_id": str(existing_company.id),
            "customer_name": "77 Cargo LLC",
        },
    }
