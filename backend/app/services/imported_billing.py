"""Write-free ETS observations, separate from native collectible balances."""
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import bindparam, or_, select, text, union_all

from app.core.config import settings
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment
from app.db.models.repair_order import RepairOrder
from app.schemas.imported_billing import ImportedBillingResponse
from app.services.ets_completed_outcome_source import ETSCompletionHold, amount, identifier, _time
from app.services.ets_source_evidence import latest_source_evidence, _digest

SOURCE = "easy_truck_shop_import"
CENT = Decimal("0.01")


def _value(value):
    return getattr(value, "value", value)


def _money(value):
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed < 0 or parsed != parsed.quantize(CENT):
            return None
        return parsed.quantize(CENT)
    except (InvalidOperation, ValueError, TypeError):
        return None


def supported_invoice(invoices):
    if any(i.deleted_at is not None for i in invoices):
        return None, "deleted_invoice_evidence"
    if any(i.source != SOURCE for i in invoices):
        return None, "mixed_invoice_source"
    active = [i for i in invoices if _value(i.status) != "cancelled"]
    if len(active) != 1:
        return None, "missing_or_ambiguous_invoice"
    if _money(active[0].total_amount) is None:
        return None, "invalid_invoice_total"
    return active[0], None



# Only the staff display reader may recognize these historical cleanup artifacts.
# Generic invoice selection and all accounting/outcome writers remain strict.
_LEGACY_VOID_REASON = ("Duplicate created by the ETS invoice backfill: one ETS "
                       "service invoice was attached to every repair order of that service.")
_RETIRED_INVOICE_MARKERS = (
    "quickbooks_invoice_id", "qbo_shop_activation_id", "quickbooks_sync_error",
    "quickbooks_synced_at", "voided_by_user_id", "voided_at", "supersedes_invoice_id",
    "created_by_user_id",
)
_RETIRED_PAYMENT_MARKERS = (
    "invoice_payment_attempt_id", "payment_provider", "authorization_number", "receipt_url",
    "recorded_by_user_id", "quickbooks_charge_id", "quickbooks_charge_status",
    "quickbooks_idempotency_key", "quickbooks_payment_id", "quickbooks_reconciled_at",
    "quickbooks_refund_id", "quickbooks_refund_receipt_id", "quickbooks_refunded_amount",
    "quickbooks_sync_error", "stripe_charge_id", "stripe_connected_account_id",
    "stripe_payment_intent_id", "stripe_platform_fee_amount", "stripe_platform_fee_percent",
)
_RETIRED_REFERENCE_TABLES = (
    "fleet_invoice_scope_events", "historical_invoice_decisions", "historical_invoice_evidence",
    "historical_invoice_mappings", "invoice_charge_adjustments", "invoice_payment_attempts",
    "invoice_payment_ledger_events", "invoice_receivable_attestations", "invoice_settlements",
    "payment_accounting_links", "payment_overpayments", "payment_refunds",
)


def _empty_markers(row, names):
    return all(getattr(row, name, None) in (None, "", Decimal("0")) for name in names)


def _retired_display_candidate(invoices, members):
    """Prove cleanup identity before fetching its financial/source evidence."""
    if _group_hold(members):
        return None
    active = [i for i in invoices if i.deleted_at is None and _value(i.status) != "cancelled"]
    if len(active) != 1 or any(i.source != SOURCE for i in invoices):
        return None
    canonical = active[0]
    member_map = {r.id: r for r in members}
    owner = member_map.get(canonical.repair_order_id)
    if (owner is None or canonical.tenant_id != owner.tenant_id
            or canonical.billed_customer_id not in (None, owner.customer_id)
            or _money(canonical.total_amount) is None):
        return None
    copies = [i for i in invoices if i.id != canonical.id]
    if not copies:
        return None
    for copy in copies:
        sibling = member_map.get(copy.repair_order_id)
        if (sibling is None or sibling.id == owner.id or copy.tenant_id != owner.tenant_id
                or copy.deleted_at is None or copy.updated_at != copy.deleted_at
                or _value(copy.status) != "cancelled" or copy.void_reason != _LEGACY_VOID_REASON
                or copy.invoice_number != canonical.invoice_number + "-" + sibling.order_number
                or copy.total_amount != canonical.total_amount
                or copy.billed_customer_id != canonical.billed_customer_id
                or copy.is_internal
                or copy.accounting_policy != "standard" or copy.quickbooks_sync_status not in (None, "pending")
                or not _empty_markers(copy, _RETIRED_INVOICE_MARKERS)):
            return None
    return canonical


