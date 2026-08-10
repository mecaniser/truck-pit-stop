"""Focused boundary tests for the additive WorkOS flow."""
import pytest

from app.api.v1.endpoints import auth
from app.core.config import settings
from app.core.security import decode_token


@pytest.fixture(autouse=True)
def workos_settings(monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "WORKOS_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "WORKOS_API_KEY", "sk_test")
    monkeypatch.setattr(settings, "WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setattr(settings, "WORKOS_REDIRECT_URI", "http://localhost:8000/api/v1/auth/workos/callback")
    monkeypatch.setattr(auth, "get_redis", lambda: _resolved(fake_redis))


async def _resolved(value):
    return value


@pytest.mark.asyncio
async def test_login_issues_bound_state_and_safe_return(client, fake_redis):
    response = await client.get("/api/v1/auth/workos/login?return_to=//evil.test", follow_redirects=False)
    assert response.status_code == 307
    assert "response_type=code" in response.headers["location"]
    assert "redirect_uri=http%3A%2F%2Flocalhost" in response.headers["location"]
    state = response.cookies.get("workos_oauth_state")
    assert state and await fake_redis.get(f"workos:oauth-state:{state}") == "1"
    assert response.cookies.get("workos_return_to").strip('"') == "/"


@pytest.mark.asyncio
async def test_callback_rejects_missing_or_mismatched_state(client):
    assert (await client.get("/api/v1/auth/workos/callback?code=x")).status_code == 401
    await client.get("/api/v1/auth/workos/login")
    assert (await client.get("/api/v1/auth/workos/callback?code=x&state=wrong")).status_code == 401


@pytest.mark.asyncio
async def test_legacy_flag_hides_workos_login(client, monkeypatch):
    monkeypatch.setattr(settings, "WORKOS_AUTH_ENABLED", False)
    assert (await client.get("/api/v1/auth/workos/login")).status_code == 404


def test_workos_principal_token_is_not_refreshable_shape():
    from app.core.security import create_access_token
    token = create_access_token({"sub": "u", "auth_provider": "workos", "workos_user_id": "wu", "workos_org_id": "wo", "permissions": ["fleet:view"]})
    assert decode_token(token).get("type") is None
    assert decode_token(token)["auth_provider"] == "workos"
