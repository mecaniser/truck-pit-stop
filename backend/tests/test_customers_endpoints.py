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
            json={"first_name": name, "last_name": "T", "email": f"{name.lower()}@example.com", "no_vehicle": True},
            headers={"Authorization": f"Bearer {token}"},
        )
    r = await client.get(CUSTOMERS_URL, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()) >= 2


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client):
    r = await client.get(CUSTOMERS_URL)
    assert r.status_code in (401, 403)
