from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import settings
from app.db.models.invoice_settlement import (
    InvoicePaymentLedgerEvent, InvoiceSettlement, PaymentAccountingLink, PaymentOverpayment,
    PaymentRefund, TenantPaymentProviderConfiguration,
)
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.services import db048_accounting_reconciliation as service
from app.services.quickbooks_payments_service import QuickBooksPaymentError
from app.services.invoice_settlement_service import create_attempt, get_or_create_settlement
from test_db048_invoice_settlements import _financial_context
import test_db048_invoice_settlements as fixtures


async def context(db, monkeypatch, *, realm=None, charge_id="CHARGE-NEW"):
    monkeypatch.setattr(fixtures, "TenantPaymentProviderConfiguration", lambda **kw:
        TenantPaymentProviderConfiguration(**dict(kw, selected_provider="quickbooks_payments",
            provider_account_snapshot=realm or kw["qbo_realm_snapshot"],
            qbo_realm_snapshot=realm or kw["qbo_realm_snapshot"])))
    tenant, owner, customer, invoice = await _financial_context(db, monkeypatch)
    config = await db.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant.id))
    connection = await db.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id == tenant.id))
    connection.scopes = "com.intuit.quickbooks.accounting com.intuit.quickbooks.payment"
    if realm:
        connection.realm_id = realm
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    settlement = await get_or_create_settlement(db, invoice=invoice, customer_id=customer.id, tenant=tenant)
    created = await create_attempt(db, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("1.00"), rail="card", expected_settlement_version=settlement.version,
        idempotency_key="refund-test-attempt", source="staff", subject_type="staff", subject_id=owner.id)
    created.attempt.provider_charge_id = charge_id
    refund = PaymentRefund(tenant_id=tenant.id, invoice_id=invoice.id, source_attempt_id=created.attempt.id,
        amount=Decimal("1.03"), reason="Test", destination_rail="card", mode="automatic", state="pending",
        actor_user_id=owner.id, actor_name_snapshot="Test", idempotency_key="refund-test", request_hash="0" * 64)
    db.add(refund)
    await db.flush()
    event = ProviderOutboxEvent(tenant_id=tenant.id, event_type=service.PROVIDER_REFUND_EVENT,
        aggregate_type="payment_refund", aggregate_id=refund.id,
        payload={"refund_id": str(refund.id), "attempt_id": str(created.attempt.id)},
        idempotency_key="refund-test", available_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    db.add(event)
    await db.commit()
    return refund, event, config, connection


@pytest.mark.asyncio
async def test_issued_id_persists_worker_and_retries_only_get(db_session, monkeypatch):
    refund, event, _, _ = await context(db_session, monkeypatch)
    calls = []
    async def submit(**kwargs):
        calls.append("POST")
        return SimpleNamespace(id="REFUND-NEW", amount=Decimal("1.03"), status="ISSUED")
    async def read(**kwargs):
        calls.append("GET")
        assert kwargs["charge_id"] == "CHARGE-NEW" and kwargs["refund_id"] == "REFUND-NEW"
        return SimpleNamespace(id="REFUND-NEW", amount=Decimal("1.03"), status="ISSUED")
    monkeypatch.setattr(service, "refund_quickbooks_charge", submit)
    monkeypatch.setattr(service, "get_quickbooks_refund", read)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    result = await service.process_due_db048_outbox_events(session_factory=factory)
    assert result["retried"] == 1
    await db_session.refresh(refund)
    await db_session.refresh(event)
    assert refund.provider_reference == "REFUND-NEW" and refund.state == "pending"
    assert refund.completed_at is None and event.provider_message_id == "REFUND-NEW"
    event.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    result = await service.process_due_db048_outbox_events(session_factory=factory)
    assert result["retried"] == 1 and calls == ["POST", "GET"]
    await db_session.refresh(refund)
    assert refund.state == "pending" and refund.last_error == "qbp_refund_accepted_pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown", [True, False])
async def test_uncertain_or_400_never_failed_or_reposted(db_session, monkeypatch, unknown):
    refund, event, _, _ = await context(db_session, monkeypatch)
    calls = []
    async def submit(**kwargs):
        calls.append("POST")
        raise QuickBooksPaymentError("rejected or uncertain", outcome_unknown=unknown)
    monkeypatch.setattr(service, "refund_quickbooks_charge", submit)
    await service._submit_stripe_refund(db_session, event)
    await db_session.commit()
    await service._submit_stripe_refund(db_session, event)
    assert calls == ["POST"] and refund.state == "pending"
    assert refund.provider_reference is None and refund.last_error == "qbp_refund_outcome_unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["id", "amount", "get_error"])