async def _retired_reference_ids(db, tenant_id, invoice_ids):
    """One batched tenant-scoped query; any native financial reference blocks."""
    if not invoice_ids:
        return set()
    tables = Invoice.metadata.tables
    queries = [select(Invoice.supersedes_invoice_id).where(
        Invoice.tenant_id == tenant_id, Invoice.supersedes_invoice_id.in_(invoice_ids))]
    for name in _RETIRED_REFERENCE_TABLES:
        table = tables[name]
        queries.append(select(table.c.invoice_id).where(
            table.c.tenant_id == tenant_id, table.c.invoice_id.in_(invoice_ids)))
        if "payment_id" in table.c:
            queries.append(select(Payment.invoice_id).join(table, table.c.payment_id == Payment.id).where(
                table.c.tenant_id == tenant_id, Payment.tenant_id == tenant_id,
                Payment.invoice_id.in_(invoice_ids)))
    accounting = tables["payment_accounting_links"]
    queries.append(select(Payment.invoice_id).join(accounting,
        accounting.c.financial_object_id == Payment.id).where(accounting.c.tenant_id == tenant_id,
        Payment.tenant_id == tenant_id, Payment.invoice_id.in_(invoice_ids)))
    queries.append(select(accounting.c.financial_object_id).where(accounting.c.tenant_id == tenant_id,
        accounting.c.financial_object_id.in_(invoice_ids)))
    return set((await db.execute(union_all(*queries))).scalars().all())


def _retired_display_verified(rows, canonical, summary, payments, blocked, evidence):
    if (summary.evidence_basis != "ets_source_snapshot"
            or summary.payment_status not in {"paid", "partially_paid", "unpaid"}
            or summary.total_amount != canonical.total_amount):
        return False
    for copy in rows:
        if copy.id == canonical.id:
            continue
        if copy.id in blocked or evidence.get(copy.id):
            return False
        for payment in payments.get(copy.id, []):
            amount = _money(payment.amount)
            if (payment.tenant_id != copy.tenant_id or payment.invoice_id != copy.id
                    or payment.source != SOURCE or _value(payment.status) != "failed"
                    or payment.deleted_at != copy.deleted_at or payment.updated_at != copy.deleted_at
                    or amount is None or amount <= 0
                    or not _empty_markers(payment, _RETIRED_PAYMENT_MARKERS)):
                return False
    return True


