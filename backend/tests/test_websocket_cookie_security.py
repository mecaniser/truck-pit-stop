"""DB-015: cookie-only WebSocket authentication and secret-redaction gates."""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.api.v1.endpoints import websocket as websocket_endpoint
from app.core import dependencies, workos_auth
from app.core.config import settings
from app.core.correlation import is_safe_correlation_id
from app.core.redaction import (
    SensitiveDataFilter,
    install_sensitive_data_filters,
    redact_sensitive,
    redact_structlog_event,
)
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.websocket import ConnectionManager
from app.db.models.customer import Customer
from app.db.models.error_log import ErrorCategory, ErrorLog, ErrorSeverity
from app.db.models.identity import ExternalIdentity, IdentityPrincipal, TenantMembership
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.services.error_service import log_error
from app.services import error_service as error_service_module


SECRET_MARKER = "DB015_SECRET_MARKER"


@pytest.fixture
def websocket_auth_state(monkeypatch, fake_redis):
    async def auth_state(jti, user_id):
        blacklisted = bool(
            jti and await fake_redis.get(f"token_blacklist:{jti}")
        )
        version = await fake_redis.get(f"token_version:{user_id}")
        return blacklisted, int(version) if version else 0

    monkeypatch.setattr(dependencies, "get_auth_token_state", auth_state)
    monkeypatch.setattr(workos_auth, "get_auth_token_state", auth_state)
    return fake_redis


def _user(*, role=UserRole.GARAGE_ADMIN, tenant_id=None, workos_user_id=None):
    marker = uuid4().hex
    return User(
        email=f"ws-{marker}@example.test",
        hashed_password="unused",
        first_name="WebSocket",
        last_name="User",
        role=role,
        tenant_id=tenant_id,
        workos_user_id=workos_user_id,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_legacy_cookie_principal_uses_https_tenant_authority(
    db_session, websocket_auth_state
):
    tenant = Tenant(name="Legacy WS", slug=f"legacy-ws-{uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    user = _user(tenant_id=tenant.id)
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        {"sub": str(user.id)}, tenant_id=str(tenant.id)
    )
    result = await websocket_endpoint.resolve_websocket_principal(token, db_session)

    assert result.principal == websocket_endpoint.WebSocketPrincipal(
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        customer_id=None,
        role=UserRole.GARAGE_ADMIN.value,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    ],
)
async def test_only_explicit_shop_staff_roles_resolve_tenant_channel(
    role, db_session, websocket_auth_state
):
    tenant = Tenant(
        name=f"Allowed {role.value}",
        slug=f"allowed-{role.value}-{uuid4().hex}",
    )
    db_session.add(tenant)
    await db_session.flush()
    user = _user(role=role, tenant_id=tenant.id)
    db_session.add(user)
    await db_session.commit()

    result = await websocket_endpoint.resolve_websocket_principal(
        create_access_token({"sub": str(user.id)}), db_session
    )

    assert result.principal is not None
    assert result.principal.role == role.value
    assert result.principal.tenant_id == str(tenant.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [UserRole.DRIVER, UserRole.FLEET_MANAGER, UserRole.SUPER_ADMIN],
)
async def test_non_shop_roles_never_resolve_tenant_wide_channel(
    role, db_session, websocket_auth_state
):
    tenant = Tenant(
        name=f"Denied {role.value}",
        slug=f"denied-{role.value}-{uuid4().hex}",
    )
    db_session.add(tenant)
    await db_session.flush()
    user = _user(role=role, tenant_id=tenant.id)
    db_session.add(user)
    await db_session.commit()

    result = await websocket_endpoint.resolve_websocket_principal(
        create_access_token({"sub": str(user.id)}), db_session
    )

    assert result.principal is None
    assert result.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION


@pytest.mark.asyncio
async def test_customer_cookie_requires_exact_active_customer_link(
    db_session, websocket_auth_state
):
    tenant = Tenant(name="Customer WS", slug=f"customer-ws-{uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    customer = Customer(
        tenant_id=tenant.id,
        first_name="C",
        last_name="Portal",
        email=f"customer-{uuid4().hex}@example.test",
    )
    user = _user(role=UserRole.CUSTOMER)
    db_session.add_all([customer, user])
    await db_session.flush()
    link = UserCustomerLink(
        user_id=user.id,
        customer_id=customer.id,
        tenant_id=tenant.id,
    )
    db_session.add(link)
    await db_session.commit()

    token = create_access_token(
        {"sub": str(user.id)}, tenant_id=str(tenant.id)
    )
    allowed = await websocket_endpoint.resolve_websocket_principal(token, db_session)
    assert allowed.principal
    assert allowed.principal.tenant_id == str(tenant.id)
    assert allowed.principal.customer_id == str(customer.id)

    link.deleted_at = link.updated_at
    await db_session.commit()
    denied = await websocket_endpoint.resolve_websocket_principal(token, db_session)
    assert denied.principal is None
    assert denied.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION


