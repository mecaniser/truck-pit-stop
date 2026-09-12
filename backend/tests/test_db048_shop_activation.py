import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.config import settings
from app.db.models.invoice import Invoice
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.quickbooks_shop_activation import QuickBooksShopActivation
from app.db.models.invoice_settlement import InvoicePaymentAttempt, TenantPaymentProviderConfiguration
from app.services import quickbooks_shop_activation as admission
from app.services.invoice_settlement_service import SettlementDomainError, create_attempt, expire_due_attempts
from app.services.invoice_accounting_policy import require_standard_payment
from tests.test_db048_cash import context
from tests.test_db048_cash_payment_timing import event


async def managed(db, monkeypatch, *, enabled=False, enrolled=False):
    ctx = await context(db, monkeypatch)
    connection = await db.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id == ctx[0].id))
    activation = QuickBooksShopActivation(tenant_id=ctx[0].id, realm_id=connection.realm_id,
        environment="production", enabled=enabled,
        activated_at=datetime.now(timezone.utc)-timedelta(days=1) if enabled else None)
    db.add(activation)
    await db.flush()
    if enrolled:
        # Admission fixture only. PG creation-only trigger is independently tested.
        ctx[3].qbo_shop_activation_id = activation.id
        await db.flush()
    return ctx, activation, connection


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["disabled", "not_enrolled", "cutoff", "import", "replacement", "hold", "realm", "writer", "environment"])
async def test_managed_admission_denials(db_session, monkeypatch, defect):
    ctx, activation, connection = await managed(db_session, monkeypatch, enabled=True, enrolled=True)
    invoice = ctx[3]
    if defect == "disabled": activation.enabled = False
    if defect == "not_enrolled": invoice.qbo_shop_activation_id = None
    if defect == "cutoff": invoice.created_at = activation.activated_at
    if defect == "import": invoice.source = "easy_truck_shop_import"
    if defect == "replacement": invoice.supersedes_invoice_id = uuid4()
    if defect == "hold": invoice.accounting_policy = "historical_export_hold"
    if defect == "realm": connection.realm_id = "other-company"
    config = await db_session.scalar(select(TenantPaymentProviderConfiguration).where(TenantPaymentProviderConfiguration.tenant_id == ctx[0].id))
    if defect in {"writer", "environment"}:
        values = {c.name: getattr(config, c.name) for c in config.__table__.columns
            if c.name not in {"id", "created_at", "updated_at", "deleted_at"}}
        config.is_active = False
        config.deactivated_at = datetime.now(timezone.utc)
        values.update(version=2, idempotency_key="replacement", is_active=True, deactivated_at=None)
        if defect == "writer": values["writer_strategy"] = "intuit_native"
        else: values["selected_provider"] = "quickbooks_payments"
        db_session.add(TenantPaymentProviderConfiguration(**values))
    if defect == "environment":
        monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_ENVIRONMENT", "sandbox")
    await db_session.flush()
    with pytest.raises(SettlementDomainError):
        await admission.require_shop_invoice_admission(db_session, invoice, payment=True)


@pytest.mark.asyncio
async def test_unmanaged_is_unchanged_and_zero_rows_by_default(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    assert await admission.load_shop_activation(db_session, ctx[0].id) is None
    assert await admission.require_shop_invoice_admission(db_session, ctx[3]) is None
    await require_standard_payment(db_session, ctx[3])


@pytest.mark.asyncio
async def test_creation_only_enrollment_and_no_late_enrollment(db_session, monkeypatch):
    ctx, activation, _ = await managed(db_session, monkeypatch, enabled=True)
    with pytest.raises(SettlementDomainError):
        await admission.enroll_new_invoice(db_session, ctx[3])
    fresh = Invoice(tenant_id=ctx[0].id, repair_order_id=uuid4(), invoice_number="NATIVE",
        subtotal=Decimal("1"), total_amount=Decimal("1"))
    await admission.enroll_new_invoice(db_session, fresh)
    assert fresh.qbo_shop_activation_id == activation.id
    assert fresh.created_at > activation.activated_at.replace(tzinfo=timezone.utc)
    imported = Invoice(tenant_id=ctx[0].id, source="import")
    await admission.enroll_new_invoice(db_session, imported)
    assert imported.qbo_shop_activation_id is None


@pytest.mark.asyncio
async def test_scope_restores_environment_and_never_crosses_tenant(db_session, monkeypatch):
    ctx, activation, connection = await managed(db_session, monkeypatch, enabled=True, enrolled=True)
    other = await context(db_session, monkeypatch)
    other_connection = await db_session.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id == other[0].id))
    monkeypatch.setattr(settings, "QUICKBOOKS_ACCOUNTING_ENVIRONMENT", "sandbox")
    @admission.accounting_operation
    async def operation(fail=False):
        await admission.require_shop_invoice_admission(db_session, ctx[3])
        assert await admission.request_environment(connection, method="POST", resource="invoice") == "production"
        assert await admission.request_environment(other_connection, method="POST", resource="invoice") == "sandbox"
        if fail: raise RuntimeError("expected")
    await operation()
    with pytest.raises(RuntimeError): await operation(True)
    with pytest.raises(SettlementDomainError):
        await admission.request_environment(connection, method="POST", resource="invoice")
    assert settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT == "sandbox"


