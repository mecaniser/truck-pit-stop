"""New-only accounting composition selection and immutable mapping snapshots."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models.invoice import InvoiceStatus
from app.db.models.invoice_settlement import PaymentAccountingLink, TenantPaymentProviderConfiguration
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.schemas.invoice_settlement import CardProviderConfigurationUpdate
from app.services.invoice_settlement_service import _configuration_mappings, get_or_create_settlement, provider_readiness
from test_db048_invoice_settlements import _financial_context


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_new_settlement_selects_explicit_composition(db_session, monkeypatch, enabled):
    tenant, _, customer, invoice = await _financial_context(db_session, monkeypatch)
    monkeypatch.setattr(settings, "DB048_GROSS_QBO_ACCOUNTING_ENABLED", enabled)
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    assert settlement.accounting_composition_version == ("gross_invoice_v1" if enabled else "legacy_principal_v1")
    assert settlement.accounting_projection_snapshot == {}
    assert settlement.accounting_fee_line_ids == {}
    assert settlement.accounting_projection_revision is None
    monkeypatch.setattr(settings, "DB048_GROSS_QBO_ACCOUNTING_ENABLED", not enabled)
    again = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    assert again.id == settlement.id
    assert again.accounting_composition_version == settlement.accounting_composition_version


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["qbo_invoice", "paid", "payment", "accounting_link"])
async def test_existing_history_never_migrates(db_session, monkeypatch, history):
    tenant, _, customer, invoice = await _financial_context(db_session, monkeypatch)
    monkeypatch.setattr(settings, "DB048_GROSS_QBO_ACCOUNTING_ENABLED", True)
    if history == "qbo_invoice":
        invoice.quickbooks_invoice_id = "123"
    elif history == "paid":
        invoice.status = InvoiceStatus.PAID
    elif history == "payment":
        db_session.add(Payment(tenant_id=tenant.id, invoice_id=invoice.id,
            payment_number=f"legacy-{uuid4().hex[:12]}", amount=Decimal("1"),
            method=PaymentMethod.ZELLE, status=PaymentStatus.COMPLETED))
    else:
        db_session.add(PaymentAccountingLink(tenant_id=tenant.id, invoice_id=invoice.id,
            financial_object_type="payment", financial_object_id=uuid4(), operation_version=1,
            owning_writer="dieselbridge", account_mapping_snapshot={}))
    await db_session.flush()
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    assert settlement.accounting_composition_version == "legacy_principal_v1"


@pytest.mark.asyncio
async def test_composition_is_immutable(db_session, monkeypatch):
    tenant, _, customer, invoice = await _financial_context(db_session, monkeypatch)
    monkeypatch.setattr(settings, "DB048_GROSS_QBO_ACCOUNTING_ENABLED", False)
    settlement = await get_or_create_settlement(db_session, invoice=invoice, customer_id=customer.id, tenant=tenant)
    with pytest.raises(ValueError, match="composition is immutable"):
        async with db_session.begin_nested():
            settlement.accounting_composition_version = "gross_invoice_v1"
            await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["qbo_card_fee_item_id", "qbo_card_fee_tax_code_id"])
async def test_new_mapping_requires_new_configuration_version(db_session, monkeypatch, field):
    tenant, _, _, _ = await _financial_context(db_session, monkeypatch)
    config = await db_session.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == tenant.id))
    assert _configuration_mappings(config)[field] is None
    with pytest.raises(ValueError, match="frozen fields"):
        async with db_session.begin_nested():
            setattr(config, field, "123")
            await db_session.flush()


def test_configuration_schema_carries_explicit_item_and_tax_code():
    body = CardProviderConfigurationUpdate(provider="quickbooks_payments",
        qbo_card_fee_item_id="101", qbo_card_fee_tax_code_id="102")
    assert body.model_dump()["qbo_card_fee_item_id"] == "101"
    assert body.model_dump()["qbo_card_fee_tax_code_id"] == "102"


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["same_tenant_gross", "other_tenant_gross", "same_tenant_legacy"])
async def test_flag_off_retains_gross_mapping_requirements_only_for_own_tenant(db_session, monkeypatch, history):
    tenant, _, customer, invoice = await _financial_context(db_session, monkeypatch)
    target_tenant, target_customer, target_invoice = tenant, customer, invoice
    if history == "other_tenant_gross":
        target_tenant, _, target_customer, target_invoice = await _financial_context(db_session, monkeypatch)
    monkeypatch.setattr(settings, "DB048_GROSS_QBO_ACCOUNTING_ENABLED", history != "same_tenant_legacy")
    await get_or_create_settlement(db_session, invoice=target_invoice,
        customer_id=target_customer.id, tenant=target_tenant)
    monkeypatch.setattr(settings, "DB048_GROSS_QBO_ACCOUNTING_ENABLED", False)
    readiness = await provider_readiness(db_session, tenant)
    missing = history == "same_tenant_gross"
    assert readiness.mappings_ready is not missing
    assert ("account_mappings_incomplete" in readiness.reasons) is missing
