"""Synthetic OAuth acceptance: no live provider, secrets, or app bypass."""

import json
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit, urlunsplit
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints.motive import vehicles
from app.core import motive_crypto
from app.core.config import settings
from app.db.models.motive_oauth import (
    MotiveAuthorization,
    MotiveRemoteVehicle,
)
from app.db.models.user import UserRole
from app.db.models.vehicle_relationship import FleetMembership
from app.services import motive_oauth as s
from app.services.motive_client import MotiveClient, MotiveProviderError
from tests.test_db036_motive_sandbox import seed

pytestmark = pytest.mark.asyncio


class Provider:
    calls = 0
    error = None

    def __init__(self):
        self.rows = []

    async def tokens(self, **kwargs):
        self.calls += 1
        return {
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
            "expires_in": 7200,
        }

    async def company(self, token):
        return "100", "Synthetic carrier"

    async def inventory(self, token):
        return [{**row, "status": "active"} for row in self.rows]

    async def gateways(self, token):
        return []

    async def history(self, *args):
        return []

    async def faults(self, *args):
        return []

    async def vehicles(self, token):
        if self.error:
            raise MotiveProviderError(self.error)
        return self.rows


async def setup(db, monkeypatch):
    actor, _, truck = await seed(db, binding=False)
    from app.db.models.customer import Customer

    customer = await db.get(Customer, truck.customer_id)
    customer.fleet_enabled = True
    membership = FleetMembership(
        tenant_id=actor.tenant_id,
        fleet_customer_id=customer.id,
        vehicle_id=truck.id,
        effective_from=s.now() - timedelta(days=1),
    )
    db.add(membership)
    await db.commit()
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", True)
    monkeypatch.setattr(settings, "MOTIVE_CLIENT_ID", "synthetic-client")
    monkeypatch.setattr(settings, "MOTIVE_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setattr(
        settings,
        "MOTIVE_REDIRECT_URI",
        "https://www.dieselbridge.com/fleet/motive/callback",
    )
    monkeypatch.setattr(
        settings,
        "MOTIVE_TOKEN_ENCRYPTION_KEYS",
        json.dumps({"v1": Fernet.generate_key().decode()}),
    )
    monkeypatch.setattr(settings, "MOTIVE_APPROVED_TENANT_IDS", str(actor.tenant_id))
    return actor, truck, membership


async def connect(db, actor, truck, client=None):
    started = await s.start(db, actor, truck.customer_id, "session-1")
    state = parse_qs(urlsplit(started["authorization_url"]).query)["state"][0]
    await s.callback(
        db, actor, "session-1", state, "synthetic-code", client=client or Provider()
    )
    return await s.connection(db, actor.tenant_id, truck.customer_id, True)


async def test_oauth_roundtrip_secret_boundary_and_replay(db_session, monkeypatch):
    actor, truck, _ = await setup(db_session, monkeypatch)
    started = await s.start(db_session, actor, truck.customer_id, "session-1")
    query = parse_qs(urlsplit(started["authorization_url"]).query)
    state = query["state"][0]
    from app.services.motive_client import SCOPES

    assert query["scope"] == [SCOPES]
    pending = (await db_session.execute(select(MotiveAuthorization))).scalar_one()
    assert state not in pending.state_hash
    provider = Provider()
    for session in ["other-session"]:
        with pytest.raises(HTTPException) as error:
            await s.callback(db_session, actor, session, state, "code", client=provider)
        assert error.value.status_code == 400 and provider.calls == 0
    result = await s.callback(
        db_session, actor, "session-1", state, "code", client=provider
    )
    assert result["status"] == "connected"
    assert "synthetic-access" not in json.dumps(result, default=str)
    row = await s.connection(db_session, actor.tenant_id, truck.customer_id)
    assert "synthetic-access" not in row.encrypted_tokens
    assert (
        motive_crypto.decrypt(
            row.encrypted_tokens, row.id, row.tenant_id, row.fleet_customer_id
        )["access_token"]
        == "synthetic-access"
    )
    with pytest.raises(HTTPException):
        await s.callback(db_session, actor, "session-1", state, "code", client=provider)
    assert provider.calls == 1