@pytest.mark.asyncio
async def test_disabled_identity_read_is_still_realm_bound(db_session, monkeypatch):
    _, activation, connection = await managed(db_session, monkeypatch)
    assert await admission.request_environment(connection, method="GET", resource=f"companyinfo/{connection.realm_id}") == "production"
    with pytest.raises(SettlementDomainError):
        await admission.request_environment(connection, method="GET", resource="query")


@pytest.mark.asyncio
async def test_disabled_and_historical_outbox_not_claimed_or_changed(db_session, monkeypatch):
    from app.services.quickbooks_sync_service import process_quickbooks_invoice_sync_events
    from app.services.db048_accounting_reconciliation import process_due_db048_outbox_events
    ctx, _, _ = await managed(db_session, monkeypatch)
    issuance = event(ctx[3])
    canonical = event(ctx[3], kind="invoice_payment.accounting_sync", payload={"invoice_id": str(ctx[3].id)})
    db_session.add_all([issuance, canonical])
    await db_session.commit()
    before = [(r.status, r.attempt_count, r.lock_token, r.available_at.replace(tzinfo=timezone.utc)) for r in (issuance, canonical)]
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    first = await process_quickbooks_invoice_sync_events(session_factory=sessions)
    second = await process_due_db048_outbox_events(session_factory=sessions)
    assert first["processed"] == second["claimed"] == 0
    for row in (issuance, canonical): await db_session.refresh(row)
    assert before == [(r.status, r.attempt_count, r.lock_token, r.available_at.replace(tzinfo=timezone.utc)) for r in (issuance, canonical)]


@pytest.mark.asyncio
async def test_disabled_maintenance_preserves_expired_reservation(db_session, monkeypatch):
    from app.services.db048_accounting_reconciliation import reconcile_due_card_attempts
    ctx = await context(db_session, monkeypatch)
    creation = await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=Decimal("10"), rail="card", expected_settlement_version=1,
        idempotency_key="old-card", source="staff", subject_type="staff", subject_id=ctx[1].id)
    creation.attempt.expires_at = datetime.now(timezone.utc)-timedelta(days=1)
    db_session.add(QuickBooksShopActivation(tenant_id=ctx[0].id, realm_id="managed", environment="production"))
    await db_session.flush()
    before = (creation.attempt.state, creation.attempt.version, creation.settlement.active_pending_principal)
    provider = AsyncMock(side_effect=AssertionError("excluded maintenance must not call provider"))
    result = await reconcile_due_card_attempts(db_session, retrieve_intent=provider, cancel_intent=provider)
    assert result["checked"] == 0 and await expire_due_attempts(db_session) == 0
    assert before == (creation.attempt.state, creation.attempt.version, creation.settlement.active_pending_principal)
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_managed_legacy_cdc_does_not_change_global_cursor(db_session, monkeypatch):
    from app.services import quickbooks_sync_service as sync
    _, _, connection = await managed(db_session, monkeypatch)
    await db_session.commit()
    original = connection.last_cdc_at
    provider = AsyncMock(side_effect=AssertionError("legacy CDC must not process managed history"))
    monkeypatch.setattr(sync, "change_data_capture", provider)
    result = await sync.backfill_quickbooks_cdc(session_factory=async_sessionmaker(db_session.bind, expire_on_commit=False))
    assert result["connections"] == 0
    await db_session.refresh(connection)
    assert connection.last_cdc_at == original
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_realm_mismatched_head_unchanged_and_other_tenant_claims(db_session, monkeypatch):
    from app.services.quickbooks_sync_service import _claim_next_quickbooks_sync_event
    ctx, _, connection = await managed(db_session, monkeypatch, enabled=True, enrolled=True)
    connection.realm_id = "wrong-company"
    excluded = event(ctx[3])
    excluded.available_at = datetime.now(timezone.utc)-timedelta(days=1)
    other = await context(db_session, monkeypatch)
    permitted = event(other[3])
    db_session.add_all([excluded, permitted])
    await db_session.commit()
    result = await _claim_next_quickbooks_sync_event(db_session)
    assert result[0] == permitted.id
    await db_session.refresh(excluded)
    assert excluded.status == "pending" and excluded.attempt_count == 0 and excluded.lock_token is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe_connect", "quickbooks_payments"])
