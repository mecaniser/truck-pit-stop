from __future__ import annotations

import pytest


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"

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
