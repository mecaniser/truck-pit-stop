"""DB-078: activation readiness for the Google Business Profile review feature.

The feature is implemented and deployed but dark behind DB-007 (Google Basic
API Access, quota 0). These tests cover the parts that would fail the moment
quota is granted, plus the credential and tenant boundaries that carry the most
risk. No test may reach Google or Anthropic over the network.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.db.models.google_review import (
    GoogleBusinessConnection,
    GoogleReview,
    GoogleReviewSettings,
    GoogleReviewStatus,
)
from app.db.models.tenant import Tenant


# Anthropic model ids are <family>-<major>-<minor>, e.g. claude-opus-4-1.
# A second digit in the minor position ("4-8") is not a released model and the
# API rejects it, so the pin must be checked as data, not eyeballed.
KNOWN_BAD_PINS = {"claude-opus-4-8"}


def test_google_reviews_model_pin_is_not_a_known_bad_id():
    from app.services import google_reviews_service

    assert google_reviews_service.MODEL not in KNOWN_BAD_PINS


def test_description_library_model_pin_is_not_a_known_bad_id():
    from app.services import description_library_service

    assert description_library_service.MODEL not in KNOWN_BAD_PINS


async def _tenant(db_session) -> Tenant:
    tenant = Tenant(name="Pit Stop", slug=f"pit-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    return tenant


async def _connection(db_session, tenant: Tenant) -> GoogleBusinessConnection:
    connection = GoogleBusinessConnection(
        tenant_id=tenant.id,
        google_account_id="111",
        location_id="222",
        status="connected",
    )
    db_session.add(connection)
    await db_session.flush()
    return connection


@pytest.mark.asyncio
async def test_failed_draft_records_an_operator_visible_reason(db_session, monkeypatch):
    """A model/API failure must name itself, not leave a silent empty draft."""
    from app.services import google_reviews_service

    tenant = await _tenant(db_session)
    connection = await _connection(db_session, tenant)
    review = GoogleReview(
        tenant_id=tenant.id,
        connection_id=connection.id,
        google_review_id="r-1",
        rating=5,
        review_text="Fast turnaround on my brakes.",
        raw_payload={},
    )
    db_session.add(review)
    await db_session.flush()

    monkeypatch.setattr(
        google_reviews_service.settings, "ANTHROPIC_API_KEY", "test-key"
    )

    class _Boom:
        def __init__(self, *args, **kwargs):
            pass

        @property
        def messages(self):
            raise RuntimeError("model: claude-opus-4-8 not found")

    monkeypatch.setattr(google_reviews_service.anthropic, "Anthropic", _Boom)

    await google_reviews_service.generate_draft(
        db_session, tenant_id=tenant.id, review=review
    )

    assert review.ai_draft is None
    assert review.requires_approval is True
    assert review.status == GoogleReviewStatus.AWAITING_APPROVAL.value
    # The operator reads the inbox, not ai_metadata; the reason must reach them.
    assert review.publish_failure_reason
    assert "claude-opus-4-8" in review.publish_failure_reason


@pytest.mark.asyncio
async def test_publish_reply_blocks_a_cross_tenant_review(db_session):
    from app.services.google_reviews_service import publish_reply

    owner = await _tenant(db_session)
    attacker = await _tenant(db_session)
    connection = await _connection(db_session, owner)
    review = GoogleReview(
        tenant_id=owner.id,
        connection_id=connection.id,
        google_review_id="r-2",
        rating=4,
        review_text="Good work.",
        reply_text="Thank you.",
        raw_payload={},
    )
    db_session.add(review)
    await db_session.flush()

    with pytest.raises(ValueError):
        await publish_reply(db_session, tenant_id=attacker.id, review=review)


def test_token_encryption_round_trips(monkeypatch):
    from app.core import google_business_crypto

    monkeypatch.setattr(
        google_business_crypto.settings,
        "GOOGLE_BUSINESS_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode(),
    )
    sealed = google_business_crypto.encrypt_google_business_token("refresh-abc")
    assert sealed != "refresh-abc"
    assert google_business_crypto.decrypt_google_business_token(sealed) == "refresh-abc"


def test_token_decryption_under_a_rotated_key_raises(monkeypatch):
    from app.core import google_business_crypto

    monkeypatch.setattr(
        google_business_crypto.settings,
        "GOOGLE_BUSINESS_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode(),
    )
    sealed = google_business_crypto.encrypt_google_business_token("refresh-abc")

    monkeypatch.setattr(
        google_business_crypto.settings,
        "GOOGLE_BUSINESS_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode(),
    )
    with pytest.raises(google_business_crypto.GoogleBusinessTokenEncryptionError):
        google_business_crypto.decrypt_google_business_token(sealed)


def test_star_rating_enum_normalizes_to_an_integer():
    from app.services.google_reviews_service import _review_fields

    _, rating, _, _, _, _ = _review_fields(
        {"reviewId": "r-3", "starRating": "FIVE", "comment": "Great"}
    )
    assert rating == 5


@pytest.mark.asyncio
async def test_successful_regeneration_clears_a_previous_draft_failure(
    db_session, monkeypatch
):
    """A stale failure must not sit under a draft that later succeeded."""
    from app.services import google_reviews_service

    tenant = await _tenant(db_session)
    connection = await _connection(db_session, tenant)
    review = GoogleReview(
        tenant_id=tenant.id,
        connection_id=connection.id,
        google_review_id="r-4",
        rating=5,
        review_text="Back on the road same day.",
        raw_payload={},
        publish_failure_reason="AI draft unavailable: earlier outage",
    )
    db_session.add(review)
    await db_session.flush()

    monkeypatch.setattr(
        google_reviews_service.settings, "ANTHROPIC_API_KEY", "test-key"
    )

    class _Block:
        type = "text"
        text = "Thanks for the kind words!"

    class _Response:
        content = [_Block()]

    class _Messages:
        def create(self, **kwargs):
            return _Response()

    class _Client:
        def __init__(self, *args, **kwargs):
            self.messages = _Messages()

    monkeypatch.setattr(google_reviews_service.anthropic, "Anthropic", _Client)

    await google_reviews_service.generate_draft(
        db_session, tenant_id=tenant.id, review=review
    )

    assert review.ai_draft == "Thanks for the kind words!"
    assert review.publish_failure_reason is None