@pytest.mark.asyncio
async def test_customer_cookie_without_exact_link_never_falls_through_to_staff(
    db_session, websocket_auth_state
):
    tenant = Tenant(name="Missing link", slug=f"missing-link-{uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    customer = Customer(
        tenant_id=tenant.id,
        first_name="Missing",
        last_name="Link",
        email=f"missing-link-{uuid4().hex}@example.test",
    )
    user = _user(
        role=UserRole.CUSTOMER,
        tenant_id=tenant.id,
    )
    db_session.add_all([customer, user])
    await db_session.flush()
    user.customer_id = customer.id
    await db_session.commit()

    result = await websocket_endpoint.resolve_websocket_principal(
        create_access_token({"sub": str(user.id)}), db_session
    )

    assert result.principal is None
    assert result.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION


@pytest.mark.asyncio
async def test_customer_cookie_rejects_link_to_customer_in_another_tenant(
    db_session, websocket_auth_state
):
    tenant = Tenant(name="Selected shop", slug=f"selected-{uuid4().hex}")
    other_tenant = Tenant(name="Other shop", slug=f"other-{uuid4().hex}")
    db_session.add_all([tenant, other_tenant])
    await db_session.flush()
    other_customer = Customer(
        tenant_id=other_tenant.id,
        first_name="Other",
        last_name="Customer",
        email=f"other-customer-{uuid4().hex}@example.test",
    )
    user = _user(role=UserRole.CUSTOMER)
    db_session.add_all([other_customer, user])
    await db_session.flush()
    db_session.add(
        UserCustomerLink(
            user_id=user.id,
            customer_id=other_customer.id,
            tenant_id=tenant.id,
        )
    )
    await db_session.commit()

    result = await websocket_endpoint.resolve_websocket_principal(
        create_access_token(
            {"sub": str(user.id)}, tenant_id=str(tenant.id)
        ),
        db_session,
    )

    assert result.principal is None
    assert result.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION


@pytest.mark.asyncio
async def test_workos_cookie_revalidates_exact_active_membership(
    db_session, websocket_auth_state
):
    organization_id = f"org_{uuid4().hex}"
    workos_user_id = f"wu_{uuid4().hex}"
    tenant = Tenant(
        name="WorkOS WS",
        slug=f"workos-ws-{uuid4().hex}",
        workos_organization_id=organization_id,
    )
    user = _user(role=UserRole.GARAGE_ADMIN, workos_user_id=workos_user_id)
    db_session.add_all([tenant, user])
    await db_session.flush()
    principal = IdentityPrincipal(user_id=user.id, status="active")
    db_session.add(principal)
    await db_session.flush()
    identity = ExternalIdentity(
        principal_id=principal.id,
        provider="workos",
        provider_subject=workos_user_id,
        status="active",
    )
    membership = TenantMembership(
        principal_id=principal.id,
        tenant_id=tenant.id,
        provider="workos",
        role_slug="garage_admin",
        status="active",
        permissions=["repair_orders:work"],
    )
    db_session.add_all([identity, membership])
    await db_session.commit()

    token = create_access_token(
        {
            "sub": str(user.id),
            "auth_provider": "workos",
            "workos_user_id": workos_user_id,
            "workos_org_id": organization_id,
            "permissions": ["repair_orders:work"],
        },
        tenant_id=str(tenant.id),
    )
    allowed = await websocket_endpoint.resolve_websocket_principal(token, db_session)
    assert allowed.principal
    assert allowed.principal.tenant_id == str(tenant.id)

    membership.status = "revoked"
    await db_session.commit()
    denied = await websocket_endpoint.resolve_websocket_principal(token, db_session)
    assert denied.principal is None
    assert denied.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.DRIVER, UserRole.FLEET_MANAGER])
async def test_consistent_workos_driver_and_fleet_roles_do_not_grant_staff_channel(
    role, db_session, websocket_auth_state
):
    token, _, _, _ = await _workos_authority_fixture(
        db_session, role=role
    )

    denied = await websocket_endpoint.resolve_websocket_principal(
        token, db_session
    )

    assert denied.principal is None
    assert denied.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION


