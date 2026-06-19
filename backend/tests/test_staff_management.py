"""Staff management: add team members with a role, list roster, update role/active."""
from __future__ import annotations

from uuid import uuid4
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555550100")

from app.api.v1.endpoints import admin
from app.api.v1.endpoints.admin import StaffCreate, StaffUpdate
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


async def _owner(db):
    tenant = Tenant(id=uuid4(), name="Staff Garage", slug=f"sg-{uuid4().hex[:8]}")
    db.add(tenant)
    await db.commit()
    owner = User(
        id=uuid4(), tenant_id=tenant.id, email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password="x", first_name="Olivia", last_name="Owner",
        role=UserRole.GARAGE_OWNER, is_active=True, is_verified=True,
    )
    db.add(owner)
    await db.commit()
    return tenant, owner


@pytest.mark.asyncio
async def test_create_staff_each_assignable_role(db_session):
    _, owner = await _owner(db_session)
    for role in (UserRole.RECEPTIONIST, UserRole.FLEET_MANAGER, UserRole.GARAGE_ADMIN, UserRole.MECHANIC):
        created = await admin.create_staff(
            body=StaffCreate(
                email=f"{role.value}-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                first_name="Sam", last_name="Staff", role=role,
            ),
            db=db_session, current_user=owner,
        )
        assert created.role == role
        assert created.is_active is True


@pytest.mark.asyncio
async def test_create_staff_rejects_non_assignable_role(db_session):
    _, owner = await _owner(db_session)
    for bad in (UserRole.SUPER_ADMIN, UserRole.GARAGE_OWNER, UserRole.CUSTOMER):
        with pytest.raises(HTTPException) as exc:
            await admin.create_staff(
                body=StaffCreate(
                    email=f"bad-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                    first_name="No", last_name="Go", role=bad,
                ),
                db=db_session, current_user=owner,
            )
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_staff_technician_applies_shift_fields(db_session):
    _, owner = await _owner(db_session)
    created = await admin.create_staff(
        body=StaffCreate(
            email=f"tech-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
            first_name="Tina", last_name="Tech", role=UserRole.MECHANIC,
            core_hours_target_minutes_override=420, shift_start_local_override="07:00",
        ),
        db=db_session, current_user=owner,
    )
    row = (await db_session.execute(
        __import__("sqlalchemy").select(User).where(User.id == created.id)
    )).scalar_one()
    assert row.core_hours_target_minutes_override == 420
    assert row.shift_start_local_override == "07:00"


@pytest.mark.asyncio
async def test_list_staff_returns_roster(db_session):
    _, owner = await _owner(db_session)
    await admin.create_staff(
        body=StaffCreate(email=f"fm-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                         first_name="Fleet", last_name="Mgr", role=UserRole.FLEET_MANAGER),
        db=db_session, current_user=owner,
    )
    roster = await admin.list_staff(db=db_session, current_user=owner)
    roles = {m.role for m in roster}
    assert UserRole.GARAGE_OWNER in roles
    assert UserRole.FLEET_MANAGER in roles


@pytest.mark.asyncio
async def test_update_staff_role_and_deactivate(db_session):
    _, owner = await _owner(db_session)
    created = await admin.create_staff(
        body=StaffCreate(email=f"r-{uuid4().hex[:6]}@example.com", password="StaffPass#2026",
                         first_name="Reese", last_name="Desk", role=UserRole.RECEPTIONIST),
        db=db_session, current_user=owner,
    )
    updated = await admin.update_staff(
        user_id=created.id, body=StaffUpdate(role=UserRole.FLEET_MANAGER, is_active=False),
        db=db_session, current_user=owner,
    )
    assert updated.role == UserRole.FLEET_MANAGER
    assert updated.is_active is False


@pytest.mark.asyncio
async def test_update_staff_cannot_modify_owner_or_self(db_session):
    _, owner = await _owner(db_session)
    with pytest.raises(HTTPException) as exc:
        await admin.update_staff(user_id=owner.id, body=StaffUpdate(is_active=False),
                                 db=db_session, current_user=owner)
    assert exc.value.status_code == 400
