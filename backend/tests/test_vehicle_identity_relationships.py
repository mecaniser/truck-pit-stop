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
from app.schemas.customer import CustomerUpdate
from app.schemas.fleet import FleetBillToCustomerUpdate, TruckUpdate
from app.schemas.vehicle import VehicleBase, VehicleRelationshipCreate, VehicleRelationshipSync, VehicleUpdate
from app.services.vehicle_identity import (
    ensure_fleet_membership,
    ensure_vehicle_relationship,
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

    active_payer = (await db_session.execute(select(VehicleCustomerRelationship).where(
        VehicleCustomerRelationship.vehicle_id == truck.id,
        VehicleCustomerRelationship.relationship_type == "default_payer",
        VehicleCustomerRelationship.effective_to.is_(None),
    ))).scalar_one()
    assert active_payer.customer_id == owner.id

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
    assert card.display_unit_number == "Owner Trucking LLC 77-12"
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

    transferred_board = await fleet.fleet_board(db=db_session, current_user=manager)
    assert transferred_board.trucks[0].display_unit_number == "Buyer Transport LLC 77-12"
    assert transferred_board.trucks[0].fleet_company_name == "77 Cargo"


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
async def test_dashboard_operator_link_enrolls_existing_truck_on_fleet_board(db_session):
    tenant = Tenant(id=uuid4(), name="Linked Fleet Garage", slug=f"linked-{uuid4().hex[:8]}")
    owner = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Owner", last_name="Contact",
        company_name="Owner Trucking LLC", email=f"owner-{uuid4().hex[:6]}@example.com",
    )
    operator = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Fleet", last_name="Contact",
        company_name="77 Cargo", email=f"operator-{uuid4().hex[:6]}@example.com",
        fleet_enabled=True,
    )
    manager = User(
        id=uuid4(), tenant_id=tenant.id, email=f"manager-{uuid4().hex[:6]}@example.com",
        hashed_password="x", first_name="Shop", last_name="Owner",
        role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    truck = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=owner.id,
        vin="1M1AW07Y1FM654321", make="Mack", model="Pinnacle", year=2020,
        unit_number="77-22",
    )
    db_session.add_all([tenant, owner, operator, manager, truck])
    await db_session.flush()
    await seed_vehicle_account_relationships(db_session, truck, owner)
    await db_session.commit()

    await vehicles.create_vehicle_relationship(
        vehicle_id=truck.id,
        body=VehicleRelationshipCreate(
            customer_id=operator.id,
            relationship_type="operator",
        ),
        db=db_session,
        current_user=manager,
    )

    linked_vehicles = await customers.list_customer_vehicles(
        customer_id=operator.id,
        skip=0,
        limit=100,
        paginated=False,
        db=db_session,
        current_user=manager,
    )
    assert [item.id for item in linked_vehicles] == [truck.id]
    membership = (await db_session.execute(select(FleetMembership).where(
        FleetMembership.vehicle_id == truck.id,
        FleetMembership.fleet_customer_id == operator.id,
        FleetMembership.effective_to.is_(None),
    ))).scalar_one()
    assert membership.vehicle_id == truck.id

    board = await fleet.fleet_board(db=db_session, current_user=manager)
    assert [item.id for item in board.trucks] == [truck.id]
    assert board.trucks[0].fleet_company_name == "77 Cargo"
    assert board.trucks[0].display_unit_number == "Owner Trucking LLC 77-22"


