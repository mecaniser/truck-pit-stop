"""DB-085: reviews that already carry a public reply on Google.

The first production sync treated every review as unreplied: it ignored Google's
`reviewReply`, queued an AI draft for each one, counted all 50 as "Unreplied", and
left approve/publish free to overwrite a reply the shop had already posted. It also
read only the first page of reviews. No test may reach Google over the network.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.db.models.google_review import GoogleBusinessConnection, GoogleReview, GoogleReviewStatus
from app.db.models.tenant import Tenant
from app.services import google_reviews_service as svc


def _review(rid: str, *, reply: str | None = None) -> dict:
    payload = {"reviewId": rid, "starRating": "FIVE", "comment": f"Great work {rid}", "createTime": "2026-09-01T12:00:00Z", "reviewer": {"displayName": "Driver"}}
    if reply is not None:
        payload["reviewReply"] = {"comment": reply, "updateTime": "2026-09-02T12:00:00Z"}
    return payload


async def _connected(db_session) -> GoogleBusinessConnection:
    tenant = Tenant(name="Pit Stop", slug=f"pit-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    connection = GoogleBusinessConnection(tenant_id=tenant.id, google_account_id="111", location_id="222", status="connected")
    db_session.add(connection)
    await db_session.flush()
    return connection


def _google(monkeypatch, pages: list[dict]) -> list[str]:
    """Serve `pages` in order from the v4 reviews endpoint and record requested URLs."""
    requested: list[str] = []

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None, params=None):
            requested.append(str(httpx.URL(url, params=params)))
            return httpx.Response(200, json=pages[len(requested) - 1], request=httpx.Request("GET", url))

    async def fake_token(db, connection): return "token"
    monkeypatch.setattr(svc, "_access_token", fake_token)
    monkeypatch.setattr(svc.httpx, "AsyncClient", FakeClient)
    return requested


def _no_drafts(monkeypatch) -> list[str]:
    drafted: list[str] = []

    async def fake_draft(db, *, tenant_id, review):
        drafted.append(review.google_review_id)
        return review
    monkeypatch.setattr(svc, "generate_draft", fake_draft)
    return drafted


async def _stored(db_session, connection, rid) -> GoogleReview:
    from sqlalchemy import select
    return (await db_session.execute(select(GoogleReview).where(GoogleReview.tenant_id == connection.tenant_id, GoogleReview.google_review_id == rid))).scalar_one()


@pytest.mark.asyncio
async def test_a_review_already_replied_on_google_is_recorded_as_replied_without_a_draft(db_session, monkeypatch):
    connection = await _connected(db_session)
    _google(monkeypatch, [{"reviews": [_review("answered", reply="Thanks for coming in!"), _review("open")]}])
    drafted = _no_drafts(monkeypatch)

    await svc.sync_connection(db_session, connection)

    answered = await _stored(db_session, connection, "answered")
    assert answered.status == GoogleReviewStatus.PUBLISHED.value
    assert answered.reply_text == "Thanks for coming in!"
    assert answered.requires_approval is False
    assert answered.published_at is not None
    assert drafted == ["open"]


@pytest.mark.asyncio
async def test_sync_corrects_a_stored_review_whose_reply_was_missed(db_session, monkeypatch):
    """The 50 reviews already in production were stored as awaiting approval with no draft."""
    connection = await _connected(db_session)
    db_session.add(GoogleReview(tenant_id=connection.tenant_id, connection_id=connection.id, google_review_id="answered", rating=5, review_text="Great work", raw_payload={}, status=GoogleReviewStatus.AWAITING_APPROVAL.value, publish_failure_reason="AI draft unavailable: 404"))
    await db_session.flush()
    _google(monkeypatch, [{"reviews": [_review("answered", reply="Thanks for coming in!")]}])
    _no_drafts(monkeypatch)

    await svc.sync_connection(db_session, connection)

    answered = await _stored(db_session, connection, "answered")
    assert answered.status == GoogleReviewStatus.PUBLISHED.value
    assert answered.reply_text == "Thanks for coming in!"
    assert answered.publish_failure_reason is None


@pytest.mark.asyncio
async def test_sync_never_discards_an_operator_edit_in_progress(db_session, monkeypatch):
    """An operator who edited the reply to replace Google's must not lose it to the next sync."""
    connection = await _connected(db_session)
    db_session.add(GoogleReview(tenant_id=connection.tenant_id, connection_id=connection.id, google_review_id="answered", rating=5, review_text="Great work", raw_payload={}, status=GoogleReviewStatus.AWAITING_APPROVAL.value, ai_draft="AI text", reply_text="Operator's improved reply"))
    await db_session.flush()
    _google(monkeypatch, [{"reviews": [_review("answered", reply="Old public reply")]}])
    _no_drafts(monkeypatch)

    await svc.sync_connection(db_session, connection)

    answered = await _stored(db_session, connection, "answered")
    assert answered.status == GoogleReviewStatus.AWAITING_APPROVAL.value
    assert answered.reply_text == "Operator's improved reply"


@pytest.mark.asyncio
async def test_sync_reads_every_page_of_reviews(db_session, monkeypatch):
    connection = await _connected(db_session)
    requested = _google(monkeypatch, [
        {"reviews": [_review("p1")], "nextPageToken": "tok-2"},
        {"reviews": [_review("p2")]},
    ])
    drafted = _no_drafts(monkeypatch)

    await svc.sync_connection(db_session, connection)

    assert drafted == ["p1", "p2"]
    assert len(requested) == 2
    assert "pageToken=tok-2" in requested[1]


@pytest.mark.asyncio
async def test_publish_refuses_to_overwrite_a_google_reply_without_human_approval(db_session, monkeypatch):
    connection = await _connected(db_session)
    review = GoogleReview(tenant_id=connection.tenant_id, connection_id=connection.id, google_review_id="answered", rating=5, review_text="Great work", raw_payload=_review("answered", reply="Existing public reply"), status=GoogleReviewStatus.NEW.value, reply_text="AI text", requires_approval=False)
    db_session.add(review)
    await db_session.flush()

    async def must_not_call(*a, **k): raise AssertionError("Google must not be called")
    monkeypatch.setattr(svc, "_access_token", must_not_call)

    with pytest.raises(RuntimeError, match="already has a public reply"):
        await svc.publish_reply(db_session, tenant_id=connection.tenant_id, review=review)


@pytest.mark.asyncio
async def test_inbox_needs_reply_filter_excludes_reviews_already_replied(db_session):
    from types import SimpleNamespace

    from app.api.v1.endpoints.google_reviews import inbox
    from app.db.models.user import UserRole

    connection = await _connected(db_session)
    for rid, status in [("new", "new"), ("pending", "awaiting_approval"), ("broken", "failed"), ("done", "published")]:
        db_session.add(GoogleReview(tenant_id=connection.tenant_id, connection_id=connection.id, google_review_id=rid, rating=5, raw_payload={}, status=status))
    await db_session.flush()
    owner = SimpleNamespace(id=uuid4(), tenant_id=connection.tenant_id, role=UserRole.GARAGE_OWNER)

    needs = await inbox(status_filter="needs_reply", rating=None, db=db_session, current_user=owner)

    assert sorted(r["status"] for r in needs) == ["awaiting_approval", "failed", "new"]
