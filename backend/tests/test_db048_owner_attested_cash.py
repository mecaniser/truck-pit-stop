from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoicePaymentLedgerEvent
from app.db.models.payment import Payment
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.schemas.invoice_settlement import InvoiceChargeAdjustmentCreate
from app.services import invoice_charge_adjustments as charges
from app.services import invoice_cash_service as cash
from app.services.historical_export_hold import digest
from app.services.invoice_settlement_service import create_attempt, fail_attempt, get_or_create_settlement
from scripts.review_owner_attested_cash import apply_review, prepare
from tests.test_db048_cash import context, pay


async def reviewed_owner_cash(db, monkeypatch):
    ctx = await context(db, monkeypatch)
    tenant, owner, customer, invoice, _ = ctx
    invoice.accounting_policy = "historical_export_hold"
    current_event = ProviderOutboxEvent(
        tenant_id=tenant.id, aggregate_id=invoice.id, aggregate_type="quickbooks_invoice",
        event_type="quickbooks.invoice.sync.v1", status="suppressed", attempt_count=10,
        available_at=datetime.now(timezone.utc), idempotency_key="replacement-export",
        payload={"cash_export_ambiguous": True, "suppression_reason": "historical_export_hold"},
    )
    db.add(current_event)

    parent_order = RepairOrder(
        tenant_id=tenant.id, customer_id=customer.id, vehicle_id=invoice.repair_order.vehicle_id,
        order_number=f"RO-PARENT-{uuid4().hex[:10]}", status=RepairOrderStatus.INVOICED,
        total_parts_cost=Decimal("0"), total_labor_cost=Decimal("100"), total_cost=Decimal("100"),
    )
    db.add(parent_order)
    await db.flush()
    parent = Invoice(
        tenant_id=tenant.id, repair_order_id=parent_order.id,
        invoice_number="TPS-PARENT-000001", subtotal=invoice.subtotal,
        total_amount=invoice.total_amount, status=InvoiceStatus.SENT,
    )
    db.add(parent)
    await db.flush()
    parent.repair_order = parent_order
    parent_order.customer = customer
    parent_settlement = await get_or_create_settlement(db, invoice=parent, tenant=tenant, customer_id=customer.id)
    creation = await create_attempt(
        db, invoice=parent, tenant=tenant, customer_id=customer.id, actor=owner,
        amount=Decimal("100.00"), rail="card", expected_settlement_version=parent_settlement.version,
        idempotency_key="historical-card-attempt", source="staff", subject_type="staff", subject_id=owner.id,
    )
    await fail_attempt(
        db, attempt_id=creation.attempt.id, tenant_id=tenant.id, actor=owner,
        expected_attempt_version=creation.attempt.version,
        failure_code="owner_attested_no_card_payment", idempotency_key="owner-attested-retirement",
    )
    parent.accounting_policy = "historical_export_hold"
    parent.status = InvoiceStatus.CANCELLED
    parent.voided_at = datetime.now(timezone.utc)
    invoice.supersedes_invoice_id = parent.id
    db.add(ProviderOutboxEvent(
        tenant_id=tenant.id, aggregate_id=parent.id, aggregate_type="quickbooks_invoice",
        event_type="quickbooks.invoice.sync.v1", status="dead", attempt_count=3,
        available_at=datetime.now(timezone.utc), idempotency_key="parent-export",
        payload={"cash_export_ambiguous": True},
    ))
    await db.flush()

    evidence = digest({"statement": "Shop owner attested no provider payment and cash received."})
    scope = {
        "tenant_id": str(tenant.id), "invoice_id": str(invoice.id), "event_id": str(current_event.id),
        "attestation": "no_provider_payment_cash_received", "provider_verified": False,
        "attestation_source": "explicit_shop_owner_instruction", "reviewer": "release-operator",
        "evidence_manifest_sha256": evidence,
    }
    manifest = await prepare(db, scope)
    await apply_review(db, manifest, digest(manifest))
    await db.refresh(invoice, attribute_names=["repair_order"])
    await db.refresh(invoice.repair_order, attribute_names=["customer"])
    return ctx, parent, creation.attempt, current_event, manifest


