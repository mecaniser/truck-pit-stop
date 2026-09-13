"""DB-064: provider outages cannot destroy an authorized browser session."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from app.api.v1.endpoints import workos_lifecycle
from app.core.config import settings
from app.services import identity_lifecycle, workos_provider, workos_session
from app.services.workos_provider import WorkOSProviderError, WorkOSProviderTemporaryError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def context(monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "WORKOS_AUTH_ENABLED", True)
    monkeypatch.setattr(workos_session, "get_redis", AsyncMock(return_value=fake_redis))
    monkeypatch.setattr(workos_lifecycle, "get_token_version", AsyncMock(return_value=0))
    monkeypatch.setattr(workos_provider, "authenticate", AsyncMock(return_value={
        "access_token": "provider-access", "refresh_token": "new-refresh", "user": {},
    }))
    monkeypatch.setattr(workos_provider, "verify_access_token", AsyncMock(return_value={
        "sub": "wu", "org_id": "org", "permissions": ["driver_portal:use"],
    }))
    monkeypatch.setattr(workos_lifecycle, "resolve_authenticated_identity", AsyncMock(return_value=(
        SimpleNamespace(id="local"), SimpleNamespace(id="tenant"), None,
    )))
    return AsyncMock(), Request({"type": "http", "method": "POST", "path": "/", "headers": []})


async def session():
    return await workos_session.create_session(refresh_token="old-refresh", local_user_id="local", workos_user_id="wu", workos_org_id="org")


@pytest.mark.parametrize("stage", ["authenticate", "verify_access_token", "membership"])
async def test_outage_preserves_session_then_recovers(context, monkeypatch, stage):
    db, request = context
    sid = await session()
    target = workos_lifecycle if stage == "membership" else workos_provider
    name = "resolve_authenticated_identity" if stage == "membership" else stage
    original = getattr(target, name)
    monkeypatch.setattr(target, name, AsyncMock(side_effect=WorkOSProviderTemporaryError("outage")))
    response = Response()
    with pytest.raises(HTTPException) as err:
        await workos_lifecycle.refresh_session(request, response, sid, db)
    assert err.value.status_code == 503
    assert err.value.detail["code"] == "session_refresh_unavailable"
    stored = await workos_session.get_session(sid)
    assert stored["refresh_token"] == ("old-refresh" if stage == "authenticate" else "new-refresh")
    assert not response.headers.getlist("set-cookie")
    monkeypatch.setattr(target, name, original)
    await workos_lifecycle.refresh_session(request, response, sid, db)
    assert any("access_token=" in cookie for cookie in response.headers.getlist("set-cookie"))
    if stage != "authenticate":
        assert workos_provider.authenticate.call_args.args[0]["refresh_token"] == "new-refresh"


@pytest.mark.parametrize("failure", ["invalid_grant", "bad_signature", "wrong_org", "wrong_user", "inactive_membership"])
async def test_definitive_auth_failures_still_revoke(context, monkeypatch, failure):
    db, request = context
    sid = await session()
    if failure == "invalid_grant":
        monkeypatch.setattr(workos_provider, "authenticate", AsyncMock(side_effect=WorkOSProviderError("invalid grant")))
    elif failure == "bad_signature":
        monkeypatch.setattr(workos_provider, "verify_access_token", AsyncMock(side_effect=WorkOSProviderError("bad signature")))
    elif failure in {"wrong_org", "wrong_user"}:
        workos_provider.verify_access_token.return_value["org_id" if failure == "wrong_org" else "sub"] = "foreign"
    else:
        monkeypatch.setattr(workos_lifecycle, "resolve_authenticated_identity", AsyncMock(side_effect=HTTPException(403, "inactive")))
    response = Response()
    with pytest.raises(HTTPException) as err:
        await workos_lifecycle.refresh_session(request, response, sid, db)
    assert err.value.status_code == 401
    assert err.value.detail["code"] == "session_ended"
    assert await workos_session.get_session(sid) is None
    assert not response.headers.getlist("set-cookie")


async def test_concurrent_renewal_never_calls_provider_without_lock(context):
    db, request = context
    sid = await session()
    lock = await workos_session.acquire_refresh_lock(sid)
    with pytest.raises(HTTPException) as err:
        await workos_lifecycle.refresh_session(request, Response(), sid, db)
    assert err.value.status_code == 409
    workos_provider.authenticate.assert_not_called()
    assert await workos_session.get_session(sid)
    await workos_session.release_refresh_lock(sid, lock)
    await workos_lifecycle.refresh_session(request, Response(), sid, db)


async def test_logout_during_provider_call_cannot_resurrect_session(context, monkeypatch):
    db, request = context
    sid = await session()
    async def provider(_payload):
        await workos_session.delete_session(sid)
        return {"access_token": "access", "refresh_token": "rotated"}
    monkeypatch.setattr(workos_provider, "authenticate", provider)
    response = Response()
    with pytest.raises(HTTPException) as err:
        await workos_lifecycle.refresh_session(request, response, sid, db)
    assert err.value.status_code == 401
    assert await workos_session.get_session(sid) is None
    assert not response.headers.getlist("set-cookie")


async def test_unexpected_failure_releases_lock(context, monkeypatch):
    db, request = context
    sid = await session()
    monkeypatch.setattr(workos_provider, "authenticate", AsyncMock(side_effect=RuntimeError("unexpected")))
    with pytest.raises(RuntimeError):
        await workos_lifecycle.refresh_session(request, Response(), sid, db)
    assert await workos_session.acquire_refresh_lock(sid)
    assert await workos_session.get_session(sid)


async def test_lost_lease_cancels_refresh_without_clearing_successor(context, monkeypatch, fake_redis):
    sid = await session()
    monkeypatch.setattr(workos_session, "_refresh_lock_seconds", lambda: 0.03)
    started = asyncio.Event()
    async def slow(_token):
        started.set()
        await asyncio.sleep(10)
    operation = asyncio.create_task(workos_session.run_with_refresh_lock(sid, slow))
    await started.wait()
    fake_redis.kv[f"{workos_session.REFRESH_LOCK_PREFIX}{sid}"] = "successor"
    with pytest.raises(workos_session.RefreshLockUnavailable):
        await operation
    assert fake_redis.kv[f"{workos_session.REFRESH_LOCK_PREFIX}{sid}"] == "successor"
    assert await workos_session.get_session(sid)


@pytest.mark.parametrize("status,payload,temporary", [
    (429, {"error": "rate_limit"}, True), (500, {"error": "invalid_grant"}, True),
    (401, {"error": "invalid_client"}, True), (400, {"error": "invalid_grant"}, False),
    (200, [], True),
])
async def test_provider_classification(monkeypatch, status, payload, temporary):
    monkeypatch.setattr(workos_provider, "_session_request", AsyncMock(return_value=httpx.Response(status, json=payload)))
    with pytest.raises(WorkOSProviderError) as err:
        await workos_provider.authenticate({"grant_type": "refresh_token"})
    assert isinstance(err.value, WorkOSProviderTemporaryError) is temporary


async def test_network_timeout_is_temporary(monkeypatch):
    client = AsyncMock()
    client.post.side_effect = httpx.ReadTimeout("timeout")
    client.__aenter__.return_value = client
    monkeypatch.setattr(workos_provider.httpx, "AsyncClient", lambda **kw: client)
    with pytest.raises(WorkOSProviderTemporaryError):
        await workos_provider.authenticate({"grant_type": "refresh_token"})


async def test_malformed_provider_json_is_temporary(monkeypatch):
    monkeypatch.setattr(workos_provider, "_session_request", AsyncMock(return_value=httpx.Response(200, content=b"bad json")))
    with pytest.raises(WorkOSProviderTemporaryError):
        await workos_provider.authenticate({"grant_type": "refresh_token"})


async def test_membership_lookup_preserves_temporary_error(monkeypatch):
    tenant = SimpleNamespace(id="tenant", is_active=True)
    external = SimpleNamespace(principal_id="principal", status="active")
    membership = SimpleNamespace(status="active")
    principal = SimpleNamespace(id="principal", user_id="local", status="active")
    user = SimpleNamespace(is_active=True)
    db = AsyncMock()
    db.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda value=value: value)
        for value in (tenant, external, membership)
    ]
    db.get.side_effect = [principal, user]
    monkeypatch.setattr(workos_provider, "find_organization_membership", AsyncMock(side_effect=WorkOSProviderTemporaryError("outage")))
    with pytest.raises(WorkOSProviderTemporaryError):
        await identity_lifecycle.resolve_authenticated_identity(db, claims={
            "sub": "wu", "org_id": "org", "role": "driver", "permissions": [],
        }, workos_user={})


@pytest.mark.parametrize("endpoint", ["jwks", "membership"])
async def test_authority_lookup_outage_is_temporary(monkeypatch, endpoint):
    monkeypatch.setattr(workos_provider, "_session_request", AsyncMock(return_value=httpx.Response(503, content=b"unavailable")))
    with pytest.raises(WorkOSProviderTemporaryError):
        if endpoint == "jwks":
            await workos_provider._get_jwks(force=True)
        else:
            await workos_provider.find_organization_membership(user_id="wu", organization_id="org")


async def test_terminal_http_response_really_expires_access_cookie(context, client, monkeypatch):
    sid = await session()
    monkeypatch.setattr(workos_provider, "authenticate", AsyncMock(side_effect=WorkOSProviderError("invalid grant")))
    client.cookies.set("workos_session", sid, path="/api/v1/auth/workos")
    response = await client.post("/api/v1/auth/workos/session/refresh", json={})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "session_ended"
    assert any("access_token=" in value and "Max-Age=0" in value for value in response.headers.get_list("set-cookie"))
