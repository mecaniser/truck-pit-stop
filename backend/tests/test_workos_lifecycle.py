import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi import Response
from starlette.requests import Request
from sqlalchemy import select
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jose import jwt
from jose.utils import base64url_encode

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.models.driver_accountability import DriverProfile
from app.db.models.identity import (
    ExternalIdentity,
    IdentityPrincipal,
    TenantInvitation,
    TenantInvitationAuditEvent,
    TenantMembership,
    WorkOSEventReceipt,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services import identity_lifecycle, workos_provider, workos_session, workos_webhooks
from app.services.workos_provider import WorkOSProviderError
from app.api.v1.endpoints import workos_lifecycle


async def _resolved(value):
    return value


@pytest.fixture(autouse=True)
def workos_lifecycle_settings(monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "WORKOS_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "WORKOS_API_KEY", "sk_test")
    monkeypatch.setattr(settings, "WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setattr(settings, "WORKOS_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(workos_session, "get_redis", lambda: _resolved(fake_redis))
    async def token_version(user_id):
        value = await fake_redis.get(f"token_version:{user_id}")
        return int(value) if value else 0
    monkeypatch.setattr(workos_lifecycle, "get_token_version", token_version)


def _signed_event(event, issued_ms=None):
    raw = json.dumps(event, separators=(",", ":")).encode()
    issued_ms = issued_ms or int(time.time() * 1000)
    signature = hmac.new(b"whsec_test", str(issued_ms).encode() + b"." + raw, hashlib.sha256).hexdigest()
    return raw, f"t={issued_ms},v1={signature}"


def _integer_bytes(value):
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


@pytest.mark.asyncio
async def test_provider_access_token_signature_and_authoritative_claims(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "test-kid",
        "use": "sig",
        "alg": "RS256",
        "n": base64url_encode(_integer_bytes(public.n)).decode(),
        "e": base64url_encode(_integer_bytes(public.e)).decode(),
    }
    async def keys(force=False):
        return {"keys": [jwk]}
    monkeypatch.setattr(workos_provider, "_get_jwks", keys)
    private_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    claims = {
        "iss": "https://api.workos.com",
        "client_id": "client_test",
        "sub": "wu_signed",
        "org_id": "org_signed",
        "role": "driver",
        "permissions": ["driver_portal:use"],
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    token = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test-kid"})
    assert (await workos_provider.verify_access_token(token))["permissions"] == ["driver_portal:use"]
    wrong_issuer = dict(claims, iss="https://unexpected-issuer.example")
    wrong_issuer_token = jwt.encode(wrong_issuer, private_pem, algorithm="RS256", headers={"kid": "test-kid"})
    with pytest.raises(WorkOSProviderError) as issuer_error:
        await workos_provider.verify_access_token(wrong_issuer_token)
    assert "received='https://unexpected-issuer.example'" in str(issuer_error.value)
    assert f"expected={settings.WORKOS_ISSUER.rstrip('/')!r}" in str(issuer_error.value)
    claims["permissions"] = "browser-controlled"
    bad = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test-kid"})
    with pytest.raises(WorkOSProviderError):
        await workos_provider.verify_access_token(bad)


def test_webhook_signature_verification_and_expiry():
    event = {"id": "event_1", "event": "user.updated", "data": {"id": "user_1"}}
    raw, signature = _signed_event(event)
    assert workos_webhooks.verify_signature(raw, signature)["id"] == "event_1"
    with pytest.raises(HTTPException):
        workos_webhooks.verify_signature(raw + b" ", signature)
    expired_raw, expired = _signed_event(event, issued_ms=int((time.time() - 301) * 1000))
    with pytest.raises(HTTPException):
        workos_webhooks.verify_signature(expired_raw, expired)


@pytest.mark.asyncio
async def test_exact_invitation_creates_passwordless_projection_and_links_driver(db_session, monkeypatch):
    tenant = Tenant(name="Invited", slug="invited", workos_organization_id="org_1")
    inviter = User(email="owner@example.test", hashed_password=get_password_hash("Str0ng@Pass!"), first_name="Owner", last_name="One", role=UserRole.GARAGE_OWNER)
    db_session.add_all([tenant, inviter]); await db_session.flush()
    driver = DriverProfile(tenant_id=tenant.id, first_name="Dana", last_name="Driver", email="driver@example.test")
    principal = IdentityPrincipal(status="pending")
    db_session.add_all([driver, principal]); await db_session.flush()
    invitation = TenantInvitation(
        tenant_id=tenant.id,
        principal_id=principal.id,
        provider_invitation_id="inv_1",
        email_snapshot="driver@example.test",
        intended_role_slug="driver",
        driver_profile_id=driver.id,
        status="pending",
        invited_by_user_id=inviter.id,
        resource_scope={},
    )
    db_session.add(invitation); await db_session.commit()

    async def accepted(_invitation_id):
        return {"id": "inv_1", "state": "accepted", "accepted_user_id": "wu_driver", "organization_id": "org_1", "role_slug": "driver", "email": "driver@example.test"}
    async def membership(**kwargs):
        assert kwargs == {"user_id": "wu_driver", "organization_id": "org_1"}
        return {"id": "om_driver", "status": "active", "role": {"slug": "driver"}}
    monkeypatch.setattr(workos_provider, "get_invitation", accepted)
    monkeypatch.setattr(workos_provider, "find_organization_membership", membership)
    claims = {"sub": "wu_driver", "org_id": "org_1", "role": "driver", "permissions": ["driver_portal:use", "inspections:perform", "incidents:report"]}
    user, resolved_tenant, membership = await identity_lifecycle.resolve_authenticated_identity(
        db_session,
        claims=claims,
        workos_user={"id": "wu_driver", "email": "driver@example.test", "first_name": "Dana", "last_name": "Driver", "email_verified": True},
    )
    await db_session.commit()
    assert user.hashed_password is None
    assert user.role == UserRole.DRIVER
    assert driver.user_id == user.id
    assert resolved_tenant.id == tenant.id
    assert membership.permissions == claims["permissions"]
    assert membership.provider_membership_id == "om_driver"
    assert invitation.provider_user_id == "wu_driver"
    assert invitation.provider_membership_id == "om_driver"


@pytest.mark.asyncio
async def test_accepted_driver_email_collision_persists_review_without_identity_mutation(db_session, monkeypatch):
    tenant = Tenant(name="Review", slug="review", workos_organization_id="org_review")
    platform_user = User(
        email="collision@example.test",
        hashed_password="legacy-hash",
        first_name="Platform",
        last_name="Administrator",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.flush()
    inviter = User(
        email="review-owner@example.test",
        hashed_password="legacy-hash",
        first_name="Review",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
    )
    db_session.add_all([platform_user, inviter])
    await db_session.flush()
    driver = DriverProfile(
        tenant_id=tenant.id,
        first_name="Invited",
        last_name="Driver",
        email=platform_user.email,
    )
    pending_principal = IdentityPrincipal(status="pending")
    db_session.add_all([driver, pending_principal])
    await db_session.flush()
    invitation = TenantInvitation(
        tenant_id=tenant.id,
        principal_id=pending_principal.id,
        provider_invitation_id="inv_review",
        email_snapshot=platform_user.email,
        intended_role_slug="driver",
        driver_profile_id=driver.id,
        status="pending",
        invited_by_user_id=inviter.id,
        resource_scope={},
    )
    db_session.add(invitation)
    await db_session.commit()
    original_platform_state = (
        platform_user.role,
        platform_user.tenant_id,
        platform_user.workos_user_id,
        platform_user.workos_identity_status,
    )

    async def accepted(_invitation_id):
        return {
            "id": "inv_review",
            "state": "accepted",
            "accepted_user_id": "wu_review_driver",
            "organization_id": "org_review",
            "role_slug": "driver",
            "email": platform_user.email,
        }

    async def membership(**kwargs):
        assert kwargs == {"user_id": "wu_review_driver", "organization_id": "org_review"}
        return {
            "id": "om_review_driver",
            "user_id": "wu_review_driver",
            "organization_id": "org_review",
            "status": "active",
            "role": {"slug": "driver"},
        }

    monkeypatch.setattr(workos_provider, "get_invitation", accepted)
    monkeypatch.setattr(workos_provider, "find_organization_membership", membership)
    with pytest.raises(identity_lifecycle.IdentityReviewRequired) as exc:
        await identity_lifecycle.resolve_authenticated_identity(
            db_session,
            claims={
                "sub": "wu_review_driver",
                "org_id": "org_review",
                "role": "driver",
                "permissions": ["driver_portal:use"],
            },
            workos_user={
                "id": "wu_review_driver",
                "email": platform_user.email,
                "first_name": "Invited",
                "last_name": "Driver",
                "email_verified": True,
            },
        )
    assert exc.value.reason == identity_lifecycle.IDENTITY_REVIEW_EMAIL_COLLISION
    await db_session.commit()
    await db_session.refresh(invitation)
    await db_session.refresh(pending_principal)
    await db_session.refresh(driver)
    await db_session.refresh(platform_user)
    assert invitation.status == "needs_review"
    assert invitation.review_reason == "existing_local_email_collision"
    assert invitation.provider_user_id == "wu_review_driver"
    assert invitation.provider_membership_id == "om_review_driver"
    assert invitation.accepted_at is not None
    assert pending_principal.status == "pending" and pending_principal.user_id is None
    assert driver.user_id is None
    assert (
        platform_user.role,
        platform_user.tenant_id,
        platform_user.workos_user_id,
        platform_user.workos_identity_status,
    ) == original_platform_state
    assert not (await db_session.execute(select(ExternalIdentity))).scalars().all()
    assert not (await db_session.execute(select(TenantMembership))).scalars().all()
    audit = (await db_session.execute(select(TenantInvitationAuditEvent))).scalar_one()
    assert audit.action == "identity_review_required"
    assert audit.status_from == "pending" and audit.status_to == "needs_review"
    assert audit.actor_user_id is None
    assert audit.metadata_json == {"reason": "existing_local_email_collision"}


@pytest.mark.asyncio
async def test_invitation_never_binds_by_email_or_wrong_accepted_user(db_session, monkeypatch):
    tenant = Tenant(name="Mismatch", slug="mismatch", workos_organization_id="org_2")
    inviter = User(email="owner2@example.test", hashed_password="x", first_name="O", last_name="T", role=UserRole.GARAGE_OWNER)
    principal = IdentityPrincipal(status="pending")
    db_session.add_all([tenant, inviter, principal]); await db_session.flush()
    db_session.add(TenantInvitation(tenant_id=tenant.id, principal_id=principal.id, provider_invitation_id="inv_2", email_snapshot="same@example.test", intended_role_slug="mechanic", status="pending", invited_by_user_id=inviter.id, resource_scope={}))
    await db_session.commit()
    async def wrong(_invitation_id):
        return {"id": "inv_2", "state": "accepted", "accepted_user_id": "someone_else", "organization_id": "org_2", "role_slug": "mechanic", "email": "same@example.test"}
    monkeypatch.setattr(workos_provider, "get_invitation", wrong)
    with pytest.raises(HTTPException) as exc:
        await identity_lifecycle.resolve_authenticated_identity(
            db_session,
            claims={"sub": "wu_new", "org_id": "org_2", "role": "mechanic", "permissions": ["repair_orders:work"]},
            workos_user={"id": "wu_new", "email": "same@example.test"},
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_exact_invitation_links_explicit_existing_owner_without_email_merge(db_session, monkeypatch):
    tenant = Tenant(name="Existing Owner", slug="existing-owner", workos_organization_id="org_owner")
    db_session.add(tenant)
    await db_session.flush()
    owner = User(
        email="owner-existing@example.test",
        hashed_password=get_password_hash("Str0ng@Pass!"),
        first_name="Existing",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(owner)
    await db_session.flush()
    principal = IdentityPrincipal(user_id=owner.id, status="pending")
    db_session.add(principal)
    await db_session.flush()
    invitation = TenantInvitation(
        tenant_id=tenant.id,
        principal_id=principal.id,
        provider_invitation_id="inv_owner",
        email_snapshot=owner.email,
        intended_role_slug="garage_owner",
        target_user_id=owner.id,
        status="pending",
        invited_by_user_id=owner.id,
        resource_scope={},
    )
    db_session.add(invitation)
    await db_session.commit()
    original_password = owner.hashed_password

    async def accepted(_invitation_id):
        return {
            "id": "inv_owner",
            "state": "accepted",
            "accepted_user_id": "wu_existing_owner",
            "organization_id": "org_owner",
            "role_slug": "garage_owner",
            "email": owner.email,
        }

    async def provider_membership(**kwargs):
        assert kwargs == {"user_id": "wu_existing_owner", "organization_id": "org_owner"}
        return {
            "id": "om_existing_owner",
            "status": "active",
            "role": {"slug": "garage_owner"},
        }

    monkeypatch.setattr(workos_provider, "get_invitation", accepted)
    monkeypatch.setattr(workos_provider, "find_organization_membership", provider_membership)
    user, resolved_tenant, membership = await identity_lifecycle.resolve_authenticated_identity(
        db_session,
        claims={
            "sub": "wu_existing_owner",
            "org_id": "org_owner",
            "role": "garage_owner",
            "permissions": ["organization:manage", "members:manage"],
        },
        workos_user={
            "id": "wu_existing_owner",
            "email": owner.email,
            "first_name": owner.first_name,
            "last_name": owner.last_name,
            "email_verified": True,
        },
    )
    await db_session.commit()
    assert user.id == owner.id
    assert user.hashed_password == original_password
    assert user.tenant_id == tenant.id
    assert user.workos_user_id == "wu_existing_owner"
    assert resolved_tenant.id == tenant.id
    assert membership.role_slug == "garage_owner"
    assert membership.provider_membership_id == "om_existing_owner"
    assert invitation.status == "accepted"
    assert invitation.provider_user_id == "wu_existing_owner"
    assert invitation.provider_membership_id == "om_existing_owner"


@pytest.mark.asyncio
async def test_existing_identity_backfills_exact_membership_and_accepted_invitation(db_session, monkeypatch):
    tenant = Tenant(name="Anchored", slug="anchored", workos_organization_id="org_anchored")
    db_session.add(tenant)
    await db_session.flush()
    owner = User(
        email="anchored-owner@example.test",
        hashed_password=None,
        first_name="Anchored",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        workos_user_id="wu_anchored",
        workos_identity_status="active",
        is_active=True,
    )
    db_session.add(owner)
    await db_session.flush()
    principal = IdentityPrincipal(user_id=owner.id, status="active")
    db_session.add(principal)
    await db_session.flush()
    external = ExternalIdentity(
        principal_id=principal.id,
        provider="workos",
        provider_subject="wu_anchored",
        status="active",
        email_snapshot=owner.email,
    )
    membership = TenantMembership(
        principal_id=principal.id,
        tenant_id=tenant.id,
        provider="workos",
        provider_membership_id=None,
        role_slug="garage_owner",
        status="active",
        permissions=["members:manage"],
        resource_scope={},
    )
    invitation = TenantInvitation(
        tenant_id=tenant.id,
        principal_id=principal.id,
        provider_invitation_id="inv_anchored",
        provider_user_id=None,
        provider_membership_id=None,
        email_snapshot=owner.email,
        intended_role_slug="garage_owner",
        target_user_id=owner.id,
        status="accepted",
        accepted_at=datetime.now(timezone.utc),
        invited_by_user_id=owner.id,
        resource_scope={},
    )
    db_session.add_all([external, membership, invitation])
    await db_session.commit()

    async def provider_membership(**kwargs):
        assert kwargs == {"user_id": "wu_anchored", "organization_id": "org_anchored"}
        return {"id": "om_anchored", "status": "active", "role": {"slug": "garage_owner"}}

    monkeypatch.setattr(workos_provider, "find_organization_membership", provider_membership)
    resolved_user, resolved_tenant, resolved_membership = await identity_lifecycle.resolve_authenticated_identity(
        db_session,
        claims={
            "sub": "wu_anchored",
            "org_id": "org_anchored",
            "role": "garage_owner",
            "permissions": ["members:manage", "organization:manage"],
        },
        workos_user={"id": "wu_anchored", "email": owner.email},
    )
    await db_session.commit()

    assert resolved_user.id == owner.id
    assert resolved_tenant.id == tenant.id
    assert resolved_membership.provider_membership_id == "om_anchored"
    assert resolved_membership.permissions == ["members:manage", "organization:manage"]
    assert invitation.provider_user_id == "wu_anchored"
    assert invitation.provider_membership_id == "om_anchored"


@pytest.mark.asyncio
async def test_membership_webhook_is_idempotent_and_revokes_session(db_session, fake_redis, monkeypatch):
    tenant = Tenant(name="Webhook", slug="webhook", workos_organization_id="org_webhook")
    user = User(email="webhook@example.test", hashed_password=None, first_name="W", last_name="U", role=UserRole.DRIVER, workos_user_id="wu_webhook")
    db_session.add_all([tenant, user]); await db_session.flush()
    principal = IdentityPrincipal(user_id=user.id, status="active")
    db_session.add(principal); await db_session.flush()
    db_session.add_all([
        ExternalIdentity(principal_id=principal.id, provider="workos", provider_subject="wu_webhook", status="active"),
        TenantMembership(principal_id=principal.id, tenant_id=tenant.id, provider="workos", provider_membership_id="om_1", role_slug="driver", status="active", permissions=["driver_portal:use"], resource_scope={}),
    ])
    await db_session.commit()
    async def increment(user_id):
        key = f"token_version:{user_id}"
        value = int(await fake_redis.get(key) or 0) + 1
        await fake_redis.set(key, str(value))
        return value
    monkeypatch.setattr(workos_webhooks, "increment_token_version", increment)
    event = {"id": "event_membership_deleted", "event": "organization_membership.deleted", "data": {"id": "om_1", "user_id": "wu_webhook", "organization_id": "org_webhook", "status": "inactive"}}
    raw, _ = _signed_event(event)
    assert await workos_webhooks.process_event(event, raw, db_session) == "processed"
    assert await workos_webhooks.process_event(event, raw, db_session) == "duplicate"
    membership = (await db_session.execute(select(TenantMembership).where(TenantMembership.provider_membership_id == "om_1"))).scalar_one()
    assert membership.status == "inactive"
    assert await fake_redis.get(f"token_version:{user.id}") == "1"
    receipts = (await db_session.execute(select(WorkOSEventReceipt))).scalars().all()
    assert len(receipts) == 1


@pytest.mark.asyncio
async def test_workos_refresh_token_is_encrypted_and_rotated_server_side(fake_redis):
    session_id = await workos_session.create_session(refresh_token="provider-secret", local_user_id="local", workos_user_id="wu", workos_org_id="org")
    raw = await fake_redis.get(f"workos:session:{session_id}")
    assert "provider-secret" not in raw
    assert (await workos_session.get_session(session_id))["refresh_token"] == "provider-secret"
    assert await workos_session.rotate_session(session_id, "rotated-secret")
    assert "rotated-secret" not in await fake_redis.get(f"workos:session:{session_id}")
    assert (await workos_session.get_session(session_id))["refresh_token"] == "rotated-secret"


@pytest.mark.asyncio
async def test_server_session_refresh_revalidates_membership_and_never_uses_legacy_refresh(db_session, fake_redis, monkeypatch):
    tenant = Tenant(name="Session", slug="session", workos_organization_id="org_session")
    user = User(email="session@example.test", hashed_password=None, first_name="S", last_name="U", role=UserRole.DRIVER, workos_user_id="wu_session")
    db_session.add_all([tenant, user]); await db_session.flush()
    principal = IdentityPrincipal(user_id=user.id, status="active")
    db_session.add(principal); await db_session.flush()
    external = ExternalIdentity(principal_id=principal.id, provider="workos", provider_subject="wu_session", status="active")
    membership = TenantMembership(principal_id=principal.id, tenant_id=tenant.id, role_slug="driver", status="active", permissions=["driver_portal:use"], resource_scope={})
    db_session.add_all([external, membership]); await db_session.commit()
    session_id = await workos_session.create_session(refresh_token="old-provider-refresh", local_user_id=str(user.id), workos_user_id="wu_session", workos_org_id="org_session")

    async def authenticate(_payload):
        assert _payload["grant_type"] == "refresh_token"
        assert _payload["refresh_token"] in {"old-provider-refresh", "new-provider-refresh"}
        return {"user": {"id": "wu_session", "email": user.email}, "access_token": "new-provider-access", "refresh_token": "new-provider-refresh"}
    async def verify(_token):
        return {"sub": "wu_session", "org_id": "org_session", "role": "driver", "permissions": ["driver_portal:use"]}
    async def provider_membership(**kwargs):
        assert kwargs == {"user_id": "wu_session", "organization_id": "org_session"}
        return {"id": "om_session", "status": "active", "role": {"slug": "driver"}}
    monkeypatch.setattr(workos_provider, "authenticate", authenticate)
    monkeypatch.setattr(workos_provider, "verify_access_token", verify)
    monkeypatch.setattr(workos_provider, "find_organization_membership", provider_membership)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1)})
    response = Response()
    result = await workos_lifecycle.refresh_session(request, response, session_id, db_session)
    assert result.expires_in == settings.WORKOS_ACCESS_TOKEN_MINUTES * 60
    assert any("access_token=" in value for value in response.headers.getlist("set-cookie"))
    assert not any("refresh_token=" in value for value in response.headers.getlist("set-cookie"))
    assert (await workos_session.get_session(session_id))["refresh_token"] == "new-provider-refresh"

    membership.status = "inactive"
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await workos_lifecycle.refresh_session(request, Response(), session_id, db_session)
    assert exc.value.status_code == 401
    assert await workos_session.get_session(session_id) is None


@pytest.mark.asyncio
async def test_workos_only_user_cannot_use_legacy_login_or_password_reset(client, db_session, fake_redis):
    user = User(email="no-legacy@example.com", hashed_password=None, first_name="No", last_name="Legacy", role=UserRole.DRIVER, workos_user_id="wu_no_legacy")
    db_session.add(user); await db_session.commit()
    login = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "Str0ng@Pass!"})
    assert login.status_code == 401
    forgot = await client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    assert forgot.status_code == 200
    assert not any(key.startswith("password_reset:") for key in fake_redis.kv)
