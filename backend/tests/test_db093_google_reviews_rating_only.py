"""DB-093: rating-only Google reviews, and empty replies.

A review with stars but no text was skipped by `generate_draft` without saying so, and
an empty reply could be approved, after which publishing failed with a generic 502
(production, 2026-09-27, review c9703059). No network in these tests.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.google_review import GoogleBusinessConnection, GoogleReview
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.services import google_reviews_service as svc


async def _review(db_session, *, rating=5, text=None, reply=None, requires_approval=True):
    tenant = Tenant(name="Pit Stop", slug=f"pit-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    connection = GoogleBusinessConnection(tenant_id=tenant.id, google_account_id="1", location_id="2", status="connected")
    db_session.add(connection)
    await db_session.flush()
    review = GoogleReview(tenant_id=tenant.id, connection_id=connection.id, google_review_id="r", rating=rating, review_text=text, reviewer_name="Tom Rohin", reply_text=reply, raw_payload={}, status="awaiting_approval", requires_approval=requires_approval)
    db_session.add(review)
    await db_session.flush()
    return SimpleNamespace(id=uuid4(), tenant_id=tenant.id, role=UserRole.GARAGE_OWNER), review


def _fake_claude(monkeypatch, reply: str) -> dict:
    sent: dict = {}

    class FakeMessages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=reply)], stop_reason="end_turn")

    class FakeAnthropic:
        def __init__(self, *a, **k): self.messages = FakeMessages()

    monkeypatch.setattr(svc.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(svc.anthropic, "Anthropic", FakeAnthropic)
    return sent


@pytest.mark.asyncio
async def test_a_rating_only_review_gets_a_short_draft_that_invents_nothing(db_session, monkeypatch):
    owner, review = await _review(db_session, rating=5)
    sent = _fake_claude(monkeypatch, "Thanks for the five stars, Tom. We appreciate it.")

    await svc.generate_draft(db_session, tenant_id=owner.tenant_id, review=review)

    prompt = sent["messages"][0]["content"]
    assert "no written review" in prompt.lower()
    assert "do not mention any details" in prompt.lower()
    assert review.reply_text == "Thanks for the five stars, Tom. We appreciate it."
    assert review.requires_approval is True


@pytest.mark.asyncio
async def test_a_low_rating_without_text_asks_for_an_apology_and_contact(db_session, monkeypatch):
    owner, review = await _review(db_session, rating=2)
    sent = _fake_claude(monkeypatch, "We are sorry we fell short, Tom. Please call us so we can put it right.")

    await svc.generate_draft(db_session, tenant_id=owner.tenant_id, review=review)

    prompt = sent["messages"][0]["content"].lower()
    assert "apolog" in prompt and "contact" in prompt


@pytest.mark.asyncio
async def test_without_an_ai_key_no_draft_is_attempted(db_session, monkeypatch):
    owner, review = await _review(db_session, rating=5)
    monkeypatch.setattr(svc.settings, "ANTHROPIC_API_KEY", "")

    class MustNotConstruct:
        def __init__(self, *a, **k): raise AssertionError("no AI call without a key")
    monkeypatch.setattr(svc.anthropic, "Anthropic", MustNotConstruct)

    await svc.generate_draft(db_session, tenant_id=owner.tenant_id, review=review)

    assert review.reply_text is None


@pytest.mark.asyncio
async def test_an_empty_reply_cannot_be_approved(db_session):
    from app.api.v1.endpoints.google_reviews import approve

    owner, review = await _review(db_session, reply="   ")
    with pytest.raises(HTTPException) as refused:
        await approve(review_id=review.id, db=db_session, current_user=owner)

    assert refused.value.status_code == 409
    assert review.requires_approval is True


@pytest.mark.asyncio
async def test_publishing_an_empty_reply_is_refused_clearly_not_as_a_google_failure(db_session):
    """The production review c9703059 was approved empty; its publish surfaced as a 502."""
    from app.api.v1.endpoints.google_reviews import publish

    owner, review = await _review(db_session, reply=None, requires_approval=False)
    with pytest.raises(HTTPException) as refused:
        await publish(review_id=review.id, db=db_session, current_user=owner)

    assert refused.value.status_code == 409