@pytest.mark.parametrize(
    "role", [UserRole.CUSTOMER, UserRole.FLEET_MANAGER, UserRole.MECHANIC]
)
async def test_role_denial(db_session, monkeypatch, role):
    actor, truck, _ = await setup(db_session, monkeypatch)
    actor.role = role
    await db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await s.start(db_session, actor, truck.customer_id, "session-1")
    assert exc.value.status_code == 403


async def test_foreign_company_and_default_off(db_session, monkeypatch):
    actor, truck, _ = await setup(db_session, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await s.start(db_session, actor, uuid4(), "session-1")
    assert exc.value.status_code == 404
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        await s.start(db_session, actor, truck.customer_id, "session-1")
    assert exc.value.status_code == 503
    assert not s.configured(actor.tenant_id)


async def test_approved_tenant_and_redirect_guard(db_session, monkeypatch):
    actor, _, _ = await setup(db_session, monkeypatch)
    for value in ["", str(uuid4())]:
        monkeypatch.setattr(settings, "MOTIVE_APPROVED_TENANT_IDS", value)
        assert not s.configured(actor.tenant_id)
    monkeypatch.setattr(settings, "MOTIVE_APPROVED_TENANT_IDS", str(actor.tenant_id))
    for url in [
        "http://localhost/callback",
        # Build a synthetic userinfo URL to exercise rejection without a secret literal.
        urlunsplit(
            (
                "https",
                "fixture-user:fixture-password@example.test",
                "/fleet/motive/callback",
                "",
                "",
            )
        ),
        "https://example.com/evil",
    ]:
        monkeypatch.setattr(settings, "MOTIVE_REDIRECT_URI", url)
        assert not s.configured(actor.tenant_id)


async def test_denied_and_expired_callbacks_consumption(db_session, monkeypatch):
    actor, truck, _ = await setup(db_session, monkeypatch)
    start = await s.start(db_session, actor, truck.customer_id, "session-1")
    state = parse_qs(urlsplit(start["authorization_url"]).query)["state"][0]
    with pytest.raises(HTTPException):
        await s.callback(db_session, actor, "session-1", state, error="access_denied")
    pending = (await db_session.execute(select(MotiveAuthorization))).scalar_one()
    assert pending.consumed_at
    start = await s.start(db_session, actor, truck.customer_id, "session-1")
    state = parse_qs(urlsplit(start["authorization_url"]).query)["state"][0]
    pending = (
        await db_session.execute(
            select(MotiveAuthorization).where(
                MotiveAuthorization.state_hash == s.digest(state)
            )
        )
    ).scalar_one()
    pending.expires_at = s.now() - timedelta(seconds=1)
    await db_session.commit()
    with pytest.raises(HTTPException):
        await s.callback(
            db_session, actor, "session-1", state, "code", client=Provider()
        )


async def test_disconnect_during_callback_cannot_resurrect(db_session, monkeypatch):
    actor, truck, _ = await setup(db_session, monkeypatch)

    class DisconnectProvider(Provider):
        async def company(self, token):
            await s.disconnect(db_session, actor, truck.customer_id)
            return await super().company(token)

    with pytest.raises(HTTPException) as exc:
        await connect(db_session, actor, truck, DisconnectProvider())
    assert exc.value.status_code == 409
    row = await s.connection(db_session, actor.tenant_id, truck.customer_id)
    assert row.encrypted_tokens is None and row.status == "disconnected"


async def test_crypto_context_version_and_tamper(monkeypatch):
    monkeypatch.setattr(
        settings,
        "MOTIVE_TOKEN_ENCRYPTION_KEYS",
        json.dumps({"v1": Fernet.generate_key().decode()}),
    )
    encrypted = motive_crypto.encrypt({"access_token": "synthetic"}, "one")
    for value, identity in [
        (encrypted, "two"),
        ("v2:" + encrypted[3:], "one"),
        (encrypted[:-5] + "abcde", "one"),
    ]:
        with pytest.raises(ValueError):
            motive_crypto.decrypt(value, identity)


async def test_discover_map_sync_ordering_unmap_and_canonical_preserved(
    db_session, monkeypatch
):
    actor, truck, membership = await setup(db_session, monkeypatch)
    row = await connect(db_session, actor, truck)
    client = Provider()
    client.rows = [
        {"id": 123, "number": "Test 1", "vin": "1" * 17, "current_location": None}
    ]
    await s.sync(db_session, row, client)
    await s.bind(db_session, actor, truck.customer_id, "123", truck.id)
    point_time = s.now() + timedelta(seconds=1)
    client.rows[0]["current_location"] = {
        "lat": 35,
        "lon": -80,
        "located_at": point_time.isoformat(),
        "kph": 80.4672,
        "bearing": 90,
    }
    row.next_sync_at = None
    result = await s.sync(db_session, row, client)
    assert result["counts"] == {
        "discovered": 1,
        "mapped": 1,
        "updated": 1,
        "rejected": 0,
    }
    remote = (await db_session.execute(select(MotiveRemoteVehicle))).scalar_one()
    assert remote.speed_mph == pytest.approx(50)
    row.next_sync_at = None
    assert (await s.sync(db_session, row, client))["counts"]["updated"] == 0
    client.rows[0]["current_location"]["lat"] = 36
    row.next_sync_at = None
    assert (await s.sync(db_session, row, client))["counts"]["rejected"] == 1
    assert remote.lat == 35
    listing = await vehicles(truck.customer_id, db_session, actor)
    assert listing["items"][0]["telemetry"]["state"] == "fresh"
    membership.effective_to = s.now()
    await db_session.commit()
    listing = await vehicles(truck.customer_id, db_session, actor)
    assert listing["items"][0]["mapping_state"] == "membership_ended"
    assert listing["items"][0]["telemetry"] is None
    await s.bind(db_session, actor, truck.customer_id, "123", None)
    assert remote.located_at is None
    await db_session.refresh(truck)
    assert (truck.mileage, truck.last_lat, truck.driver_name) == (
        100,
        1,
        "Manual Driver",
    )
    await s.disconnect(db_session, actor, truck.customer_id)
    assert not (await db_session.execute(select(MotiveRemoteVehicle))).scalars().all()


async def test_pre_mapping_points_rejected_and_foreign_truck(db_session, monkeypatch):
    actor, truck, _ = await setup(db_session, monkeypatch)
    row = await connect(db_session, actor, truck)
    client = Provider()
    client.rows = [
        {
            "id": 123,
            "current_location": {
                "lat": 35,
                "lon": -80,
                "located_at": (s.now() - timedelta(hours=1)).isoformat(),
            },
        }
    ]
    await s.sync(db_session, row, client)
    with pytest.raises(HTTPException) as exc:
        await s.bind(db_session, actor, truck.customer_id, "123", uuid4())
    assert exc.value.status_code == 404
    await s.bind(db_session, actor, truck.customer_id, "123", truck.id)
    row.next_sync_at = None
    result = await s.sync(db_session, row, client)
    assert result["counts"]["rejected"] == 1


@pytest.mark.parametrize(
    "code,expected",
    [
        ("rate_limited", "provider_error"),
        ("reauthorization_required", "reconnect_required"),
        ("provider_error", "provider_error"),
    ],
)
async def test_refresh_durable_on_sync_error(db_session, monkeypatch, code, expected):
    actor, truck, _ = await setup(db_session, monkeypatch)
    row = await connect(db_session, actor, truck)
    row.token_expires_at = s.now() - timedelta(seconds=1)
    client = Provider()
    client.error = code
    result = await s.sync(db_session, row, client)
    assert result["status"] == expected
    assert client.calls == 1 and row.next_sync_at > s.now()
    assert s.utc(row.token_expires_at) > s.now()


async def test_one_refresh_after_401(db_session, monkeypatch):
    actor, truck, _ = await setup(db_session, monkeypatch)
    row = await connect(db_session, actor, truck)

    class Once(Provider):
        async def vehicles(self, token):
            if self.calls == 0:
                raise MotiveProviderError("reauthorization_required")
            return []

    client = Once()
    assert (await s.sync(db_session, row, client))["status"] == "connected"
    assert client.calls == 1


async def test_retention(db_session, monkeypatch):
    actor, truck, _ = await setup(db_session, monkeypatch)
    row = await connect(db_session, actor, truck)
    remote = MotiveRemoteVehicle(
        tenant_id=row.tenant_id,
        connection_id=row.id,
        provider_vehicle_id="123",
        discovered_at=s.now(),
        located_at=s.now() - timedelta(days=31),
        lat=1,
        lng=2,
    )
    db_session.add(remote)
    await db_session.commit()
    await s.purge(db_session)
    await db_session.refresh(remote)
    assert remote.located_at is None and remote.lat is None


@pytest.mark.parametrize("value", [None, True, float("nan"), 91, "35"])
async def test_location_numeric_validation(value):
    with pytest.raises(MotiveProviderError):
        s.parse_point(
            {"lat": value, "lon": -80, "located_at": s.now().isoformat()}, s.now()
        )


async def test_documented_wire_shapes_pagination_and_token_form(monkeypatch):
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", True)
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/oauth/token":
            assert request.headers["content-type"].startswith(
                "application/x-www-form-urlencoded"
            )
            assert parse_qs(request.content.decode())["grant_type"] == [
                "authorization_code"
            ]
            return httpx.Response(
                200,
                json={
                    "access_token": "a",
                    "refresh_token": "r",
                    "expires_in": 7200,
                    "token_type": "Bearer",
                },
            )
        assert request.headers["Authorization"] == "Bearer a"
        if request.url.path == "/v1/companies":
            return httpx.Response(
                200,
                json={
                    "companies": [{"company": {"id": 1, "name": "Test"}}],
                    "pagination": {"total": 1},
                },
            )
        page = int(request.url.params["page_no"])
        return httpx.Response(
            200,
            json={
                "vehicles": [{"vehicle": {"id": page}}],
                "pagination": {"page_no": page, "total": 2, "per_page": 1},
            },
        )

    client = MotiveClient(httpx.MockTransport(handler))
    assert (await client.tokens(code="code"))["access_token"] == "a"
    assert await client.company("a") == ("1", "Test")
    assert await client.vehicles("a") == [{"id": 1}, {"id": 2}]
    assert len(requests) == 4


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "reauthorization_required"),
        (403, "insufficient_scope"),
        (429, "rate_limited"),
        (503, "provider_error"),
        (302, "provider_error"),
    ],
)
async def test_transport_failures(monkeypatch, status, code):
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", True)
    client = MotiveClient(httpx.MockTransport(lambda request: httpx.Response(status)))
    with pytest.raises(MotiveProviderError) as exc:
        await client.company("synthetic")
    assert exc.value.code == code


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"access_token": "a", "token_type": "Bearer", "expires_in": 7200},
        {
            "access_token": "a",
            "refresh_token": "r",
            "token_type": "Bearer",
            "expires_in": True,
        },
        {
            "access_token": "a",
            "refresh_token": "r",
            "token_type": "Bearer",
            "expires_in": 7200,
            "scope": "companies.read",
        },
    ],
)
async def test_invalid_token_responses(monkeypatch, body):
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", True)
    client = MotiveClient(
        httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    )
    with pytest.raises(MotiveProviderError):
        await client.tokens(code="synthetic")


