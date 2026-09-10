from decimal import Decimal
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.core.quickbooks_payment_gate import quickbooks_payments_enabled_for_tenant
from app.api.v1.endpoints import quickbooks, invoice_settlements
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.invoice_settlement import TenantPaymentProviderConfiguration
from app.db.models.user import UserRole
from app.schemas.invoice_settlement import CardProviderConfigurationUpdate
from app.services.invoice_settlement_service import (
    SettlementDomainError, create_attempt, get_or_create_settlement, load_active_configuration, provider_readiness,
)
from test_db048_invoice_settlements import _financial_context, _provider_step_up_context


@pytest.mark.parametrize("environment,payment_environment,allowlist,approved,expected", [
    ("production", "production", "pilot", True, True),
    ("production", "production", "other", True, False),
    ("production", "production", "", True, False),
    ("production", "sandbox", "", True, False),
    ("development", "production", "", True, False),
    ("development", "sandbox", "", True, True),
    ("development", "sandbox", "other", True, False),
    ("production", "production", "pilot", False, False),
    ("production", "production", "pilot,invalid", True, False),
    ("production", "production", "pilot,", True, False),
    ("development", "sandbox", "invalid", True, False),
    ("production", "production", " pilot , other ", True, True),
])
def test_gate_is_explicit_and_fail_closed(monkeypatch, environment, payment_environment, allowlist, approved, expected):
    pilot, other = uuid4(), uuid4()
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_ENVIRONMENT", payment_environment)
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", approved)
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_APPROVED_TENANT_IDS", allowlist.replace("pilot", str(pilot)).replace("other", str(other)))
    assert quickbooks_payments_enabled_for_tenant(pilot) is expected
    assert quickbooks_payments_enabled_for_tenant(None) is False
    assert quickbooks_payments_enabled_for_tenant("invalid") is False


class NoDatabaseAccess:
    async def execute(self, *args, **kwargs):
        raise AssertionError("Blocked tenant must not reach database/provider")


