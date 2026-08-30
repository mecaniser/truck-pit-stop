"""A shop can move itself between the classic and modern workspace.

The only rollout control was PUT /admin/presentation-rollout/tenants/{id},
which is super-admin only, so a shop could not switch its own staff workspace
without platform help. set_own_tenant_presentation is that operation scoped to
the caller's own tenant, and restricted to the roles that own the shop.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.presentation_service import set_own_tenant_presentation


def _tenant() -> Tenant:
    return Tenant(id=uuid4(), name="Workspace", slug=f"workspace-{uuid4().hex[:8]}")


def _user(tenant: Tenant, role: UserRole) -> User:
    return User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=f"user-{uuid4().hex[:8]}@example.com",
        hashed_password="not-used",
        first_name="Test",
        last_name="User",
        role=role,
        is_active=True,
        is_verified=True,
    )


async def _seed(db, role: UserRole):
    tenant = _tenant()
    user = _user(tenant, role)
    db.add_all([tenant, user])
    await db.commit()
    return tenant, user


@pytest.mark.asyncio
async def test_owner_switches_the_shop_to_the_modern_workspace(db_session):
    tenant, owner = await _seed(db_session, UserRole.GARAGE_OWNER)

    result = await set_own_tenant_presentation(db_session, owner, "new")

    assert result.resolved_variant == "new"
    assert result.source == "tenant_default"
    await db_session.refresh(tenant)
    assert tenant.staff_presentation_default == "new"
    # The Inventory tab is gated separately and falls back to the legacy catalog
    # on 404, so leaving this behind lands the shop on the modern shell wrapped
    # around the old inventory page.
    assert tenant.parts_operations_enabled is True


@pytest.mark.asyncio
async def test_owner_can_switch_back_to_classic(db_session):
    tenant, owner = await _seed(db_session, UserRole.GARAGE_OWNER)

    await set_own_tenant_presentation(db_session, owner, "new")
    result = await set_own_tenant_presentation(db_session, owner, "legacy")

    assert result.resolved_variant == "legacy"
    await db_session.refresh(tenant)
    assert tenant.staff_presentation_default == "legacy"
    assert tenant.parts_operations_enabled is False


@pytest.mark.asyncio
async def test_a_mechanic_cannot_change_the_shop_workspace(db_session):
    tenant, mechanic = await _seed(db_session, UserRole.MECHANIC)

    with pytest.raises(HTTPException) as excinfo:
        await set_own_tenant_presentation(db_session, mechanic, "new")

    assert excinfo.value.status_code == 403
    await db_session.refresh(tenant)
    # The refusal must not have written anything on the way out.
    assert tenant.staff_presentation_default != "new"


@pytest.mark.asyncio
async def test_a_customer_is_refused_before_the_tenant_is_touched(db_session):
    tenant, customer = await _seed(db_session, UserRole.CUSTOMER)

    with pytest.raises(HTTPException) as excinfo:
        await set_own_tenant_presentation(db_session, customer, "new")

    assert excinfo.value.status_code == 403
    await db_session.refresh(tenant)
    assert tenant.staff_presentation_default != "new"


@pytest.mark.asyncio
async def test_a_refused_switch_leaves_parts_operations_untouched(db_session):
    tenant, owner = await _seed(db_session, UserRole.GARAGE_OWNER)
    await set_own_tenant_presentation(db_session, owner, "new")
    mechanic = _user(tenant, UserRole.MECHANIC)
    db_session.add(mechanic)
    await db_session.commit()

    with pytest.raises(HTTPException):
        await set_own_tenant_presentation(db_session, mechanic, "legacy")

    await db_session.refresh(tenant)
    # A refusal must not half-apply the pair and strand the shop on the modern
    # workspace with its inventory switched off.
    assert tenant.staff_presentation_default == "new"
    assert tenant.parts_operations_enabled is True
