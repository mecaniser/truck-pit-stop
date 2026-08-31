"""The status filters count live orders per status.

This endpoint shipped counting a column the read model does not have
(func.count(RepairOrderReadModel.id)), which raises at query construction. The
route test that accompanied it only asserted the route was registered, so it
passed while every request failed and the frontend — which treats an error as
"counts not loaded" — silently showed filters with no numbers at all.

These call the endpoint, so a column that does not exist cannot pass again.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.security import create_access_token
from app.db.models.repair_order_read_model import RepairOrderReadModel
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole

PREFIX = "/api/v1/repair-orders"


def _headers(user: User, tenant: Tenant) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)}, tenant_id=str(tenant.id))}"}


async def _seed(db, rows: list[tuple[str, bool]]):
    suffix = uuid4().hex
    tenant = Tenant(name="Counting Shop", slug=f"counts-{suffix}", is_active=True)
    db.add(tenant)
    await db.flush()
    owner = User(
        tenant_id=tenant.id, email=f"counts-{suffix}@example.test", hashed_password="x",
        first_name="Count", last_name="Owner", role=UserRole.GARAGE_OWNER,
        is_active=True, is_verified=True,
    )
    db.add(owner)
    for status_value, is_deleted in rows:
        db.add(RepairOrderReadModel(
            repair_order_id=uuid4(), tenant_id=tenant.id, customer_id=uuid4(), vehicle_id=uuid4(),
            status=status_value, is_internal=False, is_deleted=is_deleted,
            created_at=datetime.now(timezone.utc), search_document="", search_compact="",
            payload={},
        ))
    await db.commit()
    return tenant, owner


@pytest.mark.asyncio
async def test_counts_each_status_and_totals_them(client, db_session):
    tenant, owner = await _seed(db_session, [
        ("completed", False), ("completed", False), ("in_progress", False), ("draft", False),
    ])

    response = await client.get(f"{PREFIX}/status-counts", headers=_headers(owner, tenant))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completed"] == 2
    assert body["in_progress"] == 1
    assert body["draft"] == 1
    assert body["all"] == 4


@pytest.mark.asyncio
async def test_deleted_orders_are_left_out_of_the_live_counts(client, db_session):
    tenant, owner = await _seed(db_session, [("completed", False), ("completed", True)])

    body = (await client.get(f"{PREFIX}/status-counts", headers=_headers(owner, tenant))).json()

    assert body["completed"] == 1
    assert body["all"] == 1


@pytest.mark.asyncio
async def test_counts_honour_the_same_search_the_list_applies(client, db_session):
    tenant, owner = await _seed(db_session, [("completed", False), ("completed", False)])
    # A search the seeded rows cannot match must empty the counts, or a filter
    # advertises rows the list would not show.
    body = (await client.get(f"{PREFIX}/status-counts", params={"search": "zzz-no-such-order"}, headers=_headers(owner, tenant))).json()

    assert body["all"] == 0


@pytest.mark.asyncio
async def test_counts_do_not_cross_tenants(client, db_session):
    tenant, owner = await _seed(db_session, [("completed", False)])
    await _seed(db_session, [("completed", False), ("completed", False)])

    body = (await client.get(f"{PREFIX}/status-counts", headers=_headers(owner, tenant))).json()

    assert body["completed"] == 1
    assert body["all"] == 1