def _source_summary(invoice, envelope, order, shop_id):
    """Observe source arithmetic without promoting it to settlement authority."""
    if not shop_id or not order:
        raise ETSCompletionHold("source_identity_unavailable")
    if (not isinstance(envelope, dict) or envelope.get("schema_version") != 1
            or envelope.get("source_read_unavailable_at") or envelope.get("revision_capacity_exceeded")):
        raise ETSCompletionHold("source_read_unavailable")
    rows = envelope.get("observations")
    if not isinstance(rows, list) or not rows or len(rows) > 39:
        raise ETSCompletionHold("source_evidence_unavailable")
    confirmation = envelope.get("latest_confirmation")
    if confirmation is not None:
        last = rows[-1].get("evidence") if isinstance(rows[-1], dict) else None
        if (not isinstance(confirmation, dict) or not isinstance(last, dict)
                or confirmation.get("sha256") != _digest(last)):
            raise ETSCompletionHold("source_confirmation_invalid")
        now = datetime.now(timezone.utc)
        confirmed_at = datetime.fromisoformat(_time(confirmation.get("observed_at_source"), now))
        previous_at = datetime.fromisoformat(_time(last.get("observed_at_source"), now))
        if confirmed_at < previous_at:
            raise ETSCompletionHold("source_confirmation_invalid")
    keys = ("service_id", "invoice_id", "invoice_number", "service_internal_id", "invoice_service_id", "ets_shop_id")
    latest = latest_source_evidence(envelope)
    for row in rows:
        facts = row.get("evidence")
        if not isinstance(facts, dict) or row.get("sha256") != _digest(facts) or any(facts.get(k) != latest.get(k) for k in keys):
            raise ETSCompletionHold("source_identity_mismatch")
    if (order.source != SOURCE or order.deleted_at is not None or invoice.tenant_id != order.tenant_id
            or invoice.repair_order_id != order.id or latest.get("source") != "easy_truck_shop"
            or latest.get("ets_shop_id") != shop_id):
        raise ETSCompletionHold("source_identity_mismatch")
    service = identifier(latest.get("service_id"))
    internal = identifier(latest.get("service_internal_id"))
    source_invoice_id = identifier(latest.get("invoice_id"))
    if (not service.isdigit() or not re.fullmatch(rf"ETS-{re.escape(service)}-[0-9]+(?:-[0-9]+)?", order.order_number)
            or latest.get("invoice_service_id") != internal
            or invoice.invoice_number != "ETSINV-" + identifier(latest.get("invoice_number"))):
        raise ETSCompletionHold("source_identity_mismatch")
    manifest = latest.get("invoice_manifest")
    if (not isinstance(manifest, dict) or manifest.get("complete") is not True
            or manifest.get("evidence_kind") != "verified_source_service_invoice_manifest"
            or manifest.get("service_internal_id") != internal or manifest.get("invoice_ids") != [source_invoice_id]):
        raise ETSCompletionHold("source_invoice_manifest_unverified")
    observed = _time(latest.get("observed_at_source"), datetime.now(timezone.utc))
    total, balance = amount(latest.get("total")), amount(latest.get("balance"))
    if total <= 0 or balance > total or latest.get("currency") != "USD" or latest.get("payment_lines_truncated") is not False:
        raise ETSCompletionHold("allocation_evidence_incomplete")
    if str(latest.get("invoice_status")) != ("10" if balance == 0 else "5"):
        raise ETSCompletionHold("unsupported_invoice_status")
    lines = latest.get("payment_lines")
    if not isinstance(lines, list) or len(lines) > 200:
        raise ETSCompletionHold("allocation_evidence_incomplete")
    allocations, paid = set(), Decimal("0.00")
    payment_totals, payment_allocations = {}, {}
    for line in lines:
        allocation_id = identifier(line.get("id"))
        if allocation_id in allocations:
            raise ETSCompletionHold("duplicate_allocation")
        allocations.add(allocation_id)
        p = line.get("payment") or {}
        allocated, payment_total = amount(line.get("amount")), amount(p.get("total"))
        payment_id = identifier(p.get("id"))
        if (str(p.get("status")) != "20" or str(p.get("type")) not in {"0", "10"}
                or str(p.get("provider")) not in {"0", "1"} or p.get("canceled") is not False
                or amount(p.get("credit_total")) != 0 or amount(p.get("unapplied_amount")) != 0
                or allocated <= 0 or payment_total <= 0):
            raise ETSCompletionHold("unsupported_payment_state")
        if payment_id in payment_totals:
            raise ETSCompletionHold("duplicate_payment_identity")
        payment_totals[payment_id] = payment_total
        payment_allocations[payment_id] = payment_allocations.get(payment_id, Decimal("0")) + allocated
        if payment_allocations[payment_id] > payment_total:
            raise ETSCompletionHold("payment_overallocated")
        paid += allocated
    if paid != total - balance:
        raise ETSCompletionHold("allocation_balance_mismatch")
    response = ImportedBillingResponse(invoice_id=invoice.id, invoice_number=invoice.invoice_number,
        total_amount=total, recorded_completed_amount=paid, recorded_remaining_amount=balance,
        payment_status="paid" if balance == 0 else ("partially_paid" if paid > 0 else "unpaid"),
        evidence_basis="ets_source_snapshot", observed_at=datetime.fromisoformat(observed), review_required=False)
    if datetime.now(timezone.utc) - response.observed_at > timedelta(hours=24):
        response.payment_status = "unverified"
        response.recorded_completed_amount = response.recorded_remaining_amount = None
        response.review_required = True
        response.review_reasons = ["stale_source_observation"]
    return response


