from __future__ import annotations

import pytest
import resend

import app.services.email_service as email_svc


def test_format_sender_uses_tenant_display_name(monkeypatch):
    monkeypatch.setattr(email_svc.settings, "RESEND_FROM_EMAIL", "quotes@example.com")

    assert email_svc._format_sender("Big Rig Repairs") == '"Big Rig Repairs" <quotes@example.com>'


@pytest.mark.asyncio
async def test_send_password_reset_email_calls_resend(monkeypatch):
    sent = {}

    def fake_send(params):
        sent.update(params)
        return {"id": "mock-id"}

    monkeypatch.setattr(resend.Emails, "send", fake_send)

    await email_svc.send_password_reset_email("user@example.com", "reset-token-abc")

    assert sent["to"] == "user@example.com"
    assert "Reset Your Password" in sent["subject"]
    assert "reset-token-abc" in sent["html"]


@pytest.mark.asyncio
async def test_send_password_reset_email_raises_on_failure(monkeypatch):
    def fake_send(params):
        raise RuntimeError("API down")

    monkeypatch.setattr(resend.Emails, "send", fake_send)

    with pytest.raises(Exception, match="Failed to send password reset email"):
        await email_svc.send_password_reset_email("u@e.com", "tok")


@pytest.mark.asyncio
async def test_send_email_verification_calls_resend(monkeypatch):
    sent = {}

    def fake_send(params):
        sent.update(params)
        return {"id": "mock-id"}

    monkeypatch.setattr(resend.Emails, "send", fake_send)

    await email_svc.send_email_verification("new@example.com", "verify-token-xyz")

    assert sent["to"] == "new@example.com"
    assert "Verify" in sent["subject"]
    assert "verify-token-xyz" in sent["html"]


@pytest.mark.asyncio
async def test_send_enrollment_received_email(monkeypatch):
    sent = {}

    def fake_send(params):
        sent.update(params)
        return {"id": "mock-id"}

    monkeypatch.setattr(resend.Emails, "send", fake_send)

    await email_svc.send_enrollment_received_email(
        "owner@garage.com", "Big Rig Repairs", "John"
    )

    assert sent["to"] == "owner@garage.com"
    assert "Big Rig Repairs" in sent["subject"]
    assert "John" in sent["html"]


@pytest.mark.asyncio
async def test_send_email_change_notification_masks_email(monkeypatch):
    sent = {}

    def fake_send(params):
        sent.update(params)
        return {"id": "mock-id"}

    monkeypatch.setattr(resend.Emails, "send", fake_send)

    await email_svc.send_email_change_notification(
        "old@example.com", "newlong@example.com", "Jane"
    )

    assert sent["to"] == "old@example.com"
    # New email should be partially masked
    assert "newlong@example.com" not in sent["html"]
    assert "***" in sent["html"]
