from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.models.user import User, UserRole


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"
PLATFORM_CONTACT_URL = "/api/v1/auth/platform-contact"

VALID_USER = {
    "email": "alice@example.com",
    "password": "Str0ng@Pass!",
    "first_name": "Alice",
    "last_name": "Smith",
}


@pytest.mark.asyncio
async def test_register_returns_tokens(client):
    r = await client.post(REGISTER_URL, json=VALID_USER)
    assert r.status_code == 201
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(client):
    await client.post(REGISTER_URL, json=VALID_USER)
    r = await client.post(REGISTER_URL, json=VALID_USER)
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"]


@pytest.mark.asyncio
async def test_register_weak_password_rejected(client):
    payload = {**VALID_USER, "email": "weak@example.com", "password": "short"}
    r = await client.post(REGISTER_URL, json=payload)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client):
    await client.post(REGISTER_URL, json=VALID_USER)
    r = await client.post(LOGIN_URL, json={
        "email": VALID_USER["email"],
        "password": VALID_USER["password"],
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post(REGISTER_URL, json=VALID_USER)
    r = await client.post(LOGIN_URL, json={
        "email": VALID_USER["email"],
        "password": "Wrong@Pass1",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    r = await client.post(LOGIN_URL, json={
        "email": "nobody@example.com",
        "password": "Anything@1",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    r = await client.get(ME_URL)
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_returns_user_info(client):
    reg = await client.post(REGISTER_URL, json=VALID_USER)
    token = reg.json()["access_token"]
    r = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == VALID_USER["email"]
    assert body["first_name"] == VALID_USER["first_name"]
    assert body["role"] == "customer"


@pytest.mark.asyncio
async def test_refresh_token_flow(client):
    reg = await client.post(REGISTER_URL, json=VALID_USER)
    refresh = reg.json()["refresh_token"]
    r = await client.post(REFRESH_URL, json={"refresh_token": refresh})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["access_token"] != reg.json()["access_token"]


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(client):
    r = await client.post(REFRESH_URL, json={"refresh_token": "garbage"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_session(client):
    reg = await client.post(REGISTER_URL, json=VALID_USER)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(LOGOUT_URL, headers=headers)
    assert r.status_code == 200
    assert "logged out" in r.json()["message"].lower()


@pytest.mark.asyncio
async def test_platform_contact_defaults_without_super_admin(client):
    r = await client.get(PLATFORM_CONTACT_URL)
    assert r.status_code == 200
    body = r.json()
    assert body["support_name"] == "Diesel Bridge Support"
    assert body["support_email"] is None
    assert body["support_phone"] is None


@pytest.mark.asyncio
async def test_platform_contact_returns_latest_active_super_admin(client, db_session):
    older = User(
        email="older-admin@example.com",
        hashed_password="x",
        first_name="Older",
        last_name="Admin",
        phone="(555) 111-2222",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        is_verified=True,
    )
    latest = User(
        email="latest-admin@example.com",
        hashed_password="x",
        first_name="Latest",
        last_name="Admin",
        phone="(555) 999-0000",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        is_verified=True,
    )
    older.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    older.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    latest.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    latest.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    db_session.add(older)
    db_session.add(latest)
    await db_session.commit()

    r = await client.get(PLATFORM_CONTACT_URL)
    assert r.status_code == 200
    body = r.json()
    assert body["support_name"] == "Latest Admin"
    assert body["support_email"] == "latest-admin@example.com"
    assert body["support_phone"] == "(555) 999-0000"