async def test_route_origin_validation_and_no_state_cache(db_session, monkeypatch):
    from fastapi import FastAPI

    from app.api.v1.endpoints.motive import router
    from app.core.dependencies import (
        get_current_active_user,
        get_db,
        get_token_from_request,
    )
    from app.core.security import create_access_token
    from app.middleware.idempotency import IdempotencyMiddleware

    actor, truck, _ = await setup(db_session, monkeypatch)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/fleet/motive")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_active_user] = lambda: actor
    app.dependency_overrides[get_token_from_request] = lambda: create_access_token(
        {"sub": str(actor.id)}
    )
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://www.dieselbridge.com")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://api.dieselbridge.com",
        cookies={"access_token": "synthetic"},
    ) as client:
        body = {"fleet_customer_id": str(truck.customer_id)}
        res = await client.post(
            "/api/v1/fleet/motive/connect",
            json=body,
            headers={"Origin": "https://attacker.example"},
        )
        assert res.status_code == 403
        res = await client.post(
            "/api/v1/fleet/motive/connect",
            json=body,
            headers={"Origin": "https://www.dieselbridge.com"},
        )
        assert res.status_code == 200 and res.headers["cache-control"] == "no-store"
        res = await client.post(
            "/api/v1/fleet/motive/callback",
            json={"state": "secret-echo", "code": ["secret-code"]},
            headers={"Origin": "https://www.dieselbridge.com"},
        )
        assert (
            res.status_code == 422
            and "secret-echo" not in res.text
            and "secret-code" not in res.text
        )
    for path in ["connect", "callback"]:
        assert not IdempotencyMiddleware._should_apply(
            {"type": "http", "method": "POST", "path": "/api/v1/fleet/motive/" + path}
        )


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/connection", None),
        ("GET", "/vehicles", None),
        ("POST", "/connect", {}),
        ("POST", "/sync", {}),
        ("DELETE", "/connection", None),
        (
            "PUT",
            "/bindings/123",
            {"vehicle_id": "00000000-0000-0000-0000-000000000123"},
        ),
        ("DELETE", "/bindings/123", None),
    ],
)
async def test_all_management_routes_role_denied(
    db_session, monkeypatch, method, path, body
):
    from fastapi import FastAPI

    from app.api.v1.endpoints.motive import router
    from app.core.dependencies import (
        get_current_active_user,
        get_db,
        get_token_from_request,
    )
    from app.core.security import create_access_token

    actor, truck, _ = await setup(db_session, monkeypatch)
    actor.role = UserRole.FLEET_MANAGER
    await db_session.commit()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/fleet/motive")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_active_user] = lambda: actor
    app.dependency_overrides[get_token_from_request] = lambda: create_access_token(
        {"sub": str(actor.id)}
    )
    if body is not None:
        body = {**body, "fleet_customer_id": str(truck.customer_id)}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        res = await client.request(
            method,
            "/api/v1/fleet/motive" + path,
            params={"fleet_customer_id": str(truck.customer_id)},
            json=body,
        )
    assert res.status_code == 403


