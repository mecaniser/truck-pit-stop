"""Explicit fleet administrator delegation; ordinary customer links are not grants."""

from fastapi import HTTPException
from sqlalchemy import or_, select, update

from app.db.models.customer import Customer
from app.db.models.motive_oauth import (
    MotiveAuthorization,
    MotiveConnection,
    MotiveFleetAdminGrant,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.user_customer_link import UserCustomerLink
from app.services import motive_oauth as service


async def current_identity(db, actor):
    user = (
        await db.execute(
            select(User)
            .where(User.id == actor.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not user or not user.is_active or user.deleted_at or not actor.tenant_id:
        raise HTTPException(403, "Administrator access required")
    return user


async def staff_company(db, actor, company_id, *, lock=False):
    user = await current_identity(db, actor)
    if (
        user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
        or user.tenant_id != actor.tenant_id
    ):
        raise HTTPException(403, "Administrator access required")
    company = await service.authorize(db, actor, company_id)
    if lock:
        await db.execute(
            select(Customer.id).where(Customer.id == company.id).with_for_update()
        )
        await staff_company(db, actor, company_id)
    return company


async def companies(db, actor):
    user = await current_identity(db, actor)
    query = (
        select(Customer)
        .join(Tenant, Tenant.id == Customer.tenant_id)
        .where(
            Customer.tenant_id == actor.tenant_id,
            Customer.deleted_at.is_(None),
            or_(Customer.fleet_enabled.is_(True), Customer.is_internal_fleet.is_(True)),
            Tenant.is_active.is_(True),
            Tenant.deleted_at.is_(None),
        )
    )
    if user.role == UserRole.CUSTOMER:
        query = (
            query.join(
                UserCustomerLink,
                (UserCustomerLink.customer_id == Customer.id)
                & (UserCustomerLink.tenant_id == Customer.tenant_id),
            )
            .join(
                MotiveFleetAdminGrant,
                (MotiveFleetAdminGrant.fleet_customer_id == Customer.id)
                & (MotiveFleetAdminGrant.tenant_id == Customer.tenant_id)
                & (MotiveFleetAdminGrant.user_id == UserCustomerLink.user_id),
            )
            .where(
                UserCustomerLink.user_id == user.id,
                UserCustomerLink.deleted_at.is_(None),
                Customer.id == actor.customer_id,
                MotiveFleetAdminGrant.revoked_at.is_(None),
                MotiveFleetAdminGrant.deleted_at.is_(None),
            )
        )
    elif (
        user.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
        or user.tenant_id != actor.tenant_id
    ):
        raise HTTPException(403, "Administrator access required")
    rows = (
        (
            await db.execute(
                query.order_by(Customer.company_name, Customer.id).limit(1001)
            )
        )
        .scalars()
        .all()
    )
    if len(rows) > 1000:
        raise HTTPException(409, "company_limit")
    return {
        "items": [
            {
                "id": c.id,
                "company_name": c.company_name
                or f"{c.first_name} {c.last_name}".strip(),
                "fleet_enabled": c.fleet_enabled,
                "is_internal_fleet": c.is_internal_fleet,
                "can_manage_grants": user.role
                in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN),
            }
            for c in rows
        ]
    }


def candidate_query(tenant_id, company_id):
    return (
        select(User)
        .join(UserCustomerLink, UserCustomerLink.user_id == User.id)
        .where(
            UserCustomerLink.tenant_id == tenant_id,
            UserCustomerLink.customer_id == company_id,
            UserCustomerLink.deleted_at.is_(None),
            User.role == UserRole.CUSTOMER,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )


async def candidates(db, actor, company_id):
    await staff_company(db, actor, company_id)
    users = (
        (
            await db.execute(
                candidate_query(actor.tenant_id, company_id)
                .order_by(User.first_name, User.id)
                .limit(201)
            )
        )
        .scalars()
        .all()
    )
    if len(users) > 200:
        raise HTTPException(409, "candidate_limit")
    return {
        "items": [
            {
                "user_id": u.id,
                "name": f"{u.first_name} {u.last_name}".strip(),
                "email": u.email,
            }
            for u in users
        ]
    }


async def grants(db, actor, company_id):
    await staff_company(db, actor, company_id)
    rows = (
        (
            await db.execute(
                select(MotiveFleetAdminGrant).where(
                    MotiveFleetAdminGrant.tenant_id == actor.tenant_id,
                    MotiveFleetAdminGrant.fleet_customer_id == company_id,
                    MotiveFleetAdminGrant.deleted_at.is_(None),
                    MotiveFleetAdminGrant.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    user_ids = [row.user_id for row in rows]
    users = (
        {
            u.id: u
            for u in (await db.execute(select(User).where(User.id.in_(user_ids))))
            .scalars()
            .all()
        }
        if user_ids
        else {}
    )
    return {
        "items": [
            {
                "user_id": row.user_id,
                "name": f"{users[row.user_id].first_name} {users[row.user_id].last_name}".strip()
                if row.user_id in users
                else None,
                "email": users[row.user_id].email if row.user_id in users else "",
                "granted_at": row.created_at,
                "granted_by_user_id": row.granted_by_user_id,
            }
            for row in rows
        ]
    }


async def set_grant(db, actor, company_id, user_id, *, revoke=False):
    await staff_company(db, actor, company_id, lock=True)
    row = (
        await db.execute(
            select(MotiveFleetAdminGrant)
            .where(
                MotiveFleetAdminGrant.tenant_id == actor.tenant_id,
                MotiveFleetAdminGrant.fleet_customer_id == company_id,
                MotiveFleetAdminGrant.user_id == user_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if revoke:
        if row:
            row.revoked_at = service.now()
            row.revoked_by_user_id = actor.id
        connection_ids = select(MotiveConnection.id).where(
            MotiveConnection.tenant_id == actor.tenant_id,
            MotiveConnection.fleet_customer_id == company_id,
        )
        await db.execute(
            update(MotiveAuthorization)
            .where(
                MotiveAuthorization.tenant_id == actor.tenant_id,
                MotiveAuthorization.connection_id.in_(connection_ids),
                MotiveAuthorization.user_id == user_id,
                MotiveAuthorization.consumed_at.is_(None),
            )
            .values(consumed_at=service.now())
        )
    else:
        user = (
            await db.execute(
                candidate_query(actor.tenant_id, company_id).where(User.id == user_id)
            )
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Fleet user not found")
        if row is None:
            row = MotiveFleetAdminGrant(
                tenant_id=actor.tenant_id,
                fleet_customer_id=company_id,
                user_id=user_id,
                granted_by_user_id=actor.id,
            )
            db.add(row)
        elif row.deleted_at or row.revoked_at:
            row.deleted_at = row.revoked_at = row.revoked_by_user_id = None
            row.granted_by_user_id = actor.id
    await db.commit()
    if revoke:
        return {"user_id": user_id, "granted": False}
    await db.refresh(row)
    return {
        "user_id": user_id,
        "name": f"{user.first_name} {user.last_name}".strip(),
        "email": user.email,
        "granted_at": row.created_at,
        "granted_by_user_id": row.granted_by_user_id,
    }
