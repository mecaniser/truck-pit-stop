from decimal import Decimal
import pytest
from pydantic import ValidationError
from tests.test_db048_tax_exemption import setup
from tests.test_db048_payment_checkout import quote
from app.schemas.invoice_settlement import InvoiceChargeAdjustmentCreate
from app.services import invoice_charge_adjustments as charges
from app.services.invoice_tax_exemption import snapshot
from app.services.invoice_settlement_service import create_attempt, confirm_attempt, _canonical_hash, SettlementDomainError
from app.db.models.invoice_charge_adjustment import InvoiceChargeAdjustment


async def save(db, ctx, *, fee=None, supplies=True, tax=False, version=None, key=None):
    version = ctx[4].version if version is None else version
    body = InvoiceChargeAdjustmentCreate(expected_settlement_version=version,
        tax_exempt=tax, shop_supplies_enabled=supplies, card_fee_enabled=fee)
    return await charges.adjust(db, invoice=ctx[3], tenant=ctx[0], actor=ctx[1], body=body,
        idempotency_key=key or f"fee-toggle-{version}")


@pytest.mark.asyncio
@pytest.mark.parametrize("supplies,tax,expected_tax", [(True, False, "8.74"), (False, False, "8.25"),
                                                     (True, True, "0.00"), (False, True, "0.00")])
async def test_fee_waiver_combinations_and_frozen_restoration(db_session, monkeypatch, supplies, tax, expected_tax):
    ctx = await setup(db_session, monkeypatch)
    original = snapshot(ctx[3])
    ctx[0].sales_tax_rate = Decimal("99")
    await save(db_session, ctx, fee=False, supplies=supplies, tax=tax)
    assert ctx[3].service_fee_amount == 0 and ctx[3].tax_amount == Decimal(expected_tax)
    assert ctx[4].max_card_fee == ctx[4].max_card_fee_tax == 0
    state = await charges.summary(db_session, ctx[3], ctx[4], ctx[0], ctx[1], audience="staff")
    assert not state.card_fee_enabled and state.original_card_fee_amount == 3
    await save(db_session, ctx, supplies=supplies, tax=tax)  # old client/null preserves OFF
    assert ctx[3].service_fee_amount == 0 and not charges.effective_card_fee_enabled(ctx[3])
    await save(db_session, ctx, fee=True)
    assert snapshot(ctx[3]) == original and charges.effective_card_fee_enabled(ctx[3])
    await save(db_session, ctx, fee=True, supplies=False)
    assert ctx[3].service_fee_amount == Decimal("2.83") and ctx[3].tax_amount == Decimal("8.48")


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", ["10.00", "114.74"])
async def test_quote_attempt_and_confirmed_components_really_zero(db_session, monkeypatch, amount):
    ctx = await setup(db_session, monkeypatch)
    await save(db_session, ctx, fee=False)
    result = await quote(db_session, ctx, "card", amount, ctx[4].version)
    assert result.card_fee_amount == result.card_fee_tax_amount == 0
    assert result.total_amount == Decimal(amount)
    created = await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=Decimal(amount), rail="card", expected_settlement_version=ctx[4].version,
        idempotency_key="waived-card", source="staff", subject_type="staff", subject_id=ctx[1].id)
    attempt = created.attempt
    assert attempt.card_fee_amount == attempt.card_fee_tax_amount == 0
    assert attempt.provider_charge_amount == Decimal(amount)
    attempt.provider_intent_id = "pi_local_waiver_fixture"
    confirmed = await confirm_attempt(db_session, attempt_id=attempt.id, tenant=ctx[0], actor=ctx[1],
        expected_attempt_version=attempt.version, idempotency_key="confirm-waived-card",
        received_principal=Decimal(amount), reference="pi_local_waiver_fixture",
        provider_charge_id="ch_local_waiver_fixture", provider_event_id="evt_local_waiver_fixture",
        processor_fee=Decimal("1.23"))  # Local verified-fact fixture, no provider call.
    assert confirmed.attempt.applied_card_fee_amount == confirmed.attempt.applied_card_fee_tax_amount == 0
    assert confirmed.payment.amount == Decimal(amount)
    assert confirmed.attempt.processor_fee_amount == Decimal("1.23")
    from app.services.db048_qbo_invoice_projection import InvoiceIdentity, ConfirmedEarnedAttempt, project_gross_invoice
    identity = InvoiceIdentity(str(ctx[0].id), "fixture-realm", str(ctx[3].id))
    projection = project_gross_invoice(identity=identity, composition_version="gross_invoice_v1",
        principal_base=ctx[4].principal_total, attempts=[ConfirmedEarnedAttempt(identity, str(attempt.id),
            "gross_invoice_v1", "card", confirmed.attempt.applied_principal_amount,
            confirmed.attempt.applied_card_fee_amount, confirmed.attempt.applied_card_fee_tax_amount,
            confirmed.attempt.provider_charge_amount, confirmed.attempt.unapplied_amount)])
    assert projection.invoice_total == ctx[4].principal_total
    assert projection.payments[0].fee == projection.payments[0].fee_tax == 0
    with pytest.raises(SettlementDomainError):
        await save(db_session, ctx, fee=True)


