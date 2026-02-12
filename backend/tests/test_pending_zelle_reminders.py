from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

pytest.importorskip("aiosqlite")

from app.tasks import pending_zelle_reminders
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant


class _ScalarList:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarList(self._values)


class _FakeAsyncSession:
    def __init__(self, invoices: list[Invoice]):
        self._invoices = invoices
        self.committed = False

    async def execute(self, _statement):
        return _ScalarResult(self._invoices)

    async def commit(self):
        self.committed = True


class _FakeSessionContext:
    def __init__(self, session: _FakeAsyncSession):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_pending_invoice(*, elapsed_hours: int, reminder_count: int):
    tenant_id = uuid4()
    customer_id = uuid4()
    order_id = uuid4()
    invoice_id = uuid4()
    vehicle_id = uuid4()

    tenant = Tenant(id=tenant_id, name="Truck Pit Stop", slug=f"tenant-{tenant_id.hex[:8]}")
    customer = Customer(
        id=customer_id,
        tenant_id=tenant_id,
        first_name="Alex",
        last_name="Driver",
        email="alex@example.com",
    )
    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number="RO-3301",
        status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0.00"),
        total_labor_cost=Decimal("120.00"),
        total_cost=Decimal("120.00"),
    )
    invoice = Invoice(
        id=invoice_id,
        tenant_id=tenant_id,
        repair_order_id=order_id,
        invoice_number="INV-3301",
        status=InvoiceStatus.SENT,
        subtotal=Decimal("120.00"),
        shop_supplies_amount=Decimal("0.00"),
        service_fee_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("120.00"),
        zelle_pending_submitted_at=datetime.now(timezone.utc) - timedelta(hours=elapsed_hours),
        zelle_pending_reminder_count=reminder_count,
    )

    order.customer = customer
    invoice.repair_order = order
    invoice.tenant = tenant
    return invoice


@pytest.mark.asyncio
async def test_pending_zelle_reminders_sends_first_stage_after_24h(monkeypatch):
    invoice = _build_pending_invoice(elapsed_hours=25, reminder_count=0)
    fake_session = _FakeAsyncSession([invoice])
    alert_calls: list[dict] = []

    monkeypatch.setattr(
        pending_zelle_reminders,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )

    async def _capture_alert(**kwargs):
        alert_calls.append(kwargs)

    monkeypatch.setattr(
        pending_zelle_reminders,
        "send_pending_zelle_reminder_alert",
        _capture_alert,
    )

    sent = await pending_zelle_reminders._process_pending_zelle_reminders()

    assert sent == 1
    assert fake_session.committed is True
    assert len(alert_calls) == 1
    assert alert_calls[0]["invoice_number"] == invoice.invoice_number
    assert alert_calls[0]["reminder_stage_hours"] == 24
    assert invoice.zelle_pending_reminder_count == 1
    assert invoice.zelle_pending_last_reminder_at is not None


@pytest.mark.asyncio
async def test_pending_zelle_reminders_sends_second_stage_after_48h(monkeypatch):
    invoice = _build_pending_invoice(elapsed_hours=49, reminder_count=1)
    fake_session = _FakeAsyncSession([invoice])
    alert_calls: list[dict] = []

    monkeypatch.setattr(
        pending_zelle_reminders,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )

    async def _capture_alert(**kwargs):
        alert_calls.append(kwargs)

    monkeypatch.setattr(
        pending_zelle_reminders,
        "send_pending_zelle_reminder_alert",
        _capture_alert,
    )

    sent = await pending_zelle_reminders._process_pending_zelle_reminders()

    assert sent == 1
    assert fake_session.committed is True
    assert len(alert_calls) == 1
    assert alert_calls[0]["reminder_stage_hours"] == 48
    assert invoice.zelle_pending_reminder_count == 2
    assert invoice.zelle_pending_last_reminder_at is not None


@pytest.mark.asyncio
async def test_pending_zelle_reminders_skips_not_due_and_already_reminded(monkeypatch):
    not_due = _build_pending_invoice(elapsed_hours=10, reminder_count=0)
    already_reminded_for_stage = _build_pending_invoice(elapsed_hours=30, reminder_count=1)
    fake_session = _FakeAsyncSession([not_due, already_reminded_for_stage])
    alert_calls: list[dict] = []

    monkeypatch.setattr(
        pending_zelle_reminders,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )

    async def _capture_alert(**kwargs):
        alert_calls.append(kwargs)

    monkeypatch.setattr(
        pending_zelle_reminders,
        "send_pending_zelle_reminder_alert",
        _capture_alert,
    )

    sent = await pending_zelle_reminders._process_pending_zelle_reminders()

    assert sent == 0
    assert fake_session.committed is True
    assert len(alert_calls) == 0
    assert not_due.zelle_pending_reminder_count == 0
    assert already_reminded_for_stage.zelle_pending_reminder_count == 1
    assert not_due.zelle_pending_last_reminder_at is None
    assert already_reminded_for_stage.zelle_pending_last_reminder_at is None
