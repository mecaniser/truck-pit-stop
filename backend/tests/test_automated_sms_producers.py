"""Business event identity and transaction-order regression checks (no transport)."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import ast
from pathlib import Path

import pytest

from app.db.models.user import UserRole
from app.services import pending_zelle_staff_notification_service as staff
from app.tasks import notifications, mechanic_timer_maintenance
from app.api.v1.endpoints import repair_orders


@pytest.mark.asyncio
async def test_staff_fanout_normalizes_shared_phone_and_uses_staff_identity(monkeypatch):
    tenant_id = uuid4()
    users = [SimpleNamespace(id=uuid4(), role=UserRole.GARAGE_ADMIN, phone=p)
             for p in ["(414) 555-0123", "+14145550123", "4145550456"]]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: users))))
    enqueue = AsyncMock()
    monkeypatch.setattr(staff, "enqueue_automated_sms", enqueue)
    await staff.enqueue_staff_sms(db, tenant_id=tenant_id, domain_event_id="event:123",
                                  template_name="pending_zelle_staff_submit_sms", body="Test")
    calls = enqueue.await_args_list
    assert len(calls) == 2
    assert {c.kwargs["to"] for c in calls} == {"+14145550123", "+14145550456"}
    assert all("recipient_user_id" in c.kwargs and "customer_id" not in c.kwargs for c in calls)
    assert all(c.kwargs["domain_event_id"] == "event:123" for c in calls)


@pytest.mark.asyncio
async def test_generic_legacy_task_missing_identity_fails_before_opening_db(monkeypatch):
    def forbidden():
        raise AssertionError("must reject before DB or transport")
    monkeypatch.setattr(notifications, "AsyncSessionLocal", forbidden)
    with pytest.raises(ValueError, match="stable event"):
        await notifications._enqueue_notification_sms("tenant", "+14145550123", "test", "work_started_sms", domain_event_id=None)
    assert not __import__('inspect').iscoroutinefunction(notifications.send_notification_sms.run)


@pytest.mark.asyncio
async def test_completion_routes_share_identity_and_later_occurrence_is_distinct(monkeypatch):
    order = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), order_number="TEST-1", vehicle=None,
                            customer=SimpleNamespace(id=uuid4(), phone="4145550123"))
    enqueue = AsyncMock()
    monkeypatch.setattr(repair_orders, "enqueue_automated_sms", enqueue)
    monkeypatch.setattr(repair_orders, "get_tenant_display_name", AsyncMock(return_value="Test Shop"))
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for occurrence in [at, at, at.replace(day=2)]:
        await repair_orders._enqueue_order_customer_sms(None, order, "work_complete_sms", occurrence)
    keys = [c.kwargs["domain_event_id"] for c in enqueue.await_args_list]
    assert keys[0] == keys[1] and keys[1] != keys[2]


@pytest.mark.asyncio
async def test_idle_alert_enqueues_before_streak_commit_and_broadcast(monkeypatch):
    events = []
    row = dict(tenant_id=str(uuid4()), mechanic_id=str(uuid4()), streak_id=str(uuid4()),
               mechanic_name="Test Mechanic", idle_minutes=30, local_date="2026-01-01")
    async def commit(): events.append("commit")
    async def enqueue(*args, **kwargs):
        assert kwargs["domain_event_id"] == f"mechanic-idle-streak:{row['streak_id']}"
        events.append("enqueue")
    async def broadcast(**kwargs): events.append("broadcast")
    class Session:
        async def __aenter__(self): return SimpleNamespace(commit=commit)
        async def __aexit__(self, *args): pass
    monkeypatch.setattr(mechanic_timer_maintenance, "AsyncSessionLocal", Session)
    for name in ["close_sessions_crossing_midnight", "close_breaks_crossing_midnight", "close_attendance_crossing_midnight"]:
        monkeypatch.setattr(mechanic_timer_maintenance, name, AsyncMock(return_value=[]))
    monkeypatch.setattr(mechanic_timer_maintenance, "evaluate_idle_alerts", AsyncMock(return_value=[row]))
    monkeypatch.setattr(mechanic_timer_maintenance, "enqueue_staff_sms", enqueue)
    monkeypatch.setattr(mechanic_timer_maintenance, "broadcast_mechanic_idle_alert", broadcast)
    await mechanic_timer_maintenance._process_mechanic_timer_maintenance()
    assert events == ["enqueue", "commit", "broadcast"]


def test_no_automated_producer_calls_legacy_transport():
    root = Path(__file__).resolve().parents[1] / "app"
    paths = ["api/v1/endpoints/repair_orders.py", "api/v1/endpoints/quotes.py",
             "tasks/notifications.py", "tasks/invoice_reminders.py", "tasks/mechanic_timer_maintenance.py",
             "services/pending_zelle_staff_notification_service.py"]
    for path in paths:
        tree = ast.parse((root / path).read_text())
        calls = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        assert "send_sms" not in calls and "send_sms_fn" not in calls, path


@pytest.mark.asyncio
async def test_idle_staff_fallback_is_preserved_when_only_mechanic_has_phone(monkeypatch):
    mechanic = SimpleNamespace(id=uuid4(), role=UserRole.MECHANIC, phone="4145550123")
    tenant = SimpleNamespace(phone="4145550456")
    results = [SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [mechanic])),
               SimpleNamespace(scalar_one_or_none=lambda: tenant)]
    db = SimpleNamespace(execute=AsyncMock(side_effect=results))
    enqueue = AsyncMock()
    monkeypatch.setattr(staff, "enqueue_automated_sms", enqueue)
    await staff.enqueue_staff_sms(db, tenant_id=uuid4(), domain_event_id="idle:123",
                                  template_name="mechanic_idle_alert_sms", body="Test",
                                  mechanic_id=mechanic.id)
    assert enqueue.await_count == 2
    assert enqueue.await_args_list[0].kwargs["recipient_user_id"] == mechanic.id
    assert enqueue.await_args_list[1].kwargs["recipient_tenant_contact"] is True