async def test_callback_role_revocation_and_reauthentication_gate(
    db_session, monkeypatch
):
    actor, truck, _ = await setup(db_session, monkeypatch)
    start = await s.start(db_session, actor, truck.customer_id, "session-1")
    state = parse_qs(urlsplit(start["authorization_url"]).query)["state"][0]

    async def revoked_session():
        raise HTTPException(401, "Revoked token")

    with pytest.raises(HTTPException) as exc:
        await s.callback(
            db_session,
            actor,
            "session-1",
            state,
            "code",
            client=Provider(),
            revalidate=revoked_session,
        )
    assert exc.value.status_code == 401
    assert (
        await s.connection(db_session, actor.tenant_id, truck.customer_id)
    ).encrypted_tokens is None


async def test_refresh_omission_preserved_and_key_rotation(monkeypatch):
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", True)
    client = MotiveClient(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"access_token": "a", "token_type": "Bearer", "expires_in": 7200},
            )
        )
    )
    assert (await client.tokens(refresh_token="old-refresh"))[
        "refresh_token"
    ] == "old-refresh"
    keys = {"v1": Fernet.generate_key().decode(), "v2": Fernet.generate_key().decode()}
    monkeypatch.setattr(settings, "MOTIVE_TOKEN_ENCRYPTION_KEYS", json.dumps(keys))
    encrypted = motive_crypto.encrypt(
        {"access_token": "old"}, "connection", "tenant", "fleet"
    )
    monkeypatch.setattr(settings, "MOTIVE_TOKEN_ACTIVE_KEY_VERSION", "v2")
    assert (
        motive_crypto.decrypt(encrypted, "connection", "tenant", "fleet")[
            "access_token"
        ]
        == "old"
    )
    assert motive_crypto.encrypt(
        {"access_token": "new"}, "connection", "tenant", "fleet"
    ).startswith("v2:")
    with pytest.raises(ValueError):
        motive_crypto.decrypt(encrypted, "connection", "other-tenant", "fleet")


