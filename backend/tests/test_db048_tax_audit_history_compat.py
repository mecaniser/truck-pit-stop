"""Persisted pre-143 ancestor proofs survive only the additive NULL audit."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json

import pytest

from app.db.models.invoice import Invoice
from app.services import invoice_cash_service as cash
from app.services import invoice_tax_exemption as tax
from app.services.invoice_settlement_service import invoice_money_snapshot
from tests.test_db048_reviewed_sandbox_cash import reviewed


def pre143_invoice_digest(invoice):
    # Frozen old serializer: the pre-143 schema had no tax_exemption column.
    # Deliberately independent of the production digest function.
    values = {}
    for column in Invoice.__table__.columns:
        if column.name in {"updated_at", "tax_exemption"}:
            continue
        value = getattr(invoice, column.name)
        if isinstance(value, datetime):
            value = (value.replace(tzinfo=timezone.utc) if value.tzinfo is None
                     else value.astimezone(timezone.utc)).isoformat()
        values[column.name] = value
    return sha256(json.dumps(values, sort_keys=True, default=str,
                             separators=(",", ":")).encode()).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", [None, "audit", "financial", "other_null"])
async def test_persisted_pre143_review_cash_and_tax_eligibility(db_session, monkeypatch, drift):
    ctx, queued, *_ = await reviewed(db_session, monkeypatch, local_void_parent=True)
    invoice, settlement = ctx[3:]
    parent = await db_session.get(Invoice, invoice.supersedes_invoice_id)
    legacy_digest = pre143_invoice_digest(parent)
    marker = deepcopy(queued.payload[cash.CASH_REVIEW_KEY])
    marker["ancestor_reviews"][0]["snapshot"]["invoice_sha256"] = legacy_digest
    queued.payload = {**queued.payload, cash.CASH_REVIEW_KEY: marker}
    invoice.tax_amount = Decimal("8.50")
    invoice.total_amount += Decimal("8.50")
    principal, fee, fee_tax, rate, fee_rate = invoice_money_snapshot(invoice)
    settlement.principal_total, settlement.max_card_fee, settlement.max_card_fee_tax = principal, fee, fee_tax
    settlement.sales_tax_rate_snapshot, settlement.card_fee_rate_snapshot = rate, fee_rate
    await db_session.flush()
    # Reload the persisted old proof rather than regenerate it using new code.
    await db_session.refresh(queued)
    assert queued.payload[cash.CASH_REVIEW_KEY]["ancestor_reviews"][0]["snapshot"]["invoice_sha256"] == legacy_digest
    assert cash.event_history_digest(parent) == legacy_digest
    if drift == "audit":
        parent.tax_exemption = {"schema": "invoice-tax-exemption-v1", "reason": "Changed audit"}
    elif drift == "financial":
        parent.total_amount += 1
    elif drift == "other_null":
        parent.quickbooks_sync_error = "Changed historical error"
    await db_session.flush()
    cash_reason, _ = await cash.cash_eligibility(db_session, invoice, settlement)
    tax_reason = await tax.eligibility(db_session, invoice, settlement)
    if drift:
        assert cash.event_history_digest(parent) != legacy_digest
        assert cash_reason is not None and tax_reason is not None
    else:
        assert cash_reason is None and tax_reason is None


def test_nonnull_audit_is_digest_bound():
    parent = Invoice(tax_exemption={"schema": "invoice-tax-exemption-v1", "reason": "Original"})
    original = cash.event_history_digest(parent)
    parent.tax_exemption = {**parent.tax_exemption, "reason": "Tampered"}
    assert cash.event_history_digest(parent) != original
    parent.tax_exemption = None
    assert cash.event_history_digest(parent) == pre143_invoice_digest(parent)
    assert cash.event_history_digest(parent) != original
