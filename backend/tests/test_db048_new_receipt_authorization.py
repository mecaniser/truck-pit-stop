from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.core.config import settings
from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import InvoicePaymentAttempt, InvoiceSettlement, PaymentAccountingLink, TenantPaymentProviderConfiguration
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.services.invoice_settlement_service import create_attempt, confirm_attempt, SettlementDomainError
from app.services.invoice_accounting_policy import require_exportable_invoice
from app.services.quickbooks_accounting_service import QuickBooksAccountingError
from app.services import new_receipt_accounting as auth
from tests.test_db048_cash import context


@pytest.fixture(autouse=True)
def fee_mappings(monkeypatch):
    from tests.test_db048_invoice_settlements import _financial_context
    original = _financial_context.__globals__["TenantPaymentProviderConfiguration"]
    monkeypatch.setitem(_financial_context.__globals__, "TenantPaymentProviderConfiguration",
        lambda **kw: original(**dict(kw, qbo_card_fee_item_id="fee-item", qbo_card_fee_tax_code_id="tax-code")))


async def held(db, monkeypatch):
    ctx = await context(db, monkeypatch)
    ctx[3].accounting_policy = "historical_export_hold"
    monkeypatch.setattr(settings, "QUICKBOOKS_ACCOUNTING_ENVIRONMENT", "production")
    await db.flush()
    return ctx


async def create(db, ctx, *, rail="zelle", source="staff", evidence=None, key="new"):
    return await create_attempt(db, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1] if source == "staff" else None, amount=Decimal("10"), rail=rail,
        expected_settlement_version=ctx[4].version, idempotency_key=key, source=source,
        subject_type="staff" if source == "staff" else "guest" if source == "guest_token" else "customer",
        subject_id=ctx[1].id if source == "staff" else ctx[2].id, sender_evidence=evidence)


@pytest.mark.asyncio
@pytest.mark.parametrize("rail,source", [("card","staff"),("zelle","staff"),("check","staff"),("ach","staff"),("card","customer_portal"),("zelle","guest_token"),("card","compatibility_adapter"),("card","customer_portal_compatibility")])
async def test_new_native_receipt_admitted_and_authorization_immutable(db_session, monkeypatch, rail, source):
    ctx = await held(db_session, monkeypatch)
    created = await create(db_session, ctx, rail=rail, source=source,
        evidence={"new_receipt_accounting_authorization": {"environment":"sandbox"}})
    proof = created.attempt.new_receipt_accounting_authorization
    assert proof["environment"] == "production" and proof["effective_composition"] == "gross_invoice_v1"
    replay = await create(db_session, ctx, rail=rail, source=source,
        evidence={"new_receipt_accounting_authorization": {"environment":"sandbox"}})
    assert replay.replayed and replay.attempt.id == created.attempt.id
    assert replay.attempt.new_receipt_accounting_authorization == proof
    assert ctx[3].accounting_policy == "historical_export_hold"
    created.attempt.new_receipt_accounting_authorization = {**proof, "environment":"sandbox"}
    with pytest.raises(ValueError, match="immutable"): await db_session.flush()


@pytest.mark.asyncio
async def test_old_attempt_replay_not_authorized_and_old_fact_stays_held(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    old = await create(db_session, ctx, rail="card")
    ctx[3].accounting_policy = "historical_export_hold"
    await db_session.flush()
    replay = await create(db_session, ctx, rail="card")
    assert replay.replayed and replay.attempt.new_receipt_accounting_authorization is None
    with pytest.raises(SettlementDomainError):
        await confirm_attempt(db_session, attempt_id=old.attempt.id, tenant=ctx[0], actor=ctx[1],
            expected_attempt_version=old.attempt.version, idempotency_key="manual-old", provider_charge_id="old")
    await confirm_attempt(db_session, attempt_id=old.attempt.id, tenant=ctx[0], actor=None,
        expected_attempt_version=old.attempt.version, idempotency_key="verified-old", provider_charge_id="old",
        verified_provider_fact=True)
    outbox = await db_session.scalar(select(ProviderOutboxEvent).where(ProviderOutboxEvent.aggregate_id == old.attempt.id))
    assert outbox.status == "suppressed"
    with pytest.raises(SettlementDomainError, match="historical payments"):
        await create(db_session, ctx, key="different")


@pytest.mark.asyncio
async def test_new_confirmation_does_not_release_old_invoice_jobs(db_session, monkeypatch):
    ctx = await held(db_session, monkeypatch)
    old = ProviderOutboxEvent(tenant_id=ctx[0].id, aggregate_type="quickbooks_invoice", aggregate_id=ctx[3].id,
        event_type="quickbooks.invoice.sync.v1", status="dead", attempt_count=5,
        available_at=datetime.now(timezone.utc), idempotency_key="old", payload={"original":True})
    db_session.add(old)
    new = await create(db_session, ctx)
    await confirm_attempt(db_session, attempt_id=new.attempt.id, tenant=ctx[0], actor=ctx[1],
        expected_attempt_version=new.attempt.version, idempotency_key="confirm", reference="zelle-new")
    outbox = await db_session.scalar(select(ProviderOutboxEvent).where(ProviderOutboxEvent.aggregate_id == new.attempt.id))
    assert outbox.status == "pending"
    assert old.status == "dead" and old.attempt_count == 5 and old.payload == {"original":True}
    ctx[3].quickbooks_invoice_id = "new-qbo-invoice"
    await db_session.flush()
    with pytest.raises(QuickBooksAccountingError, match="held"):
        await require_exportable_invoice(ctx[3])


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["invoice_id", "synced_at", "synced_status", "accounting_link"])
async def test_first_receipt_rejects_unapproved_accounting_history(db_session, monkeypatch, history):
    ctx = await held(db_session, monkeypatch)
    if history == "invoice_id":
        ctx[3].quickbooks_invoice_id = "preexisting-unapproved-qbo-invoice"
    elif history == "synced_at":
        ctx[3].quickbooks_synced_at = datetime.now(timezone.utc)
    elif history == "synced_status":
        ctx[3].quickbooks_sync_status = "synced"
    else:
        db_session.add(PaymentAccountingLink(tenant_id=ctx[0].id, invoice_id=ctx[3].id,
            financial_object_type="payment", financial_object_id=uuid4(), owning_writer="dieselbridge",
            provider_object_id="old-provider-payment"))
    await db_session.flush()
    with pytest.raises(SettlementDomainError, match="QuickBooks accounting history"):
        await create(db_session, ctx, rail="card")
    assert not list((await db_session.scalars(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.invoice_id == ctx[3].id))).all())


