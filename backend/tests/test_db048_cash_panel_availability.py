import pytest
from sqlalchemy import select

from app.api.v1.endpoints.invoice_settlements import settlement_summary
from app.db.models.invoice_settlement import InvoicePaymentAttempt
from app.services.invoice_accounting_policy import HISTORICAL_HOLD
from app.services.invoice_settlement_service import SettlementDomainError
from tests.test_db048_cash import context


@pytest.fixture(autouse=True)
def fee_mappings(monkeypatch):
    from tests.test_db048_invoice_settlements import _financial_context
    original = _financial_context.__globals__["TenantPaymentProviderConfiguration"]
    monkeypatch.setitem(_financial_context.__globals__, "TenantPaymentProviderConfiguration",
        lambda **kw: original(**dict(kw, qbo_card_fee_item_id="fee-item", qbo_card_fee_tax_code_id="tax-code")))


@pytest.mark.asyncio
@pytest.mark.parametrize("audience", ["staff", "customer", "guest"])
async def test_held_new_noncash_and_cash_choices_are_independent(db_session, monkeypatch, audience):
    tenant, owner, _, invoice, settlement = await context(db_session, monkeypatch)
    invoice.accounting_policy = HISTORICAL_HOLD
    await db_session.flush()
    result = await settlement_summary(db_session, settlement, tenant, audience=audience,
        current_user=owner if audience == "staff" else None)
    actions = result.allowed_actions
    assert actions.create_attempt and actions.rails == (["card", "zelle", "check", "ach", "fleet_payment"] if audience == "staff" else ["card", "zelle"])
    assert actions.confirm_manual == (audience == "staff")
    assert not actions.apply_customer_credit and not actions.retry_accounting
    assert actions.payment_unavailable_reason is None
    if audience == "staff":
        assert actions.confirm_cash and actions.cash_unavailable_reason is None
        assert actions.configure_provider and actions.resolve_overpayment and actions.authorize_early_release
    else:
        assert not actions.confirm_cash
    assert invoice.accounting_policy == HISTORICAL_HOLD
    assert await db_session.scalar(select(InvoicePaymentAttempt.id)) is None


@pytest.mark.asyncio
async def test_standard_invoice_actions_unchanged(db_session, monkeypatch):
    tenant, owner, _, _, settlement = await context(db_session, monkeypatch)
    result = await settlement_summary(db_session, settlement, tenant, audience="staff", current_user=owner)
    assert result.allowed_actions.create_attempt
    assert result.allowed_actions.rails == ["card", "zelle", "check", "ach", "fleet_payment"]
    assert result.allowed_actions.payment_unavailable_reason is None
    assert result.allowed_actions.confirm_cash


@pytest.mark.asyncio
async def test_cash_blocker_preserved_under_hold(db_session, monkeypatch):
    tenant, owner, _, invoice, settlement = await context(db_session, monkeypatch)
    invoice.accounting_policy = HISTORICAL_HOLD
    invoice.cash_export_review_required = True
    await db_session.flush()
    result = await settlement_summary(db_session, settlement, tenant, audience="staff", current_user=owner)
    assert not result.allowed_actions.confirm_cash
    assert result.allowed_actions.cash_unavailable_reason == "Previous QuickBooks accounting activity requires review before local cash."
    assert result.allowed_actions.create_attempt


@pytest.mark.asyncio
async def test_other_tenant_summary_is_not_disclosed(db_session, monkeypatch):
    _, _, _, invoice, settlement = await context(db_session, monkeypatch)
    other, owner, _, _, _ = await context(db_session, monkeypatch)
    invoice.accounting_policy = HISTORICAL_HOLD
    await db_session.flush()
    with pytest.raises(SettlementDomainError) as exc:
        await settlement_summary(db_session, settlement, other, audience="staff", current_user=owner)
    assert exc.value.code == "invoice_not_found" and exc.value.status_code == 404
