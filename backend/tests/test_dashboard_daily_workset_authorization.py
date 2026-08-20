from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import dashboard
from app.core.security import create_access_token
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink


DAILY_WORKSET_URL = "/api/v1/dashboard/daily-workset"


def _headers(user: User, *, tenant_id=None, workos: bool = False) -> dict[str, str]:
    claims = {"sub": str(user.id)}
    if workos:
        claims.update(
            {
                "auth_provider": "workos",
                "workos_user_id": user.workos_user_id,
                "workos_org_id": "org_daily_workset_test",
                "permissions": ["fleet:view"],
            }
        )
    token = create_access_token(
        claims,
        tenant_id=str(tenant_id) if tenant_id else None,
    )
    return {"Authorization": f"Bearer {token}"}


def _user(*, role: UserRole, tenant_id=None, active: bool = True, workos: bool = False) -> User:
    suffix = uuid4().hex
    return User(
        id=uuid4(),
        tenant_id=tenant_id,
        email=f"daily-workset-{role.value}-{suffix}@example.com",
        hashed_password="not-used-in-token-tests",
        first_name="Daily",
        last_name="Workset",
        role=role,
        is_active=active,
        is_verified=True,
        workos_user_id=f"workos-{suffix}" if workos else None,
    )


class _NoProtectedWorksetQueryDB:
    async def execute(self, _statement):
        raise AssertionError("denied daily-workset principal queried protected workset data")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        UserRole.CUSTOMER,
        UserRole.DRIVER,
        UserRole.FLEET_MANAGER,
        UserRole.SUPER_ADMIN,
    ],
)
async def test_daily_workset_denies_nonstaff_before_any_projection_query(role):
    user = _user(role=role, tenant_id=uuid4())

    with pytest.raises(HTTPException) as error:
        await dashboard.get_dashboard_daily_workset(
            db=_NoProtectedWorksetQueryDB(),
            current_user=user,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "Access denied"


@pytest.mark.asyncio
async def test_daily_workset_denies_missing_tenant_before_any_projection_query():
    user = _user(role=UserRole.GARAGE_OWNER)

    with pytest.raises(HTTPException) as error:
        await dashboard.get_dashboard_daily_workset(
            db=_NoProtectedWorksetQueryDB(),
            current_user=user,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "Access denied"


@pytest.mark.asyncio
async def test_daily_workset_denies_deleted_staff_before_any_projection_query():
    user = _user(role=UserRole.GARAGE_OWNER, tenant_id=uuid4())
    user.deleted_at = datetime.now(timezone.utc)

    with pytest.raises(HTTPException) as error:
        await dashboard.get_dashboard_daily_workset(
            db=_NoProtectedWorksetQueryDB(),
            current_user=user,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "Access denied"


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
async def test_daily_workset_allows_exact_shop_staff_roles(client, db_session, role):
    tenant = Tenant(
        name=f"Daily Staff {role.value}",
        slug=f"daily-staff-{role.value}-{uuid4().hex}",
        is_active=True,
    )
    user = _user(role=role)
    db_session.add(tenant)
    await db_session.flush()
    user.tenant_id = tenant.id
    db_session.add(user)
    await db_session.commit()

    response = await client.get(DAILY_WORKSET_URL, headers=_headers(user, tenant_id=tenant.id))

    assert response.status_code == 200
    assert response.json()["needs_attention"]["items"] == []


@pytest.mark.asyncio
async def test_daily_workset_denies_customer_driver_fleet_and_unscoped_platform_without_pii(client, db_session):
    tenant = Tenant(name="Daily Denials", slug=f"daily-denials-{uuid4().hex}", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    customer = Customer(
        tenant_id=tenant.id,
        first_name="Protected",
        last_name="Customer",
        email=f"protected-{uuid4().hex}@example.com",
    )
    db_session.add(customer)
    await db_session.flush()
    linked_customer = _user(role=UserRole.CUSTOMER, workos=True)
    users = [
        linked_customer,
        _user(role=UserRole.DRIVER, tenant_id=tenant.id, workos=True),
        _user(role=UserRole.FLEET_MANAGER, tenant_id=tenant.id),
        _user(role=UserRole.SUPER_ADMIN),
    ]
    db_session.add_all(users)
    await db_session.flush()
    db_session.add(
        UserCustomerLink(
            user_id=linked_customer.id,
            customer_id=customer.id,
            tenant_id=tenant.id,
        )
    )
    await db_session.commit()

    cases = [
        (_headers(linked_customer, tenant_id=tenant.id, workos=True), "linked customer"),
        (_headers(users[1], tenant_id=tenant.id, workos=True), "WorkOS driver"),
        (_headers(users[2], tenant_id=tenant.id), "fleet manager"),
        (_headers(users[3]), "unscoped platform user"),
    ]
    for headers, label in cases:
        response = await client.get(DAILY_WORKSET_URL, headers=headers)
        assert response.status_code == 403, label
        body = response.json()
        assert body["detail"] == "Access denied", label
        assert body["error"] == "Access denied", label
        assert set(body) == {"detail", "error", "correlation_id"}, label
        assert "Protected" not in response.text, label
        assert "Customer" not in response.text, label


@pytest.mark.asyncio
async def test_daily_workset_denies_inactive_user_and_inactive_tenant_without_projection_data(client, db_session):
    active_tenant = Tenant(name="Daily Active", slug=f"daily-active-{uuid4().hex}", is_active=True)
    inactive_tenant = Tenant(name="Daily Inactive", slug=f"daily-inactive-{uuid4().hex}", is_active=False)
    db_session.add_all([active_tenant, inactive_tenant])
    await db_session.flush()
    inactive_user = _user(role=UserRole.GARAGE_OWNER, tenant_id=active_tenant.id, active=False)
    deleted_user = _user(role=UserRole.GARAGE_OWNER, tenant_id=active_tenant.id)
    deleted_user.deleted_at = datetime.now(timezone.utc)
    inactive_tenant_user = _user(role=UserRole.GARAGE_OWNER, tenant_id=inactive_tenant.id)
    db_session.add_all([inactive_user, deleted_user, inactive_tenant_user])
    await db_session.commit()

    for headers in (
        _headers(inactive_user, tenant_id=active_tenant.id),
        _headers(deleted_user, tenant_id=active_tenant.id),
        _headers(inactive_tenant_user, tenant_id=inactive_tenant.id),
    ):
        response = await client.get(DAILY_WORKSET_URL, headers=headers)
        assert response.status_code == 403
        assert "needs_attention" not in response.text
        assert "customer_name" not in response.text