def summarize_imported_billing(invoices, payments, source_evidence=None, *, order=None, shop_id=None, shop_error=None):
    invoice, reason = supported_invoice(invoices)
    if reason:
        return ImportedBillingResponse(review_reasons=[reason])
    total = _money(invoice.total_amount)
    response = ImportedBillingResponse(invoice_id=invoice.id, invoice_number=invoice.invoice_number,
        total_amount=total, observed_at=invoice.updated_at)
    reasons, completed = [], Decimal("0.00")
    for p in payments:
        if p.invoice_id != invoice.id or p.tenant_id != invoice.tenant_id:
            reasons.append("payment_identity_mismatch")
            continue
        parsed = _money(p.amount)
        if p.source != SOURCE: reasons.append("mixed_payment_source")
        if p.deleted_at is not None: reasons.append("deleted_payment_evidence")
        if _value(p.status) != "completed": reasons.append("noncompleted_payment_evidence")
        if any(getattr(p, k, None) not in (None, "", Decimal("0")) for k in
               ("quickbooks_refund_id", "quickbooks_refund_receipt_id", "quickbooks_refunded_amount")):
            reasons.append("refund_evidence")
        if parsed is None or parsed <= 0: reasons.append("invalid_payment_amount")
        if not reasons: completed += parsed
    if total <= 0: reasons.append("nonpositive_invoice_total")
    if completed > total: reasons.append("overpayment_evidence")
    status = _value(invoice.status)
    if not reasons:
        if completed == total and status == "paid":
            response.payment_status, response.review_required = "paid", False
        elif 0 < completed < total and status in ("sent", "overdue"):
            response.payment_status, response.review_required = "partially_paid", False
        elif completed == 0 and status in ("sent", "overdue"):
            response.payment_status = "unpaid"
            reasons.append("source_payment_coverage_unconfirmed")
        else: reasons.append("invoice_payment_status_mismatch")
        if response.payment_status != "unverified":
            response.recorded_completed_amount, response.recorded_remaining_amount = completed, total-completed
    response.review_reasons = list(dict.fromkeys(reasons))
    if source_evidence is not None:
        try:
            if shop_error:
                raise ETSCompletionHold(shop_error)
            observed = _source_summary(invoice, source_evidence, order, shop_id)
            if (observed.total_amount != response.total_amount
                    or observed.recorded_completed_amount != response.recorded_completed_amount
                    or observed.payment_status != response.payment_status):
                observed.review_required = True
                observed.review_reasons.append("imported_financial_rows_differ")
            hard_conflicts = {"payment_identity_mismatch", "mixed_payment_source",
                              "deleted_payment_evidence", "noncompleted_payment_evidence", "refund_evidence"}.intersection(reasons)
            if any(_value(p.status) == "refunded" for p in payments):
                hard_conflicts.add("refund_evidence")
            if hard_conflicts:
                observed.payment_status = "unverified"
                observed.recorded_completed_amount = observed.recorded_remaining_amount = None
                observed.review_required = True
                observed.review_reasons.extend(sorted(hard_conflicts))
            return observed
        except (ETSCompletionHold, AttributeError, TypeError, ValueError, InvalidOperation) as exc:
            response.payment_status = "unverified"
            response.review_required = True
            response.recorded_completed_amount = response.recorded_remaining_amount = None
            response.review_reasons.append(str(exc) if isinstance(exc, ETSCompletionHold) else "invalid_source_evidence")
    else:
        # Missing historical payments cannot establish current source debt.
        # Only a complete fresh source observation owns payment-state labels.
        response.payment_status = "unverified"
        response.recorded_completed_amount = response.recorded_remaining_amount = None
        response.review_required = True
        if "source_payment_coverage_unconfirmed" not in response.review_reasons:
            response.review_reasons.append("source_payment_coverage_unconfirmed")
    return response