async def _workos_authority_fixture(
    db_session, *, role=UserRole.GARAGE_ADMIN
):
    organization_id = f"org_{uuid4().hex}"
    workos_user_id = f"wu_{uuid4().hex}"
    tenant = Tenant(
        name="WorkOS Authority",
        slug=f"workos-authority-{uuid4().hex}",
        workos_organization_id=organization_id,
    )
    user = _user(role=role, workos_user_id=workos_user_id)
    db_session.add_all([tenant, user])
    await db_session.flush()
    principal = IdentityPrincipal(user_id=user.id, status="active")
    db_session.add(principal)
    await db_session.flush()
    identity = ExternalIdentity(
        principal_id=principal.id,
        provider="workos",
        provider_subject=workos_user_id,
        status="active",
    )
    permissions = (
        ["driver_portal:use"]
        if role == UserRole.DRIVER
        else ["repair_orders:work"]
    )
    membership = TenantMembership(
        principal_id=principal.id,
        tenant_id=tenant.id,
        provider="workos",
        role_slug=role.value,
        status="active",
        permissions=permissions,
        resource_scope={},
    )
    db_session.add_all([identity, membership])
    await db_session.commit()
    token = create_access_token(
        {
            "sub": str(user.id),
            "auth_provider": "workos",
            "workos_user_id": workos_user_id,
            "workos_org_id": organization_id,
            "permissions": permissions,
        },
        tenant_id=str(tenant.id),
    )
    return token, user, identity, membership


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        UserRole.GARAGE_OWNER,
        UserRole.GARAGE_ADMIN,
        UserRole.RECEPTIONIST,
        UserRole.MECHANIC,
    ],
)
async def test_consistent_workos_shop_roles_resolve_staff_channel(
    role, db_session, websocket_auth_state
):
    token, _, _, _ = await _workos_authority_fixture(db_session, role=role)

    allowed = await websocket_endpoint.resolve_websocket_principal(
        token, db_session
    )

    assert allowed.principal is not None
    assert allowed.principal.role == role.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("local_role", "membership_role"),
    [
        (UserRole.GARAGE_ADMIN, "driver"),
        (UserRole.DRIVER, "garage_admin"),
        (UserRole.GARAGE_ADMIN, "unknown_provider_role"),
    ],
)
async def test_workos_local_and_membership_role_divergence_fails_closed(
    local_role,
    membership_role,
    db_session,
    websocket_auth_state,
):
    token, _, _, membership = await _workos_authority_fixture(
        db_session, role=local_role
    )
    membership.role_slug = membership_role
    await db_session.commit()

    with pytest.raises(HTTPException) as denied:
        await workos_auth.get_current_principal(token=token, db=db_session)

    assert denied.value.status_code == 403
    result = await websocket_endpoint.resolve_websocket_principal(
        token, db_session
    )
    assert result.principal is None
    assert result.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION


@pytest.mark.asyncio
async def test_provider_role_change_new_session_cannot_retain_old_staff_channel(
    db_session, websocket_auth_state
):
    token, user, _, membership = await _workos_authority_fixture(
        db_session, role=UserRole.GARAGE_ADMIN
    )
    assert (
        await websocket_endpoint.resolve_websocket_principal(token, db_session)
    ).principal is not None

    membership.role_slug = "driver"
    membership.permissions = ["driver_portal:use"]
    user.role = UserRole.DRIVER
    await db_session.commit()
    claims = decode_token(token)
    fresh_driver_token = create_access_token(
        {
            "sub": str(user.id),
            "auth_provider": "workos",
            "workos_user_id": user.workos_user_id,
            "workos_org_id": claims["workos_org_id"],
            "permissions": ["driver_portal:use"],
        },
        tenant_id=claims["tid"],
    )

    denied = await websocket_endpoint.resolve_websocket_principal(
        fresh_driver_token, db_session
    )

    assert denied.principal is None
    assert denied.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION


async def _apply_workos_authority_gap(
    db_session, authority_gap, identity, membership
):
    if authority_gap == "identity_missing":
        await db_session.delete(identity)
    elif authority_gap == "identity_deleted":
        identity.deleted_at = datetime.now(timezone.utc)
    elif authority_gap == "identity_inactive":
        identity.status = "inactive"
    elif authority_gap == "membership_missing":
        await db_session.delete(membership)
    elif authority_gap == "membership_deleted":
        membership.deleted_at = datetime.now(timezone.utc)
    elif authority_gap == "membership_inactive":
        membership.status = "inactive"
    else:
        membership.provider = "legacy"
    await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authority_gap",
    [
        "identity_missing",
        "identity_deleted",
        "identity_inactive",
        "membership_missing",
        "membership_deleted",
        "membership_inactive",
        "membership_legacy_provider",
    ],
)
async def test_workos_cookie_fails_closed_for_every_identity_authority_gap(
    authority_gap, db_session, websocket_auth_state
):
    token, _, identity, membership = await _workos_authority_fixture(db_session)
    await _apply_workos_authority_gap(
        db_session, authority_gap, identity, membership
    )

    denied = await websocket_endpoint.resolve_websocket_principal(token, db_session)

    assert denied.principal is None
    assert denied.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION


