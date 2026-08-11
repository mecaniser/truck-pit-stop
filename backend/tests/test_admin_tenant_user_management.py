"""SUPER_ADMIN full-mirror management of any tenant's user accounts."""
from __future__ import annotations

from uuid import uuid4
import os

import pytest
import sqlalchemy
from fastapi import HTTPException

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import admin
from app.api.v1.endpoints.admin import TenantUserCreate, TenantUserUpdate
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


async def _super_admin(db):
    sa = User(
        id=uuid4(), tenant_id=None, email=f"sa-{uuid4().hex[:8]}@example.com",
        hashed_password="x", first_name="Sandy", last_name="Admin",
        role=UserRole.SUPER_ADMIN, is_active=True, is_verified=True,
    )
    db.add(sa)
    await db.commit()
    return sa


async def _tenant_with_owner(db):
    tenant = Tenant(id=uuid4(), name="Mirror Garage", slug=f"mg-{uuid4().hex[:8]}")
    db.add(tenant)
    await db.commit()
    owner = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password="x", first_name="Olivia", last_name="Owner",
        role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    db.add(owner)
    await db.commit()
    tenant.owner_id = owner.id
    await db.commit()
    return tenant, owner


@pytest.mark.asyncio
async def test_create_tenant_user_any_role(db_session):
    sa = await _super_admin(db_session)
    tenant, _ = await _tenant_with_owner(db_session)
    for role in (UserRole.RECEPTIONIST, UserRole.FLEET_MANAGER, UserRole.GARAGE_ADMIN, UserRole.MECHANIC):
        created = await admin.create_tenant_user(
            tenant_id=tenant.id,
            body=TenantUserCreate(
                email=f"{role.value}-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                first_name="Sam", last_name="Staff", role=role,
            ),
            db=db_session, current_user=sa,
        )
        assert created.role == role
        assert created.is_active is True


