"""Browser cookie continuity without crossing a tab's identity boundary."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.security import create_refresh_token, decode_token
from tests.test_auth_endpoints import REGISTER_URL, REFRESH_URL, LOGOUT_URL, VALID_USER


@pytest.mark.asyncio
async def test_stale_tab_recovers_after_rotation_grace(client, monkeypatch):
    monkeypatch.setattr(settings, "REFRESH_TOKEN_ROTATION_GRACE_SECONDS", 0)
    registered = await client.post(REGISTER_URL, json=VALID_USER)
    stale = registered.json()["refresh_token"]
    for _ in range(3):
        # The browser cookie advances while the sleeping tab retains its body.
        response = await client.post(REFRESH_URL, json={"refresh_token": stale})
        assert response.status_code == 200
        assert decode_token(response.json()["refresh_token"])["sub"] == decode_token(stale)["sub"]


@pytest.mark.asyncio
async def test_stale_tab_recovers_through_simulated_full_day(client, monkeypatch):
    from app.core import security
    from jose import jwt

    start = datetime.now(timezone.utc)
    class Clock(datetime):
        hours = 0

        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp((start + timedelta(hours=cls.hours)).timestamp(), tz)

        @classmethod
        def utcnow(cls):
            return cls.now(timezone.utc).replace(tzinfo=None)

    monkeypatch.setattr(security, "datetime", Clock)
    monkeypatch.setattr(jwt, "datetime", Clock)
    monkeypatch.setattr(settings, "REFRESH_TOKEN_ROTATION_GRACE_SECONDS", 0)
    registered = await client.post(REGISTER_URL, json=VALID_USER)
    stale = registered.json()["refresh_token"]
    for hour in range(3, 25, 3):
        Clock.hours = hour
        assert decode_token(registered.json()["access_token"]) is None
        response = await client.post(REFRESH_URL, json={"refresh_token": stale})
        assert response.status_code == 200
        assert decode_token(response.json()["access_token"])


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["sub", "tid", "ver", "rem", "invalid"])
async def test_different_cookie_scope_cannot_overwrite_browser_session(client, mismatch):
    registered = await client.post(REGISTER_URL, json=VALID_USER)
    body = registered.json()["refresh_token"]
    claims = decode_token(body)
    cookie = create_refresh_token(
        data={"sub": "different-user" if mismatch == "sub" else claims["sub"]},
        tenant_id="different-tenant" if mismatch == "tid" else claims.get("tid"),
        token_version=1 if mismatch == "ver" else claims.get("ver", 0),
        remember_me=mismatch == "rem",
    ) if mismatch != "invalid" else "invalid-cookie"
    client.cookies.clear()
    response = await client.post(REFRESH_URL, json={"refresh_token": body}, headers={"Cookie": f"refresh_token={cookie}"})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_logout_cookie_cannot_be_used_with_stale_body(client, monkeypatch):
    monkeypatch.setattr(settings, "REFRESH_TOKEN_ROTATION_GRACE_SECONDS", 0)
    registered = await client.post(REGISTER_URL, json=VALID_USER)
    stale = registered.json()["refresh_token"]
    rotated = await client.post(REFRESH_URL, json={"refresh_token": stale})
    current = rotated.json()["refresh_token"]
    assert (await client.post(LOGOUT_URL)).status_code == 200
    response = await client.post(REFRESH_URL, json={"refresh_token": stale}, headers={"Cookie": f"refresh_token={current}"})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_cookie_only_and_body_only_clients_remain_supported(client):
    await client.post(REGISTER_URL, json=VALID_USER)
    cookie_only = await client.post(REFRESH_URL)
    assert cookie_only.status_code == 200
    client.cookies.clear()
    body_only = await client.post(REFRESH_URL, json={"refresh_token": cookie_only.json()["refresh_token"]})
    assert body_only.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["expired", "access-token", "inactive", "version-invalidated"])
async def test_selected_cookie_still_requires_current_authority(client, db_session, reason):
    from jose import jwt
    from sqlalchemy import select
    from app.core import redis
    from app.db.models.user import User

    registered = await client.post(REGISTER_URL, json=VALID_USER)
    stale = registered.json()["refresh_token"]
    rotated = await client.post(REFRESH_URL, json={"refresh_token": stale})
    cookie = rotated.json()["refresh_token"]
    claims = decode_token(cookie)
    if reason == "expired":
        claims["exp"] = int((datetime.now(timezone.utc) - timedelta(seconds=60)).timestamp())
        cookie = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    elif reason == "access-token":
        cookie = rotated.json()["access_token"]
    elif reason == "inactive":
        user = (await db_session.execute(select(User).where(User.email == VALID_USER["email"]))).scalar_one()
        user.is_active = False
        await db_session.commit()
    else:
        await redis.increment_token_version(claims["sub"])
    client.cookies.clear()
    response = await client.post(REFRESH_URL, json={"refresh_token": stale}, headers={"Cookie": f"refresh_token={cookie}"})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
