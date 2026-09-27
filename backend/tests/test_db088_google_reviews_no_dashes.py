"""DB-088: AI review replies never contain em or en dashes.

The owner does not want them in public replies (a common tell of machine-written
text). The prompt asks the model not to use them, and the draft is cleaned in code
so the rule holds even when the model ignores the instruction. No network.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.google_review import GoogleBusinessConnection, GoogleReview
from app.db.models.tenant import Tenant
from app.services import google_reviews_service as svc


@pytest.mark.parametrize("raw, clean", [
    ("Thanks, Dana — we loved having you in.", "Thanks, Dana, we loved having you in."),
    ("Fast work—and fair prices.", "Fast work, and fair prices."),
    ("Back on the road – see you next service.", "Back on the road, see you next service."),
    ("Most brake jobs take 2–3 hours.", "Most brake jobs take 2-3 hours."),
    ("We aim for 1 — 2 days.", "We aim for 1-2 days."),
    ("Thank you — see you soon —", "Thank you, see you soon."),
    ("No dashes here - just a hyphen.", "No dashes here - just a hyphen."),
])
def test_dashes_are_removed_from_reply_text(raw, clean):
    assert svc._remove_dashes(raw) == clean


@pytest.mark.asyncio
async def test_a_generated_draft_never_contains_a_dash(db_session, monkeypatch):
    tenant = Tenant(name="Pit Stop", slug=f"pit-{uuid4().hex[:8]}")
    db_session.add(tenant)
    await db_session.flush()
    connection = GoogleBusinessConnection(tenant_id=tenant.id, google_account_id="1", location_id="2", status="connected")
    db_session.add(connection)
    await db_session.flush()
    review = GoogleReview(tenant_id=tenant.id, connection_id=connection.id, google_review_id="r", rating=5, review_text="Quick brake job.", raw_payload={})
    db_session.add(review)
    await db_session.flush()
    sent: dict = {}

    class FakeMessages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="Thanks — a quick brake job is the best kind–boring and done.")], stop_reason="end_turn")

    class FakeAnthropic:
        def __init__(self, *a, **k): self.messages = FakeMessages()

    monkeypatch.setattr(svc.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(svc.anthropic, "Anthropic", FakeAnthropic)
    await svc.generate_draft(db_session, tenant_id=tenant.id, review=review)

    for text in (review.ai_draft, review.reply_text):
        assert "—" not in text and "–" not in text
    assert review.reply_text == "Thanks, a quick brake job is the best kind, boring and done."
    assert "dash" in sent["system"].lower()
