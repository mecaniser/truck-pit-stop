from __future__ import annotations

from copy import deepcopy

import pytest

from app.core.config import settings


@pytest.fixture
def restore_settings():
    original = deepcopy(settings.__dict__)
    yield
    for key, value in original.items():
        setattr(settings, key, value)


def _configure_valid_production() -> None:
    settings.ENVIRONMENT = "production"
    settings.WORKOS_AUTH_ENABLED = True
    settings.WORKOS_ENVIRONMENT = "production"
    settings.WORKOS_API_KEY = "sk_live_example"
    settings.WORKOS_CLIENT_ID = "client_production"
    settings.WORKOS_REDIRECT_URI = "https://api.dieselbridge.com/api/v1/auth/workos/callback"
    settings.WORKOS_POST_LOGIN_URL = "https://www.dieselbridge.com"
    settings.WORKOS_WEBHOOK_SECRET = "whsec_production"


def test_valid_production_workos_configuration_passes(restore_settings):
    _configure_valid_production()

    settings.validate_workos_deployment()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("WORKOS_ENVIRONMENT", "staging", "cannot use WorkOS Staging"),
        ("WORKOS_API_KEY", "sk_test_staging", "production API key"),
        (
            "WORKOS_REDIRECT_URI",
            "http://localhost:8000/api/v1/auth/workos/callback",
            "Diesel Bridge API callback",
        ),
        ("WORKOS_POST_LOGIN_URL", "http://localhost:5173", "Diesel Bridge app origin"),
        ("WORKOS_WEBHOOK_SECRET", "", "webhook secret"),
    ],
)
def test_production_rejects_cross_environment_configuration(
    restore_settings,
    field: str,
    value: str,
    message: str,
):
    _configure_valid_production()
    setattr(settings, field, value)

    with pytest.raises(ValueError, match=message):
        settings.validate_workos_deployment()


def test_staging_rejects_live_api_key(restore_settings):
    settings.ENVIRONMENT = "development"
    settings.WORKOS_AUTH_ENABLED = True
    settings.WORKOS_ENVIRONMENT = "staging"
    settings.WORKOS_API_KEY = "sk_live_example"
    settings.WORKOS_CLIENT_ID = "client_staging"

    with pytest.raises(ValueError, match="Staging requires a staging API key"):
        settings.validate_workos_deployment()


def test_disabled_workos_does_not_block_legacy_startup(restore_settings):
    settings.ENVIRONMENT = "production"
    settings.WORKOS_AUTH_ENABLED = False
    settings.WORKOS_API_KEY = ""
    settings.WORKOS_CLIENT_ID = ""

    settings.validate_workos_deployment()