@pytest.mark.asyncio
async def test_truck_connections_can_be_relinked_and_unlinked_without_losing_history(db_session):
    tenant = Tenant(id=uuid4(), name="Relink Garage", slug=f"relink-{uuid4().hex[:8]}")
    house = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="House", last_name="Account",
        company_name="House Account", email=f"house-{uuid4().hex[:6]}@example.com",
        is_internal_fleet=True, fleet_enabled=True,
    )
    owner = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="ELS", last_name="Dispatch",
        company_name="ELS Logistics LLC", email=f"els-{uuid4().hex[:6]}@example.com",
    )
    operator = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Fleet", last_name="Dispatch",
        company_name="77 Cargo", email=f"77-{uuid4().hex[:6]}@example.com",
        phone="17048352433", billing_city="Charlotte", billing_state="NC", billing_zip="28202",
        fleet_enabled=True,
    )
    manager = User(
        id=uuid4(), tenant_id=tenant.id, email=f"manager-{uuid4().hex[:6]}@example.com",
        hashed_password="x", first_name="Shop", last_name="Owner",
        role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    truck = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=house.id,
        vin="4V4WC9EG9LN250022", make="Volvo", model="VNR", year=2020,
        unit_number="77 Cargo 603",
    )
    db_session.add_all([tenant, house, owner, operator, manager, truck])
    await db_session.flush()
    await seed_vehicle_account_relationships(db_session, truck, house)
    await ensure_fleet_membership(
        db_session,
        tenant_id=tenant.id,
        vehicle_id=truck.id,
        fleet_customer_id=operator.id,
    )
    await db_session.commit()

    initial_detail = await fleet.truck_detail(
        vehicle_id=truck.id, db=db_session, current_user=manager,
    )
    assert initial_detail.fleet_account_company_name == "77 Cargo"
    assert initial_detail.fleet_account_email == operator.email
    assert initial_detail.fleet_account_phone == "17048352433"
    assert initial_detail.bill_to_company_name == "77 Cargo"
    assert initial_detail.bill_to_relationship_type == "default_payer"

    await vehicles.sync_vehicle_relationships(
        vehicle_id=truck.id,
        body=VehicleRelationshipSync(
            customer_id=owner.id,
            relationship_types=["owner", "default_payer"],
            unit_number="603",
        ),
        db=db_session,
        current_user=manager,
    )

    await db_session.refresh(truck)
    assert truck.customer_id == owner.id
    assert truck.unit_number == "603"
    board = await fleet.fleet_board(db=db_session, current_user=manager)
    assert board.trucks[0].display_unit_number == "ELS Logistics LLC 603"
    assert board.trucks[0].fleet_company_name == "77 Cargo"
    relinked_detail = await fleet.truck_detail(
        vehicle_id=truck.id, db=db_session, current_user=manager,
    )
    assert relinked_detail.bill_to_company_name == "ELS Logistics LLC"
    assert relinked_detail.bill_to_email == owner.email
    assert relinked_detail.fleet_account_company_name == "77 Cargo"

    updated_email = f"billing-{uuid4().hex[:6]}@els.example.com"
    await fleet.update_truck(
        vehicle_id=truck.id,
        body=TruckUpdate(bill_to_customer=FleetBillToCustomerUpdate(
            customer_id=owner.id,
            company_name="ELS Logistics Updated LLC",
            first_name="Accounts",
            last_name="Payable",
            email=updated_email,
            phone="17045550199",
            billing_address_line1="100 Fleet Way",
            billing_city="Charlotte",
            billing_state="NC",
            billing_zip="28202",
            billing_country="USA",
        )),
        db=db_session,
        current_user=manager,
    )
    await db_session.refresh(owner)
    assert owner.company_name == "ELS Logistics Updated LLC"
    assert owner.email == updated_email
    assert owner.phone == "17045550199"
    updated_detail = await fleet.truck_detail(
        vehicle_id=truck.id, db=db_session, current_user=manager,
    )
    assert updated_detail.bill_to_company_name == "ELS Logistics Updated LLC"
    assert updated_detail.bill_to_email == updated_email
    assert updated_detail.truck.display_unit_number == "ELS Logistics Updated LLC 603"

    await vehicles.sync_vehicle_relationships(
        vehicle_id=truck.id,
        body=VehicleRelationshipSync(
            customer_id=operator.id,
            relationship_types=[],
            unit_number="603",
        ),
        db=db_session,
        current_user=manager,
    )
    assert (await fleet.fleet_board(db=db_session, current_user=manager)).trucks == []

    await vehicles.sync_vehicle_relationships(
        vehicle_id=truck.id,
        body=VehicleRelationshipSync(
            customer_id=operator.id,
            relationship_types=["operator"],
            unit_number="603",
        ),
        db=db_session,
        current_user=manager,
    )
    relinked_board = await fleet.fleet_board(db=db_session, current_user=manager)
    assert relinked_board.trucks[0].display_unit_number == "ELS Logistics Updated LLC 603"
    operator_periods = list((await db_session.execute(select(VehicleCustomerRelationship).where(
        VehicleCustomerRelationship.vehicle_id == truck.id,
        VehicleCustomerRelationship.customer_id == operator.id,
        VehicleCustomerRelationship.relationship_type == "operator",
    ))).scalars().all())
    assert len(operator_periods) == 2
    assert len([period for period in operator_periods if period.effective_to is None]) == 1
    assert len([period for period in operator_periods if period.effective_to is not None]) == 1

    active_operator = next(period for period in operator_periods if period.effective_to is None)
    await vehicles.unlink_vehicle_relationship(
        vehicle_id=truck.id,
        relationship_id=active_operator.id,
        db=db_session,
        current_user=manager,
    )
    assert (await fleet.fleet_board(db=db_session, current_user=manager)).trucks == []
    refreshed_periods = list((await db_session.execute(select(VehicleCustomerRelationship).where(
        VehicleCustomerRelationship.vehicle_id == truck.id,
        VehicleCustomerRelationship.customer_id == operator.id,
        VehicleCustomerRelationship.relationship_type == "operator",
    ))).scalars().all())
    assert len([period for period in refreshed_periods if period.effective_to is None]) == 0
    assert len([period for period in refreshed_periods if period.effective_to is not None]) == 2

    # The owner/lessor can select the authority from its own customer profile.
    # This must restore 77 Cargo to Fleet Board without turning 77 Cargo into
    # the owner or default invoice recipient.
    await vehicles.sync_vehicle_relationships(
        vehicle_id=truck.id,
        body=VehicleRelationshipSync(
            customer_id=owner.id,
            relationship_types=["owner", "default_payer"],
            operating_authority_customer_id=operator.id,
            unit_number="603",
        ),
        db=db_session,
        current_user=manager,
    )
    authority_board = await fleet.fleet_board(db=db_session, current_user=manager)
    assert authority_board.trucks[0].owner_company_name == "ELS Logistics Updated LLC"
    assert authority_board.trucks[0].fleet_company_name == "77 Cargo"
    authority_detail = await fleet.truck_detail(
        vehicle_id=truck.id, db=db_session, current_user=manager,
    )
    assert authority_detail.fleet_account_company_name == "77 Cargo"
    assert authority_detail.bill_to_company_name == "ELS Logistics Updated LLC"


