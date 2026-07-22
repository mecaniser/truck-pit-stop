from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import invoices
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, order: RepairOrder, tenant: Tenant):
        self.order = order
        self.tenant = tenant
        self.execute_calls = 0
        self.added: list[object] = []
        self.commit_count = 0

    async def execute(self, statement):
        self.execute_calls += 1
        entity = statement.column_descriptions[0].get("entity")

        if self.execute_calls == 1:
            assert entity is RepairOrder
            return _ScalarResult(self.order)
        if self.execute_calls == 2:
            # Existing invoice check
            from app.db.models.invoice import Invoice
            assert entity is Invoice
            return _ScalarResult(None)
        if self.execute_calls == 3:
            assert entity is Tenant
            return _ScalarResult(self.tenant)
        raise AssertionError(f"Unexpected query call #{self.execute_calls} for entity {entity}")

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _obj):
        # Mimic DB-populated defaults expected by response model validation.
        if getattr(_obj, "id", None) is None:
            _obj.id = uuid4()
        if getattr(_obj, "created_at", None) is None:
            _obj.created_at = datetime.now(timezone.utc)
        if getattr(_obj, "updated_at", None) is None:
            _obj.updated_at = datetime.now(timezone.utc)
        if getattr(_obj, "zelle_pending_reminder_count", None) is None:
            _obj.zelle_pending_reminder_count = 0
        if getattr(_obj, "reminder_count", None) is None:
            _obj.reminder_count = 0
        return None


def _build_context():
    tenant_id = uuid4()
    order_id = uuid4()
    customer_id = uuid4()
    vehicle_id = uuid4()
    user_id = uuid4()

    order = RepairOrder(
        id=order_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        order_number="RO-2001",
        status=RepairOrderStatus.COMPLETED,
        is_internal=False,
        is_warranty_repair=False,
        is_pm=False,
        total_parts_cost=Decimal("100.00"),
        total_labor_cost=Decimal("50.00"),
        total_cost=Decimal("150.00"),
    )
    tenant = Tenant(
        id=tenant_id,
        name="Test Garage",
        sales_tax_rate=Decimal("0.000"),
        shop_supplies_rate=Decimal("0.000"),
        service_fee_rate=Decimal("0.000"),
    )
    user = User(
        id=user_id,
        email="owner@example.com",
        hashed_password="hashed-password",
        first_name="Owner",
        last_name="User",
        role=UserRole.GARAGE_OWNER,
        tenant_id=tenant_id,
        is_active=True,
        is_verified=True,
    )
    return order, tenant, user


@pytest.mark.asyncio
async def test_create_invoice_applies_discount_amount(monkeypatch):
    order, tenant, user = _build_context()
    fake_db = _FakeAsyncSession(order=order, tenant=tenant)

    async def _fake_create_with_retry(*, db, create_fn, generate_number_fn, entity_name, commit=True):
        _ = db
        _ = generate_number_fn
        _ = entity_name
        _ = commit
        return await create_fn("INV-9001")

    async def _noop_async(**_kwargs):
        return None

    async def _no_email_queue(*_args, **_kwargs):
        return False

    async def _no_line_items(*_args, **_kwargs):
        return [], []

    monkeypatch.setattr("app.core.unique_id.create_with_retry", _fake_create_with_retry)
    monkeypatch.setattr(invoices, "broadcast_invoice_created", _noop_async)
    monkeypatch.setattr(invoices, "broadcast_repair_order_update", _noop_async)
    monkeypatch.setattr(invoices, "send_email", _noop_async)
    monkeypatch.setattr(invoices, "enqueue_invoice_created_email", _no_email_queue)
    monkeypatch.setattr(invoices, "_load_line_items", _no_line_items)

    response = await invoices.create_invoice(
        invoices.InvoiceCreate(
            repair_order_id=order.id,
            due_date=date.today(),
            discount_amount=Decimal("10.00"),
        ),
        db=fake_db,
        current_user=user,
    )

    assert response.discount_amount == Decimal("10.00")
    assert response.total_amount == Decimal("140.00")
    assert order.status == RepairOrderStatus.INVOICED
    assert fake_db.commit_count == 1


@pytest.mark.asyncio
async def test_create_invoice_rejects_discount_above_total(monkeypatch):
    order, tenant, user = _build_context()
    fake_db = _FakeAsyncSession(order=order, tenant=tenant)

    with pytest.raises(HTTPException) as exc:
        await invoices.create_invoice(
            invoices.InvoiceCreate(
                repair_order_id=order.id,
                due_date=date.today(),
                discount_amount=Decimal("151.00"),
            ),
            db=fake_db,
            current_user=user,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "discount_amount cannot exceed invoice total"
