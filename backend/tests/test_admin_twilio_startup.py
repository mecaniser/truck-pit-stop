import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import admin


def test_admin_twilio_client_is_created_only_for_configured_actions(monkeypatch):
    monkeypatch.setattr(admin.settings, "TWILIO_ACCOUNT_SID", "")
    monkeypatch.setattr(admin.settings, "TWILIO_AUTH_TOKEN", "")

    with pytest.raises(HTTPException, match="Twilio account credentials are not configured") as exc_info:
        admin._get_twilio_client()

    assert exc_info.value.status_code == 400
