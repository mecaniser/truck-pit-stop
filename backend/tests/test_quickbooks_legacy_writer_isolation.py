from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.user import UserRole
from app.api.v1.endpoints import quickbooks
from app.core.config import settings
from app.services import quickbooks_accounting_service as accounting
from app.services import quickbooks_sync_service as sync
from test_db048_invoice_settlements import _financial_context


@pytest.mark.asyncio
async def test_legacy_reconciliation_excludes_canonical_pending_completed_and_refunds(
    db_session, _db_engine, monkeypatch,
):
    tenant, _owner, _customer, invoice = await _financial_context(db_session, monkeypatch)
    canonical = []
    for status in (PaymentStatus.PENDING, PaymentStatus.COMPLETED):
        payment = Payment(
            tenant_id=tenant.id, invoice_id=invoice.id, payment_number=f"CANON-{uuid4().hex}",
            amount=Decimal("10"), method=PaymentMethod.QUICKBOOKS, status=status,
            quickbooks_charge_id=f"canonical-{status.value}",
            invoice_payment_attempt_id=uuid4(), quickbooks_charge_status="UNTOUCHED",
        )
        canonical.append(payment)
    canonical_refund = Payment(
        tenant_id=tenant.id, invoice_id=invoice.id, payment_number=f"REFUND-{uuid4().hex}",
        amount=Decimal("-1"), method=PaymentMethod.QUICKBOOKS, status=PaymentStatus.COMPLETED,
        quickbooks_refund_id="canonical-refund", invoice_payment_attempt_id=uuid4(),
    )
    legacy = Payment(
        tenant_id=tenant.id, invoice_id=invoice.id, payment_number=f"LEGACY-{uuid4().hex}",
        amount=Decimal("10"), method=PaymentMethod.QUICKBOOKS, status=PaymentStatus.PENDING,
        quickbooks_charge_id="legacy-charge",
    )
    db_session.add_all([*canonical, canonical_refund, legacy])
    await db_session.commit()
    calls = []

    async def no_refresh(connection):
        return None

    async def charge(**kwargs):
        calls.append(("GET", kwargs["charge_id"]))
        assert kwargs["charge_id"] == "legacy-charge"
        return SimpleNamespace(status="CAPTURED")

    async def payment_sync(connection, payment, invoice, customer):
        calls.append(("SYNC", payment.id))
        assert payment.id == legacy.id
        return "legacy-receipt"

    async def forbidden_refund(*args, **kwargs):
        raise AssertionError("Canonical refund must not enter the legacy writer")

    monkeypatch.setattr(sync, "_refresh_if_needed", no_refresh)
    monkeypatch.setattr(sync, "get_charge", charge)
    monkeypatch.setattr(sync, "sync_payment", payment_sync)
    monkeypatch.setattr(sync, "create_refund_receipt", forbidden_refund)
    result = await sync.reconcile_quickbooks_payments(
        session_factory=async_sessionmaker(_db_engine, expire_on_commit=False),
    )
    assert result == {"checked": 1, "reconciled": 1, "failed": 0}
    assert calls == [("GET", "legacy-charge"), ("SYNC", legacy.id)]
    for payment in canonical:
        await db_session.refresh(payment)
        assert payment.quickbooks_charge_status == "UNTOUCHED"
        assert payment.quickbooks_reconciled_at is None
        assert payment.quickbooks_payment_id is None
    assert canonical[0].status == PaymentStatus.PENDING
    assert canonical[1].status == PaymentStatus.COMPLETED
    await db_session.refresh(legacy)
    assert legacy.status == PaymentStatus.COMPLETED
    await db_session.refresh(canonical_refund)
    assert canonical_refund.quickbooks_refund_receipt_id is None
    assert canonical_refund.quickbooks_reconciled_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_id", [None, "already-mapped"])
async def test_direct_legacy_writer_rejects_canonical_payment_before_provider(monkeypatch, existing_id):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Canonical payment must never reach legacy provider I/O")
    monkeypatch.setattr(accounting, "sync_invoice", forbidden)
    monkeypatch.setattr(accounting, "ensure_customer", forbidden)
    monkeypatch.setattr(accounting, "_query", forbidden)
    monkeypatch.setattr(accounting, "_request", forbidden)
    payment = Payment(invoice_payment_attempt_id=uuid4(), quickbooks_payment_id=existing_id)
    with pytest.raises(accounting.QuickBooksAccountingError, match="settlement accounting writer"):
        await accounting.sync_payment(None, payment, None, None)


@pytest.mark.asyncio
async def test_manual_legacy_reconciliation_rejects_canonical_before_mutation(monkeypatch):
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    tenant_id, payment_id = uuid4(), uuid4()
    payment = Payment(id=payment_id, tenant_id=tenant_id, invoice_payment_attempt_id=uuid4(),
                      quickbooks_charge_id="canonical", quickbooks_charge_status="UNTOUCHED",
                      status=PaymentStatus.PENDING)
    class Database:
        async def get(self, model, identity):
            assert model is Payment and identity == payment_id
            return payment
    async def forbidden(*args, **kwargs):
        raise AssertionError("Canonical row must not reach legacy provider")
    monkeypatch.setattr(quickbooks, "_get_connection", forbidden)
    monkeypatch.setattr(quickbooks, "get_charge", forbidden)
    with pytest.raises(HTTPException) as exc:
        await quickbooks.reconcile_quickbooks_payment(
            payment_id, db=Database(),
            current_user=SimpleNamespace(tenant_id=tenant_id, role=UserRole.GARAGE_OWNER),
        )
    assert exc.value.status_code == 409
    assert payment.status == PaymentStatus.PENDING
    assert payment.quickbooks_charge_status == "UNTOUCHED"
