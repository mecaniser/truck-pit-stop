from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.inventory import Inventory
from app.db.models.service import Service
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def workspace_typeahead_context(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name="Primary Garage", slug=f"primary-{suffix}", is_active=True)
    other_tenant = Tenant(name="Other Garage", slug=f"other-{suffix}", is_active=True)
    db_session.add_all([tenant, other_tenant])
    await db_session.flush()

    customer = Customer(
        tenant_id=tenant.id,
        first_name="Avery",
        last_name="Driver",
        company_name="Acme Hauling",
        email=f"avery-{suffix}@example.com",
        phone="555-0100",
    )
    deleted_customer = Customer(
        tenant_id=tenant.id,
        first_name="Retired",
        last_name="Customer",
        company_name="Retired Hauling",
        email=f"retired-{suffix}@example.com",
        deleted_at=datetime.now(timezone.utc),
    )
    internal_customer = Customer(
        tenant_id=tenant.id,
        first_name="Garage",
        last_name="Fleet",
        company_name="Primary Internal Fleet",
        email=f"fleet-{suffix}@example.com",
        is_internal_fleet=True,
    )
    other_customer = Customer(
        tenant_id=other_tenant.id,
        first_name="Other",
        last_name="Driver",
        company_name="Acme Foreign",
        email=f"other-{suffix}@example.com",
    )
    db_session.add_all([customer, deleted_customer, internal_customer, other_customer])
    await db_session.flush()

    vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2022,
        unit_number="ACME-01",
        license_plate="ACME01",
        vin="1FUJHHDR8NLACME01",
    )
    deleted_vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=customer.id,
        make="Freightliner",
        model="Retired",
        year=2015,
        unit_number="RETIRED-01",
        deleted_at=datetime.now(timezone.utc),
    )
    internal_vehicle = Vehicle(
        tenant_id=tenant.id,
        customer_id=internal_customer.id,
        make="Peterbilt",
        model="579",
        year=2023,
        unit_number="FLEET-01",
    )
    other_vehicle = Vehicle(
        tenant_id=other_tenant.id,
        customer_id=other_customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2021,
        unit_number="OTHER-01",
    )
    db_session.add_all([vehicle, deleted_vehicle, internal_vehicle, other_vehicle])

    service = Service(
        tenant_id=tenant.id,
        name="Annual Inspection",
        description="DOT inspection",
        duration_minutes=60,
        base_price=Decimal("149.00"),
        is_active=True,
    )
    inactive_service = Service(
        tenant_id=tenant.id,
        name="Retired Inspection",
        duration_minutes=60,
        is_active=False,
    )
    deleted_service = Service(
        tenant_id=tenant.id,
        name="Deleted Inspection",
        duration_minutes=60,
        is_active=True,
        deleted_at=datetime.now(timezone.utc),
    )
    other_service = Service(
        tenant_id=other_tenant.id,
        name="Foreign Inspection",
        duration_minutes=60,
        is_active=True,
    )
    db_session.add_all([service, inactive_service, deleted_service, other_service])

    inventory = Inventory(
        tenant_id=tenant.id,
        sku="AF-100",
        name="Air Filter",
        stock_quantity=4,
        on_order_quantity=2,
        reorder_level=1,
        cost=Decimal("20.00"),
        selling_price=Decimal("39.00"),
    )
    out_of_stock_inventory = Inventory(
        tenant_id=tenant.id,
        sku="OF-200",
        name="Oil Filter",
        stock_quantity=0,
        on_order_quantity=3,
        reorder_level=1,
        cost=Decimal("10.00"),
        selling_price=Decimal("19.00"),
    )
    deleted_inventory = Inventory(
        tenant_id=tenant.id,
        sku="DF-300",
        name="Deleted Filter",
        stock_quantity=8,
        reorder_level=1,
        cost=Decimal("10.00"),
        selling_price=Decimal("19.00"),
        deleted_at=datetime.now(timezone.utc),
    )
    other_inventory = Inventory(
        tenant_id=other_tenant.id,
        sku="FF-400",
        name="Foreign Filter",
        stock_quantity=8,
        reorder_level=1,
        cost=Decimal("10.00"),
        selling_price=Decimal("19.00"),
    )
    db_session.add_all([inventory, out_of_stock_inventory, deleted_inventory, other_inventory])

    owner = User(
        tenant_id=tenant.id,
        email=f"owner-{suffix}@example.com",
        hashed_password="not-used-in-token-tests",
        first_name="Owner",
        last_name="User",
        role=UserRole.GARAGE_OWNER,
        is_active=True,
        is_verified=True,
    )
    fleet_manager = User(
        tenant_id=tenant.id,
        email=f"fleet-manager-{suffix}@example.com",
        hashed_password="not-used-in-token-tests",
        first_name="Fleet",
        last_name="Manager",
        role=UserRole.FLEET_MANAGER,
        is_active=True,
        is_verified=True,
    )
    customer_user = User(
        tenant_id=tenant.id,
        customer_id=customer.id,
        email=f"customer-user-{suffix}@example.com",
        hashed_password="not-used-in-token-tests",
        first_name="Avery",
        last_name="User",
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([owner, fleet_manager, customer_user])
    await db_session.commit()

    return {
        "owner_token": create_access_token({"sub": str(owner.id)}),
        "fleet_token": create_access_token({"sub": str(fleet_manager.id)}),
        "customer_token": create_access_token({"sub": str(customer_user.id)}),
        "customer": customer,
        "internal_customer": internal_customer,
        "vehicle": vehicle,
        "internal_vehicle": internal_vehicle,
        "service": service,
        "inventory": inventory,
        "out_of_stock_inventory": out_of_stock_inventory,
    }


@pytest.mark.asyncio
async def test_workspace_typeaheads_are_tenant_scoped_capped_and_minimal(client, workspace_typeahead_context):
    ctx = workspace_typeahead_context
    headers = _auth(ctx["owner_token"])

    customers = await client.get("/api/v1/customers/typeahead", params={"q": "acme"}, headers=headers)
    assert customers.status_code == 200
    assert [item["id"] for item in customers.json()] == [str(ctx["customer"].id)]
    assert set(customers.json()[0]) == {"id", "first_name", "last_name", "company_name", "email", "phone"}

    vehicles = await client.get(
        "/api/v1/vehicles/typeahead",
        params={"customer_id": str(ctx["customer"].id), "q": "freight"},
        headers=headers,
    )
    assert vehicles.status_code == 200
    assert [item["id"] for item in vehicles.json()] == [str(ctx["vehicle"].id)]
    assert set(vehicles.json()[0]) == {
        "id", "customer_id", "make", "model", "year", "unit_number", "license_plate", "vin"
    }

    services = await client.get("/api/v1/services/typeahead", params={"q": "inspection"}, headers=headers)
    assert services.status_code == 200
    assert [item["id"] for item in services.json()] == [str(ctx["service"].id)]
    assert "parts" not in services.json()[0]
    assert "computed_total_price" not in services.json()[0]

    inventory = await client.get("/api/v1/inventory/typeahead", params={"q": "filter"}, headers=headers)
    assert inventory.status_code == 200
    assert [item["id"] for item in inventory.json()] == [str(ctx["inventory"].id)]
    assert set(inventory.json()[0]) == {
        "id", "sku", "name", "stock_quantity", "on_order_quantity", "unit_type", "cost", "selling_price"
    }

    including_out_of_stock = await client.get(
        "/api/v1/inventory/typeahead",
        params={"q": "filter", "in_stock": "false"},
        headers=headers,
    )
    assert including_out_of_stock.status_code == 200
    assert {item["id"] for item in including_out_of_stock.json()} == {
        str(ctx["inventory"].id),
        str(ctx["out_of_stock_inventory"].id),
    }

    cap = await client.get("/api/v1/customers/typeahead", params={"limit": 51}, headers=headers)
    assert cap.status_code == 422


@pytest.mark.asyncio
async def test_workspace_typeaheads_preserve_customer_and_fleet_scopes(client, workspace_typeahead_context):
    ctx = workspace_typeahead_context

    customer_headers = _auth(ctx["customer_token"])
    own_customers = await client.get("/api/v1/customers/typeahead", headers=customer_headers)
    assert own_customers.status_code == 200
    assert [item["id"] for item in own_customers.json()] == [str(ctx["customer"].id)]

    own_vehicles = await client.get("/api/v1/vehicles/typeahead", headers=customer_headers)
    assert own_vehicles.status_code == 200
    assert [item["id"] for item in own_vehicles.json()] == [str(ctx["vehicle"].id)]

    fleet_headers = _auth(ctx["fleet_token"])
    fleet_customers = await client.get("/api/v1/customers/typeahead", headers=fleet_headers)
    assert fleet_customers.status_code == 200
    assert [item["id"] for item in fleet_customers.json()] == [str(ctx["internal_customer"].id)]

    fleet_vehicles = await client.get("/api/v1/vehicles/typeahead", headers=fleet_headers)
    assert fleet_vehicles.status_code == 200
    assert [item["id"] for item in fleet_vehicles.json()] == [str(ctx["internal_vehicle"].id)]
