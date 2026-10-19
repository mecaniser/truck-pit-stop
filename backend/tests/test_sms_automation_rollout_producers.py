"""Rollout compatibility checks; mock sessions/providers, no external mutation."""
import ast
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import settings
from app.api.v1.endpoints import repair_orders
from app.services import pending_zelle_staff_notification_service as staff, twilio_service
from app.tasks import invoice_reminders


@pytest.mark.asyncio
async def test_disabled_customer_and_staff_enqueue_do_not_open_database(monkeypatch):
    monkeypatch.setattr(settings, "SMS_AUTOMATION_OUTBOX_ENABLED", False)
    db = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("no database I/O")))
    enqueue = AsyncMock(side_effect=AssertionError("no durable intent"))
    monkeypatch.setattr(repair_orders, "enqueue_automated_sms", enqueue)
    monkeypatch.setattr(staff, "enqueue_automated_sms", enqueue)
    await repair_orders._enqueue_order_customer_sms(db, None, "work_complete_sms", None)
    await staff.enqueue_staff_sms(db, tenant_id=uuid4(), domain_event_id="event", template_name="sms", body="test")
    db.execute.assert_not_awaited()
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_zelle_only_postcommit_email_phase_uses_legacy_sms_when_disabled(monkeypatch, enabled):
    monkeypatch.setattr(settings, "SMS_AUTOMATION_OUTBOX_ENABLED", enabled)
    legacy, durable, email = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(twilio_service, "send_sms", legacy)
    monkeypatch.setattr(staff, "enqueue_staff_sms", durable)
    monkeypatch.setattr(staff, "send_email", email)
    kwargs = dict(tenant_id=uuid4(), emails={"test@example.invalid"}, phones={"+17045550123"},
                  subject="test", email_body="test", sms_body="test", email_template_name="email",
                  sms_template_name="sms", domain_event_id="event")
    await staff._send_staff_alert(None, **kwargs, phase="enqueue")
    legacy.assert_not_awaited()
    await staff._send_staff_alert(None, **kwargs, phase="email")
    assert legacy.await_count == (0 if enabled else 1)
    email.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("provider_error", [False, True])
@pytest.mark.parametrize("with_email", [False, True])
async def test_invoice_rollout_preserves_lock_and_commit_order(monkeypatch, enabled, provider_error, with_email):
    from app.services import financial_transaction_lock
    monkeypatch.setattr(settings, "SMS_AUTOMATION_OUTBOX_ENABLED", enabled)
    events = []
    invoice = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), status=invoice_reminders.InvoiceStatus.SENT,
        deleted_at=None, voided_at=None, zelle_pending_submitted_at=None, reminder_count=0,
        last_reminder_sent_at=None, due_date=datetime.now(timezone.utc), invoice_number="TEST", total_amount=10,
        tenant=SimpleNamespace(name="Test Shop", phone=None, email=None), repair_order=SimpleNamespace(deleted_at=None,
        status=SimpleNamespace(value="completed"), vehicle=None,
        customer=SimpleNamespace(id=uuid4(), first_name="Test", phone="+17045550123",
                                 email="test@example.invalid" if with_email else None)))
    async def lock(*args): events.append("lock")
    async def commit(): events.append("commit")
    async def legacy(db, *args, **kwargs):
        assert db is notification_db
        events.append("legacy")
        if provider_error: raise RuntimeError("simulated provider error")
    async def email(db, *args, **kwargs):
        assert db is notification_db
        events.append("email")
    async def durable(db, **kwargs):
        assert db is domain_db
        events.append("durable")
    domain_db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [invoice]))), commit=commit)
    notification_db = object()
    class Session:
        def __init__(self): self.db = domain_db if not events else notification_db
        async def __aenter__(self): return self.db
        async def __aexit__(self, *args): pass
    monkeypatch.setattr(invoice_reminders, "AsyncSessionLocal", Session)
    monkeypatch.setattr(financial_transaction_lock, "lock_tenant_financials", lock)
    monkeypatch.setattr(invoice_reminders, "send_email", email)
    monkeypatch.setattr(invoice_reminders, "generate_invoice_access_link", AsyncMock(return_value="https://example.invalid/test"))
    monkeypatch.setattr(invoice_reminders, "send_sms", legacy)
    monkeypatch.setattr(invoice_reminders, "enqueue_automated_sms", durable)
    assert await invoice_reminders._process_invoice_reminders() == 1
    expected = ["lock", "durable", "commit"] if enabled else ["lock", "legacy"]
    if with_email: expected.append("email")
    if not enabled: expected.append("commit")
    assert events == expected
    assert invoice.reminder_count == 1


@pytest.mark.parametrize("path,names", [
    ("api/v1/endpoints/repair_orders.py", ["assign_mechanic", "start_work", "complete_work", "admin_complete_unassigned_work", "approve_completion"]),
    ("api/v1/endpoints/quotes.py", ["send_quote_to_customer", "decline_quote", "decline_quote_by_token"]),
])
def test_endpoint_legacy_delivery_occurs_after_domain_commit(path, names):
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app" / path).read_text())
    for name in names:
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        commits = [n.lineno for n in calls if isinstance(n.func, ast.Attribute) and n.func.attr == "commit"]
        legacy = [n for n in calls if isinstance(n.func, ast.Name) and n.func.id == "send_sms"]
        assert legacy, name
        assert all(call.lineno > min(commits) for call in legacy), name
        for call in legacy:
            guards = [n for n in ast.walk(fn) if isinstance(n, ast.If) and n.lineno < call.lineno <= n.end_lineno]
            assert any(ast.unparse(n.test) == "not settings.SMS_AUTOMATION_OUTBOX_ENABLED" for n in guards), name
