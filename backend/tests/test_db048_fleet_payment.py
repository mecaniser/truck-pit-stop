"""Fleet canonical receipts: local domain tests; no external instrument redemption."""
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import select, func

from app.api.v1.endpoints.invoice_settlements import allocation_page, read_invoice_payment_quote, settlement_summary
from app.db.models.invoice_settlement import InvoicePaymentAttempt, PaymentAccountingLink, InvoicePaymentLedgerEvent
from app.db.models.payment import Payment, PaymentMethod
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.user import UserRole
from app.schemas.invoice_settlement import PaymentAttemptCreate
from app.services import invoice_settlement_service as service
from app.services.fleet_payment_evidence import normalize_fleet_evidence, fleet_reference_fingerprint
from tests.test_db048_cash import context, pay


def evidence(provider="EFS", reference="FLEET-123", **extra):
    return dict(fleet_provider=provider, reference_number=reference, **extra)


async def create(db, ctx, *, key="fleet-create", amount="40", data=None, **kwargs):
    return await service.create_attempt(db, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=kwargs.pop("actor", ctx[1]), amount=Decimal(amount), rail="fleet_payment",
        expected_settlement_version=kwargs.pop("version", ctx[4].version), idempotency_key=key,
        source="staff", subject_type=kwargs.pop("subject_type", "staff"), subject_id=ctx[1].id,
        sender_evidence=data if data is not None else evidence(), **kwargs)


async def confirm(db, ctx, attempt, **kwargs):
    return await service.confirm_attempt(db, attempt_id=attempt.id, tenant=ctx[0],
        actor=kwargs.pop("actor", ctx[1]), expected_attempt_version=kwargs.pop("version", attempt.version),
        idempotency_key="fleet-confirm", **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,name", [("EFS", None), ("Comchek", None), ("T-Chek", None), ("Other", "Fleet Union")])
@pytest.mark.parametrize("amount", ["40", "100"])
async def test_fleet_full_partial_receipt_projection_and_staff_evidence(db_session, monkeypatch, provider, name, amount):
    ctx = await context(db_session, monkeypatch)
    data = evidence(provider, fleet_provider_name=name, authorization_number="APPROVAL-1", note="Verified by staff")
    made = await create(db_session, ctx, amount=amount, data=data)
    assert made.attempt.provider == "manual"
    assert made.attempt.provider_charge_amount == Decimal(amount)
    assert made.attempt.card_fee_amount == made.attempt.card_fee_tax_amount == 0
    assert ctx[4].active_pending_principal == Decimal(amount)
    pending = (await allocation_page(db_session, invoice=ctx[3], cursor=None, limit=25, audience="staff")).items[0]
    assert pending.sender_evidence.reference_number == "FLEET-123"
    assert pending.fleet_provider == provider and pending.authorization_number == "APPROVAL-1"
    with pytest.raises(service.SettlementDomainError):
        await pay(db_session, ctx, version=ctx[4].version)
    result = await confirm(db_session, ctx, made.attempt)
    await db_session.flush()
    assert result.payment.method == PaymentMethod.FLEET_PAYMENT
    assert result.payment.payment_provider == (name or provider)
    assert result.payment.reference_number == "FLEET-123"
    assert result.payment.authorization_number == "APPROVAL-1"
    assert result.payment.recorded_by_user_id == ctx[1].id
    assert ctx[4].confirmed_principal == Decimal(amount) and ctx[4].active_pending_principal == 0
    assert ctx[3].accounting_policy == "standard"
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 1
    assert await db_session.scalar(select(func.count()).select_from(PaymentAccountingLink)) == 1
    link = await db_session.scalar(select(PaymentAccountingLink))
    assert link.account_mapping_snapshot["check_deposit_account"]
    for audience in ("staff", "customer", "guest"):
        row = (await allocation_page(db_session, invoice=ctx[3], cursor=None, limit=25, audience=audience)).items[0]
        if audience == "staff":
            assert row.fleet_provider == provider and row.authorization_number == "APPROVAL-1"
            assert row.reference == "FLEET-123"
        else:
            assert row.fleet_provider is None and row.authorization_number is None
            assert row.reference != "FLEET-123"
    again = await confirm(db_session, ctx, made.attempt)
    assert again.replayed and again.payment.id == result.payment.id
    assert (await create(db_session, ctx, amount=amount, data=data)).replayed


@pytest.mark.parametrize("data", [
    {}, evidence("Unknown"), evidence(reference=" "), evidence("Other"),
    evidence("Other", fleet_provider_name="EFS"), evidence(fleet_provider_name="unexpected"),
    evidence(reference="a" * 256),
    {"fleet_provider": "EFS", "reference": "one", "reference_number": "two"},
    evidence(authorization_number="x" * 256), evidence(note="x" * 1001),
])
def test_fleet_invalid_evidence_request(data):
    with pytest.raises((ValidationError, ValueError)):
        PaymentAttemptCreate(amount="50", rail="fleet_payment", expected_settlement_version=1, sender_evidence=data)


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["customer", "guest", "foreign", "no_actor", "no_permission", "stale", "missing_evidence"])
async def test_fleet_creation_denials_do_not_reserve(db_session, monkeypatch, defect):
    ctx = await context(db_session, monkeypatch)
    args = {}
    if defect in {"customer", "guest"}: args["subject_type"] = defect
    if defect == "foreign":
        args["actor"] = NS(tenant_id=uuid4(), role=UserRole.GARAGE_OWNER)
    if defect == "no_actor": args["actor"] = None
    if defect == "no_permission": monkeypatch.setattr(service, "user_has_permission", lambda *args: False)
    if defect == "stale": args["version"] = 99
    if defect == "missing_evidence": args["data"] = {}
    with pytest.raises(service.SettlementDomainError): await create(db_session, ctx, **args)
    assert ctx[4].active_pending_principal == 0
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentAttempt)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["foreign", "no_permission", "stale", "reference", "amount"])
async def test_fleet_confirm_denials_preserve_reservation(db_session, monkeypatch, defect):
    ctx = await context(db_session, monkeypatch)
    made = await create(db_session, ctx)
    args = {}
    if defect == "foreign": args["actor"] = NS(tenant_id=uuid4(), role=UserRole.GARAGE_OWNER)
    if defect == "no_permission": monkeypatch.setattr(service, "user_has_permission", lambda *args: False)
    if defect == "stale": args["version"] = 99
    if defect == "reference": args["reference"] = "Different"
    if defect == "amount": args["received_principal"] = Decimal("40.01")
    with pytest.raises(service.SettlementDomainError): await confirm(db_session, ctx, made.attempt, **args)
    assert made.attempt.state == "pending" and ctx[4].active_pending_principal == 40
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 0


