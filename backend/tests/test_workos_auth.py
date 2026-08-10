"""Focused boundary tests for the additive WorkOS flow."""
import pytest
from datetime import datetime, timezone
from starlette.requests import Request

from app.api.v1.endpoints import auth
from app.core.config import settings
from app.core.security import decode_token
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.core.workos_auth import CurrentPrincipal, get_current_principal, require_permission
from fastapi import HTTPException
from uuid import uuid4


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


def _request(state: str, return_to: str = "/"):
    headers = [(b"cookie", f"workos_oauth_state={state}; workos_return_to={return_to}".encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": ("127.0.0.1", 1)})


class _WorkOSResponse:
    status_code = 200
    def json(self):
        return {"user": {"id": "wu_1"}, "organization_id": "org_1", "permissions": ["fleet:view"]}


class _WorkOSClient:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def post(self, *args, **kwargs): return _WorkOSResponse()


class _BadWorkOSClient(_WorkOSClient):
    def __init__(self, status_code=400, payload=None): self.status_code, self.payload = status_code, payload or {}
    async def post(self, *args, **kwargs):
        result = _WorkOSResponse(); result.status_code = self.status_code; result.json = lambda: self.payload; return result


@pytest.mark.asyncio
async def test_callback_issues_only_short_workos_access_token(db_session, fake_redis, monkeypatch):
    tenant = Tenant(name="T", slug="t", workos_organization_id="org_1")
    user = User(email="u@example.test", hashed_password="x", first_name="U", last_name="T", role=UserRole.GARAGE_ADMIN, tenant_id=None, workos_user_id="wu_1")
    db_session.add_all([tenant, user]); await db_session.commit()
    await fake_redis.setex("workos:oauth-state:s", 600, "1")
    monkeypatch.setattr(auth, "get_redis", lambda: _resolved(fake_redis))
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kwargs: _WorkOSClient())
    before_tenant = user.tenant_id
    response = await auth.workos_callback(_request("s"), "code", "s", db_session)
    token = decode_token(response.headers.getlist("set-cookie")[0].split("access_token=")[1].split(";")[0])
    assert token["auth_provider"] == "workos" and token["permissions"] == ["fleet:view"]
    assert user.tenant_id == before_tenant
    assert all("refresh_token=" not in value or "Max-Age=0" in value for value in response.headers.getlist("set-cookie"))


def _workos_token(user_id, workos_user_id="wu_1", org_id="org_1", permissions=None):
    from app.core.security import create_access_token
    return create_access_token({"sub": str(user_id), "auth_provider": "workos", "workos_user_id": workos_user_id, "workos_org_id": org_id, "permissions": permissions or ["fleet:view"]})


@pytest.mark.asyncio
async def test_current_principal_validates_mapping_and_active_state(db_session):
    tenant = Tenant(name="Principal", slug="principal", workos_organization_id="org_1")
    user = User(email="principal@example.test", hashed_password="x", first_name="P", last_name="U", role=UserRole.GARAGE_ADMIN, workos_user_id="wu_1")
    db_session.add_all([tenant, user]); await db_session.commit()
    principal = await get_current_principal(_workos_token(user.id, permissions=["fleet:view", "fleet:assign"]), db_session)
    assert principal == CurrentPrincipal(user.id, "wu_1", "org_1", tenant.id, frozenset({"fleet:view", "fleet:assign"}))
    for token in [
        _workos_token(user.id, workos_user_id="wrong"),
        _workos_token(user.id, org_id="org_missing"),
        _workos_token(uuid4()),
    ]:
        with pytest.raises(HTTPException): await get_current_principal(token, db_session)
    user.is_active = False; await db_session.commit()
    with pytest.raises(HTTPException): await get_current_principal(_workos_token(user.id), db_session)
    user.is_active = True; tenant.is_active = False; await db_session.commit()
    with pytest.raises(HTTPException): await get_current_principal(_workos_token(user.id), db_session)


@pytest.mark.asyncio
async def test_current_principal_rejects_legacy_and_permission_guard():
    from app.core.security import create_access_token
    with pytest.raises(HTTPException): await get_current_principal(create_access_token({"sub": str(uuid4())}), None)
    principal = CurrentPrincipal(uuid4(), "wu", "org", uuid4(), frozenset({"fleet:view"}))
    with pytest.raises(HTTPException): await require_permission("fleet:view", "fleet:assign")(principal)
    assert await require_permission("fleet:view")(principal) == principal


@pytest.mark.asyncio
async def test_callback_fails_closed_for_bad_workos_response(db_session, fake_redis, monkeypatch):
    tenant = Tenant(name="Reject", slug="reject", workos_organization_id="org_1")
    user = User(email="reject@example.test", hashed_password="x", first_name="R", last_name="U", role=UserRole.GARAGE_ADMIN, workos_user_id="wu_1")
    db_session.add_all([tenant, user]); await db_session.commit()
    monkeypatch.setattr(auth, "get_redis", lambda: _resolved(fake_redis))
    cases = [None, {"user": {}, "organization_id": "org_1", "permissions": []}, {"user": {"id": "wu_1"}, "permissions": []}, {"user": {"id": "wu_1"}, "organization_id": "org_1"}, {"user": {"id": "wu_1"}, "organization_id": "org_1", "permissions": "bad"}, {"user": {"id": "wu_1"}, "organization_id": "org_1", "permissions": [1]}]
    for i, payload in enumerate(cases):
        await fake_redis.setex(f"workos:oauth-state:r{i}", 600, "1")
        monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kwargs: _BadWorkOSClient(400) if payload is None else _BadWorkOSClient(200, payload))
        with pytest.raises(HTTPException): await auth.workos_callback(_request(f"r{i}"), "code", f"r{i}", db_session)


@pytest.mark.asyncio
async def test_workos_state_replay_and_refresh_are_rejected(client, fake_redis, monkeypatch):
    await client.get("/api/v1/auth/workos/login")
    state = client.cookies.get("workos_oauth_state")
    assert state
    await fake_redis.delete(f"workos:oauth-state:{state}")
    assert (await client.get(f"/api/v1/auth/workos/callback?code=x&state={state}")).status_code == 401
    from app.core.security import create_access_token
    token = _workos_token(uuid4())
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401