def trusted_shop_binding(tenant_id):
    try:
        def parse(raw):
            mapping = json.loads(raw)
            if not isinstance(mapping, dict):
                raise ValueError()
            return {str(UUID(key)): identifier(value) for key, value in mapping.items()}
        dedicated = parse(settings.ETS_IMPORTED_BILLING_SHOPS)
        completion = parse(settings.ETS_COMPLETED_OUTCOME_SHOPS)
        key = str(tenant_id)
        if key in dedicated and key in completion and dedicated[key] != completion[key]:
            return None, "source_shop_binding_conflict"
        shop = dedicated.get(key) or completion.get(key)
        return shop, None if shop else "source_identity_unavailable"
    except (KeyError, ValueError, TypeError, AttributeError, ETSCompletionHold):
        return None, "source_shop_binding_unavailable"


async def _source_evidence(db, tenant_id, invoice_ids):
    if not invoice_ids or db.bind.dialect.name != "postgresql":
        return {}
    statement = text("""SELECT i.id, to_jsonb(i)->'ets_source_evidence' AS evidence
        FROM invoices i WHERE i.tenant_id=:tenant_id AND i.id IN :invoice_ids""").bindparams(bindparam("invoice_ids", expanding=True))
    rows = (await db.execute(statement, {"tenant_id":tenant_id,"invoice_ids":invoice_ids})).all()
    result = {}
    for row in rows:
        evidence = row.evidence
        if isinstance(evidence, str):
            try: evidence = json.loads(evidence)
            except ValueError: pass
        result[row.id] = evidence
    return result


def _job_key(order):
    match = re.fullmatch(r"(ETS-[0-9]+-[0-9]+)(?:-[0-9]+)?", getattr(order, "order_number", "") or "")
    return match.group(1) if match else None


def _group_hold(members):
    if any(row.source != SOURCE or row.deleted_at is not None for row in members):
        return "shared_job_source_conflict"
    identities = {(row.customer_id, row.vehicle_id) for row in members}
    if len(identities) != 1 or any(customer is None or vehicle is None for customer, vehicle in identities):
        return "shared_job_identity_conflict"
    return None


