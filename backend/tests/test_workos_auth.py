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
from app.core import workos_auth
from app.services import workos_provider, workos_session
from app.services.workos_provider import WorkOSProviderError
from fastapi import HTTPException
from uuid import uuid4


@pytest.fixture(autouse=True)
def workos_settings(monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "WORKOS_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "WORKOS_API_KEY", "sk_test")
    monkeypatch.setattr(settings, "WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setattr(settings, "WORKOS_REDIRECT_URI", "http://localhost:8000/api/v1/auth/workos/callback")
    monkeypatch.setattr(auth, "get_redis", lambda: _resolved(fake_redis))
    monkeypatch.setattr(workos_session, "get_redis", lambda: _resolved(fake_redis))
    async def _auth_state(jti, user_id):
        blacklisted = bool(jti and await fake_redis.get(f"token_blacklist:{jti}"))
        version = await fake_redis.get(f"token_version:{user_id}")
        return blacklisted, int(version) if version else 0
    async def _token_version(user_id):
        version = await fake_redis.get(f"token_version:{user_id}")
        return int(version) if version else 0
    monkeypatch.setattr(workos_auth, "get_auth_token_state", _auth_state)
    monkeypatch.setattr(auth, "get_token_version", _token_version)


async def _resolved(value):
    return value


@pytest.mark.asyncio
async def test_login_issues_bound_state_and_safe_return(client, fake_redis):
    response = await client.get("/api/v1/auth/workos/login?return_to=//evil.test", follow_redirects=False)
    assert response.status_code == 307
    assert "response_type=code" in response.headers["location"]
    assert "provider=authkit" in response.headers["location"]
    assert "redirect_uri=http%3A%2F%2Flocalhost" in response.headers["location"]
    state = response.cookies.get("workos_oauth_state")
    assert state and await fake_redis.get(f"workos:oauth-state:{state}") == "1"
    assert response.cookies.get("workos_return_to").strip('"') == "/"


@pytest.mark.asyncio
async def test_login_selects_exact_active_mapped_tenant(client, db_session):
    tenant = Tenant(
        name="Selected tenant",
        slug="selected-tenant",
        workos_organization_id="org_selected",
    )
    db_session.add(tenant)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/auth/workos/login?tenant_id={tenant.id}&return_to=%2Fdashboard",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert "organization_id=org_selected" in response.headers["location"]
    assert "prompt=login" in response.headers["location"]
    assert response.cookies.get("workos_return_to").strip('"') == "/dashboard"


@pytest.mark.asyncio
async def test_login_rejects_inactive_or_unmapped_tenant(client, db_session):
    inactive = Tenant(
        name="Inactive tenant",
        slug="inactive-tenant",
        workos_organization_id="org_inactive",
        is_active=False,
    )
    unmapped = Tenant(name="Unmapped tenant", slug="unmapped-tenant")
    db_session.add_all([inactive, unmapped])
    await db_session.commit()

    for tenant in (inactive, unmapped):
        response = await client.get(
            f"/api/v1/auth/workos/login?tenant_id={tenant.id}",
            follow_redirects=False,
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "WorkOS organization is not available"


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


async def _authenticate(_payload):
    return {
        "user": {"id": "wu_1", "email": "u@example.test"},
        "access_token": "provider-access",
        "refresh_token": "provider-refresh",
    }


async def _verify(_token):
    return {
        "sub": "wu_1",
        "org_id": "org_1",
        "role": "garage_admin",
        "permissions": ["fleet:view"],
    }


@pytest.mark.asyncio
async def test_callback_issues_short_access_and_opaque_server_session(db_session, fake_redis, monkeypatch):
    tenant = Tenant(name="T", slug="t", workos_organization_id="org_1")
    user = User(email="u@example.test", hashed_password="x", first_name="U", last_name="T", role=UserRole.GARAGE_ADMIN, tenant_id=None, workos_user_id="wu_1")
    db_session.add_all([tenant, user]); await db_session.commit()
    await fake_redis.setex("workos:oauth-state:s", 600, "1")
    monkeypatch.setattr(auth, "get_redis", lambda: _resolved(fake_redis))
    monkeypatch.setattr(workos_provider, "authenticate", _authenticate)
    monkeypatch.setattr(workos_provider, "verify_access_token", _verify)
    before_tenant = user.tenant_id
    response = await auth.workos_callback(_request("s"), "code", "s", db_session)
    token = decode_token(response.headers.getlist("set-cookie")[0].split("access_token=")[1].split(";")[0])
    assert token["auth_provider"] == "workos" and token["permissions"] == ["fleet:view"]
    assert user.tenant_id == before_tenant
    assert all("refresh_token=" not in value or "Max-Age=0" in value for value in response.headers.getlist("set-cookie"))
    session_id = next(value.split("workos_session=")[1].split(";")[0] for value in response.headers.getlist("set-cookie") if "workos_session=" in value)
    stored = await fake_redis.get(f"workos:session:{session_id}")
    assert stored and "provider-refresh" not in stored


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


@pytest.mark.asyncio
async def test_current_principal_rejects_revoked_or_stale_workos_token(db_session, fake_redis):
    tenant = Tenant(name="Revoked", slug="revoked", workos_organization_id="org_1")
    user = User(email="revoked@example.test", hashed_password="x", first_name="R", last_name="U", role=UserRole.GARAGE_ADMIN, workos_user_id="wu_1")
    db_session.add_all([tenant, user]); await db_session.commit()
    token = _workos_token(user.id)
    claims = decode_token(token)
    await fake_redis.setex(f"token_blacklist:{claims['jti']}", 300, "1")
    with pytest.raises(HTTPException):
        await get_current_principal(token, db_session)
    await fake_redis.delete(f"token_blacklist:{claims['jti']}")
    await fake_redis.set(f"token_version:{user.id}", "1")
    with pytest.raises(HTTPException):
        await get_current_principal(token, db_session)
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
    async def provider_failure(_payload):
        raise WorkOSProviderError("failed")
    async def verify_failure(_token):
        raise WorkOSProviderError("bad claims")
    async def no_refresh(_payload):
        value = await _authenticate(_payload)
        value.pop("refresh_token")
        return value
    cases = [
        (provider_failure, _verify),
        (_authenticate, verify_failure),
        (no_refresh, _verify),
    ]
    for i, (authenticate, verify) in enumerate(cases):
        await fake_redis.setex(f"workos:oauth-state:r{i}", 600, "1")
        monkeypatch.setattr(workos_provider, "authenticate", authenticate)
        monkeypatch.setattr(workos_provider, "verify_access_token", verify)
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


@pytest.mark.asyncio
async def test_workos_logout_clears_only_access_cookie(client):
    token = _workos_token(uuid4())
    client.cookies.set("access_token", token)
    client.cookies.set("refresh_token", "legacy-refresh", path="/api/v1/auth")
    response = await client.post("/api/v1/auth/workos/logout")
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    assert any("access_token=\"\"" in cookie or "access_token=" in cookie for cookie in cookies)
    assert not any("refresh_token=" in cookie for cookie in cookies)


@pytest.mark.asyncio
async def test_workos_logout_can_end_server_session_after_access_expiry(client, fake_redis):
    await fake_redis.setex("workos:session:opaque", 600, "{}")
    client.cookies.set("workos_session", "opaque", path="/api/v1/auth/workos")
    response = await client.post("/api/v1/auth/workos/logout")
    assert response.status_code == 200
    assert await fake_redis.get("workos:session:opaque") is None
