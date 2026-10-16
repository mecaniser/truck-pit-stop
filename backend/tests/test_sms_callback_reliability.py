"""No network or database access: callback ordering and webhook acknowledgement contract."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql

from app.api.v1.endpoints import twilio_webhooks
from app.db.models.sms_message import SMSDeliveryStatus as S, SMSMessageDirection, SMSMessageSource
from app.db.models.notification import NotificationStatus
from app.services import messaging_service


class FakeDB:
    def __init__(self, *rows, commit_error=None):
        self.rows = list(rows)
        self.queries = []
        self.commit = AsyncMock(side_effect=commit_error)
        self.rollback = AsyncMock()
        self.refresh = AsyncMock()

    async def execute(self, query):
        self.queries.append(query)
        row = self.rows.pop(0)
        return SimpleNamespace(scalar_one_or_none=lambda: row, scalars=lambda: SimpleNamespace(all=lambda: row))


def message(status):
    return SimpleNamespace(
        id=uuid4(), tenant_id=uuid4(), customer_id=uuid4(), thread_id=uuid4(),
        direction=SMSMessageDirection.OUTBOUND, source=SMSMessageSource.MANUAL,
        body="fixture", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        delivery_status=status, sent_at=None, delivered_at=None, failed_at=None,
        error_code=None, error_message=None,
    )


@pytest.fixture(autouse=True)
def block_external(monkeypatch):
    monkeypatch.setattr(messaging_service, "broadcast_sms_message_event", AsyncMock())
    monkeypatch.setattr(messaging_service, "_get_twilio_client", lambda: pytest.fail("No provider calls permitted"))


@pytest.mark.asyncio
@pytest.mark.parametrize("initial", list(S))
@pytest.mark.parametrize("incoming", ["queued", "sending", "sent", "delivered", "undelivered", "failed", "canceled"])
async def test_transition_matrix_and_atomic_notification(initial, incoming):
    sms = message(initial)
    prior_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sms.sent_at = sms.delivered_at = sms.failed_at = prior_time
    notification = SimpleNamespace(status=NotificationStatus.PENDING, delivered_at=prior_time, error_message=None)
    target = messaging_service._twilio_status_to_delivery_status(incoming)
    allowed = {
        S.PENDING: {S.QUEUED, S.SENT, S.DELIVERED, S.UNDELIVERED, S.FAILED},
        S.QUEUED: {S.SENT, S.DELIVERED, S.UNDELIVERED, S.FAILED},
        S.SENT: {S.DELIVERED, S.UNDELIVERED, S.FAILED},
    }
    advances = target in allowed.get(initial, set())
    db = FakeDB(sms, *([notification] if advances else []))
    await messaging_service.process_twilio_status_callback(db, message_sid="SMfixture", message_status=incoming)
    assert sms.delivery_status == (target if advances else initial)
    assert notification.status == (messaging_service._delivery_status_to_notification_status(target) if advances else NotificationStatus.PENDING)
    if not advances:
        assert sms.delivered_at == sms.failed_at == prior_time
        messaging_service.broadcast_sms_message_event.assert_not_awaited()
    else:
        assert "notifications.tenant_id" in str(db.queries[1])
    assert "FOR UPDATE" in str(db.queries[0].compile(dialect=postgresql.dialect()))
    assert db.queries[0].get_execution_options()["populate_existing"] is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("incoming", [None, "", "future-status", "receiving", "received", "pending"])
async def test_unknown_callback_is_noop(incoming):
    sms = message(S.DELIVERED)
    db = FakeDB(sms)
    assert await messaging_service.process_twilio_status_callback(db, message_sid="SMfixture", message_status=incoming) is sms
    assert sms.delivery_status == S.DELIVERED
    assert len(db.queries) == 1
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_opt_out_survives_terminal_conflict_and_duplicate_preserves_timestamp():
    sms = message(S.DELIVERED)
    customer = SimpleNamespace(sms_opt_out=False, sms_opted_out_at=None, sms_opt_out_source=None)
    for _ in range(2):
        db = FakeDB(sms, customer)
        await messaging_service.process_twilio_status_callback(db, message_sid="SMfixture", message_status="failed", error_code="21610")
        assert sms.delivery_status == S.DELIVERED
        assert customer.sms_opt_out is True
        assert "customers.tenant_id" in str(db.queries[1])
        if _ == 0:
            timestamp = customer.sms_opted_out_at
        else:
            assert customer.sms_opted_out_at == timestamp
    messaging_service.broadcast_sms_message_event.assert_not_awaited()


async def post_callback(monkeypatch, db, data, valid=True):
    monkeypatch.setattr(twilio_webhooks, "_has_valid_signature", lambda *args: valid)
    app = FastAPI()
    app.include_router(twilio_webhooks.router)
    app.dependency_overrides[twilio_webhooks.get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        return await client.post("/sms/status", data=data)


@pytest.mark.asyncio
@pytest.mark.parametrize("data,rows,expected", [
    ({"MessageStatus": "delivered"}, [], 400),
    ({"MessageSid": "SMmissing", "MessageStatus": "delivered"}, [None, []], 503),
    ({"MessageSid": "SMfixture", "MessageStatus": "future-status"}, [message(S.SENT)], 200),
    ({"MessageSid": "SMmissing", "MessageStatus": "future-status"}, [None, []], 503),
])
async def test_webhook_acknowledgement(monkeypatch, data, rows, expected):
    db = FakeDB(*rows)
    response = await post_callback(monkeypatch, db, data)
    assert response.status_code == expected
    assert db.rollback.await_count == (1 if expected != 200 else 0)
    if expected == 503:
        assert response.headers["retry-after"] == "5"


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_and_returns_retryable_failure(monkeypatch):
    db = FakeDB(message(S.SENT), None, commit_error=RuntimeError("fixture persistence failure"))
    response = await post_callback(monkeypatch, db, {"MessageSid": "SMfixture", "MessageStatus": "delivered"})
    assert response.status_code == 503
    db.rollback.assert_awaited_once()
    messaging_service.broadcast_sms_message_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_signature_does_not_touch_database(monkeypatch):
    db = FakeDB()
    response = await post_callback(monkeypatch, db, {"MessageSid": "SMfixture", "MessageStatus": "delivered"}, valid=False)
    assert response.status_code == 400
    assert db.queries == []
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_status,code", [("delivered", ""), ("failed", "21610")])
async def test_notification_only_callback_acknowledged_without_mutation(monkeypatch, provider_status, code):
    notification = SimpleNamespace(status=NotificationStatus.SENT, delivered_at=None, error_message=None)
    before = vars(notification).copy()
    db = FakeDB(None, [notification])
    response = await post_callback(monkeypatch, db, {
        "MessageSid": "SMlegacy", "MessageStatus": provider_status, "ErrorCode": code,
    })
    assert response.status_code == 200
    assert vars(notification) == before
    assert len(db.queries) == 2
    sql = str(db.queries[1].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "notifications.type = 'sms'" in sql
    assert "LIMIT 2" in sql
    db.commit.assert_awaited_once()
    messaging_service.broadcast_sms_message_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_notification_sid_rejected_without_mutation(monkeypatch):
    rows = [SimpleNamespace(status=NotificationStatus.SENT) for _ in range(2)]
    db = FakeDB(None, rows)
    response = await post_callback(monkeypatch, db, {"MessageSid": "SMambiguous", "MessageStatus": "delivered"})
    assert response.status_code == 503
    assert all(row.status == NotificationStatus.SENT for row in rows)
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