async def legacy_adjusted_owner_cash(db, monkeypatch):
    """Return the exact pre-PR387 review state after one audited fee change."""
    ctx, parent, _, event, _ = await reviewed_owner_cash(db, monkeypatch)
    tenant, owner, _, invoice, settlement = ctx
    root = event.payload[cash.OWNER_CASH_REVIEW_KEY]["invoice_history_sha256"]
    await charges.adjust(db, invoice=invoice, tenant=tenant, actor=owner,
        body=InvoiceChargeAdjustmentCreate(expected_settlement_version=settlement.version,
            tax_exempt=False, shop_supplies_enabled=True, card_fee_enabled=False),
        idempotency_key="legacy-owner-reviewed-card-fee-off")
    marker = {key: value for key, value in event.payload[cash.OWNER_CASH_REVIEW_KEY].items()
              if key not in {"reviewed_invoice_history_sha256", "charge_adjustment_transitions"}}
    marker["invoice_history_sha256"] = root
    event.payload = {**event.payload, cash.OWNER_CASH_REVIEW_KEY: marker}
    await db.flush()
    return ctx, parent, event


PRE142_INVOICE_FIELDS = (
    "id", "tenant_id", "repair_order_id", "invoice_number", "accounting_policy",
    "cash_export_review_required", "is_internal", "recipient_name", "recipient_email",
    "recipient_phone", "status", "subtotal", "shop_supplies_amount", "service_fee_amount",
    "tax_amount", "tax_exemption", "discount_amount", "total_amount", "line_items_snapshot", "due_date",
    "paid_at", "ets_invoiced_at", "notes", "source", "created_by_user_id", "voided_at",
    "voided_by_user_id", "void_reason", "supersedes_invoice_id", "zelle_pending_submitted_at",
    "zelle_pending_sender_email", "zelle_pending_sender_phone", "zelle_pending_last_reminder_at",
    "zelle_pending_reminder_count", "last_reminder_sent_at", "reminder_count",
    "quickbooks_invoice_id", "quickbooks_sync_status", "quickbooks_synced_at",
    "quickbooks_sync_error", "created_at", "deleted_at",
)


def pre142_activation_digest(invoice, *, value_overrides=None, charge_adjustments=None):
    """Frozen pre-142 invoice serializer; later model columns cannot enter it."""
    values = {}
    for name in PRE142_INVOICE_FIELDS:
        value = (value_overrides[name] if value_overrides and name in value_overrides
                 else getattr(invoice, name))
        if name == "tax_exemption" and value is None:
            continue
        if isinstance(value, datetime):
            value = (value.replace(tzinfo=timezone.utc) if value.tzinfo is None
                     else value.astimezone(timezone.utc)).isoformat()
        values[name] = value
    if charge_adjustments:
        values["charge_adjustments"] = [cash.event_history_digest(row) for row in charge_adjustments]
    return sha256(json.dumps(values, sort_keys=True, default=str,
                             separators=(",", ":")).encode()).hexdigest()


@pytest.mark.asyncio
async def test_owner_review_is_exact_metadata_only_and_enables_cash(db_session, monkeypatch):
    ctx, parent, attempt, event, manifest = await reviewed_owner_cash(db_session, monkeypatch)
    reason, _ = await cash.cash_eligibility(db_session, ctx[3], ctx[4])
    assert reason is None
    assert event.status == "suppressed" and event.attempt_count == 10
    assert event.payload["cash_export_ambiguous"] is True
    assert parent.accounting_policy == "historical_export_hold"
    assert attempt.state == "failed" and attempt.received_amount is None
    assert await db_session.scalar(select(Payment.id)) is None
    assert (await apply_review(db_session, manifest, digest(manifest)))["changed_fields"] == []