@pytest.mark.asyncio
async def test_subsequent_authorized_receipt_accepts_own_accounting_history(db_session, monkeypatch):
    ctx = await held(db_session, monkeypatch)
    first = await create(db_session, ctx)
    await confirm_attempt(db_session, attempt_id=first.attempt.id, tenant=ctx[0], actor=ctx[1],
        expected_attempt_version=first.attempt.version, idempotency_key="first-confirm", reference="first-zelle")
    ctx[3].quickbooks_invoice_id = "new-authorized-invoice"
    ctx[3].quickbooks_synced_at = datetime.now(timezone.utc)
    ctx[3].quickbooks_sync_status = "synced"
    await db_session.flush()
    second = await create(db_session, ctx, key="second")
    assert second.attempt.new_receipt_accounting_authorization is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["total_amount", "service_fee_amount", "tax_amount"])
async def test_invoice_snapshot_drift_denied_before_new_receipt(db_session, monkeypatch, field):
    ctx = await held(db_session, monkeypatch)
    setattr(ctx[3], field, getattr(ctx[3], field) + Decimal("100"))
    await db_session.flush()
    with pytest.raises(SettlementDomainError, match="amounts differ from the payment snapshot"):
        await create(db_session, ctx, rail="card")
    assert not list((await db_session.scalars(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.invoice_id == ctx[3].id))).all())


@pytest.mark.asyncio
async def test_parent_pending_reservation_denies_new_collection(db_session, monkeypatch):
    ctx = await held(db_session, monkeypatch)
    parent = Invoice(tenant_id=ctx[0].id, repair_order_id=ctx[3].repair_order_id, invoice_number="OLD",
        subtotal=Decimal("224.62"), total_amount=Decimal("232.48"), status="cancelled", voided_at=datetime.now(timezone.utc))
    db_session.add(parent)
    await db_session.flush()
    db_session.add(InvoiceSettlement(tenant_id=ctx[0].id, invoice_id=parent.id, customer_id=ctx[2].id,
        principal_total=Decimal("224.62"), active_pending_principal=Decimal("224.62")))
    ctx[3].supersedes_invoice_id = parent.id
    await db_session.flush()
    with pytest.raises(SettlementDomainError, match="previous version of this invoice has a pending payment"):
        await create(db_session, ctx)
    assert await db_session.scalar(select(InvoicePaymentAttempt.id)) is None


@pytest.mark.asyncio
async def test_backfill_source_cannot_receive_new_authorization(db_session, monkeypatch):
    ctx = await held(db_session, monkeypatch)
    with pytest.raises(SettlementDomainError, match="Accounting is not ready"):
        await create(db_session, ctx, source="backfill")


