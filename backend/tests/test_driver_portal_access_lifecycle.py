from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.endpoints import workos_lifecycle
from app.core.config import settings
from app.core.security import create_access_token
from app.core.workos_auth import CurrentPrincipal
from app.db.models.driver_accountability import DriverProfile
from app.db.models.identity import (
    ExternalIdentity,
    IdentityPrincipal,
    TenantInvitation,
    TenantInvitationAuditEvent,
    TenantMembership,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.schemas.workos_lifecycle import WorkOSInvitationCreate, WorkOSOrganizationProvision
from app.services import workos_provider, workos_webhooks


async def _manager_context(db_session, *, slug: str = "portal"):
    tenant = Tenant(name="Portal Garage", slug=f"{slug}-{uuid4().hex[:8]}", workos_organization_id=f"org_{uuid4().hex}")
    manager = User(
        email=f"manager-{uuid4().hex}@example.test",
        hashed_password=None,
        first_name="Fleet",
        last_name="Manager",
        role=UserRole.FLEET_MANAGER,
        tenant_id=tenant.id,
        workos_user_id=f"wu_{uuid4().hex}",
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([tenant, manager])
    await db_session.flush()
    principal = CurrentPrincipal(
        local_user_id=manager.id,
        workos_user_id=manager.workos_user_id,
        workos_org_id=tenant.workos_organization_id,
        tenant_id=tenant.id,
        permissions=frozenset({"members:manage"}),
    )
    return tenant, manager, principal


async def _driver(db_session, tenant, *, email="driver@example.test"):
    driver = DriverProfile(
        tenant_id=tenant.id,
        first_name="Dana",
        last_name="Driver",
        email=email,
        employment_status="active",
    )
    db_session.add(driver)
    await db_session.flush()
    return driver


async def _invitation(db_session, tenant, manager, driver, *, state="pending", expires_at=None):
    identity = IdentityPrincipal(status="pending")
    db_session.add(identity)
    await db_session.flush()
    invitation = TenantInvitation(
        tenant_id=tenant.id,
        principal_id=identity.id,
        provider_invitation_id=f"inv_{uuid4().hex}",
        email_snapshot=driver.email,
        intended_role_slug="driver",
        resource_scope={},
        driver_profile_id=driver.id,
        status=state,
        expires_at=expires_at or datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_user_id=manager.id,
    )
    db_session.add(invitation)
    await db_session.flush()
    return invitation


@pytest.mark.asyncio
async def test_portal_projection_separates_profile_and_access_states(db_session):
    tenant, manager, principal = await _manager_context(db_session)
    driver = await _driver(db_session, tenant)

    empty = await workos_lifecycle.get_driver_portal_access(str(driver.id), principal, db_session)
    assert empty.profile_status == "active"
    assert empty.portal_access_status == "not_invited"
    assert empty.can_invite is True

    invitation = await _invitation(db_session, tenant, manager, driver)
    pending = await workos_lifecycle.get_driver_portal_access(str(driver.id), principal, db_session)
    assert pending.portal_access_status == "pending"
    assert pending.invitation_id == invitation.id
    assert pending.can_resend is True
    assert pending.can_revoke is True

    invitation.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    driver.employment_status = "inactive"
    await db_session.flush()
    expired = await workos_lifecycle.get_driver_portal_access(str(driver.id), principal, db_session)
    assert expired.profile_status == "inactive"
    assert expired.portal_access_status == "expired"
    assert expired.can_invite is True


@pytest.mark.asyncio
async def test_legacy_manager_capability_fails_closed_until_explicit_workos_link(db_session, monkeypatch):
    monkeypatch.setattr(settings, "WORKOS_AUTH_ENABLED", True)
    tenant, manager, _ = await _manager_context(db_session)
    legacy_token = create_access_token(data={"sub": str(manager.id)}, tenant_id=str(tenant.id))

    manager.workos_user_id = None
    await db_session.flush()
    not_ready = await workos_lifecycle.get_workos_capabilities(
        "/fleet/trucks/one", manager, legacy_token, db_session
    )
    assert not_ready.session_provider == "legacy"
    assert not_ready.organization_provisioned is True
    assert not_ready.driver_invitation_management.reason == "manager_not_provisioned"
    assert not_ready.driver_invitation_management.reauth_path is None

    manager.workos_user_id = "wu_manager_linked"
    await db_session.flush()
    reauth = await workos_lifecycle.get_workos_capabilities(
        "/fleet/trucks/one", manager, legacy_token, db_session
    )
    assert reauth.driver_invitation_management.reason == "workos_reauthentication_required"
    assert reauth.driver_invitation_management.reauth_path == (
        f"/auth/workos/login?return_to=%2Ffleet%2Ftrucks%2Fone&tenant_id={tenant.id}"
    )


@pytest.mark.asyncio
async def test_workos_manager_capability_requires_authoritative_permission(db_session, fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "WORKOS_AUTH_ENABLED", True)
    tenant, manager, _ = await _manager_context(db_session)
    identity = IdentityPrincipal(user_id=manager.id, status="active")
    db_session.add(identity)
    await db_session.flush()
    db_session.add_all([
        ExternalIdentity(
            principal_id=identity.id,
            provider="workos",
            provider_subject=manager.workos_user_id,
            status="active",
        ),
        TenantMembership(
            principal_id=identity.id,
            tenant_id=tenant.id,
            provider="workos",
            role_slug="fleet_manager",
            status="active",
            permissions=[],
            resource_scope={},
        ),
    ])
    await db_session.flush()

    def token(permissions):
        return create_access_token(
            data={
                "sub": str(manager.id),
                "auth_provider": "workos",
                "workos_user_id": manager.workos_user_id,
                "workos_org_id": tenant.workos_organization_id,
                "permissions": permissions,
            },
            tenant_id=str(tenant.id),
        )

    missing = await workos_lifecycle.get_workos_capabilities(
        "/fleet", manager, token(["fleet:view"]), db_session
    )
    assert missing.driver_invitation_management.reason == "missing_permission"
    assert missing.driver_invitation_management.available is False

    available = await workos_lifecycle.get_workos_capabilities(
        "/fleet", manager, token(["fleet:view", "members:manage"]), db_session
    )
    assert available.session_provider == "workos"
    assert available.driver_invitation_management.reason == "available"
    assert available.driver_invitation_management.available is True

    bootstrapped = await workos_lifecycle.get_workos_session_user(
        await workos_lifecycle.get_current_principal(token=token(["members:manage"]), db=db_session),
        db_session,
    )
    assert bootstrapped.id == manager.id
    assert bootstrapped.role == UserRole.FLEET_MANAGER


@pytest.mark.asyncio
async def test_portal_projection_active_suspended_and_needs_review(db_session):
    tenant, _, principal = await _manager_context(db_session)
    driver = await _driver(db_session, tenant)
    user = User(
        email=f"driver-{uuid4().hex}@example.test",
        hashed_password=None,
        first_name="Dana",
        last_name="Driver",
        role=UserRole.DRIVER,
        tenant_id=tenant.id,
        workos_user_id=f"wu_{uuid4().hex}",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    driver.user_id = user.id

    unprojected = await workos_lifecycle.get_driver_portal_access(str(driver.id), principal, db_session)
    assert unprojected.portal_access_status == "needs_review"

    identity = IdentityPrincipal(user_id=user.id, status="active")
    db_session.add(identity)
    await db_session.flush()
    external = ExternalIdentity(principal_id=identity.id, provider="workos", provider_subject=user.workos_user_id, status="active")
    membership = TenantMembership(
        principal_id=identity.id,
        tenant_id=tenant.id,
        provider="workos",
        role_slug="driver",
        status="active",
        permissions=["driver_portal:use"],
        resource_scope={},
    )
    db_session.add_all([external, membership])
    await db_session.flush()
    active = await workos_lifecycle.get_driver_portal_access(str(driver.id), principal, db_session)
    assert active.portal_access_status == "active"
    assert active.local_user_id == user.id
    assert active.can_invite is False

    membership.status = "inactive"
    await db_session.flush()
    suspended = await workos_lifecycle.get_driver_portal_access(str(driver.id), principal, db_session)
    assert suspended.portal_access_status == "suspended"


@pytest.mark.asyncio
async def test_driver_portal_status_is_tenant_scoped(db_session):
    tenant, _, principal = await _manager_context(db_session)
    other = Tenant(name="Other", slug=f"other-{uuid4().hex[:8]}")
    db_session.add(other)
    await db_session.flush()
    driver = await _driver(db_session, other)
    with pytest.raises(HTTPException) as exc:
        await workos_lifecycle.get_driver_portal_access(str(driver.id), principal, db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_driver_invitation_requires_explicit_unlinked_profile_and_is_audited(db_session, monkeypatch):
    tenant, manager, principal = await _manager_context(db_session)
    driver = await _driver(db_session, tenant)

    async def send(**kwargs):
        assert kwargs["organization_id"] == tenant.workos_organization_id
        assert kwargs["role_slug"] == "driver"
        return {
            "id": "inv_created",
            "state": "pending",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        }

    monkeypatch.setattr(workos_provider, "send_invitation", send)
    created = await workos_lifecycle.create_invitation(
        WorkOSInvitationCreate(
            email="invitee@example.com",
            role_slug="driver",
            driver_profile_id=driver.id,
        ),
        principal,
        db_session,
    )
    assert created.driver_profile_id == driver.id
    assert created.status == "pending"
    audit = (await db_session.execute(select(TenantInvitationAuditEvent))).scalar_one()
    assert audit.action == "created"
    assert audit.actor_user_id == manager.id

    with pytest.raises(HTTPException) as exc:
        await workos_lifecycle.create_invitation(
            WorkOSInvitationCreate(
                email="second@example.com",
                role_slug="driver",
                driver_profile_id=driver.id,
            ),
            principal,
            db_session,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_organization_provision_targets_exact_existing_owner(db_session, monkeypatch):
    tenant = Tenant(
        name="Pilot Garage",
        slug=f"pilot-{uuid4().hex[:8]}",
        enrollment_status="approved",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.flush()
    owner = User(
        email="pilot-owner@example.com",
        hashed_password="existing-password-hash",
        first_name="Pilot",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    platform = User(
        email="platform@example.com",
        hashed_password="platform-password-hash",
        first_name="Platform",
        last_name="Admin",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([owner, platform])
    await db_session.flush()

    async def organization(**kwargs):
        assert kwargs["tenant_id"] == str(tenant.id)
        return {"id": "org_pilot", "external_id": str(tenant.id)}

    async def invitation(**kwargs):
        assert kwargs["email"] == owner.email
        assert kwargs["role_slug"] == "garage_owner"
        return {
            "id": "inv_pilot_owner",
            "state": "pending",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        }

    monkeypatch.setattr(workos_provider, "get_or_create_organization", organization)
    monkeypatch.setattr(workos_provider, "send_invitation", invitation)
    result = await workos_lifecycle.provision_organization(
        WorkOSOrganizationProvision(
            tenant_id=tenant.id,
            owner_user_id=owner.id,
            owner_email=owner.email,
        ),
        platform,
        db_session,
    )
    assert result.workos_organization_id == "org_pilot"
    assert result.owner_invitation.target_user_id == owner.id
    stored = (await db_session.execute(select(TenantInvitation))).scalar_one()
    principal = await db_session.get(IdentityPrincipal, stored.principal_id)
    assert stored.target_user_id == owner.id
    assert principal.user_id == owner.id
    assert owner.workos_user_id is None


@pytest.mark.asyncio
async def test_organization_provision_rejects_identity_conflict_before_provider_write(db_session, monkeypatch):
    tenant = Tenant(
        name="Conflicting Pilot Garage",
        slug=f"conflicting-pilot-{uuid4().hex[:8]}",
        enrollment_status="approved",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.flush()
    owner = User(
        email="conflicting-owner@example.com",
        hashed_password="existing-password-hash",
        first_name="Conflicting",
        last_name="Owner",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    platform = User(
        email="platform-conflict@example.com",
        hashed_password="platform-password-hash",
        first_name="Platform",
        last_name="Admin",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([owner, platform])
    await db_session.flush()
    db_session.add(IdentityPrincipal(user_id=owner.id, status="active"))
    await db_session.commit()

    async def unexpected_provider_write(**_kwargs):
        pytest.fail("provider organization must not be created after a local identity conflict")

    monkeypatch.setattr(workos_provider, "get_or_create_organization", unexpected_provider_write)
    with pytest.raises(HTTPException) as exc:
        await workos_lifecycle.provision_organization(
            WorkOSOrganizationProvision(
                tenant_id=tenant.id,
                owner_user_id=owner.id,
                owner_email=owner.email,
            ),
            platform,
            db_session,
        )
    assert exc.value.status_code == 409
    assert tenant.workos_organization_id is None


@pytest.mark.asyncio
async def test_pending_resend_updates_expiry_and_appends_audit(db_session, monkeypatch):
    tenant, manager, principal = await _manager_context(db_session)
    driver = await _driver(db_session, tenant)
    invitation = await _invitation(db_session, tenant, manager, driver)
    new_expiry = datetime.now(timezone.utc) + timedelta(days=8)
    calls = []

    async def resend(provider_invitation_id):
        calls.append(provider_invitation_id)
        return {"id": provider_invitation_id, "state": "pending", "expires_at": new_expiry.isoformat()}

    monkeypatch.setattr(workos_provider, "resend_invitation", resend)
    result = await workos_lifecycle.resend_driver_invitation(str(invitation.id), principal, db_session)
    assert result.portal_access_status == "pending"
    assert result.invitation_id == invitation.id
    assert calls == [invitation.provider_invitation_id]
    events = (await db_session.execute(select(TenantInvitationAuditEvent))).scalars().all()
    assert [(event.action, event.actor_user_id) for event in events] == [("resent", manager.id)]


@pytest.mark.asyncio
async def test_expired_resend_creates_fresh_invitation_and_preserves_history(db_session, monkeypatch):
    tenant, manager, principal = await _manager_context(db_session)
    driver = await _driver(db_session, tenant)
    expired = await _invitation(
        db_session,
        tenant,
        manager,
        driver,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    async def send(**kwargs):
        assert kwargs["email"] == driver.email
        assert kwargs["role_slug"] == "driver"
        return {"id": "inv_fresh", "state": "pending", "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}

    monkeypatch.setattr(workos_provider, "send_invitation", send)
    result = await workos_lifecycle.resend_driver_invitation(str(expired.id), principal, db_session)
    invitations = (await db_session.execute(
        select(TenantInvitation).where(TenantInvitation.driver_profile_id == driver.id).order_by(TenantInvitation.created_at)
    )).scalars().all()
    assert len(invitations) == 2
    assert expired.status == "expired"
    assert result.portal_access_status == "pending"
    assert result.invitation_id != expired.id
    events = (await db_session.execute(
        select(TenantInvitationAuditEvent).order_by(TenantInvitationAuditEvent.created_at, TenantInvitationAuditEvent.action)
    )).scalars().all()
    assert {event.action for event in events} == {"expired_observed", "reissued"}
    reissued = next(event for event in events if event.action == "reissued")
    assert reissued.status_from is None
    assert reissued.status_to == "pending"


@pytest.mark.asyncio
async def test_revoke_is_provider_confirmed_audited_and_idempotent(db_session, monkeypatch):
    tenant, manager, principal = await _manager_context(db_session)
    driver = await _driver(db_session, tenant)
    invitation = await _invitation(db_session, tenant, manager, driver)
    calls = []

    async def revoke(provider_invitation_id):
        calls.append(provider_invitation_id)
        return {"id": provider_invitation_id, "state": "revoked", "revoked_at": datetime.now(timezone.utc).isoformat()}

    monkeypatch.setattr(workos_provider, "revoke_invitation", revoke)
    first = await workos_lifecycle.revoke_driver_invitation(str(invitation.id), principal, db_session)
    second = await workos_lifecycle.revoke_driver_invitation(str(invitation.id), principal, db_session)
    assert first.portal_access_status == second.portal_access_status == "revoked"
    assert calls == [invitation.provider_invitation_id]
    events = (await db_session.execute(select(TenantInvitationAuditEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].action == "revoked"
    assert events[0].actor_user_id == manager.id


@pytest.mark.asyncio
async def test_invitation_webhook_transition_is_idempotent_and_audited(db_session):
    tenant, manager, _ = await _manager_context(db_session)
    driver = await _driver(db_session, tenant)
    invitation = await _invitation(db_session, tenant, manager, driver)
    event = {
        "id": f"event_{uuid4().hex}",
        "event": "invitation.accepted",
        "data": {"id": invitation.provider_invitation_id, "state": "accepted"},
    }
    raw = json.dumps(event, separators=(",", ":")).encode()
    assert await workos_webhooks.process_event(event, raw, db_session) == "processed"
    assert await workos_webhooks.process_event(event, raw, db_session) == "duplicate"
    await db_session.refresh(invitation)
    assert invitation.status == "accepted"
    events = (await db_session.execute(select(TenantInvitationAuditEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].action == "provider_reconciled"
    assert events[0].provider_event_id == event["id"]