@pytest.mark.asyncio
async def test_owner_review_survives_nullable_activation_column_added_after_review(db_session, monkeypatch):
    """A pre-migration ancestor proof treats a later NULL column as absent."""
    ctx, parent, _, event, _ = await reviewed_owner_cash(db_session, monkeypatch)
    review = event.payload[cash.OWNER_CASH_REVIEW_KEY]
    canonical = review["ancestor_reviews"][0]["snapshot"]["invoice_sha256"]
    legacy = pre142_activation_digest(parent)
    marker = {**review, "ancestor_reviews": [{
        **review["ancestor_reviews"][0],
        "snapshot": {**review["ancestor_reviews"][0]["snapshot"], "invoice_sha256": legacy},
    }]}
    event.payload = {**event.payload, cash.OWNER_CASH_REVIEW_KEY: marker}
    await db_session.flush()

    assert parent.qbo_shop_activation_id is None
    assert cash.event_history_digest(parent) == canonical
    assert legacy != canonical
    assert (await cash.cash_eligibility(db_session, ctx[3], ctx[4]))[0] is None

    # A production invoice cannot be enrolled after creation. Exercise the
    # non-NULL binding on a detached representation instead of issuing an
    # UPDATE that PostgreSQL's creation-only trigger correctly rejects.
    enrolled = Invoice(**{
        column.name: getattr(parent, column.name)
        for column in Invoice.__table__.columns
        if column.name not in {"id", "created_at", "updated_at"}
    })
    enrolled.id = parent.id
    enrolled.created_at = parent.created_at
    enrolled.qbo_shop_activation_id = uuid4()
    assert legacy not in cash.compatible_invoice_history_digests(enrolled)


def test_pre142_activation_digest_binds_nonnull_tax_exemption():
    invoice = Invoice(tax_exemption={"schema": "invoice-tax-exemption-v1", "reason": "Reviewed"})
    legacy = pre142_activation_digest(invoice)
    assert legacy in cash.compatible_invoice_history_digests(invoice)
    invoice.tax_exemption = {**invoice.tax_exemption, "reason": "Changed"}
    assert legacy not in cash.compatible_invoice_history_digests(invoice)
    invoice.tax_exemption = {"schema": "invoice-tax-exemption-v1", "reason": "Reviewed"}
    invoice.qbo_shop_activation_id = uuid4()
    assert legacy not in cash.compatible_invoice_history_digests(invoice)


@pytest.mark.parametrize("malformed_digest", [None, [], {}, 1, "short"])
def test_malformed_legacy_ancestor_digest_denies_safely(malformed_digest):
    invoice = Invoice()
    current = {"invoice_sha256": cash.event_history_digest(invoice)}
    proof = {"snapshot": {"invoice_sha256": malformed_digest}}
    assert cash.compatible_ancestor_snapshot(proof, current, invoice) is False


@pytest.mark.asyncio
async def test_pre142_current_review_rebinds_through_audited_charge(db_session, monkeypatch):
    ctx, _, _, event, _ = await reviewed_owner_cash(db_session, monkeypatch)
    tenant, owner, _, invoice, settlement = ctx
    review = event.payload[cash.OWNER_CASH_REVIEW_KEY]
    legacy = pre142_activation_digest(invoice)
    event.payload = {**event.payload, cash.OWNER_CASH_REVIEW_KEY: {
        **review, "invoice_history_sha256": legacy,
    }}
    await db_session.flush()

    assert cash.valid_owner_cash_review(event, invoice)
    await charges.adjust(db_session, invoice=invoice, tenant=tenant, actor=owner,
        body=InvoiceChargeAdjustmentCreate(expected_settlement_version=settlement.version,
            tax_exempt=False, shop_supplies_enabled=True, card_fee_enabled=False),
        idempotency_key="pre142-owner-reviewed-card-fee-off")

    rebound = event.payload[cash.OWNER_CASH_REVIEW_KEY]
    assert rebound["reviewed_invoice_history_sha256"] == legacy
    assert rebound["charge_adjustment_transitions"][0]["before_invoice_history_sha256"] == legacy
    assert cash.valid_owner_cash_review(event, invoice)