@pytest.mark.asyncio
@pytest.mark.parametrize("token_kind", ["malformed", "expired", "refresh"])
async def test_cookie_rejects_non_access_token_shapes(
    token_kind, db_session, websocket_auth_state
):
    if token_kind == "malformed":
        token = "not-a-jwt"
    elif token_kind == "expired":
        token = create_access_token(
            {"sub": str(uuid4())}, expires_delta=timedelta(seconds=-1)
        )
    else:
        token = create_refresh_token({"sub": str(uuid4())})

    result = await websocket_endpoint.resolve_websocket_principal(token, db_session)
    assert result.principal is None
    assert result.close_code == websocket_endpoint.WS_CLOSE_AUTHENTICATION


@pytest.mark.asyncio
async def test_cookie_rejects_blacklisted_stale_inactive_and_inactive_tenant(
    db_session, websocket_auth_state
):
    tenant = Tenant(name="State WS", slug=f"state-ws-{uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    user = _user(tenant_id=tenant.id)
    db_session.add(user)
    await db_session.commit()
    token = create_access_token({"sub": str(user.id)}, tenant_id=str(tenant.id))
    claims = decode_token(token)

    await websocket_auth_state.setex(
        f"token_blacklist:{claims['jti']}", 60, "1"
    )
    revoked = await websocket_endpoint.resolve_websocket_principal(token, db_session)
    assert revoked.principal is None
    assert revoked.close_code == websocket_endpoint.WS_CLOSE_AUTHENTICATION

    await websocket_auth_state.delete(f"token_blacklist:{claims['jti']}")
    await websocket_auth_state.set(f"token_version:{user.id}", "1")
    stale = await websocket_endpoint.resolve_websocket_principal(token, db_session)
    assert stale.principal is None
    assert stale.close_code == websocket_endpoint.WS_CLOSE_AUTHENTICATION

    await websocket_auth_state.delete(f"token_version:{user.id}")
    user.is_active = False
    await db_session.commit()
    inactive = await websocket_endpoint.resolve_websocket_principal(token, db_session)
    assert inactive.principal is None
    assert inactive.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION

    user.is_active = True
    tenant.is_active = False
    await db_session.commit()
    tenant_denied = await websocket_endpoint.resolve_websocket_principal(
        token, db_session
    )
    assert tenant_denied.principal is None
    assert tenant_denied.close_code == websocket_endpoint.WS_CLOSE_AUTHORIZATION


class FakeWebSocket:
    def __init__(self, *, origin, cookies=None, query_params=None, messages=None):
        self.headers = {"origin": origin} if origin is not None else {}
        self.cookies = cookies or {}
        self.query_params = query_params or {}
        self.messages = list(messages or [{"type": "websocket.disconnect"}])
        self.closed = []
        self.sent_text = []
        self.sent_json = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def close(self, *, code, reason):
        self.closed.append((code, reason))

    async def receive(self):
        return self.messages.pop(0)

    async def send_text(self, value):
        self.sent_text.append(value)

    async def send_json(self, value):
        self.sent_json.append(value)


class FakeConnectionManager:
    def __init__(self):
        self.connected = []
        self.disconnected = []

    async def connect_staff(self, websocket, tenant_id, user_id):
        websocket.accepted = True
        self.connected.append(("staff", tenant_id, user_id))
        return True

    async def connect_customer(self, websocket, customer_id):
        websocket.accepted = True
        self.connected.append(("customer", customer_id))
        return True

    async def disconnect_staff(self, tenant_id, user_id, websocket):
        self.disconnected.append(("staff", tenant_id, user_id))

    async def disconnect_customer(self, customer_id, websocket):
        self.disconnected.append(("customer", customer_id))


class ASGIConnectionManager(FakeConnectionManager):
    async def connect_staff(self, websocket, tenant_id, user_id):
        await websocket.accept()
        self.connected.append(("staff", tenant_id, user_id))
        return True

    async def connect_customer(self, websocket, customer_id):
        await websocket.accept()
        self.connected.append(("customer", customer_id))
        return True


class ASGIEventConnectionManager(ASGIConnectionManager):
    def __init__(self, event):
        super().__init__()
        self.event = event

    async def connect_staff(self, websocket, tenant_id, user_id):
        connected = await super().connect_staff(websocket, tenant_id, user_id)
        await websocket.send_json(self.event)
        return connected

    async def connect_customer(self, websocket, customer_id):
        connected = await super().connect_customer(websocket, customer_id)
        await websocket.send_json(self.event)
        return connected


def _staff_principal():
    return websocket_endpoint.WebSocketPrincipal(
        user_id=str(uuid4()),
        tenant_id=str(uuid4()),
        customer_id=None,
        role=UserRole.GARAGE_ADMIN.value,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authority_gap",
    [
        "identity_missing",
        "identity_deleted",
        "identity_inactive",
        "membership_missing",
        "membership_deleted",
        "membership_inactive",
        "membership_legacy_provider",
    ],
)
async def test_live_workos_revalidation_closes_after_authority_is_revoked(
    authority_gap,
    db_session,
    websocket_auth_state,
    monkeypatch,
):
    token, _, identity, membership = await _workos_authority_fixture(db_session)
    initial = await websocket_endpoint.resolve_websocket_principal(token, db_session)
    assert initial.principal is not None

    async def validate(current_token):
        return await websocket_endpoint.resolve_websocket_principal(
            current_token, db_session
        )

    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    await _apply_workos_authority_gap(
        db_session, authority_gap, identity, membership
    )
    socket = FakeWebSocket(origin="https://app.example.test")

    authorized = await websocket_endpoint._connection_is_still_authorized(
        socket, token, initial.principal
    )

    assert authorized is False
    assert socket.closed == [
        (websocket_endpoint.WS_CLOSE_AUTHORIZATION, "Not authorized")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("projection_synchronized", [False, True])
async def test_live_workos_socket_closes_when_membership_role_changes(
    projection_synchronized,
    db_session,
    websocket_auth_state,
    monkeypatch,
):
    token, user, _, membership = await _workos_authority_fixture(
        db_session, role=UserRole.GARAGE_ADMIN
    )
    initial = await websocket_endpoint.resolve_websocket_principal(
        token, db_session
    )
    assert initial.principal is not None

    async def validate(current_token):
        return await websocket_endpoint.resolve_websocket_principal(
            current_token, db_session
        )

    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    membership.role_slug = "driver"
    membership.permissions = ["driver_portal:use"]
    if projection_synchronized:
        user.role = UserRole.DRIVER
    await db_session.commit()
    socket = FakeWebSocket(origin="https://app.example.test")

    authorized = await websocket_endpoint._connection_is_still_authorized(
        socket, token, initial.principal
    )

    assert authorized is False
    assert socket.closed == [
        (websocket_endpoint.WS_CLOSE_AUTHORIZATION, "Not authorized")
    ]


@pytest.mark.asyncio
async def test_cookie_only_connects_without_javascript_token_and_query_cannot_override(
    monkeypatch
):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")
    principal = _staff_principal()
    observed_tokens = []

    async def validate(token):
        observed_tokens.append(token)
        return websocket_endpoint.WebSocketAuthResult(principal)

    fake_manager = FakeConnectionManager()
    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    monkeypatch.setattr(websocket_endpoint, "manager", fake_manager)
    socket = FakeWebSocket(
        origin="https://app.example.test",
        cookies={"access_token": "http-only-cookie"},
        query_params={"token": "attacker-query-token"},
    )

    await websocket_endpoint.websocket_endpoint(socket)

    assert observed_tokens == ["http-only-cookie"]
    assert fake_manager.connected == [
        ("staff", principal.tenant_id, principal.user_id)
    ]
    assert socket.closed == []


def test_real_asgi_handshake_uses_cookie_and_never_query_token(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")
    principal = _staff_principal()
    observed_tokens = []

    async def validate(token):
        observed_tokens.append(token)
        return websocket_endpoint.WebSocketAuthResult(principal)

    manager = ASGIConnectionManager()
    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    monkeypatch.setattr(websocket_endpoint, "manager", manager)
    app = FastAPI()
    app.include_router(websocket_endpoint.router, prefix="/api/v1")

    with TestClient(app) as client:
        client.cookies.set("access_token", "http-only-cookie")
        with client.websocket_connect(
            f"/api/v1/ws?token={SECRET_MARKER}",
            headers={"origin": "https://app.example.test"},
        ) as socket:
            socket.send_text("ping")
            assert socket.receive_text() == "pong"

    assert observed_tokens == ["http-only-cookie", "http-only-cookie"]
    assert manager.connected == [
        ("staff", principal.tenant_id, principal.user_id)
    ]


@pytest.mark.parametrize(
    "role", [UserRole.DRIVER.value, UserRole.FLEET_MANAGER.value, "unknown"]
)
@pytest.mark.parametrize(
    "sensitive_event",
    [
        {"type": "repair_order_update", "order_id": "sensitive-order"},
        {"type": "invoice_created", "invoice_id": "sensitive-invoice"},
        {"type": "sms_message_created", "body": "sensitive-message"},
    ],
)
def test_real_asgi_non_shop_roles_cannot_join_sensitive_tenant_channel(
    role, sensitive_event, monkeypatch
):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")
    tenant_id = str(uuid4())
    principal = websocket_endpoint.WebSocketPrincipal(
        user_id=str(uuid4()),
        tenant_id=tenant_id,
        customer_id=None,
        role=role,
    )

    async def validate(_token):
        return websocket_endpoint.WebSocketAuthResult(principal)

    manager = ASGIEventConnectionManager(sensitive_event)
    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    monkeypatch.setattr(websocket_endpoint, "manager", manager)
    app = FastAPI()
    app.include_router(websocket_endpoint.router, prefix="/api/v1")

    with TestClient(app) as client:
        client.cookies.set("access_token", "http-only-cookie")
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(
                "/api/v1/ws",
                headers={"origin": "https://app.example.test"},
            ) as socket:
                socket.receive_json()

    assert closed.value.code == websocket_endpoint.WS_CLOSE_AUTHORIZATION
    assert closed.value.reason == "Not authorized"
    assert manager.connected == []


@pytest.mark.parametrize(
    "role",
    [
        UserRole.GARAGE_OWNER.value,
        UserRole.GARAGE_ADMIN.value,
        UserRole.RECEPTIONIST.value,
        UserRole.MECHANIC.value,
    ],
)
def test_real_asgi_explicit_shop_staff_receives_tenant_event(role, monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")
    event = {"type": "repair_order_update", "order_id": str(uuid4())}
    principal = websocket_endpoint.WebSocketPrincipal(
        user_id=str(uuid4()),
        tenant_id=str(uuid4()),
        customer_id=None,
        role=role,
    )

    async def validate(_token):
        return websocket_endpoint.WebSocketAuthResult(principal)

    manager = ASGIEventConnectionManager(event)
    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    monkeypatch.setattr(websocket_endpoint, "manager", manager)
    app = FastAPI()
    app.include_router(websocket_endpoint.router, prefix="/api/v1")

    with TestClient(app) as client:
        client.cookies.set("access_token", "http-only-cookie")
        with client.websocket_connect(
            "/api/v1/ws", headers={"origin": "https://app.example.test"}
        ) as socket:
            assert socket.receive_json() == event

    assert manager.connected == [
        ("staff", principal.tenant_id, principal.user_id)
    ]


def test_real_asgi_customer_receives_only_own_customer_channel(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")
    event = {"type": "invoice_created", "invoice_id": str(uuid4())}
    principal = websocket_endpoint.WebSocketPrincipal(
        user_id=str(uuid4()),
        tenant_id=str(uuid4()),
        customer_id=str(uuid4()),
        role=UserRole.CUSTOMER.value,
    )

    async def validate(_token):
        return websocket_endpoint.WebSocketAuthResult(principal)

    manager = ASGIEventConnectionManager(event)
    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    monkeypatch.setattr(websocket_endpoint, "manager", manager)
    app = FastAPI()
    app.include_router(websocket_endpoint.router, prefix="/api/v1")

    with TestClient(app) as client:
        client.cookies.set("access_token", "http-only-cookie")
        with client.websocket_connect(
            "/api/v1/ws", headers={"origin": "https://app.example.test"}
        ) as socket:
            assert socket.receive_json() == event

    assert manager.connected == [("customer", principal.customer_id)]


@pytest.mark.parametrize(
    ("tenant_id", "customer_id"),
    [(str(uuid4()), None), (None, str(uuid4()))],
)
def test_real_asgi_incomplete_customer_context_never_falls_through_to_staff(
    tenant_id, customer_id, monkeypatch
):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")
    principal = websocket_endpoint.WebSocketPrincipal(
        user_id=str(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer_id,
        role=UserRole.CUSTOMER.value,
    )

    async def validate(_token):
        return websocket_endpoint.WebSocketAuthResult(principal)

    manager = ASGIConnectionManager()
    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    monkeypatch.setattr(websocket_endpoint, "manager", manager)
    app = FastAPI()
    app.include_router(websocket_endpoint.router, prefix="/api/v1")

    with TestClient(app) as client:
        client.cookies.set("access_token", "http-only-cookie")
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(
                "/api/v1/ws",
                headers={"origin": "https://app.example.test"},
            ) as socket:
                socket.receive_json()

    assert closed.value.code == websocket_endpoint.WS_CLOSE_AUTHORIZATION
    assert manager.connected == []


def test_real_asgi_query_only_handshake_returns_generic_auth_close(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")

    async def must_not_validate(_token):
        raise AssertionError("query credentials must never reach token validation")

    monkeypatch.setattr(
        websocket_endpoint, "validate_websocket_token", must_not_validate
    )
    app = FastAPI()
    app.include_router(websocket_endpoint.router, prefix="/api/v1")

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(
                f"/api/v1/ws?token={SECRET_MARKER}",
                headers={"origin": "https://app.example.test"},
            ) as socket:
                socket.receive_text()

    assert closed.value.code == websocket_endpoint.WS_CLOSE_AUTHENTICATION
    assert closed.value.reason == "Authentication required"


@pytest.mark.asyncio
async def test_query_only_authentication_fails_without_reading_query(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")

    async def must_not_validate(_token):
        raise AssertionError("query credentials must never reach token validation")

    monkeypatch.setattr(
        websocket_endpoint, "validate_websocket_token", must_not_validate
    )
    socket = FakeWebSocket(
        origin="https://app.example.test",
        query_params={"token": "valid-looking-query-token"},
    )

    await websocket_endpoint.websocket_endpoint(socket)

    assert socket.closed == [
        (websocket_endpoint.WS_CLOSE_AUTHENTICATION, "Authentication required")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [None, "https://evil.example.test", "https://app.example.test.evil"])
async def test_websocket_origin_must_exactly_match_configured_allowlist(
    origin, monkeypatch
):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")
    socket = FakeWebSocket(
        origin=origin,
        cookies={"access_token": "unused"},
    )

    await websocket_endpoint.websocket_endpoint(socket)

    assert socket.closed == [
        (websocket_endpoint.WS_CLOSE_ORIGIN, "Origin not allowed")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ({"type": "websocket.receive", "text": "unknown"}, 1008),
        (
            {
                "type": "websocket.receive",
                "text": "x" * (websocket_endpoint.WS_MAX_CLIENT_MESSAGE_BYTES + 1),
            },
            1009,
        ),
    ],
)
async def test_notification_socket_rejects_unknown_or_oversized_client_messages(
    message, expected_code, monkeypatch
):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")
    principal = _staff_principal()

    async def validate(_token):
        return websocket_endpoint.WebSocketAuthResult(principal)

    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    monkeypatch.setattr(websocket_endpoint, "manager", FakeConnectionManager())
    socket = FakeWebSocket(
        origin="https://app.example.test",
        cookies={"access_token": "cookie"},
        messages=[message],
    )

    await websocket_endpoint.websocket_endpoint(socket)

    assert socket.closed[0][0] == expected_code
    assert SECRET_MARKER not in socket.closed[0][1]


@pytest.mark.asyncio
@pytest.mark.parametrize("live_failure", [4001, 4002])
async def test_live_connection_closes_when_token_expires_or_context_is_revoked(
    live_failure, monkeypatch
):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")
    principal = _staff_principal()
    responses = [
        websocket_endpoint.WebSocketAuthResult(principal),
        websocket_endpoint.WebSocketAuthResult(None, live_failure),
    ]

    async def validate(_token):
        return responses.pop(0)

    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    monkeypatch.setattr(websocket_endpoint, "manager", FakeConnectionManager())
    socket = FakeWebSocket(
        origin="https://app.example.test",
        cookies={"access_token": "cookie"},
        messages=[{"type": "websocket.receive", "text": "ping"}],
    )

    await websocket_endpoint.websocket_endpoint(socket)

    assert socket.sent_text == []
    assert socket.closed[0][0] == live_failure


@pytest.mark.asyncio
async def test_ping_pong_contract_survives_cookie_auth(monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS_STR", "https://app.example.test")
    principal = _staff_principal()

    async def validate(_token):
        return websocket_endpoint.WebSocketAuthResult(principal)

    monkeypatch.setattr(websocket_endpoint, "validate_websocket_token", validate)
    monkeypatch.setattr(websocket_endpoint, "manager", FakeConnectionManager())
    socket = FakeWebSocket(
        origin="https://app.example.test",
        cookies={"access_token": "cookie"},
        messages=[
            {"type": "websocket.receive", "text": "ping"},
            {"type": "websocket.disconnect"},
        ],
    )

    await websocket_endpoint.websocket_endpoint(socket)

    assert socket.sent_text == ["pong"]
    assert socket.closed == []


@pytest.mark.asyncio
async def test_tenant_broadcast_never_crosses_connection_partition():
    manager = ConnectionManager()
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    socket_a = FakeWebSocket(origin="https://app.example.test")
    socket_b = FakeWebSocket(origin="https://app.example.test")
    manager.tenant_connections = {
        tenant_a: {"user-a": [socket_a]},
        tenant_b: {"user-b": [socket_b]},
    }

    sent = await manager.broadcast_to_tenant(tenant_a, {"type": "repair_order_update"})

    assert sent == 1
    assert socket_a.sent_json == [{"type": "repair_order_update"}]
    assert socket_b.sent_json == []


def test_recursive_redaction_covers_nested_query_urls_and_uvicorn_arguments():
    value = {
        "url": f"/api/v1/ws?token={SECRET_MARKER}&safe=yes",
        "nested": [
            {"access_token": SECRET_MARKER},
            f"Authorization: Bearer {SECRET_MARKER}",
        ],
    }
    redacted = redact_sensitive(value)
    assert SECRET_MARKER not in json.dumps(redacted)
    assert redacted["nested"][0]["access_token"] == "[REDACTED]"

    record = logging.LogRecord(
        "uvicorn.access",
        logging.WARNING,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "127.0.0.1:1",
            "GET",
            f"/api/v1/ws?token={SECRET_MARKER}",
            "1.1",
            403,
        ),
        None,
    )
    SensitiveDataFilter().filter(record)
    assert SECRET_MARKER not in record.getMessage()

    event = redact_structlog_event(
        None,
        "warning",
        {"event": "request", "query_params": {"token": SECRET_MARKER}},
    )
    assert SECRET_MARKER not in json.dumps(event)


def test_installed_filter_removes_secret_from_captured_uvicorn_log():
    logger = logging.getLogger("uvicorn.access")
    logger.setLevel(logging.WARNING)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s\n%(exc_text)s"))
    logger.addHandler(handler)
    try:
        install_sensitive_data_filters()
        try:
            raise RuntimeError(f"failed /api/v1/ws?token={SECRET_MARKER}")
        except RuntimeError:
            logger.exception(
                "request failed for %s",
                f"/api/v1/ws?access_token={SECRET_MARKER}",
            )
        output = stream.getvalue()
        assert SECRET_MARKER not in output
        assert "[REDACTED]" in output
    finally:
        logger.removeHandler(handler)


@pytest.mark.asyncio
async def test_persistent_error_fields_never_store_secret_marker(
    _db_engine,
    db_session,
    monkeypatch,
):
    owned_session_factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    monkeypatch.setattr(
        error_service_module,
        "AsyncSessionLocal",
        owned_session_factory,
    )
    error = await log_error(
        error_type="WebSocketError",
        message=f"failed /api/v1/ws?token={SECRET_MARKER}",
        category=ErrorCategory.AUTH,
        severity=ErrorSeverity.ERROR,
        correlation_id=f"token={SECRET_MARKER}\r\nCookie: access_token=leak",
        endpoint=f"/api/v1/ws?access_token={SECRET_MARKER}",
        method="GET",
        stack_trace=f"trace Authorization: Bearer {SECRET_MARKER}",
        request_context={
            "url": f"https://api.example.test/api/v1/ws?token={SECRET_MARKER}",
            "query_params": {"token": SECRET_MARKER},
            "nested": [{"cookie": f"access_token={SECRET_MARKER}"}],
        },
    )

    persisted = json.dumps(
        {
            "message": error.message,
            "correlation_id": error.correlation_id,
            "endpoint": error.endpoint,
            "stack_trace": error.stack_trace,
            "request_context": error.request_context,
        }
    )
    assert SECRET_MARKER not in persisted
    assert "[REDACTED]" in persisted
    assert is_safe_correlation_id(error.correlation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "untrusted_correlation_id",
    [
        f"token={SECRET_MARKER}",
        f"eyJhbGciOiJIUzI1NiJ9.{SECRET_MARKER}.signature",
        f"Cookie=access_token={SECRET_MARKER}",
        f"trace\r\nCookie: access_token={SECRET_MARKER}",
        "x" * 65,
    ],
)
async def test_untrusted_correlation_id_is_replaced_before_logs_and_error_persistence(
    untrusted_correlation_id, _db_engine, db_session, monkeypatch
):
    from app import main as main_module
    from app.middleware.observability import ObservabilityMiddleware

    persisted_errors = []
    owned_session_factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    monkeypatch.setattr(
        error_service_module,
        "AsyncSessionLocal",
        owned_session_factory,
    )

    async def persist_with_test_session(**kwargs):
        persisted = await log_error(**kwargs)
        persisted_errors.append(persisted)
        return persisted

    monkeypatch.setattr(
        main_module.error_service, "log_error", persist_with_test_session
    )

    async def unused_app(_scope, _receive, _send):
        raise AssertionError("dispatch should use call_next")

    middleware = ObservabilityMiddleware(unused_app)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/api/v1/failure",
        "raw_path": b"/api/v1/failure",
        "query_string": b"",
        "headers": [
            (b"host", b"api.example.test"),
            (b"x-correlation-id", untrusted_correlation_id.encode("latin1")),
        ],
        "client": ("127.0.0.1", 43100),
        "server": ("api.example.test", 443),
    }
    request = Request(scope)

    async def call_next(observed_request):
        envelope = main_module._snapshot_error(
            observed_request,
            error_type="CorrelationBoundaryError",
            message="safe failure",
            category=ErrorCategory.UNHANDLED,
            severity=ErrorSeverity.ERROR,
            correlation_id=observed_request.state.correlation_id,
            status_code=500,
        )
        await main_module._log_error_async(envelope)
        return Response("failed", status_code=500)

    response = await middleware.dispatch(request, call_next)
    response_correlation_id = response.headers["X-Correlation-ID"]
    stored = (
        await db_session.execute(
            select(ErrorLog).where(
                ErrorLog.id == persisted_errors[0].id
            )
        )
    ).scalar_one()

    assert is_safe_correlation_id(response_correlation_id)
    assert stored.correlation_id == response_correlation_id
    assert SECRET_MARKER not in stored.correlation_id
    assert "token=" not in stored.correlation_id.lower()
    assert "cookie" not in stored.correlation_id.lower()
    assert "\r" not in stored.correlation_id
    assert "\n" not in stored.correlation_id
