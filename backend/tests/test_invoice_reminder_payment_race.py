"""A payment completed after discovery must suppress unpaid reminders."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.models.invoice import InvoiceStatus
from app.tasks import invoice_reminders


@pytest.mark.asyncio
@pytest.mark.parametrize("new_status", [InvoiceStatus.PAID, InvoiceStatus.CANCELLED])
async def test_reminder_rechecks_invoice_after_financial_boundary(monkeypatch, new_status):
    invoice = SimpleNamespace(tenant_id=uuid4(), status=InvoiceStatus.SENT)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [invoice]))),
        commit=AsyncMock(),
    )

    class Context:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    async def acquire_and_refresh(db, tenant_id):
        assert db is session and tenant_id == invoice.tenant_id
        # Competing payment/lifecycle writer commits after discovery; lock helper
        # refreshes this identity before the task is allowed to use it.
        invoice.status = new_status

    send_sms = AsyncMock(side_effect=AssertionError("must not send unpaid SMS"))
    send_email = AsyncMock(side_effect=AssertionError("must not send unpaid email"))
    monkeypatch.setattr(invoice_reminders, "AsyncSessionLocal", Context)
    monkeypatch.setattr("app.services.financial_transaction_lock.lock_tenant_financials", acquire_and_refresh)
    monkeypatch.setattr(invoice_reminders, "send_sms", send_sms)
    monkeypatch.setattr(invoice_reminders, "send_email", send_email)
    assert await invoice_reminders._process_invoice_reminders() == 0
    assert invoice.status == new_status
    send_sms.assert_not_awaited()
    send_email.assert_not_awaited()