@pytest.mark.asyncio
async def test_duplicate_fleet_reference_and_distinct_provider(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    first = await create(db_session, ctx)
    await confirm(db_session, ctx, first.attempt)
    duplicate = await create(db_session, ctx, key="duplicate", data=evidence(reference=" fleet-123 "))
    with pytest.raises(service.SettlementDomainError, match="already been recorded"):
        await confirm(db_session, ctx, duplicate.attempt)
    assert duplicate.attempt.state == "pending"
    distinct = await create(db_session, ctx, key="distinct", amount="20", data=evidence("Comchek"))
    await confirm(db_session, ctx, distinct.attempt)
    assert ctx[4].confirmed_principal == 60


@pytest.mark.asyncio
async def test_fleet_conflicting_idempotency_and_frozen_evidence(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    made = await create(db_session, ctx)
    with pytest.raises(service.SettlementDomainError, match="different request"):
        await create(db_session, ctx, data=evidence("Comchek"))
    made.attempt.manual_evidence = normalize_fleet_evidence(evidence(reference="changed"))
    with pytest.raises(ValueError, match="immutable"): await db_session.flush()


@pytest.mark.asyncio
async def test_fleet_quote_is_fee_free_without_writes_and_not_customer_rail(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    quote = await read_invoice_payment_quote(ctx[3].id, "fleet_payment", Decimal("40"), 1, db_session, ctx[1])
    assert quote.total_amount == 40 and quote.card_fee_amount == quote.card_fee_tax_amount == 0
    for model in (InvoicePaymentAttempt, InvoicePaymentLedgerEvent, Payment, ProviderOutboxEvent):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0
    staff = await settlement_summary(db_session, ctx[4], ctx[0], audience="staff", current_user=ctx[1])
    customer = await settlement_summary(db_session, ctx[4], ctx[0], audience="customer")
    assert "fleet_payment" in staff.allowed_actions.rails
    assert "fleet_payment" not in customer.allowed_actions.rails


def test_fleet_identity_provider_scoping_and_other_alias_guard():
    assert fleet_reference_fingerprint(evidence(reference=" Ab 12 ")) == fleet_reference_fingerprint(evidence(reference="ab  12"))
    assert fleet_reference_fingerprint(evidence("EFS")) != fleet_reference_fingerprint(evidence("Comchek"))


@pytest.mark.asyncio
async def test_same_fleet_reference_is_independent_between_tenants(db_session, monkeypatch):
    first = await context(db_session, monkeypatch)
    second = await context(db_session, monkeypatch)
    for ctx in (first, second):
        made = await create(db_session, ctx)
        await confirm(db_session, ctx, made.attempt)
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 2


@pytest.mark.asyncio
async def test_new_fleet_receipt_does_not_release_historical_export_hold(db_session, monkeypatch):
    from tests.test_db048_invoice_settlements import _financial_context
    from app.services.new_receipt_accounting import authorization_matches
    from app.db.models.invoice_settlement import TenantPaymentProviderConfiguration
    original = _financial_context.__globals__["TenantPaymentProviderConfiguration"]
    monkeypatch.setitem(_financial_context.__globals__, "TenantPaymentProviderConfiguration",
        lambda **kw: original(**dict(kw, qbo_card_fee_item_id="fee-item", qbo_card_fee_tax_code_id="tax-code")))
    ctx = await context(db_session, monkeypatch)
    ctx[3].accounting_policy = "historical_export_hold"
    await db_session.flush()
    made = await create(db_session, ctx)
    config = await db_session.scalar(select(TenantPaymentProviderConfiguration).where(
        TenantPaymentProviderConfiguration.tenant_id == ctx[0].id))
    assert authorization_matches(made.attempt, config)
    await confirm(db_session, ctx, made.attempt)
    assert ctx[3].accounting_policy == "historical_export_hold"
    assert made.attempt.new_receipt_accounting_authorization is not None


def test_gross_projection_accepts_fleet_but_rejects_fleet_card_fee():
    from tests.test_db048_qbo_invoice_projection import attempt, project
    row = attempt(rail="fleet_payment", fee=Decimal(0), captured_gross=Decimal(200))
    assert project([row]).remaining_principal == 800
    with pytest.raises(ValueError, match="Non-card"):
        project([attempt(rail="fleet_payment")])


@pytest.mark.asyncio
async def test_legacy_principal_writer_uses_fleet_deposit_mapping(monkeypatch):
    from tests.test_db048_gross_accounting import envelope
    from app.services import db048_accounting_reconciliation as r
    env = envelope()
    env.attempt.rail, env.attempt.provider = "fleet_payment", "manual"
    env.attempt.manual_evidence = normalize_fleet_evidence(evidence("T-Chek"))
    env.attempt.provider_reference = "FLEET-123"
    env.attempt.applied_card_fee_amount = env.attempt.applied_card_fee_tax_amount = Decimal(0)
    env.attempt.card_fee_amount = env.attempt.card_fee_tax_amount = Decimal(0)
    env.attempt.received_amount = env.attempt.principal_amount = Decimal(100)
    env.attempt.processor_fee_amount = Decimal(0)
    env.attempt.provider_charge_amount = Decimal(100)
    env.attempt.unapplied_amount = Decimal(0)
    env.link.account_mapping_snapshot = {"check_deposit_account": "fleet-deposit", "zelle_ach_account": "not-this"}
    monkeypatch.setattr(r, "_ensure_db048_qbo_invoice", AsyncMock(return_value=("customer", "invoice")))
    monkeypatch.setattr(r, "_resolve_qbo_account_reference", AsyncMock(side_effect=lambda connection, value: value))
    monkeypatch.setattr(r, "_query", AsyncMock(return_value=[]))
    request = AsyncMock(return_value={"Payment": {"Id": "fleet-qbo-payment"}})
    monkeypatch.setattr(r, "_request", request)
    assert await r.sync_db048_payment(env) == "fleet-qbo-payment"
    payload = request.call_args.kwargs["json"]
    assert payload["DepositToAccountRef"] == {"value": "fleet-deposit"}
    assert "T-Chek" in payload["PrivateNote"] and "FLEET-123" in payload["PrivateNote"]


@pytest.mark.asyncio
async def test_fleet_qbo_presentation_gross_receipt_replay_and_mapping(monkeypatch):
    from tests.test_db048_gross_accounting import envelope, provider
    from app.services import db048_accounting_reconciliation as r, db048_qbo_gross_accounting as g
    env = envelope()
    env.attempt.rail = "fleet_payment"
    env.attempt.provider = "manual"
    env.attempt.provider_charge_id = None
    env.attempt.provider_reference = "A-VERY-LONG-FLEET-TRACE-123456"
    env.attempt.manual_evidence = normalize_fleet_evidence(evidence(reference=env.attempt.provider_reference))
    env.attempt.applied_card_fee_amount = env.attempt.applied_card_fee_tax_amount = Decimal(0)
    env.attempt.provider_charge_amount = env.attempt.applied_principal_amount
    env.attempt.unapplied_amount = Decimal(0)
    env.link.account_mapping_snapshot = {"check_deposit_account": "fleet-deposit", "zelle_ach_account": "not-this"}
    db, state = provider(monkeypatch, env)
    assert await g.sync_gross_payment(db, env) == "payment-1"
    assert state["payment"]["DepositToAccountRef"]["value"] == "fleet-deposit"
    assert state["payment"]["PaymentRefNum"].startswith("EFS ")
    assert len(state["payment"]["PaymentRefNum"]) <= 21
    assert env.attempt.provider_reference in state["payment"]["PrivateNote"]
    assert "EFS" in state["payment"]["PrivateNote"]
    assert state["payment"]["TotalAmt"] == 100
    assert await g._source_deposit_account(env, env.link) == "fleet-deposit"
    await g.sync_gross_payment(db, env)
    assert len(state["posts"]) == 2
    assert all("ProcessPayment" not in call["json"] for _, call in state["posts"])
