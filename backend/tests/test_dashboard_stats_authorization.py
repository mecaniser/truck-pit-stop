"""Legacy stats must share the tenant-wide shop-workset role boundary."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import dashboard
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.user_customer_link import UserCustomerLink
from test_dashboard_daily_workset_authorization import _user, _headers, _NoProtectedWorksetQueryDB


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.CUSTOMER, UserRole.DRIVER, UserRole.FLEET_MANAGER, UserRole.SUPER_ADMIN])
async def test_stats_denies_nonstaff_before_any_tenant_query(role):
    with pytest.raises(HTTPException) as error:
        await dashboard.get_dashboard_stats(db=_NoProtectedWorksetQueryDB(),
            current_user=_user(role=role, tenant_id=uuid4()))
    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_tenant", [True, False])
async def test_stats_denies_unscoped_and_deleted_staff_before_any_tenant_query(missing_tenant):
    user = _user(role=UserRole.GARAGE_OWNER, tenant_id=None if missing_tenant else uuid4())
    if not missing_tenant:
        user.deleted_at = datetime.now(UTC)
    with pytest.raises(HTTPException) as error:
        await dashboard.get_dashboard_stats(db=_NoProtectedWorksetQueryDB(), current_user=user)
    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(dashboard.DAILY_WORKSET_STAFF_ROLES))
async def test_stats_preserves_exact_supported_staff_roles(db_session, role):
    tenant = Tenant(name="Stats staff", slug=f"stats-{uuid4()}")
    db_session.add(tenant)
    await db_session.flush()
    user = _user(role=role, tenant_id=tenant.id)
    db_session.add(user)
    await db_session.commit()
    stats = await dashboard.get_dashboard_stats(db=db_session, current_user=user)
    assert stats.total_repair_orders == 0 and stats.orders_on_floor == []


@pytest.mark.asyncio
async def test_stats_denies_real_linked_customer_principal_and_other_narrow_roles(client, db_session):
    tenant = Tenant(name="Stats privacy", slug=f"stats-privacy-{uuid4()}")
    db_session.add(tenant)
    await db_session.flush()
    customer = Customer(tenant_id=tenant.id, first_name="Protected", last_name="Stats",
                        email=f"stats-{uuid4()}@example.invalid")
    db_session.add(customer)
    await db_session.flush()
    users = [_user(role=UserRole.CUSTOMER, workos=True),
             _user(role=UserRole.DRIVER, tenant_id=tenant.id, workos=True),
             _user(role=UserRole.FLEET_MANAGER, tenant_id=tenant.id),
             _user(role=UserRole.SUPER_ADMIN)]
    db_session.add_all(users)
    await db_session.flush()
    db_session.add(UserCustomerLink(user_id=users[0].id, customer_id=customer.id, tenant_id=tenant.id))
    await db_session.commit()
    for user in users:
        response = await client.get("/api/v1/dashboard/stats", headers=_headers(user,
            tenant_id=tenant.id if user.role != UserRole.SUPER_ADMIN else None,
            workos=user.role in {UserRole.CUSTOMER, UserRole.DRIVER}))
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"
        assert "orders_on_floor" not in response.text and "hold_reason" not in response.text
