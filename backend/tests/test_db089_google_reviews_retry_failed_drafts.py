"""DB-089: reviews whose AI draft failed are retried by the sync, and always wait for approval.

A draft was attempted once, when the sync first stored a review. Every review imported
while DB-078 pinned `claude-opus-4-1` (404) kept "AI draft unavailable" in
publish_failure_reason after DB-084 fixed the model, because nothing tried again; each one
showed the stale error until an operator pressed Regenerate AI.

The sync now retries those drafts. A retried draft never auto-publishes, whatever the
shop's 5-star setting: nobody has read it, and a backlog retried in one sync would
otherwise reach Google as a burst of unreviewed public replies. No test reaches Google or
Anthropic over the network.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.db.models.google_review import GoogleBusinessConnection, GoogleReview, GoogleReviewSettings, GoogleReviewStatus
from app.db.models.tenant import Tenant
from app.services import google_reviews_service as svc

STALE = "AI draft unavailable: Error code: 404 - {'type': 'error', 'error': {'type': 'not_found_error', 'message': 'model: claude-opus-4-1'}}"


async def _shop(db_session, *, auto_publish_five_star: bool) -> GoogleBusinessConnection:
    tenant = Tenant(name="Pit Stop", slug=f"pit-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(GoogleReviewSettings(tenant_id=tenant.id, auto_publish_five_star=auto_publish_five_star))
    connection = GoogleBusinessConnection(tenant_id=tenant.id, google_account_id="111", location_id="222", status="connected")
    db_session.add(connection)
    await db_session.flush()
    return connection


async def _stored(db_session, connection, rid: str, **fields) -> GoogleReview:
    review = GoogleReview(tenant_id=connection.tenant_id, connection_id=connection.id, google_review_id=rid, rating=5, review_text=f"Great work {rid}", **fields)
    db_session.add(review)
    await db_session.flush()
    return review


def _google_lists(monkeypatch, rids: list[str]) -> None:
    """Serve one page listing `rids`, none carrying a reply on Google."""
    page = {"reviews": [{"reviewId": rid, "starRating": "FIVE", "comment": f"Great work {rid}", "createTime": "2026-09-01T12:00:00Z", "reviewer": {"displayName": "Driver"}} for rid in rids]}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None, params=None):
            return httpx.Response(200, json=page, request=httpx.Request("GET", url))

    async def fake_token(db, connection): return "token"
    monkeypatch.setattr(svc, "_access_token", fake_token)
    monkeypatch.setattr(svc.httpx, "AsyncClient", FakeClient)


def _model_replies(monkeypatch, text: str = "Thanks for trusting us with your truck!") -> list[str]:
    """Answer every draft request with `text` and record which reviews were drafted."""
    prompts: list[str] = []
    monkeypatch.setattr(svc.settings, "ANTHROPIC_API_KEY", "test-key")

    class Block:
        type = "text"

    class Messages:
        def create(self, **kwargs):
            prompts.append(kwargs["messages"][0]["content"])
            block = Block()
            block.text = text
            return type("Response", (), {"content": [block]})()

    class Client:
        def __init__(self, *a, **k): self.messages = Messages()

    monkeypatch.setattr(svc.anthropic, "Anthropic", Client)
    return prompts


@pytest.mark.asyncio
async def test_sync_retries_a_draft_that_failed_and_clears_the_stale_error(db_session, monkeypatch):
    connection = await _shop(db_session, auto_publish_five_star=False)
    review = await _stored(db_session, connection, "failed", status=GoogleReviewStatus.AWAITING_APPROVAL.value, requires_approval=True, publish_failure_reason=STALE, ai_metadata={"error": "404"})
    _google_lists(monkeypatch, ["failed"])
    prompts = _model_replies(monkeypatch)

    await svc.sync_connection(db_session, connection)

    assert len(prompts) == 1
    assert review.reply_text == "Thanks for trusting us with your truck!"
    assert review.publish_failure_reason is None


@pytest.mark.asyncio
async def test_a_retried_five_star_draft_waits_for_approval_even_with_auto_publish_on(db_session, monkeypatch):
    connection = await _shop(db_session, auto_publish_five_star=True)
    review = await _stored(db_session, connection, "failed", status=GoogleReviewStatus.AWAITING_APPROVAL.value, requires_approval=True, publish_failure_reason=STALE)
    _google_lists(monkeypatch, ["failed"])
    _model_replies(monkeypatch)

    await svc.sync_connection(db_session, connection)

    assert review.reply_text
    assert review.requires_approval is True
    assert review.status == GoogleReviewStatus.AWAITING_APPROVAL.value
    # The publish worker selects NEW/FAILED reviews that need no approval; this one must not qualify.
    due = (await db_session.execute(select(GoogleReview).where(GoogleReview.id == review.id, GoogleReview.status.in_([GoogleReviewStatus.NEW.value, GoogleReviewStatus.FAILED.value]), GoogleReview.requires_approval.is_(False)))).scalar_one_or_none()
    assert due is None


@pytest.mark.asyncio
async def test_a_new_five_star_review_still_follows_the_auto_publish_setting(db_session, monkeypatch):
    """Only retries are held back; a first draft keeps the shop's chosen behaviour."""
    connection = await _shop(db_session, auto_publish_five_star=True)
    _google_lists(monkeypatch, ["fresh"])
    _model_replies(monkeypatch)

    await svc.sync_connection(db_session, connection)

    review = (await db_session.execute(select(GoogleReview).where(GoogleReview.google_review_id == "fresh"))).scalar_one()
    assert review.requires_approval is False
    assert review.status == GoogleReviewStatus.NEW.value


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"status": GoogleReviewStatus.AWAITING_APPROVAL.value, "reply_text": "Draft we already have", "ai_draft": "Draft we already have"}, id="draft-succeeded"),
        pytest.param({"status": GoogleReviewStatus.AWAITING_APPROVAL.value, "reply_text": "Operator is writing this", "publish_failure_reason": STALE}, id="operator-wrote-a-reply"),
        pytest.param({"status": GoogleReviewStatus.FAILED.value, "reply_text": "Approved reply", "publish_failure_reason": "Google rejected the reply"}, id="publish-failed-not-draft"),
        pytest.param({"status": GoogleReviewStatus.PUBLISHED.value, "reply_text": "Live on Google", "publish_failure_reason": None}, id="already-replied"),
    ],
)
@pytest.mark.asyncio
async def test_sync_leaves_reviews_alone_when_there_is_no_failed_draft_to_retry(db_session, monkeypatch, fields):
    connection = await _shop(db_session, auto_publish_five_star=False)
    review = await _stored(db_session, connection, "kept", **fields)
    _google_lists(monkeypatch, ["kept"])
    prompts = _model_replies(monkeypatch)

    await svc.sync_connection(db_session, connection)

    assert prompts == []
    assert review.reply_text == fields["reply_text"]
    assert review.status == fields["status"]