@pytest.mark.asyncio
async def test_enabling_customer_fleet_enrolls_owned_and_operated_trucks(db_session):
    tenant = Tenant(id=uuid4(), name="Customer Fleet Garage", slug=f"customer-fleet-{uuid4().hex[:8]}")
    company = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Fleet", last_name="Contact",
        company_name="77 Cargo", email=f"fleet-{uuid4().hex[:6]}@example.com",
        fleet_enabled=False,
    )
    other_owner = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Owner", last_name="Contact",
        company_name="Owner LLC", email=f"owner-{uuid4().hex[:6]}@example.com",
    )
    legacy_fleet = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Garage", last_name="Fleet",
        company_name="Internal Fleet", email=f"internal-{uuid4().hex[:6]}@example.com",
        is_internal_fleet=True, fleet_enabled=True,
    )
    manager = User(
        id=uuid4(), tenant_id=tenant.id, email=f"manager-{uuid4().hex[:6]}@example.com",
        hashed_password="x", first_name="Shop", last_name="Owner",
        role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    company_truck = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=company.id,
        make="Volvo", model="VNL 760", unit_number="77-01",
    )
    leased_truck = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=other_owner.id,
        make="Peterbilt", model="579", unit_number="77-02",
    )
    db_session.add_all([tenant, company, other_owner, legacy_fleet, manager, company_truck, leased_truck])
    await db_session.flush()
    await seed_vehicle_account_relationships(db_session, company_truck, company)
    await seed_vehicle_account_relationships(db_session, leased_truck, other_owner)
    legacy_membership = await ensure_fleet_membership(
        db_session,
        tenant_id=tenant.id,
        vehicle_id=company_truck.id,
        fleet_customer_id=legacy_fleet.id,
    )
    await ensure_vehicle_relationship(
        db_session,
        tenant_id=tenant.id,
        vehicle_id=leased_truck.id,
        customer_id=company.id,
        relationship_type="operator",
    )
    await db_session.commit()

    updated = await customers.update_customer(
        customer_id=company.id,
        customer_data=CustomerUpdate(fleet_enabled=True),
        db=db_session,
        current_user=manager,
    )

    assert updated.fleet_enabled is True
    await db_session.refresh(legacy_membership)
    assert legacy_membership.effective_to is not None
    memberships = list((await db_session.execute(select(FleetMembership).where(
        FleetMembership.vehicle_id.in_((company_truck.id, leased_truck.id)),
        FleetMembership.effective_to.is_(None),
    ))).scalars().all())
    assert {membership.vehicle_id for membership in memberships} == {company_truck.id, leased_truck.id}
    assert {membership.fleet_customer_id for membership in memberships} == {company.id}

    active_operators = list((await db_session.execute(select(VehicleCustomerRelationship).where(
        VehicleCustomerRelationship.vehicle_id.in_((company_truck.id, leased_truck.id)),
        VehicleCustomerRelationship.relationship_type == "operator",
        VehicleCustomerRelationship.effective_to.is_(None),
    ))).scalars().all())
    assert {relationship.customer_id for relationship in active_operators} == {company.id}

    board = await fleet.fleet_board(db=db_session, current_user=manager)
    assert {item.id for item in board.trucks} == {company_truck.id, leased_truck.id}
    assert {item.fleet_company_name for item in board.trucks} == {"77 Cargo"}


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
    db_session.add_all([
        tenant, existing_company, editing_company, manager, existing_truck, editing_truck,
        VehicleCustomerRelationship(
            id=uuid4(), tenant_id=tenant.id, vehicle_id=existing_truck.id,
            customer_id=editing_company.id, relationship_type="owner", is_primary=True,
        ),
        VehicleCustomerRelationship(
            id=uuid4(), tenant_id=tenant.id, vehicle_id=existing_truck.id,
            customer_id=existing_company.id, relationship_type="operator",
        ),
        VehicleCustomerRelationship(
            id=uuid4(), tenant_id=tenant.id, vehicle_id=existing_truck.id,
            customer_id=editing_company.id, relationship_type="default_payer", is_primary=True,
        ),
    ])
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
            "owner_lessor_name": "Owner Trucking LLC",
            "operating_authority_name": "77 Cargo LLC",
            "default_invoice_recipient_name": "Owner Trucking LLC",
        },
    }


