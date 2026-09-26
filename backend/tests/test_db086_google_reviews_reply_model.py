"""DB-086: each shop chooses which Claude model drafts its Google review replies.

The choice is limited to a fixed list so a tenant can never send an arbitrary or
retired model id (DB-084 was a retired pin). Each model carries its own request
shape: Sonnet 5 thinks by default, and thinking tokens count against the short
draft budget, so it runs with thinking disabled. No test reaches Anthropic.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.db.models.google_review import GoogleBusinessConnection, GoogleReview, GoogleReviewSettings
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.services import google_reviews_service as svc


async def _owner(db_session):
    tenant = Tenant(name="Pit Stop", slug=f"pit-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    return SimpleNamespace(id=uuid4(), tenant_id=tenant.id, role=UserRole.GARAGE_OWNER)


@pytest.mark.asyncio
async def test_settings_default_to_opus_4_8_and_list_the_offered_models(db_session):
    from app.api.v1.endpoints.google_reviews import get_settings

    owner = await _owner(db_session)
    result = await get_settings(db=db_session, current_user=owner)

    assert result["reply_model"] == "claude-opus-4-8"
    assert [o["id"] for o in result["reply_model_options"]] == ["claude-opus-4-8", "claude-sonnet-5"]
    assert all(o["label"] for o in result["reply_model_options"])


@pytest.mark.asyncio
async def test_a_shop_can_choose_sonnet_5(db_session):
    from app.api.v1.endpoints.google_reviews import ReviewSettingsPayload, get_settings, save_settings

    owner = await _owner(db_session)
    await save_settings(payload=ReviewSettingsPayload(reply_model="claude-sonnet-5"), db=db_session, current_user=owner)

    assert (await get_settings(db=db_session, current_user=owner))["reply_model"] == "claude-sonnet-5"


def test_an_unlisted_model_is_rejected():
    from app.api.v1.endpoints.google_reviews import ReviewSettingsPayload

    for bad in ("claude-opus-4-1", "gpt-4o", ""):
        with pytest.raises(ValidationError):
            ReviewSettingsPayload(reply_model=bad)


async def _draft_with(db_session, monkeypatch, reply_model: str | None) -> tuple[dict, GoogleReview]:
    owner = await _owner(db_session)
    connection = GoogleBusinessConnection(tenant_id=owner.tenant_id, google_account_id="1", location_id="2", status="connected")
    db_session.add(connection)
    db_session.add(GoogleReviewSettings(tenant_id=owner.tenant_id, reply_model=reply_model))
    await db_session.flush()
    review = GoogleReview(tenant_id=owner.tenant_id, connection_id=connection.id, google_review_id="r", rating=5, review_text="Quick brake job.", raw_payload={})
    db_session.add(review)
    await db_session.flush()

    sent: dict = {}

    class FakeMessages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="Thanks for trusting us with your brakes!")], stop_reason="end_turn")

    class FakeAnthropic:
        def __init__(self, *a, **k): self.messages = FakeMessages()

    monkeypatch.setattr(svc.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(svc.anthropic, "Anthropic", FakeAnthropic)
    await svc.generate_draft(db_session, tenant_id=owner.tenant_id, review=review)
    return sent, review


@pytest.mark.asyncio
async def test_drafts_use_the_shops_chosen_model(db_session, monkeypatch):
    sent, review = await _draft_with(db_session, monkeypatch, "claude-sonnet-5")

    assert sent["model"] == "claude-sonnet-5"
    assert sent["thinking"] == {"type": "disabled"}
    assert review.ai_model == "claude-sonnet-5"
    assert review.reply_text == "Thanks for trusting us with your brakes!"


@pytest.mark.asyncio
async def test_drafts_fall_back_to_opus_4_8_without_a_choice(db_session, monkeypatch):
    sent, review = await _draft_with(db_session, monkeypatch, None)

    assert sent["model"] == "claude-opus-4-8"
    assert "thinking" not in sent  # Opus 4.8 runs without thinking when the parameter is omitted
    assert review.ai_model == "claude-opus-4-8"


def test_the_api_accepts_exactly_the_offered_models():
    from typing import get_args

    from app.api.v1.endpoints.google_reviews import ReviewSettingsPayload

    assert set(get_args(ReviewSettingsPayload.model_fields["reply_model"].annotation)) == set(svc.REPLY_MODELS)