@pytest.mark.asyncio
async def test_pre142_explicit_charge_chain_rebinds_to_canonical_digest(db_session, monkeypatch):
    ctx, _, _, event, _ = await reviewed_owner_cash(db_session, monkeypatch)
    tenant, owner, _, invoice, settlement = ctx
    await charges.adjust(db_session, invoice=invoice, tenant=tenant, actor=owner,
        body=InvoiceChargeAdjustmentCreate(expected_settlement_version=settlement.version,
            tax_exempt=False, shop_supplies_enabled=True, card_fee_enabled=False),
        idempotency_key="pre142-explicit-chain-card-fee-off")
    row = invoice.charge_adjustments[0]
    review = event.payload[cash.OWNER_CASH_REVIEW_KEY]
    before = cash._owner_cash_amount_snapshot(row.evidence["before"])
    after = cash._owner_cash_amount_snapshot(row.evidence["after"])
    legacy_before = pre142_activation_digest(invoice, value_overrides=before,
                                             charge_adjustments=[])
    legacy_after = pre142_activation_digest(invoice, value_overrides=after,
                                            charge_adjustments=[row])
    transition = {**review["charge_adjustment_transitions"][0],
                  "before_invoice_history_sha256": legacy_before,
                  "after_invoice_history_sha256": legacy_after}
    event.payload = {**event.payload, cash.OWNER_CASH_REVIEW_KEY: {
        **review, "reviewed_invoice_history_sha256": legacy_before,
        "charge_adjustment_transitions": [transition],
        "invoice_history_sha256": legacy_after,
    }}
    await db_session.flush()

    assert cash.valid_owner_cash_review(event, invoice)
    await charges.adjust(db_session, invoice=invoice, tenant=tenant, actor=owner,
        body=InvoiceChargeAdjustmentCreate(expected_settlement_version=settlement.version,
            tax_exempt=False, shop_supplies_enabled=True, card_fee_enabled=True),
        idempotency_key="pre142-explicit-chain-card-fee-on")
    rebound = event.payload[cash.OWNER_CASH_REVIEW_KEY]
    assert rebound["charge_adjustment_transitions"][1]["before_invoice_history_sha256"] == legacy_after
    assert rebound["invoice_history_sha256"] == cash.event_history_digest(invoice)
    assert cash.valid_owner_cash_review(event, invoice)


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["event_payload", "event_provider", "event_lease", "marker_tenant", "missing_ancestor", "ancestor_provider", "ancestor_zelle", "ancestor_synced_status", "ancestor_other_outbox", "new_money"])
async def test_owner_review_rejects_drift_and_provider_or_money_evidence(db_session, monkeypatch, defect):
    ctx, _, attempt, event, _ = await reviewed_owner_cash(db_session, monkeypatch)
    if defect == "event_payload":
        event.payload = {**event.payload, "changed": True}
    elif defect == "event_provider":
        event.provider_message_id = "qbo-object"
    elif defect == "event_lease":
        event.lock_token = "active"
    elif defect == "marker_tenant":
        marker = {**event.payload[cash.OWNER_CASH_REVIEW_KEY], "tenant_id": str(uuid4())}
        event.payload = {**event.payload, cash.OWNER_CASH_REVIEW_KEY: marker}
    elif defect == "missing_ancestor":
        marker = {**event.payload[cash.OWNER_CASH_REVIEW_KEY], "ancestor_reviews": []}
        event.payload = {**event.payload, cash.OWNER_CASH_REVIEW_KEY: marker}
    elif defect == "ancestor_provider":
        attempt.provider_charge_id = "provider-charge"
    elif defect == "ancestor_zelle":
        parent = await db_session.get(Invoice, ctx[3].supersedes_invoice_id)
        parent.zelle_pending_submitted_at = datetime.now(timezone.utc)
    elif defect == "ancestor_synced_status":
        parent = await db_session.get(Invoice, ctx[3].supersedes_invoice_id)
        parent.quickbooks_sync_status = "synced"
    elif defect == "ancestor_other_outbox":
        db_session.add(ProviderOutboxEvent(
            tenant_id=ctx[0].id, aggregate_id=ctx[3].supersedes_invoice_id,
            aggregate_type="payment", event_type="payment.accounting.v1", status="dead",
            attempt_count=1, available_at=datetime.now(timezone.utc),
            idempotency_key=f"unexpected-financial-event-{uuid4()}", payload={},
        ))
    else:
        ctx[4].confirmed_principal = Decimal("1.00")
    await db_session.flush()
    assert (await cash.cash_eligibility(db_session, ctx[3], ctx[4]))[0] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["policy", "replacement", "ambiguity"])