@pytest.mark.asyncio
async def test_persisted_old_hash_replays_and_explicit_fee_conflicts(db_session, monkeypatch):
    ctx = await setup(db_session, monkeypatch)
    original = snapshot(ctx[3])
    old_body = dict(expected_settlement_version=1, tax_exempt=False, shop_supplies_enabled=True, support_reference=None)
    old_hash = _canonical_hash({"invoice_id": str(ctx[3].id), "actor_id": str(ctx[1].id), **old_body})
    row = InvoiceChargeAdjustment(tenant_id=ctx[0].id, invoice_id=ctx[3].id, version=2,
        idempotency_key="pre-extension", request_hash=old_hash, evidence={"original": original,
            "before": original, "after": original, "settings": {"tax_exempt": False, "shop_supplies_enabled": True}})
    ctx[3].charge_adjustments.append(row)
    db_session.add(row)
    ctx[4].version = 2
    await db_session.flush()
    await save(db_session, ctx, version=1, key="pre-extension")
    assert ctx[4].version == 2 and charges.effective_card_fee_enabled(ctx[3])
    with pytest.raises(SettlementDomainError) as conflict:
        await save(db_session, ctx, fee=False, version=1, key="pre-extension")
    assert conflict.value.code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_waived_card_refund_uses_actual_excess_without_surcharge(db_session, monkeypatch):
    ctx = await setup(db_session, monkeypatch)
    await save(db_session, ctx, fee=False)
    principal = ctx[4].principal_total
    created = await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=principal, rail="card", expected_settlement_version=ctx[4].version,
        idempotency_key="waived-refund-source", source="staff", subject_type="staff", subject_id=ctx[1].id)
    # Model an already verified excess capture locally; never submit a charge/refund.
    created.attempt.provider_intent_id = "pi_local_refund_fixture"
    created.attempt.provider_charge_amount = principal + Decimal("10")
    confirmed = await confirm_attempt(db_session, attempt_id=created.attempt.id, tenant=ctx[0], actor=ctx[1],
        expected_attempt_version=created.attempt.version, idempotency_key="waived-refund-confirm",
        received_principal=principal + Decimal("10"), reference="pi_local_refund_fixture",
        provider_charge_id="ch_local_refund_fixture", provider_event_id="evt_local_refund_fixture")
    assert confirmed.refund.amount == Decimal("10")
    assert confirmed.attempt.applied_card_fee_amount == confirmed.attempt.applied_card_fee_tax_amount == 0
    assert confirmed.payment.amount == principal


@pytest.mark.parametrize("value", ["false", "true", 0, 1, [], {}])
def test_fee_flag_is_strict(value):
    with pytest.raises(ValidationError):
        InvoiceChargeAdjustmentCreate(expected_settlement_version=1, tax_exempt=False,
            shop_supplies_enabled=True, card_fee_enabled=value)