@pytest.mark.asyncio
async def test_ensure_vehicle_relationship_reuses_pending_row_when_autoflush_is_disabled(db_session):
    tenant = Tenant(id=uuid4(), name="Pending Role Garage", slug=f"pending-role-{uuid4().hex[:8]}")
    company = Customer(
        id=uuid4(), tenant_id=tenant.id, first_name="Fleet", last_name="Authority",
        company_name="77 Cargo", email=f"pending-role-{uuid4().hex[:6]}@example.com",
    )
    truck = Vehicle(
        id=uuid4(), tenant_id=tenant.id, customer_id=company.id,
        make="Volvo", model="VNR", vin="4V4NC9EH0MN271902",
    )
    db_session.add_all([tenant, company, truck])
    await db_session.flush()
    db_session.autoflush = False

    first = await ensure_vehicle_relationship(
        db_session,
        tenant_id=tenant.id,
        vehicle_id=truck.id,
        customer_id=company.id,
        relationship_type="operator",
        is_primary=True,
    )
    second = await ensure_vehicle_relationship(
        db_session,
        tenant_id=tenant.id,
        vehicle_id=truck.id,
        customer_id=company.id,
        relationship_type="operator",
    )

    assert second is first
    await db_session.commit()
    rows = list((await db_session.execute(select(VehicleCustomerRelationship).where(
        VehicleCustomerRelationship.vehicle_id == truck.id,
        VehicleCustomerRelationship.customer_id == company.id,
        VehicleCustomerRelationship.relationship_type == "operator",
        VehicleCustomerRelationship.effective_to.is_(None),
    ))).scalars().all())
    assert len(rows) == 1
    assert rows[0].is_primary is True
