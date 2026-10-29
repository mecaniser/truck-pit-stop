from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from app.api.v1.endpoints.dashboard import (
    get_dashboard_daily_workset,
    get_dashboard_daily_workset_value_summary,
)
from app.api.v1.endpoints.invoice_settlements import confirm_invoice_cash
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.user import User
from app.schemas.invoice_settlement import CashConfirmationCreate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.test_db048_reviewed_test_cash import reviewed


@pytest.mark.asyncio
async def test_reviewed_cash_commits_in_fresh_request_and_refreshes_closeout(db_session, monkeypatch):
    ctx, _, _, _, _ = await reviewed(db_session, monkeypatch)
    invoice_id, owner_id, order_id = ctx[3].id, ctx[1].id, ctx[3].repair_order_id
    version = ctx[4].version
    ctx[3].repair_order.status = RepairOrderStatus.INVOICED
    await db_session.commit()

    # Separate request sessions have no strong Customer fixture reference in
    # their identity map. This is the real endpoint boundary, unlike pay(ctx).
    async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as request:
        owner = await request.get(User, owner_id)
        before = await get_dashboard_daily_workset(db=request, current_user=owner)
        assert any(item.id == str(order_id) for item in before.ready_to_close.items)
        totals_before = await get_dashboard_daily_workset_value_summary(
            lane='ready_to_close', search=None, db=request, current_user=owner)
        assert totals_before.order_count == 1
        assert totals_before.order_value > 0
        result = await confirm_invoice_cash(invoice_id, CashConfirmationCreate(expected_settlement_version=version),
            idempotency_header='fresh-cash-request', db=request, current_user=owner)
        assert result.settlement.state == 'paid'
        payment_id = result.payment_id

    async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as request:
        owner = await request.get(User, owner_id)
        repeated = await confirm_invoice_cash(invoice_id, CashConfirmationCreate(expected_settlement_version=version),
            idempotency_header='fresh-cash-request', db=request, current_user=owner)
        assert repeated.payment_id == payment_id
        assert await request.scalar(select(func.count()).select_from(Payment)) == 1
        assert (await request.get(Invoice, invoice_id)).status == InvoiceStatus.PAID
        assert (await request.get(RepairOrder, order_id)).status == RepairOrderStatus.PAID
        daily = await get_dashboard_daily_workset(db=request, current_user=owner)
        assert not any(item.id == str(order_id) for item in daily.ready_to_close.items)
        assert any(item.id == str(order_id) for item in daily.closed_today.items)
        totals = await get_dashboard_daily_workset_value_summary(lane='ready_to_close', search=None, db=request, current_user=owner)
        assert totals.order_count == 0
        assert totals.order_value == Decimal(0)


@pytest.mark.asyncio
async def test_cash_precommit_failure_rolls_back_receipt_and_closeout(db_session, monkeypatch):
    ctx, _, _, _, _ = await reviewed(db_session, monkeypatch)
    invoice_id, owner_id, order_id = ctx[3].id, ctx[1].id, ctx[3].repair_order_id
    version = ctx[4].version
    ctx[3].repair_order.status = RepairOrderStatus.INVOICED
    await db_session.commit()
    monkeypatch.setattr('app.services.paid_invoice_webhook_service.enqueue_paid_invoice_webhook',
        AsyncMock(side_effect=RuntimeError('synthetic precommit failure')))
    async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as request:
        owner = await request.get(User, owner_id)
        with pytest.raises(RuntimeError, match='synthetic precommit failure'):
            await confirm_invoice_cash(invoice_id, CashConfirmationCreate(expected_settlement_version=version),
                idempotency_header='rollback-cash-request', db=request, current_user=owner)
        await request.rollback()
    async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as verification:
        assert await verification.scalar(select(func.count()).select_from(Payment)) == 0
        invoice = await verification.get(Invoice, invoice_id)
        assert invoice.status == InvoiceStatus.SENT
        assert invoice.paid_at is None
        assert (await verification.get(RepairOrder, order_id)).status == RepairOrderStatus.INVOICED
