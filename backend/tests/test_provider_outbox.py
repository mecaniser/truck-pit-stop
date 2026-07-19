from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.notification import Notification, NotificationStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.tenant import Tenant
from app.services.provider_outbox_service import (
    EmailDelivery,
    ProviderDeliveryError,
    _deliver_email,
    enqueue_email_notification,
    process_due_provider_outbox_events,
)


async def _enqueue_test_email(factory) -> tuple[object, object]:
    async with factory() as db:
        tenant = Tenant(name="Outbox Test Garage", slug=f"outbox-{uuid4().hex}")
        db.add(tenant)
        await db.flush()
        event = await enqueue_email_notification(
            db,
            tenant_id=tenant.id,
            aggregate_type="quote",
            aggregate_id=uuid4(),
            idempotency_key=f"quote-email:{uuid4().hex}",
            recipient="customer@example.com",
            subject="Quote ready",
            body="<p>Ready</p>",
            template_name="quote_approval",
            sender_name="Outbox Test Garage",
        )
        await db.commit()
        return event.id, tenant.id


@pytest.mark.asyncio
async def test_outbox_delivers_email_after_the_request_transaction(_db_engine):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    event_id, _tenant_id = await _enqueue_test_email(factory)
    delivered = []

    async def _deliver(email):
        delivered.append(email)
        return "resend-message-123"

    result = await process_due_provider_outbox_events(
        session_factory=factory,
        deliver_email=_deliver,
    )

    assert result == {"claimed": 1, "succeeded": 1, "retried": 0, "dead": 0, "invalid": 0}
    assert len(delivered) == 1
    assert delivered[0].recipient == "customer@example.com"

    async with factory() as db:
        event = await db.get(ProviderOutboxEvent, event_id)
        notification = (
            await db.execute(
                select(Notification).where(Notification.external_id == "resend-message-123")
            )
        ).scalar_one()

    assert event.status == ProviderOutboxStatus.SUCCEEDED.value
    assert event.attempt_count == 1
    assert notification.status == NotificationStatus.SENT


@pytest.mark.asyncio
async def test_outbox_retries_transient_provider_failures(_db_engine):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    event_id, _tenant_id = await _enqueue_test_email(factory)

    async def _unavailable(_email):
        raise ProviderDeliveryError("provider unavailable", retryable=True)

    result = await process_due_provider_outbox_events(
        session_factory=factory,
        deliver_email=_unavailable,
    )

    assert result == {"claimed": 1, "succeeded": 0, "retried": 1, "dead": 0, "invalid": 0}
    async with factory() as db:
        event = await db.get(ProviderOutboxEvent, event_id)
        notification = await db.get(Notification, event.payload["notification_id"])

    assert event.status == ProviderOutboxStatus.PENDING.value
    assert event.attempt_count == 1
    assert event.available_at is not None
    assert notification.status == NotificationStatus.PENDING


@pytest.mark.asyncio
async def test_outbox_dead_letters_non_retryable_failures(_db_engine):
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    event_id, _tenant_id = await _enqueue_test_email(factory)

    async def _rejected(_email):
        raise ProviderDeliveryError("recipient rejected", retryable=False)

    result = await process_due_provider_outbox_events(
        session_factory=factory,
        deliver_email=_rejected,
    )

    assert result == {"claimed": 1, "succeeded": 0, "retried": 0, "dead": 1, "invalid": 0}
    async with factory() as db:
        event = await db.get(ProviderOutboxEvent, event_id)
        notification = await db.get(Notification, event.payload["notification_id"])

    assert event.status == ProviderOutboxStatus.DEAD.value
    assert notification.status == NotificationStatus.FAILED
    assert notification.error_message == "ProviderDeliveryError: recipient rejected"


@pytest.mark.asyncio
async def test_outbox_uses_resend_idempotency_key(monkeypatch):
    sent = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": "resend-message-456"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, json):
            sent.update(url=url, headers=headers, json=json)
            return FakeResponse()

    monkeypatch.setattr("app.services.provider_outbox_service.httpx.AsyncClient", lambda **_kwargs: FakeClient())
    monkeypatch.setattr("app.services.provider_outbox_service.settings.RESEND_API_KEY", "test-resend-key")

    response_id = await _deliver_email(
        EmailDelivery(
            event_id=uuid4(),
            lock_token="lease-token",
            notification_id=uuid4(),
            idempotency_key="quote-email-idempotency-key",
            sender_name="Outbox Test Garage",
            recipient="customer@example.com",
            subject="Quote ready",
            body="<p>Ready</p>",
        )
    )

    assert response_id == "resend-message-456"
    assert sent["headers"]["Idempotency-Key"] == "quote-email-idempotency-key"
    assert sent["headers"]["User-Agent"] == "truck-pit-stop-provider-outbox/1.0"
