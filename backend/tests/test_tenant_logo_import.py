from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.api.v1.endpoints import admin as admin_endpoints
from app.api.v1.endpoints import auth as auth_endpoints


ENROLL_URL = "/api/v1/auth/enroll-garage"
IMPORT_LOGO_URL = "/api/v1/admin/garage-profile/import-logo"


@pytest_asyncio.fixture
async def garage_owner_token(db_session):
    tenant = Tenant(
        name="Import Garage",
        slug="import-garage",
        website="https://garage.example.com",
        is_active=True,
        enrollment_status="approved",
    )
    db_session.add(tenant)
    await db_session.flush()

    user = User(
        email="owner@garage.example.com",
        hashed_password=get_password_hash("Str0ng@Pass!"),
        first_name="Owner",
        last_name="User",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    tenant.owner_id = user.id
    await db_session.commit()

    token = create_access_token({"sub": str(user.id)})
    return token, tenant.id


@pytest_asyncio.fixture
async def garage_owner_without_website_token(db_session):
    tenant = Tenant(
        name="No Website Garage",
        slug="no-website-garage",
        is_active=True,
        enrollment_status="approved",
    )
    db_session.add(tenant)
    await db_session.flush()

    user = User(
        email="owner@nowebsite.example.com",
        hashed_password=get_password_hash("Str0ng@Pass!"),
        first_name="Owner",
        last_name="User",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    tenant.owner_id = user.id
    await db_session.commit()

    token = create_access_token({"sub": str(user.id)})
    return token, tenant.id


@pytest.mark.asyncio
async def test_enroll_garage_imports_logo_when_website_present(client, db_session, monkeypatch):
    async def _fake_import_logo(website: str, tenant_id: str | None = None):
        assert website == "https://garage.example.com"
        assert tenant_id is not None
        return "https://cdn.example.com/tenant-logo.png"

    monkeypatch.setattr(auth_endpoints, "import_logo_from_website", _fake_import_logo)

    response = await client.post(
        ENROLL_URL,
        json={
            "garage_name": "Garage Import Test",
            "slug": "garage-import-test",
            "address": "123 Diesel Way",
            "phone": "5551234567",
            "email": "owner@garage.example.com",
            "website": "https://garage.example.com",
            "business_license": "LIC-123",
            "ein": "12-3456789",
            "owner_email": "owner@garage.example.com",
            "owner_first_name": "Garage",
            "owner_last_name": "Owner",
            "owner_phone": "5551234567",
            "owner_password": "Str0ng@Pass!",
        },
    )

    assert response.status_code == 201

    result = await db_session.execute(select(Tenant).where(Tenant.slug == "garage-import-test"))
    tenant = result.scalar_one()
    assert tenant.logo_url == "https://cdn.example.com/tenant-logo.png"


@pytest.mark.asyncio
async def test_enroll_garage_still_succeeds_when_logo_import_fails(client, db_session, monkeypatch):
    async def _fake_import_logo(_website: str, tenant_id: str | None = None):
        raise ValueError("boom")

    monkeypatch.setattr(auth_endpoints, "import_logo_from_website", _fake_import_logo)

    response = await client.post(
        ENROLL_URL,
        json={
            "garage_name": "Garage Import Fallback",
            "slug": "garage-import-fallback",
            "address": "456 Diesel Way",
            "phone": "5551234568",
            "email": "fallback@garage.example.com",
            "website": "https://garage.example.com",
            "business_license": "LIC-456",
            "ein": "98-7654321",
            "owner_email": "fallback@garage.example.com",
            "owner_first_name": "Fallback",
            "owner_last_name": "Owner",
            "owner_phone": "5551234568",
            "owner_password": "Str0ng@Pass!",
        },
    )

    assert response.status_code == 201

    result = await db_session.execute(select(Tenant).where(Tenant.slug == "garage-import-fallback"))
    tenant = result.scalar_one()
    assert tenant.logo_url is None


@pytest.mark.asyncio
async def test_import_logo_endpoint_updates_tenant_logo(client, db_session, garage_owner_token, monkeypatch):
    token, tenant_id = garage_owner_token

    async def _fake_import_logo(website: str, tenant_id: str | None = None):
        assert website == "https://new-garage.example.com"
        assert tenant_id is not None
        return "https://cdn.example.com/imported-logo.png"

    monkeypatch.setattr(admin_endpoints, "import_logo_from_website", _fake_import_logo)

    response = await client.post(
        IMPORT_LOGO_URL,
        json={"website": "https://new-garage.example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["website"] == "https://new-garage.example.com"
    assert body["logo_url"] == "https://cdn.example.com/imported-logo.png"

    result = await db_session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one()
    assert tenant.website == "https://new-garage.example.com"
    assert tenant.logo_url == "https://cdn.example.com/imported-logo.png"


@pytest.mark.asyncio
async def test_import_logo_endpoint_requires_website(client, garage_owner_without_website_token):
    token, _tenant_id = garage_owner_without_website_token

    response = await client.post(
        IMPORT_LOGO_URL,
        json={"website": ""},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Website is required before importing a logo"