async def test_disable_after_commit_blocks_actual_new_capture_helper(db_session, monkeypatch, provider):
    from app.api.v1.endpoints import invoice_settlements as endpoints
    ctx, activation, connection = await managed(db_session, monkeypatch, enabled=True, enrolled=True)
    tenant, owner, customer, invoice, _ = ctx
    if provider == "quickbooks_payments":
        config = await db_session.scalar(select(TenantPaymentProviderConfiguration).where(
            TenantPaymentProviderConfiguration.tenant_id == tenant.id))
        values = {c.name: getattr(config, c.name) for c in config.__table__.columns
            if c.name not in {"id", "created_at", "updated_at", "deleted_at"}}
        config.is_active = False
        config.deactivated_at = datetime.now(timezone.utc)
        values.update(version=2, idempotency_key="qbp-config", is_active=True, deactivated_at=None,
            selected_provider=provider, provider_account_snapshot=connection.realm_id)
        db_session.add(TenantPaymentProviderConfiguration(**values))
        connection.scopes = "com.intuit.quickbooks.accounting com.intuit.quickbooks.payment"
        monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_ENVIRONMENT", "production")
        monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
        monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_APPROVED_TENANT_IDS", str(tenant.id))
    await db_session.flush()
    creation = await create_attempt(db_session, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, amount=Decimal("10"), rail="card", expected_settlement_version=1,
        idempotency_key="disable-race", source="staff", subject_type="staff", subject_id=owner.id)
    original_commit = db_session.commit
    async def commit_then_disable(*args, **kwargs):
        await original_commit()
        activation.enabled = False
        await original_commit()
    provider_call = AsyncMock(side_effect=AssertionError("disabled shop must never dispatch new capture"))
    if provider == "stripe_connect":
        monkeypatch.setattr(db_session, "commit", commit_then_disable)
        monkeypatch.setattr(endpoints, "_create_stripe_intent", provider_call)
        operation = endpoints._persist_and_bind_stripe_intent(db_session, attempt=creation.attempt,
            tenant=tenant, invoice=invoice, customer=customer, idempotency_key="race", actor=owner)
    else:
        monkeypatch.setattr(endpoints, "_refresh_connection_if_needed", commit_then_disable)
        monkeypatch.setattr(endpoints, "create_quickbooks_charge", provider_call)
        operation = endpoints.charge_quickbooks_settlement_attempt(db_session, attempt=creation.attempt,
            tenant=tenant, invoice=invoice, actor=owner, payment_token="opaque",
            expected_attempt_version=creation.attempt.version, idempotency_key="race")
    with pytest.raises(SettlementDomainError) as exc:
        await operation
    assert exc.value.code == "quickbooks_shop_disabled"
    provider_call.assert_not_awaited()
    assert creation.attempt.state == "pending"


@pytest.mark.asyncio
async def test_original_qbp_provider_environment_checked_after_switch_to_stripe(db_session, monkeypatch):
    ctx, _, _ = await managed(db_session, monkeypatch, enabled=True, enrolled=True)
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_ENVIRONMENT", "sandbox")
    # Current Stripe admission must not determine the environment of an old
    # QuickBooks charge/refund. Its immutable source provider does.
    await admission.require_shop_invoice_admission(db_session, ctx[3], payment=True)
    with pytest.raises(SettlementDomainError) as exc:
        await admission.require_shop_invoice_admission(db_session, ctx[3], payment=True,
            payment_provider="quickbooks_payments")
    assert exc.value.code == "quickbooks_activation_environment_mismatch"


@pytest.mark.asyncio
async def test_old_qbp_refund_cannot_cross_environment_after_provider_switch(db_session, monkeypatch):
    from tests.test_db048_qbp_refund_reconciliation import context as refund_context
    from app.services import db048_accounting_reconciliation as reconciliation
    refund, outbox, config, connection = await refund_context(db_session, monkeypatch)
    invoice = await db_session.get(Invoice, refund.invoice_id)
    activation = QuickBooksShopActivation(tenant_id=invoice.tenant_id, realm_id=connection.realm_id,
        environment="production", enabled=True, activated_at=invoice.created_at-timedelta(days=1))
    db_session.add(activation)
    await db_session.flush()
    invoice.qbo_shop_activation_id = activation.id
    values = {c.name: getattr(config, c.name) for c in config.__table__.columns
        if c.name not in {"id", "created_at", "updated_at", "deleted_at"}}
    config.is_active = False
    config.deactivated_at = datetime.now(timezone.utc)
    values.update(version=2, idempotency_key="stripe-switch", is_active=True, deactivated_at=None,
        selected_provider="stripe_connect")
    db_session.add(TenantPaymentProviderConfiguration(**values))
    await db_session.flush()
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_ENVIRONMENT", "sandbox")
    provider_call = AsyncMock(side_effect=AssertionError("source environment cannot cross"))
    monkeypatch.setattr(reconciliation, "refund_quickbooks_charge", provider_call)
    with pytest.raises(SettlementDomainError) as exc:
        await reconciliation._submit_stripe_refund(db_session, outbox)
    assert exc.value.code == "quickbooks_activation_environment_mismatch"
    provider_call.assert_not_awaited()
    assert refund.state == "pending" and refund.provider_reference is None