async def test_owner_review_never_becomes_a_general_export_bypass(db_session, monkeypatch, defect):
    ctx, _, _, event, manifest = await reviewed_owner_cash(db_session, monkeypatch)
    if defect == "policy":
        ctx[3].accounting_policy = "standard"
    elif defect == "replacement":
        ctx[3].supersedes_invoice_id = None
    else:
        event.payload = {**event.payload, "cash_export_ambiguous": False}
    await db_session.flush()
    with pytest.raises(ValueError, match="Owner review is limited"):
        await prepare(db_session, manifest["scope"])
    assert (await cash.cash_eligibility(db_session, ctx[3], ctx[4]))[0] is not None


@pytest.mark.asyncio
async def test_owner_review_rejects_a_post_review_invoice_amount_change(db_session, monkeypatch):
    ctx, _, _, _, _ = await reviewed_owner_cash(db_session, monkeypatch)
    ctx[3].total_amount += Decimal("1.00")
    await db_session.flush()
    reason, _ = await cash.cash_eligibility(db_session, ctx[3], ctx[4])
    assert reason == "The owner-attested export history changed. Accounting review is required before cash."


@pytest.mark.asyncio
async def test_owner_review_allows_audited_fee_controls_and_rebinds_cash_eligibility(db_session, monkeypatch):
    ctx, _, _, event, _ = await reviewed_owner_cash(db_session, monkeypatch)
    tenant, owner, _, invoice, settlement = ctx
    controls = await charges.summary(db_session, invoice, settlement, tenant, owner, audience="staff")
    assert controls.can_adjust is True
    before = event.payload[cash.OWNER_CASH_REVIEW_KEY]["invoice_history_sha256"]
    await charges.adjust(db_session, invoice=invoice, tenant=tenant, actor=owner,
        body=InvoiceChargeAdjustmentCreate(expected_settlement_version=settlement.version,
            tax_exempt=False, shop_supplies_enabled=True, card_fee_enabled=False),
        idempotency_key="owner-reviewed-card-fee-off")
    review = event.payload[cash.OWNER_CASH_REVIEW_KEY]
    assert invoice.service_fee_amount == Decimal("0.00")
    assert review["reviewed_invoice_history_sha256"] == before
    assert review["charge_adjustment_transitions"][-1]["adjustment_version"] == settlement.version
    assert cash.valid_owner_cash_review(event, invoice)
    assert (await cash.cash_eligibility(db_session, invoice, settlement))[0] is None
    invoice.total_amount += Decimal("1.00")
    await db_session.flush()
    assert (await cash.cash_eligibility(db_session, invoice, settlement))[0] == "The owner-attested export history changed. Accounting review is required before cash."