@pytest.mark.parametrize(
    "response",
    [
        {"vehicles": [], "pagination": {"page_no": 1, "total": 5}},
        {
            "vehicles": [{"vehicle": {"id": 1}}, {"vehicle": {"id": 1}}],
            "pagination": {"page_no": 1, "total": 2},
        },
        {
            "vehicles": [{"vehicle": {"id": 1}}],
            "pagination": {"page_no": 1, "total": 0},
        },
        {"vehicles": [], "pagination": {"page_no": 2, "total": 0}},
    ],
)
async def test_bad_inventory_pagination(monkeypatch, response):
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", True)
    client = MotiveClient(
        httpx.MockTransport(lambda request: httpx.Response(200, json=response))
    )
    with pytest.raises(MotiveProviderError):
        await client.vehicles("synthetic")


async def test_transport_off_never_calls_provider(monkeypatch):
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", False)

    def forbidden(request):
        raise AssertionError("Network must be dark")

    with pytest.raises(MotiveProviderError):
        await MotiveClient(httpx.MockTransport(forbidden)).tokens(code="code")


async def test_worker_filters_before_limit_and_disabled_status(db_session, monkeypatch):
    from app.db.models.customer import Customer
    from app.db.models.motive_oauth import MotiveConnection
    from app.tasks.motive import due_connections

    actor, truck, _ = await setup(db_session, monkeypatch)
    row = await connect(db_session, actor, truck)
    for index in range(21):
        customer = Customer(
            tenant_id=actor.tenant_id,
            first_name="Fixture",
            last_name="Inactive",
            email=f"inactive{index}@example.test",
            fleet_enabled=False,
        )
        db_session.add(customer)
        await db_session.flush()
        db_session.add(
            MotiveConnection(
                tenant_id=actor.tenant_id,
                fleet_customer_id=customer.id,
                status="connected",
                next_sync_at=s.now() - timedelta(days=1),
            )
        )
    await db_session.commit()
    assert (
        await db_session.execute(due_connections([actor.tenant_id]))
    ).scalars().all() == [row.id]
    assert (await db_session.execute(due_connections([uuid4()]))).scalars().all() == []
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", False)
    response = s.response(row, truck.customer_id, actor.tenant_id)
    assert response["next_sync_at"] is not None
    assert response["status"] == "not_configured" and response["company"]["id"] == "100"
    await s.disconnect(db_session, actor, truck.customer_id)
    assert row.encrypted_tokens is None


async def test_retry_after_bounded(monkeypatch):
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", True)
    from app.services.motive_client import retry_after_seconds

    assert retry_after_seconds("999999") == 3600
    assert retry_after_seconds("garbage") == 0
    client = MotiveClient(
        httpx.MockTransport(
            lambda request: httpx.Response(429, headers={"Retry-After": "300"})
        )
    )
    with pytest.raises(MotiveProviderError) as exc:
        await client.company("synthetic")
    assert exc.value.retry_after == 300
