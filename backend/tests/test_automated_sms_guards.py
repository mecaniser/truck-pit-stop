"""Automated entrypoints cannot silently fall back to unprotected provider calls."""
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from app.services import messaging_service, twilio_service
from app.services.automated_sms_service import enqueue_automated_sms


@pytest.fixture(autouse=True)
def durable_automation_enabled(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'SMS_AUTOMATION_OUTBOX_ENABLED', True)


@pytest.mark.asyncio
async def test_legacy_automated_sender_requires_event_before_db_or_provider():
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await twilio_service.send_sms(db, '00000000-0000-0000-0000-000000000001', '+15005550888', 'Synthetic')
    assert exc.value.detail['code'] == 'missing_event_identity'
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_low_level_automated_provider_bypass_rejected(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(messaging_service, '_get_twilio_client', lambda: pytest.fail('Provider forbidden'))
    with pytest.raises(ValueError, match='stable domain event'):
        await messaging_service.send_sms_with_tracking(db, '00000000-0000-0000-0000-000000000001', '+15005550888', 'Synthetic')
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_manual_path_preserved(monkeypatch):
    notification = object()
    sender = AsyncMock(return_value=(notification, None, None))
    monkeypatch.setattr(twilio_service, 'send_sms_with_tracking', sender)
    assert await twilio_service.send_sms(AsyncMock(), 'tenant', 'to', 'body', source='manual') is notification
    assert sender.await_args.kwargs['source'] == 'manual'


@pytest.mark.asyncio
@pytest.mark.parametrize('fields', [{}, {'customer_id': 'one', 'recipient_user_id': 'two'}])
async def test_exactly_one_identity_required(fields):
    with pytest.raises(HTTPException) as exc:
        await enqueue_automated_sms(AsyncMock(), tenant_id='tenant', domain_event_id='event', template_name='work_started_sms', to='phone', body='body', **fields)
    assert exc.value.detail['code'] == 'identity_unverified'