@pytest.mark.asyncio
async def test_authorized_legacy_reversal_uses_same_gross_lineage_and_environment(db_session, monkeypatch):
    from app.services import db048_accounting_reconciliation as r, db048_qbo_gross_accounting as g
    from tests.test_db048_gross_accounting import provider, envelope
    ctx = await held(db_session, monkeypatch)
    created = await create(db_session, ctx, rail="card")
    created.attempt.provider_intent_id = "pi-new"
    await confirm_attempt(db_session, attempt_id=created.attempt.id, tenant=ctx[0], actor=ctx[1],
        expected_attempt_version=created.attempt.version, idempotency_key="confirm", provider_charge_id="ch-new",
        provider_event_id="evt-new", received_principal=Decimal("10"))
    lock, projection = g._locked_settlement, g._projection
    _, state = provider(monkeypatch, envelope())
    monkeypatch.setattr(g, "_locked_settlement", lock)
    monkeypatch.setattr(g, "_projection", projection)
    monkeypatch.setattr(r, "_resolve_qbo_account_reference", AsyncMock(side_effect=lambda connection,value:
        "income" if value == "Card Fee Income" else value))
    request = r._request
    async def scoped_request(connection, method, path, **kwargs):
        assert auth.request_environment(connection) == "production"
        return await request(connection, method, path, **kwargs)
    monkeypatch.setattr(r, "_request", scoped_request)
    monkeypatch.setattr(settings, "QUICKBOOKS_ACCOUNTING_ENVIRONMENT", "sandbox")
    async def dispatch(kind):
        link = await db_session.scalar(select(PaymentAccountingLink).where(
            PaymentAccountingLink.attempt_id == created.attempt.id, PaymentAccountingLink.financial_object_type == kind))
        outbox = await db_session.scalar(select(ProviderOutboxEvent).where(
            ProviderOutboxEvent.payload["accounting_link_id"].as_string() == str(link.id)))
        outbox.status, outbox.lock_token = "processing", "lease"
        outbox.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        await db_session.flush()
        resolved = await r.load_accounting_envelope(db_session, outbox)
        await r.deliver_accounting_envelope(db_session, resolved)
        assert auth.request_environment(resolved.connection) == "sandbox"
        return resolved
    original = await dispatch("invoice_payment")
    await r.reverse_confirmed_attempt(db_session, tenant_id=ctx[0].id, provider_account_id=created.attempt.provider_account_id,
        provider_charge_id="ch-new", provider_event_id="evt-reversed", reason="test")
    await dispatch("payment_reversal")
    assert ctx[3].accounting_policy == "historical_export_hold"
    assert ctx[4].accounting_composition_version == "legacy_principal_v1"
    assert await auth.attempt_effective_gross(db_session, ctx[4], created.attempt)
    assert state["payment"]["TotalAmt"] == 0
    assert state["invoice"]["TotalAmt"] == float(ctx[4].principal_total)
    with pytest.raises(QuickBooksAccountingError): await require_exportable_invoice(ctx[3])


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["none", "expired_lease", "wrong_event_link", "realm", "tenant", "exception", "cancel"])
async def test_receipt_scope_exact_identity_and_reset(db_session, monkeypatch, defect):
    import asyncio
    from app.services import db048_accounting_reconciliation as r
    from app.db.models.quickbooks_connection import QuickBooksConnection
    ctx = await held(db_session, monkeypatch)
    created = await create(db_session, ctx)
    await confirm_attempt(db_session, attempt_id=created.attempt.id, tenant=ctx[0], actor=ctx[1],
        expected_attempt_version=created.attempt.version, idempotency_key="confirm", reference="scoped-zelle")
    event = await db_session.scalar(select(ProviderOutboxEvent).where(ProviderOutboxEvent.aggregate_id == created.attempt.id))
    event.status, event.lock_token = "processing", "lease"
    event.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    await db_session.flush()
    env = await r.load_accounting_envelope(db_session, event)
    if defect == "expired_lease": event.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    if defect == "wrong_event_link": event.payload = {**event.payload, "accounting_link_id": str(uuid4())}
    if defect == "realm": env.connection.realm_id = "different-company"
    if defect == "tenant": env.connection.tenant_id = uuid4()
    await db_session.flush()
    monkeypatch.setattr(settings, "QUICKBOOKS_ACCOUNTING_ENVIRONMENT", "sandbox")
    entered = []
    @auth.receipt_accounting_operation
    async def dispatch(db, envelope):
        entered.append(True)
        await require_exportable_invoice(envelope.invoice)
        assert auth.request_environment(envelope.connection) == "production"
        await asyncio.sleep(0)
        if defect == "exception": raise RuntimeError("test reset")
        if defect == "cancel": raise asyncio.CancelledError()
        return "ok"
    if defect == "none":
        async def unrelated():
            await asyncio.sleep(0)
            assert auth.request_environment(env.connection) == "sandbox"
        await asyncio.gather(dispatch(db_session, env), unrelated())
    elif defect == "exception":
        with pytest.raises(RuntimeError): await dispatch(db_session, env)
    elif defect == "cancel":
        with pytest.raises(asyncio.CancelledError): await dispatch(db_session, env)
    else:
        with pytest.raises(QuickBooksAccountingError): await dispatch(db_session, env)
        assert entered == []
    assert auth.request_environment(env.connection) == "sandbox"
