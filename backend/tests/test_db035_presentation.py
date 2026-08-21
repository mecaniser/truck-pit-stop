from __future__ import annotations

from uuid import uuid4

import pytest
from app.core.security import create_access_token
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from sqlalchemy import select


def _headers(user: User, tenant: Tenant) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id)}, tenant_id=str(tenant.id))
    return {"Authorization": f"Bearer {token}"}


async def _staff(db_session, role: UserRole, tenant: Tenant) -> User:
    user = User(
        tenant_id=tenant.id,
        email=f"{role.value}-{uuid4().hex}@example.com",
        hashed_password="hashed-password",
        first_name="DB035",
        last_name="Staff",
        role=role,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_staff_appearance_bootstrap_put_conflict_and_reset(client, db_session):
    tenant = Tenant(name="DB035 Shop", slug=f"db035-{uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    user = await _staff(db_session, UserRole.GARAGE_OWNER, tenant)
    await db_session.commit()
    headers = _headers(user, tenant)

    bootstrap = await client.get("/api/v1/auth/me/appearance", headers=headers)
    assert bootstrap.status_code == 200
    assert bootstrap.json()["resolved_variant"] == "legacy"
    assert bootstrap.json()["revision"] == 0
    assert bootstrap.json()["legacy_migration_status"] == "pending"

    body = {
        "schema_version": 1,
        "base_revision": 0,
        "appearance": {
            "accent": "indigo",
            "font_family": "inter",
            "font_size": "large",
            "density": "comfortable",
            "notification_position": "top_right",
            "mode": "light",
        },
        "migration_source": "legacy_local_v1",
    }
    updated = await client.put("/api/v1/auth/me/appearance", json=body, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["revision"] == 1
    assert updated.json()["appearance"]["accent"] == "indigo"
    assert updated.json()["legacy_migration_status"] == "complete"

    stale = await client.put(
        "/api/v1/auth/me/appearance",
        json={**body, "appearance": {**body["appearance"], "accent": "rose"}},
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == "Presentation settings changed elsewhere"

    reset = await client.request(
        "DELETE",
        "/api/v1/auth/me/appearance",
        json={"schema_version": 1, "base_revision": 1},
        headers=headers,
    )
    assert reset.status_code == 200
    assert reset.json()["revision"] == 0
    assert reset.json()["appearance"]["accent"] == "cyan"


@pytest.mark.asyncio
async def test_rollout_is_super_admin_only_and_targets_are_tenant_scoped(client, db_session):
    tenant = Tenant(name="DB035 Rollout", slug=f"db035-rollout-{uuid4().hex}")
    other = Tenant(name="DB035 Other", slug=f"db035-other-{uuid4().hex}")
    db_session.add_all([tenant, other])
    await db_session.flush()
    super_admin = await _staff(db_session, UserRole.SUPER_ADMIN, tenant)
    owner = await _staff(db_session, UserRole.GARAGE_OWNER, tenant)
    foreign_owner = await _staff(db_session, UserRole.GARAGE_OWNER, other)
    await db_session.commit()

    denied = await client.put(
        f"/api/v1/admin/presentation-rollout/tenants/{tenant.id}",
        json={"schema_version": 1, "presentation": "new"},
        headers=_headers(owner, tenant),
    )
    assert denied.status_code == 403

    tenant_update = await client.put(
        f"/api/v1/admin/presentation-rollout/tenants/{tenant.id}",
        json={"schema_version": 1, "presentation": "new"},
        headers=_headers(super_admin, tenant),
    )
    assert tenant_update.status_code == 200

    user_update = await client.put(
        f"/api/v1/admin/presentation-rollout/tenants/{tenant.id}/users/{owner.id}",
        json={"schema_version": 1, "presentation_override": "legacy"},
        headers=_headers(super_admin, tenant),
    )
    assert user_update.status_code == 200
    assert user_update.json()["presentation_override"] == "legacy"

    foreign_target = await client.put(
        f"/api/v1/admin/presentation-rollout/tenants/{tenant.id}/users/{foreign_owner.id}",
        json={"schema_version": 1, "presentation_override": "new"},
        headers=_headers(super_admin, tenant),
    )
    assert foreign_target.status_code == 404
    assert foreign_target.json()["detail"] == "Not found"

    fresh = await client.get("/api/v1/auth/me", headers=_headers(owner, tenant))
    assert fresh.status_code == 200
    assert fresh.json()["presentation"]["resolved_variant"] == "legacy"
    assert fresh.json()["presentation"]["source"] == "user_override"


@pytest.mark.asyncio
async def test_customer_cannot_read_or_mutate_staff_appearance(client, db_session):
    tenant = Tenant(name="DB035 Customer", slug=f"db035-customer-{uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    customer = await _staff(db_session, UserRole.CUSTOMER, tenant)
    await db_session.commit()
    headers = _headers(customer, tenant)

    response = await client.get("/api/v1/auth/me/appearance", headers=headers)
    assert response.status_code == 403
    response = await client.put(
        "/api/v1/auth/me/appearance",
        json={"schema_version": 1, "base_revision": 0, "appearance": {
            "accent": "cyan", "font_family": "geist", "font_size": "default",
            "density": "default", "notification_position": "bottom_right", "mode": "dark",
        }},
        headers=headers,
    )
    assert response.status_code == 403
