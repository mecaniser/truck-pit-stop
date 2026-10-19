from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.invoices import auto_create_invoice_for_order, create_invoice, update_invoice, void_invoice, resend_invoice
from app.api.v1.endpoints.invoice_settlements import invoice_for_principal
from app.services.invoice_settlement_service import SettlementDomainError
from app.db.models.user import UserRole
from app.api.v1.endpoints import quickbooks
from app.db.models.repair_order import RepairOrderStatus


@pytest.mark.asyncio
async def test_imported_order_cannot_auto_create_invoice_even_if_no_invoice_exists():
    db = SimpleNamespace(execute=AsyncMock())
    order = SimpleNamespace(source="easy_truck_shop_import", id=uuid4())

    with pytest.raises(HTTPException) as exc:
        await auto_create_invoice_for_order(db, order, SimpleNamespace())

    assert exc.value.status_code == 409
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_imported_order_cannot_manually_create_invoice_even_if_completed():
    tenant_id = uuid4()
    order = SimpleNamespace(
        id=uuid4(), tenant_id=tenant_id, source="easy_truck_shop_import",
        status=RepairOrderStatus.COMPLETED,
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: order)))
    actor = SimpleNamespace(tenant_id=tenant_id, role="garage_owner")

    with pytest.raises(HTTPException) as exc:
        await create_invoice(SimpleNamespace(repair_order_id=order.id), db, actor)

    assert exc.value.status_code == 409
    assert db.execute.await_count == 1  # order lookup only; no invoice, outbox or provider work


@pytest.mark.asyncio
async def test_imported_invoice_cannot_enter_native_settlement_or_payment_routes():
    tenant_id = uuid4()
    invoice = SimpleNamespace(
        id=uuid4(), tenant_id=tenant_id, source="easy_truck_shop_import",
        repair_order=SimpleNamespace(source="easy_truck_shop_import", deleted_at=None),
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: invoice)))
    actor = SimpleNamespace(tenant_id=tenant_id, role=UserRole.GARAGE_OWNER)

    with pytest.raises(SettlementDomainError) as exc:
        await invoice_for_principal(db, invoice.id, actor)

    assert exc.value.status_code == 409
    assert db.execute.await_count == 1  # no tenant/provider/settlement read or write


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["update", "void", "resend"])
async def test_imported_invoice_cannot_be_changed_voided_or_resent(monkeypatch, action):
    tenant_id = uuid4()
    order = SimpleNamespace(source="easy_truck_shop_import")
    invoice = SimpleNamespace(id=uuid4(), tenant_id=tenant_id, source="easy_truck_shop_import", repair_order=order)
    row = SimpleNamespace(
        scalar_one_or_none=lambda: invoice,
        one_or_none=lambda: (invoice, order, SimpleNamespace(), SimpleNamespace()),
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=row), scalar=AsyncMock(return_value=None))
    actor = SimpleNamespace(tenant_id=tenant_id, role=UserRole.GARAGE_OWNER)
    lock = AsyncMock()
    monkeypatch.setattr("app.services.financial_transaction_lock.lock_tenant_financials", lock)

    with pytest.raises(HTTPException) as exc:
        if action == "update":
            await update_invoice(invoice.id, SimpleNamespace(due_date=None, notes=None), db, actor)
        elif action == "void":
            await void_invoice(invoice.id, SimpleNamespace(reason="Source owned"), db, actor)
        else:
            await resend_invoice(invoice.id, SimpleNamespace(custom_email=None), db, actor)

    assert exc.value.status_code == 409
    assert db.execute.await_count == 1
    assert db.scalar.await_count == (1 if action == "void" else 0)


@pytest.mark.asyncio
async def test_imported_invoice_cannot_enter_quickbooks_export_or_charge(monkeypatch):
    tenant_id = uuid4()
    order = SimpleNamespace(source="easy_truck_shop_import")
    invoice = SimpleNamespace(id=uuid4(), tenant_id=tenant_id, source="easy_truck_shop_import", repair_order=order)
    lock = AsyncMock()
    monkeypatch.setattr("app.services.financial_transaction_lock.lock_tenant_financials", lock)
    monkeypatch.setattr(quickbooks, "_require_quickbooks_admin", lambda _: None)
    monkeypatch.setattr(quickbooks, "_invoice_accounting_context", AsyncMock(return_value=(invoice, order, SimpleNamespace())))
    monkeypatch.setattr(quickbooks, "_require_quickbooks_payments_approved_release", lambda: None)
    monkeypatch.setattr(quickbooks, "quickbooks_payments_enabled_for_tenant", lambda _: True)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: invoice)))

    with pytest.raises(HTTPException) as export_exc:
        await quickbooks.sync_quickbooks_invoice_now(invoice.id, db, SimpleNamespace(tenant_id=tenant_id, role=UserRole.GARAGE_OWNER))
    assert export_exc.value.status_code == 409
    db.execute.assert_not_awaited()

    with pytest.raises(HTTPException) as charge_exc:
        await quickbooks.charge_quickbooks_invoice(
            SimpleNamespace(invoice_id=invoice.id, token="unused-token", idempotency_key="unused-idempotency"),
            db,
            SimpleNamespace(tenant_id=tenant_id, role=UserRole.CUSTOMER, customer_id=uuid4()),
        )
    assert charge_exc.value.status_code == 409
    assert db.execute.await_count == 1
