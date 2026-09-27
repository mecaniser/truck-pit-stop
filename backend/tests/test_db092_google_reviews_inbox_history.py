"""DB-092: the inbox shows the whole review history, page by page.

Production syncs 7 pages (~300-350 reviews) but the inbox returned only the newest 200,
so the oldest replied reviews never appeared. The list is now paged with a total, and a
review already replied on Google cannot be silently overwritten by an AI regeneration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.google_reviews import inbox, regenerate
from app.db.models.google_review import GoogleBusinessConnection, GoogleReview
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole


async def _shop_with_reviews(db_session, statuses: list[str]):
    tenant = Tenant(name="Pit Stop", slug=f"pit-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    connection = GoogleBusinessConnection(tenant_id=tenant.id, google_account_id="1", location_id="2", status="connected")
    db_session.add(connection)
    await db_session.flush()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    reviews = []
    for i, status in enumerate(statuses):
        review = GoogleReview(tenant_id=tenant.id, connection_id=connection.id, google_review_id=f"r{i}", rating=5, raw_payload={}, status=status, review_created_at=start + timedelta(days=i))
        db_session.add(review)
        reviews.append(review)
    await db_session.flush()
    return SimpleNamespace(id=uuid4(), tenant_id=tenant.id, role=UserRole.GARAGE_OWNER), reviews


@pytest.mark.asyncio
async def test_inbox_pages_through_the_full_history_newest_first(db_session):
    owner, _ = await _shop_with_reviews(db_session, ["published"] * 120)

    first = await inbox(status_filter=None, rating=None, limit=50, offset=0, db=db_session, current_user=owner)
    last = await inbox(status_filter=None, rating=None, limit=50, offset=100, db=db_session, current_user=owner)

    assert first["total"] == 120 and len(first["items"]) == 50
    assert [first["limit"], first["offset"]] == [50, 0]
    assert len(last["items"]) == 20
    assert first["items"][0]["review_created_at"] > first["items"][-1]["review_created_at"]


@pytest.mark.asyncio
async def test_inbox_total_counts_only_the_active_filter(db_session):
    owner, _ = await _shop_with_reviews(db_session, ["published"] * 5 + ["awaiting_approval"] * 3)

    replied = await inbox(status_filter="published", rating=None, limit=50, offset=0, db=db_session, current_user=owner)

    assert replied["total"] == 5
    assert {r["status"] for r in replied["items"]} == {"published"}


@pytest.mark.asyncio
async def test_regenerating_a_review_already_replied_on_google_is_refused(db_session):
    owner, reviews = await _shop_with_reviews(db_session, ["published"])

    with pytest.raises(HTTPException) as refused:
        await regenerate(review_id=reviews[0].id, db=db_session, current_user=owner)

    assert refused.value.status_code == 409