@pytest.mark.asyncio
async def test_owner_review_reconciles_a_pre_release_audited_charge_adjustment(db_session, monkeypatch):
    """A held invoice adjusted before PR387 is usable only when its row chain closes."""
    ctx, _, event = await legacy_adjusted_owner_cash(db_session, monkeypatch)
    tenant, owner, _, invoice, settlement = ctx
    assert cash.valid_owner_cash_review(event, invoice)
    assert (await cash.cash_eligibility(db_session, invoice, settlement))[0] is None
    assert (await charges.summary(db_session, invoice, settlement, tenant, owner, audience="staff")).can_adjust is True

    # A later normal adjustment records the reconstructed chain; unrelated
    # mutation still invalidates cash rather than broadening the exception.
    await charges.adjust(db_session, invoice=invoice, tenant=tenant, actor=owner,
        body=InvoiceChargeAdjustmentCreate(expected_settlement_version=settlement.version,
            tax_exempt=False, shop_supplies_enabled=True, card_fee_enabled=True),
        idempotency_key="legacy-owner-reviewed-card-fee-on")
    review = event.payload[cash.OWNER_CASH_REVIEW_KEY]
    assert len(review["charge_adjustment_transitions"]) == 2
    assert cash.valid_owner_cash_review(event, invoice)
    assert (await cash.cash_eligibility(db_session, invoice, settlement))[0] is None
    invoice.total_amount += Decimal("1.00")
    await db_session.flush()
    assert not cash.valid_owner_cash_review(event, invoice)


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["malformed_evidence", "tenant_mismatch"])
async def test_legacy_owner_review_rejects_tampered_adjustment_chain(db_session, monkeypatch, defect):
    ctx, _, event = await legacy_adjusted_owner_cash(db_session, monkeypatch)
    invoice = ctx[3]
    row = invoice.charge_adjustments[0]
    if defect == "malformed_evidence":
        row.evidence = {**row.evidence, "after": {**row.evidence["after"], "total_amount": "999.00"}}
    else:
        row.tenant_id = uuid4()
    await db_session.flush()
    assert not cash.valid_owner_cash_review(event, invoice)
    assert (await cash.cash_eligibility(db_session, invoice, ctx[4]))[0] == (
        "The owner-attested export history changed. Accounting review is required before cash.")


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["provider", "payment", "ancestor"])
async def test_legacy_owner_review_rejects_post_reconstruction_financial_drift(db_session, monkeypatch, defect):
    ctx, parent, event = await legacy_adjusted_owner_cash(db_session, monkeypatch)
    invoice, settlement = ctx[3], ctx[4]
    if defect == "provider":
        event.provider_message_id = "unexpected-provider-object"
    elif defect == "payment":
        settlement.confirmed_principal = Decimal("1.00")
    else:
        parent.zelle_pending_submitted_at = datetime.now(timezone.utc)
    await db_session.flush()
    assert (await cash.cash_eligibility(db_session, invoice, settlement))[0] is not None


@pytest.mark.asyncio
async def test_owner_review_confirmation_never_calls_quickbooks(db_session, monkeypatch):
    from app.services import quickbooks_accounting_service as accounting

    ctx, parent, _, event, _ = await reviewed_owner_cash(db_session, monkeypatch)
    expected = event.payload[cash.OWNER_CASH_REVIEW_KEY]["ancestor_reviews"][0]["snapshot"]
    assert await cash.owner_attested_ancestor_snapshot(db_session, parent, lock=True) == expected
    assert (await cash.cash_eligibility(db_session, ctx[3], ctx[4], lock=True))[0] is None
    provider = AsyncMock(side_effect=AssertionError("owner-attested cash must not call QuickBooks"))
    monkeypatch.setattr(accounting, "_request", provider)
    await pay(db_session, ctx)
    provider.assert_not_awaited()
    assert ctx[3].accounting_policy == "local_cash_only"


@pytest.mark.asyncio
async def test_owner_review_rejects_unrelated_ancestor_ledger(db_session, monkeypatch):
    ctx, parent, _, _, _ = await reviewed_owner_cash(db_session, monkeypatch)
    ledger = await db_session.scalar(select(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.invoice_id == parent.id).limit(1))
    db_session.add(InvoicePaymentLedgerEvent(
        tenant_id=ledger.tenant_id, invoice_id=ledger.invoice_id,
        settlement_id=ledger.settlement_id, attempt_id=ledger.attempt_id,
        customer_id=ledger.customer_id, actor_user_id=ledger.actor_user_id,
        actor_name_snapshot=ledger.actor_name_snapshot, actor_role_snapshot=ledger.actor_role_snapshot,
        sequence=99, correlation_id=uuid4(), idempotency_key=f"unexpected-{uuid4()}",
        occurred_at=datetime.now(timezone.utc), event_type="payment_confirmed",
        principal_delta=Decimal("0"), pending_delta=Decimal("0"),
        unapplied_delta=Decimal("0"), refund_pending_delta=Decimal("0"),
        money_snapshot={}, evidence_snapshot={},
    ))
    await db_session.flush()
    reason, _ = await cash.cash_eligibility(db_session, ctx[3], ctx[4])
    assert "outside the owner's reviewed cash attestation" in reason
