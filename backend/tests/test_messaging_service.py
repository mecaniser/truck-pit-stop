from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.models.customer import Customer
from app.db.models.sms_message import SMSDeliveryStatus
from app.services import messaging_service


def test_apply_opt_keyword_sets_opt_out():
    customer = Customer(
        tenant_id=uuid4(),
        first_name="Test",
        last_name="Customer",
        email="test@example.com",
    )

    messaging_service._apply_opt_keyword(customer, "STOP")

    assert customer.sms_opt_out is True
    assert customer.sms_opt_out_source == "inbound_keyword"
    assert customer.sms_opted_out_at is not None


def test_apply_opt_keyword_clears_opt_out_on_start():
    customer = Customer(
        tenant_id=uuid4(),
        first_name="Test",
        last_name="Customer",
        email="test@example.com",
        sms_opt_out=True,
        sms_opt_out_source="inbound_keyword",
    )

    messaging_service._apply_opt_keyword(customer, "START")

    assert customer.sms_opt_out is False
    assert customer.sms_opt_out_source == "inbound_keyword"
    assert customer.sms_opted_out_at is None


@pytest.mark.parametrize(
    ("twilio_status", "expected"),
    [
        ("queued", SMSDeliveryStatus.QUEUED),
        ("sent", SMSDeliveryStatus.SENT),
        ("delivered", SMSDeliveryStatus.DELIVERED),
        ("undelivered", SMSDeliveryStatus.UNDELIVERED),
        ("failed", SMSDeliveryStatus.FAILED),
        ("unknown-status", SMSDeliveryStatus.PENDING),
    ],
)
def test_twilio_status_mapping(twilio_status: str, expected: SMSDeliveryStatus):
    assert messaging_service._twilio_status_to_delivery_status(twilio_status) == expected


class _FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, _seconds: int) -> bool:
        return True


@pytest.mark.asyncio
async def test_enforce_tenant_send_rate_limit(monkeypatch):
    fake_redis = _FakeRedis()

    async def _fake_get_redis():
        return fake_redis

    monkeypatch.setattr(messaging_service, "get_redis", _fake_get_redis)

    tenant_id = str(uuid4())
    allowed = []
    for _ in range(31):
        allowed.append(await messaging_service.enforce_tenant_send_rate_limit(tenant_id, limit=30, window_seconds=60))

    assert all(allowed[:30])
    assert allowed[30] is False


def test_validate_twilio_signature_without_token(monkeypatch):
    monkeypatch.setattr(messaging_service.settings, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(messaging_service.settings, "ENVIRONMENT", "development")
    assert messaging_service.validate_twilio_signature("http://localhost/test", {"a": "1"}, None) is True

    monkeypatch.setattr(messaging_service.settings, "ENVIRONMENT", "production")
    assert messaging_service.validate_twilio_signature("http://localhost/test", {"a": "1"}, None) is False


def test_normalize_for_twilio_us_10_digit_with_plus_prefix():
    assert messaging_service._normalize_for_twilio("+7047050486") == "+17047050486"


def test_normalize_for_twilio_us_10_digit_without_prefix():
    assert messaging_service._normalize_for_twilio("7047050486") == "+17047050486"


def test_normalize_for_twilio_keeps_valid_international_e164():
    assert messaging_service._normalize_for_twilio("+447700900123") == "+447700900123"


def test_status_callback_url_skips_localhost(monkeypatch):
    monkeypatch.setattr(messaging_service.settings, "PUBLIC_API_BASE_URL", "http://localhost:8000")
    assert messaging_service._status_callback_url() is None

    monkeypatch.setattr(messaging_service.settings, "PUBLIC_API_BASE_URL", "http://127.0.0.1:8000")
    assert messaging_service._status_callback_url() is None


def test_status_callback_url_returns_public_url(monkeypatch):
    monkeypatch.setattr(messaging_service.settings, "PUBLIC_API_BASE_URL", "https://api.example.com")
    assert (
        messaging_service._status_callback_url()
        == "https://api.example.com/api/v1/webhooks/twilio/sms/status"
    )


def test_phone_match_candidates_expands_us_variants():
    assert messaging_service._phone_match_candidates("+1 (704) 705-0486") == ["17047050486", "7047050486"]
    assert messaging_service._phone_match_candidates("7047050486") == ["7047050486", "17047050486"]


def test_canonical_customer_phone_prefers_10_digit_us():
    assert messaging_service._canonical_customer_phone("+17047050486") == "7047050486"
    assert messaging_service._canonical_customer_phone("7047050486") == "7047050486"
