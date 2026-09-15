from __future__ import annotations

import pytest
import pytest_asyncio

from app.core.security import get_password_hash, create_access_token
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer


CUSTOMERS_URL = "/api/v1/customers"


@pytest_asyncio.fixture
async def staff_token(db_session):
    """Create a tenant + staff user and return (token, tenant_id)."""
    tenant = Tenant(name="Test Garage", slug="test-garage", is_active=True)
    db_session.add(tenant)
    await db_session.flush()

    user = User(
        email="staff@garage.com",
        hashed_password=get_password_hash("Str0ng@Pass!"),
        first_name="Staff",
        last_name="User",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return token, str(tenant.id)


@pytest.mark.asyncio
async def test_create_customer(client, staff_token):
    token, _ = staff_token
    r = await client.post(
        CUSTOMERS_URL,
        json={
            "first_name": "John",
            "last_name": "Doe",
            "company_name": "Doe Logistics LLC",
            "email": "john@example.com",
            "no_vehicle": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["first_name"] == "John"
    assert body["email"] == "john@example.com"


@pytest.mark.asyncio
async def test_create_customer_with_vehicle(client, staff_token):
    token, _ = staff_token
    r = await client.post(
        CUSTOMERS_URL,
        json={
            "first_name": "Jane",
            "last_name": "Doe",
            "company_name": "Jane Freight LLC",
            "email": "jane@example.com",
            "initial_vehicle": {
                "make": "Freightliner",
                "model": "Cascadia",
                "year": 2020,
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert len(body.get("vehicles", [])) == 1
    assert body["vehicles"][0]["make"] == "Freightliner"


@pytest.mark.asyncio
async def test_create_customer_duplicate_email_fails(client, staff_token):
    token, _ = staff_token
    payload = {
        "first_name": "Dup",
        "last_name": "User",
        "company_name": "Dup Transport LLC",
        "email": "dup@example.com",
        "no_vehicle": True,
    }
    await client.post(CUSTOMERS_URL, json=payload, headers={"Authorization": f"Bearer {token}"})
    r = await client.post(CUSTOMERS_URL, json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_customers(client, staff_token):
    token, _ = staff_token
    # Create two customers
    for name in ("Alice", "Bob"):
        await client.post(
            CUSTOMERS_URL,
            json={"first_name": name, "last_name": "T", "company_name": f"{name} LLC", "email": f"{name.lower()}@example.com", "no_vehicle": True},
            headers={"Authorization": f"Bearer {token}"},
        )
    r = await client.get(CUSTOMERS_URL, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()) >= 2


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client):
    r = await client.get(CUSTOMERS_URL)
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_deleting_a_truck_another_customer_owns_names_the_owner(client, staff_token, db_session):
    """A truck on one company's board can be owned by another.

    Matching on customer_id alone answered "Vehicle not found" for a truck that
    plainly exists, and the operator concluded it had been deleted. The error
    now says who owns it and what to do instead.
    """
    from uuid import uuid4
    from app.db.models.vehicle import Vehicle

    token, tenant_id = staff_token

    owner = Customer(
        id=uuid4(), tenant_id=tenant_id, first_name="House", last_name="Account",
        company_name="House Account", email=f"house-{uuid4().hex[:8]}@example.test",
    )
    other = Customer(
        id=uuid4(), tenant_id=tenant_id, first_name="Elis", last_name="Logistics",
        company_name="Elis Logistics", email=f"elis-{uuid4().hex[:8]}@example.test",
    )
    truck = Vehicle(
        id=uuid4(), tenant_id=tenant_id, customer_id=owner.id,
        make="Volvo", model="VNR", year=2020, unit_number="603",
    )
    db_session.add_all([owner, other, truck])
    await db_session.commit()

    # Deleting it from the company that does NOT own it.
    r = await client.delete(
        f"{CUSTOMERS_URL}/{other.id}/vehicles/{truck.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "House Account" in detail, detail
    assert "not found" != detail.lower()
    assert "603" in detail, detail

    # From its real owner it still deletes.
    r = await client.delete(
        f"{CUSTOMERS_URL}/{owner.id}/vehicles/{truck.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_deleting_a_truck_that_does_not_exist_still_says_not_found(client, staff_token, db_session):
    """The owner-specific message must not swallow a genuine miss."""
    from uuid import uuid4

    token, tenant_id = staff_token
    customer = Customer(
        id=uuid4(), tenant_id=tenant_id, first_name="A", last_name="B",
        company_name="Acme", email=f"acme-{uuid4().hex[:8]}@example.test",
    )
    db_session.add(customer)
    await db_session.commit()

    r = await client.delete(
        f"{CUSTOMERS_URL}/{customer.id}/vehicles/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Vehicle not found"