async def test_known_id_mismatch_or_get_error_retains_pending(db_session, monkeypatch, kind):
    refund, event, _, _ = await context(db_session, monkeypatch)
    refund.provider_reference = "REFUND-NEW"
    async def forbidden(**kwargs):
        pytest.fail("Known refund must never POST")
    async def read(**kwargs):
        if kind == "get_error":
            raise QuickBooksPaymentError("400", outcome_unknown=False)
        return SimpleNamespace(id="FOREIGN" if kind == "id" else "REFUND-NEW",
            amount=Decimal("9") if kind == "amount" else Decimal("1.03"), status="ISSUED")
    monkeypatch.setattr(service, "refund_quickbooks_charge", forbidden)
    monkeypatch.setattr(service, "get_quickbooks_refund", read)
    await service._submit_stripe_refund(db_session, event)
    assert refund.provider_reference == "REFUND-NEW" and refund.state == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["realm", "account", "tenant"])
async def test_original_identity_fence_prevents_provider_access(db_session, monkeypatch, kind):
    refund, event, config, connection = await context(db_session, monkeypatch)
    if kind == "realm":
        connection.realm_id = "FOREIGN"
    elif kind == "account":
        set_committed_value(config, "provider_account_snapshot", "FOREIGN")
    else:
        set_committed_value(event, "tenant_id", uuid4())
    async def forbidden(**kwargs):
        pytest.fail("Identity mismatch reached provider")
    monkeypatch.setattr(service, "refund_quickbooks_charge", forbidden)
    with pytest.raises(service.DB048ReconciliationError):
        await service._submit_stripe_refund(db_session, event)


@pytest.mark.asyncio
async def test_reclaimed_unknown_event_never_posts(db_session, monkeypatch):
    refund, event, _, _ = await context(db_session, monkeypatch)
    event.attempt_count = 2
    async def forbidden(**kwargs):
        pytest.fail("Previously claimed unknown refund must not POST")
    monkeypatch.setattr(service, "refund_quickbooks_charge", forbidden)
    await service._submit_stripe_refund(db_session, event)
    assert refund.state == "pending" and refund.last_error == "qbp_refund_outcome_unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("lease_lost", [False, True])
async def test_worker_settlement_deadline_or_lost_lease_preserves_id(db_session, monkeypatch, lease_lost):
    refund, event, _, _ = await context(db_session, monkeypatch)
    monkeypatch.setattr(settings, "PROVIDER_OUTBOX_MAX_ATTEMPTS", 1)
    if not lease_lost:
        refund.created_at = datetime.now(timezone.utc) - timedelta(days=15)
        await db_session.commit()
    class FutureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(hours=2)
    async def submit(**kwargs):
        if lease_lost:
            monkeypatch.setattr(service, "datetime", FutureClock)
        return SimpleNamespace(id="REFUND-NEW", amount=Decimal("1.03"), status="ISSUED")
    monkeypatch.setattr(service, "refund_quickbooks_charge", submit)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    result = await service.process_due_db048_outbox_events(session_factory=factory)
    assert result["lease_lost" if lease_lost else "dead"] == 1
    await db_session.refresh(refund)
    await db_session.refresh(event)
    assert refund.provider_reference == "REFUND-NEW" and refund.state == "pending"
    assert event.status == ("processing" if lease_lost else "dead")


@pytest.mark.asyncio
async def test_issued_polling_outlives_error_budget(db_session, monkeypatch):
    refund, event, _, _ = await context(db_session, monkeypatch)
    refund.provider_reference = "REFUND-NEW"
    event.attempt_count = 20
    await db_session.commit()
    monkeypatch.setattr(settings, "PROVIDER_OUTBOX_MAX_ATTEMPTS", 1)
    async def read(**kwargs):
        return SimpleNamespace(id="REFUND-NEW", amount=Decimal("1.03"), status="ISSUED")
    monkeypatch.setattr(service, "get_quickbooks_refund", read)
    result = await service.process_due_db048_outbox_events(
        session_factory=async_sessionmaker(db_session.bind, expire_on_commit=False))
    await db_session.refresh(event)
    assert result["retried"] == 1 and event.status == "pending"
    assert event.available_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(hours=5)