@pytest.mark.asyncio
async def test_excluded_shop_legacy_refund_is_blocked_before_lookup_or_provider(monkeypatch):
    nc_tenant, wi_tenant = uuid4(), uuid4()
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_APPROVED_TENANT_IDS", str(nc_tenant))
    owner = SimpleNamespace(role=UserRole.GARAGE_OWNER, tenant_id=wi_tenant)
    provider_calls = []

    async def forbidden_provider(*args, **kwargs):
        provider_calls.append(True)
        raise AssertionError("Excluded shop must not issue a provider refund")

    monkeypatch.setattr(quickbooks, "refund_charge", forbidden_provider)
    with pytest.raises(HTTPException) as exc:
        await quickbooks.refund_quickbooks_payment(
            uuid4(), quickbooks.QuickBooksRefundRequest(amount=Decimal("1"), reason="Pilot boundary test"),
            db=NoDatabaseAccess(), current_user=owner,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == "QuickBooks Payments is not approved for this shop"
    assert provider_calls == []


@pytest.mark.asyncio
async def test_nonpilot_legacy_availability_and_charge_are_blocked_before_provider(monkeypatch):
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_APPROVED_TENANT_IDS", str(uuid4()))
    user = SimpleNamespace(role=UserRole.CUSTOMER, customer_id=uuid4(), tenant_id=uuid4())
    result = await quickbooks.quickbooks_payment_availability(uuid4(), db=NoDatabaseAccess(), current_user=user)
    assert result.available is False
    with pytest.raises(HTTPException) as exc:
        await quickbooks.charge_quickbooks_invoice(SimpleNamespace(), db=NoDatabaseAccess(), current_user=user)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_pending_canonical_and_guest_charge_cannot_bypass_revoked_admission(monkeypatch):
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_APPROVED_TENANT_IDS", str(uuid4()))
    tenant = SimpleNamespace(id=uuid4())
    invoice = SimpleNamespace(id=uuid4())
    attempt = SimpleNamespace(invoice_id=invoice.id, tenant_id=tenant.id, rail="card", provider="quickbooks_payments", state="pending", version=1, provider_charge_id=None)
    with pytest.raises(SettlementDomainError) as exc:
        await invoice_settlements.charge_quickbooks_settlement_attempt(
            NoDatabaseAccess(), attempt=attempt, invoice=invoice, tenant=tenant,
            actor=None, payment_token="opaque", expected_attempt_version=1, idempotency_key="pilot-test",
        )
    assert exc.value.code == "quickbooks_payments_platform_approval_missing"


@pytest.mark.asyncio
@pytest.mark.parametrize("subject_type", ["customer", "guest"])
async def test_two_tenant_readiness_and_attempt_preparation(db_session, monkeypatch, subject_type, client):
    contexts = [await _financial_context(db_session, monkeypatch) for _ in range(2)]
    pilot = contexts[0][0]
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_APPROVED_TENANT_IDS", str(pilot.id))
    for tenant, owner, customer, invoice in contexts:
        connection = await db_session.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id == tenant.id))
        connection.scopes = "com.intuit.quickbooks.accounting com.intuit.quickbooks.payment"
        previous = await load_active_configuration(db_session, tenant.id)
        previous.is_active = False
        previous.deactivated_at = datetime.now(timezone.utc)
        fields = {column.name: getattr(previous, column.name) for column in TenantPaymentProviderConfiguration.__table__.columns
                  if column.name not in {"id", "created_at", "updated_at", "deleted_at"}}
        fields.update(version=previous.version + 1, is_active=True, selected_provider="quickbooks_payments",
                      provider_account_snapshot=connection.realm_id, idempotency_key=f"qbp-{tenant.id}", deactivated_at=None)
        config = TenantPaymentProviderConfiguration(**fields)
        db_session.add(config)
        await db_session.flush()
        settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
        readiness = await provider_readiness(db_session, tenant, config)
        assert readiness.provider_global_gate is (tenant.id == pilot.id)
        kwargs = dict(invoice=invoice, tenant=tenant, customer_id=customer.id, actor=None,
                      amount=Decimal("1"), rail="card", expected_settlement_version=settlement.version,
                      idempotency_key=f"pilot-{tenant.id}", source="guest_token" if subject_type == "guest" else "customer",
                      subject_type=subject_type, subject_id=customer.id)
        if tenant.id == pilot.id:
            assert readiness.status == "ready", readiness.reasons
            created = await create_attempt(db_session, **kwargs)
            assert created.attempt.provider == "quickbooks_payments"
        else:
            with pytest.raises(SettlementDomainError) as exc:
                await create_attempt(db_session, **kwargs)
            assert exc.value.code == "quickbooks_payments_external_approval_pending"
            with pytest.raises(SettlementDomainError) as exc:
                await invoice_settlements.update_card_provider_configuration(
                    CardProviderConfigurationUpdate(selected_provider="quickbooks_payments", expected_version=config.version),
                    idempotency_header=f"select-{tenant.id}", db=db_session, current_user=owner,
                    step_up_context=await _provider_step_up_context(db_session, owner),
                )
            assert exc.value.code == "quickbooks_payments_platform_approval_missing"


@pytest.mark.asyncio
async def test_existing_charge_can_reconcile_after_tenant_admission_removed(monkeypatch):
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED", True)
    monkeypatch.setattr(settings, "QUICKBOOKS_PAYMENTS_APPROVED_TENANT_IDS", str(uuid4()))
    tenant = SimpleNamespace(id=uuid4())
    invoice = SimpleNamespace(id=uuid4())
    attempt = SimpleNamespace(invoice_id=invoice.id, tenant_id=tenant.id, rail="card", provider="quickbooks_payments", state="pending", version=1, provider_charge_id="existing-charge", provider_configuration_version=1)
    class ReconciliationReached(Exception):
        pass
    class HistoricalDatabase:
        async def scalar(self, *args, **kwargs):
            raise ReconciliationReached()
    # Historical GET path continues to its original configuration/auth checks;
    # no new provider charge is permitted by this admission exception.
    with pytest.raises(ReconciliationReached):
        await invoice_settlements.charge_quickbooks_settlement_attempt(
            HistoricalDatabase(), attempt=attempt, invoice=invoice, tenant=tenant,
            actor=None, payment_token="opaque", expected_attempt_version=1, idempotency_key="historical-test",
        )