@pytest.mark.asyncio
async def test_a_retry_that_fails_again_keeps_the_review_waiting_with_the_new_reason(db_session, monkeypatch):
    connection = await _shop(db_session, auto_publish_five_star=True)
    review = await _stored(db_session, connection, "failed", status=GoogleReviewStatus.AWAITING_APPROVAL.value, requires_approval=True, publish_failure_reason=STALE)
    _google_lists(monkeypatch, ["failed"])
    monkeypatch.setattr(svc.settings, "ANTHROPIC_API_KEY", "test-key")

    class Down:
        def __init__(self, *a, **k): self.messages = self
        def create(self, **kwargs): raise RuntimeError("overloaded")

    monkeypatch.setattr(svc.anthropic, "Anthropic", Down)

    await svc.sync_connection(db_session, connection)

    assert review.publish_failure_reason == "AI draft unavailable: overloaded"
    assert review.requires_approval is True
    assert review.status == GoogleReviewStatus.AWAITING_APPROVAL.value


@pytest.mark.asyncio
async def test_automatic_retries_stop_after_five_failed_attempts(db_session, monkeypatch):
    """A draft that keeps failing must not cost a model call every 15 minutes forever.
    Regenerate AI still works by hand."""
    connection = await _shop(db_session, auto_publish_five_star=False)
    review = await _stored(db_session, connection, "failed", status=GoogleReviewStatus.AWAITING_APPROVAL.value, requires_approval=True, publish_failure_reason=STALE)
    _google_lists(monkeypatch, ["failed"])
    monkeypatch.setattr(svc.settings, "ANTHROPIC_API_KEY", "test-key")
    calls: list[int] = []

    class Down:
        def __init__(self, *a, **k): self.messages = self
        def create(self, **kwargs):
            calls.append(1)
            raise RuntimeError("AI returned no reply")

    monkeypatch.setattr(svc.anthropic, "Anthropic", Down)

    for _ in range(8):
        await svc.sync_connection(db_session, connection)

    assert len(calls) == 5
    assert review.ai_metadata["draft_attempts"] == 5
    assert review.publish_failure_reason.startswith("AI draft unavailable: ")