@pytest.mark.asyncio
async def test_create_tenant_user_rejects_super_admin_and_customer(db_session):
    sa = await _super_admin(db_session)
    tenant, _ = await _tenant_with_owner(db_session)
    for bad in (UserRole.SUPER_ADMIN, UserRole.CUSTOMER):
        with pytest.raises(HTTPException) as exc:
            await admin.create_tenant_user(
                tenant_id=tenant.id,
                body=TenantUserCreate(
                    email=f"bad-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                    first_name="No", last_name="Go", role=bad,
                ),
                db=db_session, current_user=sa,
            )
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_tenant_user_unknown_tenant_404(db_session):
    sa = await _super_admin(db_session)
    with pytest.raises(HTTPException) as exc:
        await admin.create_tenant_user(
            tenant_id=uuid4(),
            body=TenantUserCreate(
                email=f"x-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                first_name="Ghost", last_name="Tenant", role=UserRole.MECHANIC,
            ),
            db=db_session, current_user=sa,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_deactivate_and_reactivate_tenant_preserves_the_shop(db_session):
    sa = await _super_admin(db_session)
    tenant, _ = await _tenant_with_owner(db_session)

    await admin.deactivate_tenant(tenant_id=tenant.id, db=db_session, current_user=sa)
    inactive = (await db_session.execute(
        sqlalchemy.select(Tenant).where(Tenant.id == tenant.id)
    )).scalar_one()
    assert inactive.is_active is False

    await admin.update_tenant(
        tenant_id=tenant.id,
        tenant_data=admin.TenantUpdate(is_active=True),
        db=db_session,
        current_user=sa,
    )
    reactivated = (await db_session.execute(
        sqlalchemy.select(Tenant).where(Tenant.id == tenant.id)
    )).scalar_one()
    assert reactivated.is_active is True


@pytest.mark.asyncio
async def test_list_tenant_users_marks_owner(db_session):
    sa = await _super_admin(db_session)
    tenant, owner = await _tenant_with_owner(db_session)
    await admin.create_tenant_user(
        tenant_id=tenant.id,
        body=TenantUserCreate(email=f"fm-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                              first_name="Fleet", last_name="Mgr", role=UserRole.FLEET_MANAGER),
        db=db_session, current_user=sa,
    )
    roster = await admin.list_tenant_users(tenant_id=tenant.id, include_customers=False,
                                           db=db_session, current_user=sa)
    owners = [m for m in roster if m.is_owner]
    assert len(owners) == 1 and owners[0].id == owner.id
    assert UserRole.FLEET_MANAGER in {m.role for m in roster}


@pytest.mark.asyncio
async def test_update_tenant_user_can_reset_owner_password_and_email(db_session):
    sa = await _super_admin(db_session)
    tenant, owner = await _tenant_with_owner(db_session)
    new_email = f"new-owner-{uuid4().hex[:6]}@example.com"
    updated = await admin.update_tenant_user(
        tenant_id=tenant.id, user_id=owner.id,
        body=TenantUserUpdate(email=new_email, password="FreshPass#2026", first_name="Olive"),
        db=db_session, current_user=sa,
    )
    assert updated.email == new_email
    assert updated.first_name == "Olive"
    assert updated.is_owner is True
    row = (await db_session.execute(
        sqlalchemy.select(User).where(User.id == owner.id)
    )).scalar_one()
    assert row.hashed_password != "x"  # password was hashed/changed


@pytest.mark.asyncio
async def test_update_tenant_user_role_change_repoints_owner(db_session):
    sa = await _super_admin(db_session)
    tenant, owner = await _tenant_with_owner(db_session)
    admin_user = await admin.create_tenant_user(
        tenant_id=tenant.id,
        body=TenantUserCreate(email=f"ga-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                              first_name="Gary", last_name="Admin", role=UserRole.GARAGE_ADMIN),
        db=db_session, current_user=sa,
    )
    # Demote the owner; tenant.owner_id should be cleared.
    await admin.update_tenant_user(
        tenant_id=tenant.id, user_id=owner.id, body=TenantUserUpdate(role=UserRole.GARAGE_ADMIN),
        db=db_session, current_user=sa,
    )
    refreshed = (await db_session.execute(
        sqlalchemy.select(Tenant).where(Tenant.id == tenant.id)
    )).scalar_one()
    assert refreshed.owner_id is None
    # Promote the admin to owner; tenant.owner_id should point to them.
    promoted = await admin.update_tenant_user(
        tenant_id=tenant.id, user_id=admin_user.id, body=TenantUserUpdate(role=UserRole.GARAGE_OWNER),
        db=db_session, current_user=sa,
    )
    assert promoted.is_owner is True


@pytest.mark.asyncio
async def test_update_tenant_user_rejects_duplicate_email(db_session):
    sa = await _super_admin(db_session)
    tenant, _ = await _tenant_with_owner(db_session)
    a = await admin.create_tenant_user(
        tenant_id=tenant.id,
        body=TenantUserCreate(email=f"a-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                              first_name="A", last_name="One", role=UserRole.RECEPTIONIST),
        db=db_session, current_user=sa)
    b = await admin.create_tenant_user(
        tenant_id=tenant.id,
        body=TenantUserCreate(email=f"b-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                              first_name="B", last_name="Two", role=UserRole.RECEPTIONIST),
        db=db_session, current_user=sa)
    with pytest.raises(HTTPException) as exc:
        await admin.update_tenant_user(tenant_id=tenant.id, user_id=b.id,
                                       body=TenantUserUpdate(email=a.email),
                                       db=db_session, current_user=sa)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_tenant_user_wrong_tenant_404(db_session):
    sa = await _super_admin(db_session)
    tenant_a, owner_a = await _tenant_with_owner(db_session)
    tenant_b, _ = await _tenant_with_owner(db_session)
    # owner_a does not belong to tenant_b
    with pytest.raises(HTTPException) as exc:
        await admin.update_tenant_user(tenant_id=tenant_b.id, user_id=owner_a.id,
                                       body=TenantUserUpdate(is_active=False),
                                       db=db_session, current_user=sa)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Communications access (can_access_messaging) grant
# ---------------------------------------------------------------------------

from app.api.v1.endpoints.messages import require_staff_user


async def _messaging_allowed(user: User, db_session) -> bool:
    checker = require_staff_user()
    try:
        await checker(current_user=user, db=db_session)
        return True
    except HTTPException:
        return False


@pytest.mark.asyncio
async def test_fleet_manager_messaging_off_by_default(db_session):
    sa = await _super_admin(db_session)
    tenant, _ = await _tenant_with_owner(db_session)
    created = await admin.create_tenant_user(
        tenant_id=tenant.id,
        body=TenantUserCreate(email=f"fm-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                              first_name="Fred", last_name="Fleet", role=UserRole.FLEET_MANAGER),
        db=db_session, current_user=sa,
    )
    assert created.can_access_messaging is False
    row = (await db_session.execute(
        sqlalchemy.select(User).where(User.id == created.id)
    )).scalar_one()
    assert await _messaging_allowed(row, db_session) is False


@pytest.mark.asyncio
async def test_fleet_manager_messaging_granted_on_create(db_session):
    sa = await _super_admin(db_session)
    tenant, _ = await _tenant_with_owner(db_session)
    created = await admin.create_tenant_user(
        tenant_id=tenant.id,
        body=TenantUserCreate(email=f"fm-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                              first_name="Gail", last_name="Fleet", role=UserRole.FLEET_MANAGER,
                              can_access_messaging=True),
        db=db_session, current_user=sa,
    )
    assert created.can_access_messaging is True
    row = (await db_session.execute(
        sqlalchemy.select(User).where(User.id == created.id)
    )).scalar_one()
    assert await _messaging_allowed(row, db_session) is True


@pytest.mark.asyncio
async def test_messaging_grant_can_be_toggled_via_update(db_session):
    sa = await _super_admin(db_session)
    tenant, _ = await _tenant_with_owner(db_session)
    created = await admin.create_tenant_user(
        tenant_id=tenant.id,
        body=TenantUserCreate(email=f"fm-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                              first_name="Hank", last_name="Fleet", role=UserRole.FLEET_MANAGER),
        db=db_session, current_user=sa,
    )
    granted = await admin.update_tenant_user(
        tenant_id=tenant.id, user_id=created.id,
        body=TenantUserUpdate(can_access_messaging=True), db=db_session, current_user=sa,
    )
    assert granted.can_access_messaging is True
    revoked = await admin.update_tenant_user(
        tenant_id=tenant.id, user_id=created.id,
        body=TenantUserUpdate(can_access_messaging=False), db=db_session, current_user=sa,
    )
    assert revoked.can_access_messaging is False


@pytest.mark.asyncio
async def test_receptionist_messaging_allowed_by_role(db_session):
    sa = await _super_admin(db_session)
    tenant, _ = await _tenant_with_owner(db_session)
    created = await admin.create_tenant_user(
        tenant_id=tenant.id,
        body=TenantUserCreate(email=f"r-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                              first_name="Rita", last_name="Desk", role=UserRole.RECEPTIONIST),
        db=db_session, current_user=sa,
    )
    row = (await db_session.execute(
        sqlalchemy.select(User).where(User.id == created.id)
    )).scalar_one()
    # Receptionists have messaging by role even though the flag defaults False.
    assert await _messaging_allowed(row, db_session) is True
