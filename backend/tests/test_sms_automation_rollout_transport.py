"""Rollout-off compatibility boundaries, using mocked transport only."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from app.core.config import settings
from app.services import twilio_service, automated_sms_service
from app.tasks import notifications

@pytest.mark.asyncio
async def test_legacy_wrapper_keeps_immediate_transport_without_event_identity(monkeypatch):
    monkeypatch.setattr(settings, 'SMS_AUTOMATION_OUTBOX_ENABLED', False)
    notice = object()
    sender = AsyncMock(return_value=(notice, None, None))
    monkeypatch.setattr(twilio_service, 'send_sms_with_tracking', sender)
    enqueue = AsyncMock(side_effect=AssertionError('No queued intent when rollout is off'))
    monkeypatch.setattr(automated_sms_service, 'enqueue_automated_sms', enqueue)
    assert await twilio_service.send_sms(object(), 'tenant', 'synthetic', 'body') is notice
    sender.assert_awaited_once()
    enqueue.assert_not_awaited()

@pytest.mark.asyncio
async def test_old_notification_task_payload_works_when_rollout_off(monkeypatch):
    monkeypatch.setattr(settings, 'SMS_AUTOMATION_OUTBOX_ENABLED', False)
    db = SimpleNamespace(commit=AsyncMock())
    @asynccontextmanager
    async def session():
        yield db
    monkeypatch.setattr(notifications, 'AsyncSessionLocal', session)
    notice = SimpleNamespace(id=uuid4(), status=SimpleNamespace(value='sent'))
    sender = AsyncMock(return_value=notice)
    monkeypatch.setattr(notifications, 'send_sms', sender)
    enqueue = AsyncMock()
    monkeypatch.setattr(notifications, 'enqueue_automated_sms', enqueue)
    result = await notifications._enqueue_notification_sms('tenant', 'synthetic', 'body', None, domain_event_id=None)
    assert result == {'notification_id': str(notice.id), 'status': 'sent'}
    sender.assert_awaited_once()
    enqueue.assert_not_awaited()