@pytest.mark.asyncio
async def test_get_error_budget_separate_from_normal_poll_count(db_session, monkeypatch):
    refund, event, _, _ = await context(db_session, monkeypatch)
    refund.provider_reference = "REFUND-NEW"
    event.attempt_count = 20
    await db_session.commit()
    monkeypatch.setattr(settings, "PROVIDER_OUTBOX_MAX_ATTEMPTS", 2)
    async def read(**kwargs):
        raise QuickBooksPaymentError("Unavailable", outcome_unknown=True)
    monkeypatch.setattr(service, "get_quickbooks_refund", read)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    result = await service.process_due_db048_outbox_events(session_factory=factory)
    await db_session.refresh(event)
    await db_session.refresh(refund)
    assert result["retried"] == 1 and refund.retry_count == 1
    event.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    result = await service.process_due_db048_outbox_events(session_factory=factory)
    await db_session.refresh(event)
    await db_session.refresh(refund)
    assert result["dead"] == 1 and refund.retry_count == 2
    assert refund.state == "pending" and refund.provider_reference == "REFUND-NEW"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["SETTLED", "DECLINED"])
async def test_verified_terminal_status_changes_once(db_session, monkeypatch, status):
    refund, event, _, _ = await context(db_session, monkeypatch)
    refund.provider_reference = "REFUND-NEW"
    settlement = await db_session.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id == refund.invoice_id))
    overpayment = PaymentOverpayment(tenant_id=refund.tenant_id, invoice_id=refund.invoice_id,
        settlement_id=settlement.id, source_attempt_id=refund.source_attempt_id,
        customer_id=settlement.customer_id, amount=Decimal("1.03"), state="refunding")
    db_session.add(overpayment)
    await db_session.flush()
    refund.overpayment_id = overpayment.id
    settlement.refund_pending = settlement.unapplied_credit = Decimal("1.03")
    calls = []
    async def read(**kwargs):
        calls.append("GET")
        return SimpleNamespace(id="REFUND-NEW", amount=Decimal("1.03"), status=status)
    async def forbidden(**kwargs):
        pytest.fail("Known refund must not POST")
    monkeypatch.setattr(service, "get_quickbooks_refund", read)
    monkeypatch.setattr(service, "refund_quickbooks_charge", forbidden)
    await service._submit_stripe_refund(db_session, event)
    await db_session.commit()
    assert refund.state == ("succeeded" if status == "SETTLED" else "failed")
    assert await db_session.scalar(select(func.count()).select_from(PaymentAccountingLink)) == (1 if status == "SETTLED" else 0)
    if status == "SETTLED":
        await service._submit_stripe_refund(db_session, event)
        assert settlement.refund_pending == Decimal("0") and overpayment.state == "refunded"
        assert await db_session.scalar(select(func.count()).select_from(PaymentAccountingLink)) == 1
        assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent).where(
            InvoicePaymentLedgerEvent.event_type == "refund_succeeded")) == 1
    else:
        assert settlement.refund_pending == Decimal("1.03") and overpayment.state == "refund_required"
    assert calls == ["GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["failed", "manual_action_required"])
async def test_nonpending_qbp_cannot_resubmit(db_session, monkeypatch, state):
    refund, event, _, _ = await context(db_session, monkeypatch)
    refund.state = state
    async def forbidden(**kwargs):
        pytest.fail("Non-pending refund must not submit")
    monkeypatch.setattr(service, "refund_quickbooks_charge", forbidden)
    with pytest.raises(service.DB048ReconciliationError, match="explicit state"):
        await service._submit_stripe_refund(db_session, event)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["good", "foreign_id", "amount", "nonfinite", "http400", "path"])
async def test_get_refund_exact_charge_identity_and_validation(monkeypatch, kind):
    from app.services import quickbooks_payments_service as payments
    import httpx
    monkeypatch.setattr(payments, "decrypt_quickbooks_token", lambda _: "test-access")
    monkeypatch.setattr(payments.settings, "QUICKBOOKS_PAYMENTS_ENVIRONMENT", "sandbox")
    calls = []
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            calls.append(url)
            assert url == "https://sandbox.api.intuit.com/quickbooks/v4/payments/charges/CHARGE-NEW/refunds/REFUND-NEW"
            return httpx.Response(400 if kind == "http400" else 200, json={
                "id": "FOREIGN" if kind == "foreign_id" else "REFUND-NEW", "status": "ISSUED",
                "amount": "1.031" if kind == "amount" else "NaN" if kind == "nonfinite" else "1.03"})
    monkeypatch.setattr(payments.httpx, "AsyncClient", Client)
    kwargs = dict(connection=SimpleNamespace(encrypted_access_token="test"),
                  charge_id="../foreign" if kind == "path" else "CHARGE-NEW", refund_id="REFUND-NEW")
    if kind == "good":
        result = await payments.get_refund(**kwargs)
        assert result.id == "REFUND-NEW" and result.status == "ISSUED" and result.amount == Decimal("1.03")
    else:
        with pytest.raises(QuickBooksPaymentError) as error:
            await payments.get_refund(**kwargs)
        assert error.value.outcome_unknown
    assert len(calls) == (0 if kind == "path" else 1)