async def _load_billing_batch(db, orders, tenant_id):
    """Resolve invoice context once per job, without changing financial ownership.

    Candidate orders deliberately include deleted/native rows: a conflicting
    apparent sibling must hold the group, not silently disappear from evidence.
    Queries are bounded per page rather than repeated per operation.
    """
    results = {}
    valid = []
    for order in orders:
        if (order.tenant_id != tenant_id or order.source != SOURCE
                or order.deleted_at is not None or not _job_key(order)):
            results[order.id] = ImportedBillingResponse(review_reasons=["source_identity_unavailable"])
        else:
            valid.append(order)
    if not valid:
        return results
    keys = {_job_key(order) for order in valid}
    predicates = [predicate for key in keys for predicate in
                  (RepairOrder.order_number == key, RepairOrder.order_number.like(key + "-%"))]
    candidates = list((await db.scalars(select(RepairOrder).where(
        RepairOrder.tenant_id == tenant_id, or_(*predicates)).limit(2001))).all())
    if len(candidates) > 2000:
        results.update({order.id: ImportedBillingResponse(review_reasons=["shared_job_capacity_exceeded"])
                        for order in valid})
        return results
    groups = {}
    for candidate in candidates:
        key = _job_key(candidate)
        if candidate.tenant_id == tenant_id and key in keys:
            groups.setdefault(key, []).append(candidate)
    eligible, holds, identity_conflicts = {}, {}, set()
    for order in valid:
        key = _job_key(order)
        members = groups.get(key, [])
        reason = _group_hold(members) if members else "source_identity_unavailable"
        if not any(member.id == order.id for member in members):
            reason = "source_identity_unavailable"
        if reason == "shared_job_identity_conflict":
            # A sibling identity mismatch forbids sharing, but must not erase
            # the valid invoice already owned by a directly linked order.
            # Inspect the entire group's invoices before preserving that owner.
            identity_conflicts.add(key)
            eligible[key] = members
        elif reason:
            holds[key] = reason
        else:
            eligible[key] = members
    ids = [member.id for members in eligible.values() for member in members]
    invoices = list((await db.scalars(select(Invoice).where(
        Invoice.tenant_id == tenant_id, Invoice.repair_order_id.in_(ids), Invoice.accounting_policy != "source_collection_hold"))).all()) if ids else []
    by_order = {}
    for invoice in invoices:
        by_order.setdefault(invoice.repair_order_id, []).append(invoice)
    canonical, retired_candidates = {}, set()
    for key, members in eligible.items():
        rows = [invoice for member in members for invoice in by_order.get(member.id, [])]
        invoice, reason = supported_invoice(rows)
        if reason == "deleted_invoice_evidence":
            candidate = _retired_display_candidate(rows, members)
            if candidate is not None:
                invoice, reason = candidate, None
                retired_candidates.add(key)
        if reason:
            holds[key] = reason
            continue
        owner = next(member for member in members if member.id == invoice.repair_order_id)
        if owner.customer_id is None or owner.vehicle_id is None:
            holds[key] = "source_identity_unavailable"
            continue
        if getattr(invoice, "billed_customer_id", None) not in (None, owner.customer_id):
            holds[key] = "invoice_customer_identity_mismatch"
            continue
        canonical[key] = (rows, invoice, owner, len(members) > 1 and key not in identity_conflicts)
    invoice_ids = [value[1].id for value in canonical.values()]
    retired_ids = [row.id for key in retired_candidates for row in canonical[key][0]
                   if row.id != canonical[key][1].id]
    payment_invoice_ids = invoice_ids + retired_ids
    payments = list((await db.scalars(select(Payment).where(
        Payment.tenant_id == tenant_id, Payment.invoice_id.in_(payment_invoice_ids)))).all()) if payment_invoice_ids else []
    by_invoice = {}
    for payment in payments:
        by_invoice.setdefault(payment.invoice_id, []).append(payment)
    blocked_retired = await _retired_reference_ids(db, tenant_id, retired_ids)
    evidence = await _source_evidence(db, tenant_id, payment_invoice_ids)
    shop, shop_error = trusted_shop_binding(tenant_id)
    summaries = {}
    for key, (rows, invoice, owner, shared) in canonical.items():
        summary = summarize_imported_billing([invoice] if key in retired_candidates else rows, by_invoice.get(invoice.id, []), evidence.get(invoice.id),
            order=owner, shop_id=shop, shop_error=shop_error)
        if key in retired_candidates and not _retired_display_verified(
                rows, invoice, summary, by_invoice, blocked_retired, evidence):
            holds[key] = "deleted_invoice_evidence"
            continue
        summary.invoice_repair_order_id = owner.id
        summary.invoice_repair_order_number = owner.order_number
        summary.shared_invoice = shared
        if key in identity_conflicts:
            summary.review_required = True
            summary.review_reasons.append("shared_job_identity_conflict")
        summaries[key] = summary
    for order in valid:
        key = _job_key(order)
        if key in holds:
            results[order.id] = ImportedBillingResponse(review_reasons=[holds[key]])
        elif key in identity_conflicts and order.id != summaries[key].invoice_repair_order_id:
            results[order.id] = ImportedBillingResponse(review_reasons=["shared_job_identity_conflict"])
        else:
            results[order.id] = summaries[key].model_copy(deep=True)
    return results


async def load_imported_billing(db, order):
    return (await _load_billing_batch(db, [order], order.tenant_id))[order.id]


async def attach_imported_invoice_totals(db, items, actor):
    """Staff-only, non-additive shared invoice context; no financial writes."""
    from app.services.parts_pricing import STAFF
    if actor.role not in STAFF:
        return
    imported = [item for item in items if item.source == SOURCE and item.tenant_id == actor.tenant_id and item.deleted_at is None]
    if not imported:
        return
    summaries = await _load_billing_batch(db, imported, actor.tenant_id)
    for item in imported:
        item.imported_billing = summaries[item.id]
        item.imported_invoice_total_amount = item.imported_billing.total_amount
