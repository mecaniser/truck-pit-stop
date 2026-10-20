from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
import hashlib
import json
import re
from uuid import UUID

VERSION = "db136-v1"
ACTIVATION_DATE = "2026-10-20"
ZERO = Decimal("0")
CENT = Decimal(".01")


def canonical(value):
    if isinstance(value, dict):
        return {str(key): canonical(item) for key, item in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    if isinstance(value, datetime):
        return stamp(value)
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def digest(value):
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def moment(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone required")
    return value.astimezone(timezone.utc)


def stamp(value):
    return moment(value).isoformat().replace("+00:00", "Z")


def money(value):
    return str(Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP))


def decimal(value):
    if isinstance(value, (float, bool)) or value is None:
        raise ValueError("unknown decimal")
    text = str(value)
    if len(text) > 64 or not re.fullmatch(r"\d+(?:\.\d+)?", text):
        raise ValueError("invalid decimal representation")
    result = Decimal(text)
    if not result.is_finite() or result < 0:
        raise ValueError("invalid decimal")
    return result


def micros(start, end):
    difference = end - start
    return (difference.days * 86400 + difference.seconds) * 1000000 + difference.microseconds


def seconds(start, end):
    return max(0, micros(start, end) // 1000000)


def intersects(start, end, other):
    try:
        left = moment(other["started_at"])
        right = moment(other["ended_at"]) if other.get("ended_at") else datetime.max.replace(tzinfo=timezone.utc)
        # Invalid intervals remain conflicting source evidence when their
        # timestamp lies inside the candidate; never silently discard them.
        return start < right and left < end or (right <= left and start <= left < end)
    except (ValueError, TypeError, KeyError):
        return True


def attendance_covers(start, end, attendance):
    intervals = []
    for row in attendance:
        if row.get("deleted_at") or not row.get("ended_at"):
            continue
        try:
            a, b = moment(row["started_at"]), moment(row["ended_at"])
            if a < b and a < end and start < b:
                intervals.append((max(start, a), min(end, b)))
        except (ValueError, TypeError):
            continue
    covered = start
    for left, right in sorted(intervals):
        if left > covered:
            return False
        covered = max(covered, right)
    return covered >= end


def relevant_attendance_audits(bundle, session, start, end):
    linked_ids = {row["id"] for row in bundle["attendance"] if row["mechanic_id"] == session["mechanic_id"] and intersects(start, end, row)}
    linked_breaks = {row["id"] for row in bundle["breaks"] if row["mechanic_id"] == session["mechanic_id"] and intersects(start, end, row)}
    result = []
    for audit in bundle["attendance_audits"]:
        if audit["mechanic_id"] != session["mechanic_id"]:
            continue
        snapshot_intersects = any(isinstance(audit.get(key), dict) and audit[key].get("started_at")
                                  and intersects(start, end, audit[key]) for key in ("before_snapshot", "after_snapshot"))
        if audit.get("attendance_session_id") in linked_ids or audit.get("break_session_id") in linked_breaks or snapshot_intersects:
            result.append(audit)
    return result


def discount_allocation(lines, subtotal):
    gross = sum((line[2] for line in lines), ZERO)
    if subtotal < 0 or subtotal > gross:
        raise ValueError("issued discount basis")
    discount_cents = int((gross - subtotal) * 100)
    shares = []
    for kind, index, amount in lines:
        exact = Decimal(discount_cents) * amount / gross if gross else ZERO
        floor = int(exact.to_integral_value(rounding=ROUND_FLOOR))
        shares.append([kind, index, amount, floor, exact - floor])
    remainder = discount_cents - sum(item[3] for item in shares)
    for item in sorted(shares, key=lambda item: (-item[4], 0 if item[0] == "labor" else 1, item[1]))[:remainder]:
        item[3] += 1
    return [{"kind": kind, "snapshot_index": index, "gross": money(amount),
             "allocated_discount": money(Decimal(allocated) / 100),
             "net": money(amount - Decimal(allocated) / 100)} for kind, index, amount, allocated, _ in shares]


def revenue_and_expenses(bundle):
    order, invoices = bundle["order"], bundle["invoices"]
    revenue = {"basis": "issued_native_net_direct_v1", "status": "unavailable", "net_direct_revenue": None,
               "issued_discount": None, "tax": None, "fees": None, "supplies": None, "hold_reasons": []}
    parts = {"status": "unavailable", "known_cost": None, "line_count": 0, "missing_cost_line_count": 0}
    sublet = dict(parts)
    reasons, allocation = [], []
    if order.get("is_internal") or order.get("is_warranty_repair"):
        reasons.append("internal_or_warranty_revenue_unavailable")
    finalized = [row for row in invoices if not row.get("deleted_at") and not row.get("voided_at")
                 and not row.get("is_internal") and row["status"] in {"sent", "overdue", "paid"}]
    if len(finalized) != 1:
        revenue["status"] = "provisional" if not finalized else "unavailable"
        reasons.append("issued_invoice_missing_or_ambiguous")
    if reasons:
        revenue["hold_reasons"] = reasons
        return revenue, parts, sublet, allocation
    invoice = finalized[0]
    if (invoice.get("source") == "easy_truck_shop_import" or invoice.get("accounting_policy") == "historical_export_hold"
            or invoice.get("billed_customer_id") != bundle["customer"].get("id")
            or not invoice.get("billed_customer_id") or bundle["customer"].get("deleted_at")):
        reasons.append("issued_identity_unresolved")
    if invoice.get("supersedes_invoice_id") or any(row.get("supersedes_invoice_id") for row in invoices):
        reasons.append("invoice_revision_economics_unresolved")
    try:
        snapshot = invoice.get("line_items_snapshot")
        if not isinstance(snapshot, dict) or type(snapshot.get("version")) is not int or snapshot["version"] != 1:
            raise ValueError("snapshot")
        snapshot_labor, snapshot_parts = snapshot.get("labor"), snapshot.get("parts")
        if not isinstance(snapshot_labor, list) or not isinstance(snapshot_parts, list) or len(snapshot_labor) + len(snapshot_parts) > 20000:
            raise ValueError("snapshot bounds")
        lines = [(kind, index, decimal(item[field])) for kind, items, field in (
            ("labor", snapshot_labor, "total_cost"), ("parts", snapshot_parts, "total_price"))
            for index, item in enumerate(items)]
        if any(amount != amount.quantize(CENT) for _, _, amount in lines):
            raise ValueError("fractional cents")
        subtotal = decimal(invoice["subtotal"])
        taxes, fees, supplies = (decimal(invoice[key]) for key in ("tax_amount", "service_fee_amount", "shop_supplies_amount"))
        if decimal(invoice["discount_amount"]) != ZERO or decimal(invoice["total_amount"]) != subtotal + taxes + fees + supplies:
            raise ValueError("invoice totals")
        allocation = discount_allocation(lines, subtotal)
        revenue.update(net_direct_revenue=money(subtotal), issued_discount=money(sum((line[2] for line in lines), ZERO) - subtotal),
                       tax=money(taxes), fees=money(fees), supplies=money(supplies))
        # Unique financial structures prove live expense identity. Names or
        # positions never select a cost. Duplicates remain unresolved.
        labor_key = lambda item: (str(item.get("description", "")), decimal(item["hours"]),
                                  decimal(item["hourly_rate"]), decimal(item["total_cost"]))
        part_key = lambda item: (str(item.get("name", "")),
                                 decimal(item["quantity"]), decimal(item["unit_price"]),
                                 decimal(item["total_price"]))
        live_labor = bundle["labor"]
        live_parts = bundle["parts"]
        source_labor_keys = [labor_key(item) for item in snapshot_labor]
        source_part_keys = [part_key(item) for item in snapshot_parts]
        current_labor_keys = [labor_key(item) for item in live_labor if not item.get("deleted_at")]
        inventory = {item["id"]: item for item in bundle["inventory"]}
        current_part_keys = [part_key({**inventory.get(item["inventory_id"], {}), **item})
                             for item in live_parts if not item.get("deleted_at")]
        structure_matches = (Counter(source_labor_keys) == Counter(current_labor_keys)
                             and Counter(source_part_keys) == Counter(current_part_keys)
                             and len(set(source_labor_keys)) == len(source_labor_keys)
                             and len(set(source_part_keys)) == len(source_part_keys)
                             and not any(item.get("deleted_at") for item in [*live_labor, *live_parts]))
        if not structure_matches:
            raise ValueError("expense identity")
        part_cost, missing_parts = ZERO, 0
        for item in live_parts:
            if item.get("unit_cost") is None:
                missing_parts += 1
            else:
                part_cost += decimal(item["unit_cost"]) * decimal(item["quantity"])
        sublets = [item for item in live_labor if item.get("line_type") == "sublet"]
        missing_sublets = sum(item.get("vendor_cost") is None for item in sublets)
        sublet_cost = sum((decimal(item["vendor_cost"]) for item in sublets if item.get("vendor_cost") is not None), ZERO)
        parts = {"status": "partial" if missing_parts else "complete", "known_cost": money(part_cost),
                 "line_count": len(live_parts), "missing_cost_line_count": missing_parts}
        sublet = {"status": "partial" if missing_sublets else ("complete" if sublets else "not_applicable"),
                  "known_cost": money(sublet_cost), "line_count": len(sublets), "missing_cost_line_count": missing_sublets}
        if missing_parts or missing_sublets:
            reasons.append("direct_expense_missing")
    except (ValueError, TypeError, KeyError, ArithmeticError):
        reasons.append("issued_snapshot_or_expense_identity_unresolved")
    # Funding is not revenue. Ordinary completed payment/credit application is
    # not added again. Unknown/reversed/refunded credit provenance is held.
    if any(bundle[key] for key in ("adjustments", "refunds", "disputes", "returns")) or any(
            row.get("entry_type") in {"refunded", "reversed"} for row in bundle["credits"]):
        reasons.append("revenue_adjustment_review_required")
    if bundle.get("credit_ambiguity"):
        reasons.append("historical_credit_source_unresolved")
    if any(row.get("state") != "credited" for row in bundle["overpayments"]):
        reasons.append("overpayment_review_required")
    revenue["hold_reasons"] = sorted(set(reasons))
    revenue["status"] = "complete" if not reasons else "unavailable"
    if "issued_snapshot_or_expense_identity_unresolved" in reasons or "issued_identity_unresolved" in reasons:
        revenue["net_direct_revenue"] = None
    return revenue, parts, sublet, allocation


def labor_projection(bundle, activation, review=None):
    order = bundle["order"]
    own = [row for row in bundle["sessions"] if row.get("repair_order_id") == order["id"]]
    mechanics = {row["id"]: row for row in bundle["mechanics"]}
    operations = {row["id"]: row for row in bundle["labor"]}
    accepted = set(review.get("reviewed_exception_ids", [])) if review else set()
    bucket_us = {key: 0 for key in ("costed", "unrated", "pre_activation", "held")}
    known = ZERO
    details, reasons, open_count = [], set(), 0
    attributed_us, general_us = 0, 0
    for session in own:
        before_buckets, before_known = dict(bucket_us), known
        item_reasons = set()
        mechanic = mechanics.get(session["mechanic_id"])
        snapshot = session.get("labor_id_snapshot")
        operation = operations.get(snapshot) if snapshot else None
        if not mechanic or mechanic.get("role") != "mechanic" or mechanic.get("deleted_at"):
            item_reasons.add("technician_identity_unresolved")
        if session.get("session_type") != "repair_order" or session.get("tenant_id") != order["tenant_id"]:
            item_reasons.add("session_identity_unresolved")
        if snapshot and (not operation or operation.get("repair_order_id") != order["id"]
                         or operation.get("tenant_id") != order["tenant_id"]):
            item_reasons.add("operation_snapshot_unresolved")
        if session.get("labor_id") and not snapshot:
            item_reasons.add("operation_snapshot_unresolved")
        if session.get("labor_id") and snapshot and session["labor_id"] != snapshot:
            item_reasons.add("operation_snapshot_unresolved")
        audits = [row for row in bundle["time_audits"] if row.get("session_id") == session["id"]]
        corrected = [row for row in audits if row.get("action") in {"edit", "delete", "auto_midnight_stop"}]
        for audit in corrected:
            if audit.get("deleted_at"):
                item_reasons.add("time_audit_source_unresolved")
            for key in ("before_snapshot", "after_snapshot"):
                value = audit.get(key)
                if value is not None and not isinstance(value, dict):
                    item_reasons.add("time_audit_source_unresolved")
                if isinstance(value, dict) and value.get("mechanic_id") not in {None, session["mechanic_id"]}:
                    item_reasons.add("time_source_identity_discrepancy")
        acknowledged = session["id"] in accepted
        if corrected and not acknowledged:
            item_reasons.add("source_correction_review_required")
        if session.get("stop_reason") not in {None, "manual", "stop", "manual_stop"} and not acknowledged:
            item_reasons.add("automatic_stop_review_required")
        if session.get("deleted_at") and not acknowledged:
            item_reasons.add("deleted_session_review_required")
        session_cost, session_costed, duration = ZERO, 0, 0
        head = bundle["policy_heads"].get(session["mechanic_id"])
        policy = head["policy"] if head else None
        session_activation = activation
        try:
            start = moment(session["started_at"])
            end = moment(session["ended_at"]) if session.get("ended_at") else None
            session_activation = moment(policy["activation_at"]) if policy else activation
            if policy and bundle.get("shop_timezone") and policy.get("shop_timezone") != bundle["shop_timezone"]:
                item_reasons.add("cost_policy_timezone_review_required")
            if end is None:
                open_count += 1
                item_reasons.add("open_session")
            elif end <= start:
                item_reasons.add("invalid_session_interval")
            elif session.get("deleted_at") and acknowledged:
                # Reviewed removed mistaken evidence is retained in the source
                # fingerprint, but is not charged or counted as recorded work.
                pass
            elif operation and operation.get("line_type") == "sublet":
                # Vendor expense is counted once through the expense component.
                pass
            else:
                duration = micros(start, end)
                peers = [row for row in bundle["sessions"] if row["mechanic_id"] == session["mechanic_id"] and row["id"] != session["id"]]
                if any(intersects(start, end, row) for row in peers):
                    item_reasons.add("technician_time_overlap")
                attendance = [row for row in bundle["attendance"] if row["mechanic_id"] == session["mechanic_id"]]
                if not attendance_covers(start, end, attendance):
                    item_reasons.add("attendance_coverage_incomplete")
                for attendance_row in attendance:
                    if intersects(start, end, attendance_row) and (attendance_row.get("deleted_at") or not attendance_row.get("ended_at")):
                        item_reasons.add("attendance_source_incomplete")
                for audit in relevant_attendance_audits(bundle, session, start, end):
                    if audit.get("action") not in {"clock_in", "clock_out", "break_start", "break_end"}:
                        if audit.get("deleted_at") or any(audit.get(key) is not None and not isinstance(audit[key], dict)
                                                         for key in ("before_snapshot", "after_snapshot")):
                            item_reasons.add("attendance_audit_source_unresolved")
                        if session["id"] not in accepted:
                            item_reasons.add("attendance_correction_review_required")
                if any(intersects(start, end, row) for row in bundle["breaks"] if row["mechanic_id"] == session["mechanic_id"]):
                    item_reasons.add("break_conflict")
                if item_reasons or session.get("deleted_at"):
                    bucket_us["held"] += duration
                else:
                    pre_end = min(end, session_activation)
                    if start < pre_end:
                        bucket_us["pre_activation"] += micros(start, pre_end)
                        item_reasons.add("pre_activation_time")
                    current = max(start, session_activation)
                    segments = policy.get("segments", []) if policy else []
                    cuts = {current, end} if current < end else set()
                    for segment in segments:
                        for field in ("effective_from", "effective_to"):
                            if segment.get(field):
                                boundary = moment(segment[field])
                                if current < boundary < end:
                                    cuts.add(boundary)
                    cuts = sorted(cuts)
                    for left, right in zip(cuts, cuts[1:]):
                        applicable = [segment for segment in segments if moment(segment["effective_from"]) <= left
                                      and (not segment.get("effective_to") or right <= moment(segment["effective_to"]))]
                        elapsed = micros(left, right)
                        if len(applicable) != 1:
                            bucket_us["unrated"] += elapsed
                            item_reasons.add("loaded_direct_rate_missing")
                        else:
                            session_costed += elapsed
                            session_cost += Decimal(elapsed) / Decimal(3600000000) * decimal(applicable[0]["hourly_cost"])
                    bucket_us["costed"] += session_costed
                    known += session_cost
                if snapshot and operation:
                    attributed_us += duration
                else:
                    general_us += duration
        except (ValueError, TypeError, KeyError, ArithmeticError):
            item_reasons.add("source_time_or_policy_invalid")
            # A malformed policy/source cannot produce a guessed cost.
            bucket_us, known = before_buckets, before_known
            session_cost, session_costed = ZERO, 0
            if duration:
                known_pre = micros(start, min(end, session_activation)) if start < min(end, session_activation) else 0
                bucket_us["pre_activation"] += known_pre
                bucket_us["held"] += duration - known_pre
        reasons.update(item_reasons)
        details.append({"id": session["id"], "mechanic_id": session["mechanic_id"],
                        "mechanic_name": " ".join(filter(None, (mechanic.get("first_name"), mechanic.get("last_name")))) if mechanic else "Unavailable",
                        "labor_id_snapshot": snapshot, "started_at": stamp(session["started_at"]) if isinstance(session.get("started_at"), datetime) and session["started_at"].tzinfo else None,
                        "ended_at": stamp(session["ended_at"]) if isinstance(session.get("ended_at"), datetime) and session["ended_at"].tzinfo else None,
                        "recorded_seconds": duration // 1000000, "costed_seconds": session_costed // 1000000,
                        "known_cost": money(session_cost) if session_costed else None, "hold_reasons": sorted(item_reasons)})
    recorded = sum(bucket_us.values()) // 1000000
    display = {key: value // 1000000 for key, value in bucket_us.items()}
    remainder = recorded - sum(display.values())
    for key in sorted(bucket_us, key=lambda key: (-(bucket_us[key] % 1000000), key))[:remainder]:
        display[key] += 1
    assertion = review.get("time_capture") if review else None
    if assertion == "no_internal_labor" and not reasons and not any(row["recorded_seconds"] or "open_session" in row["hold_reasons"] for row in details):
        status = "not_applicable"
        reasons.discard("source_correction_review_required")
    else:
        if assertion != "complete":
            reasons.add("owner_time_capture_review_required")
        if not own:
            reasons.add("no_recorded_job_time")
        status = "unavailable" if bucket_us["costed"] == 0 else "partial" if reasons else "complete"
    labor = {"status": status, "known_cost": money(known) if bucket_us["costed"] or status == "not_applicable" else None,
             "recorded_seconds": recorded, "costed_seconds": display["costed"], "unrated_seconds": display["unrated"],
             "pre_activation_seconds": display["pre_activation"], "held_seconds": display["held"],
             "open_session_count": open_count, "operation_attributed_seconds": attributed_us // 1000000,
             "general_ro_seconds": general_us // 1000000, "hold_reasons": sorted(reasons)}
    return labor, details


def derive(bundle, activation, review_override=None):
    order, prior = bundle["order"], bundle.get("review")
    current = bool(prior and prior["source_fingerprint"] == bundle["source_fingerprint"]
                   and prior["policy_heads_digest"] == bundle["policy_heads_digest"] and prior["calculation_version"] == VERSION)
    review = review_override if review_override is not None else prior if current else None
    classification = review["business_classification"] if review else "unknown"
    imported = order.get("source") == "easy_truck_shop_import" or any(
        invoice.get("source") == "easy_truck_shop_import" or invoice.get("accounting_policy") == "historical_export_hold" for invoice in bundle["invoices"])
    if imported:
        labor = {"status": "unavailable", "known_cost": None, "hold_reasons": ["ets_owned_history"],
                 **{key: 0 for key in ("recorded_seconds", "costed_seconds", "unrated_seconds", "pre_activation_seconds",
                     "held_seconds", "open_session_count", "operation_attributed_seconds", "general_ro_seconds")}}
        revenue = {"basis": "issued_native_net_direct_v1", "status": "unavailable", "net_direct_revenue": None,
                   "issued_discount": None, "tax": None, "fees": None, "supplies": None, "hold_reasons": ["ets_owned_history"]}
        parts = {"status": "unavailable", "known_cost": None, "line_count": 0, "missing_cost_line_count": 0}
        sublet, sessions, allocations = dict(parts), [], []
    else:
        labor, sessions = labor_projection(bundle, activation, review)
        revenue, parts, sublet, allocations = revenue_and_expenses(bundle)
    holds = set(revenue["hold_reasons"]) | set(labor["hold_reasons"])
    if not review:
        holds.add("owner_business_review_required" if not prior else "owner_review_stale")
    if imported:
        holds.add("ets_owned_history")
    if classification != "real":
        holds.add("test_excluded" if classification == "test" else "business_scope_unverified")
    if not bundle["customer"] or bundle["customer"].get("deleted_at"):
        holds.add("customer_identity_unresolved")
    if parts["status"] not in {"complete", "not_applicable"} or sublet["status"] not in {"complete", "not_applicable"}:
        holds.add("direct_expense_incomplete")
    complete = not holds and labor["status"] in {"complete", "not_applicable"}
    contribution = None
    if complete:
        contribution = Decimal(revenue["net_direct_revenue"]) - Decimal(labor["known_cost"]) - Decimal(parts["known_cost"]) - Decimal(sublet["known_cost"])
    known = labor["known_cost"]
    cost_status = "complete" if complete else "partial" if known is not None else "unavailable"
    customer = bundle["customer"]
    cohort = order.get("work_completed_at") or order["created_at"]
    row = {"order_id": order["id"], "order_number": order["order_number"],
           "customer_name": customer.get("company_name") or " ".join(filter(None, (customer.get("first_name"), customer.get("last_name")))) or "Unavailable",
           "type": "warranty" if order.get("is_warranty_repair") else "internal" if order.get("is_internal") else "pm" if order.get("is_pm") else "repair",
           "status": order["status"], "cohort_at": stamp(cohort),
           "date_basis": "work_completed_at" if order.get("work_completed_at") else "created_at",
           "business_classification": classification, "source_owner": "ets_history" if imported else "native" if classification == "real" else "review_required",
           "review_status": "current" if review_override is not None or current else "stale" if prior else "none",
           "review_version": prior["version"] if prior else 0, "cost_status": cost_status,
           "revenue": revenue, "labor": labor, "parts": parts, "sublet": sublet,
           "direct_contribution": money(contribution) if contribution is not None else None,
           "margin_pct": money(contribution / Decimal(revenue["net_direct_revenue"]) * 100) if contribution is not None and Decimal(revenue["net_direct_revenue"]) > 0 else None,
           "hold_reasons": sorted(holds), "drilldown": f"/dashboard/repair-orders?selected={order['id']}"}
    separate = {"misc_seconds": None, "idle_seconds": None, "break_seconds": None, "cost_status": "unavailable",
                "scope": "selected_job_timer_window", "scope_windows": [], "time_status": "unavailable"}
    # Separate time is measured with unions, not allocated as job expense.
    def union_duration(items, window_start, window_end):
        ranges = []
        for item in items:
            try:
                a, b = moment(item["started_at"]), moment(item["ended_at"])
                if not item.get("deleted_at") and a < b and a < window_end and window_start < b:
                    ranges.append((max(a, window_start), min(b, window_end)))
            except (ValueError, TypeError, KeyError):
                continue
        total, left, right = 0, None, None
        for a, b in sorted(ranges):
            if right is None or a > right:
                if right is not None:
                    total += micros(left, right)
                left, right = a, b
            else:
                right = max(right, b)
        return (total + (micros(left, right) if right is not None else 0)) // 1000000
    unknown_separate_scope = False
    for mechanic_id in ({item["mechanic_id"] for item in bundle["sessions"] if item.get("repair_order_id") == order["id"]} if not imported else set()):
        scoped = lambda key: [item for item in bundle[key] if item["mechanic_id"] == mechanic_id]
        selected = []
        own_open = False
        for session in scoped("sessions"):
            if session.get("repair_order_id") != order["id"] or session.get("deleted_at"):
                continue
            try:
                left, right = moment(session["started_at"]), moment(session["ended_at"])
                if left < right:
                    selected.append((left, right))
                else:
                    own_open = True
            except (ValueError, TypeError, KeyError):
                own_open = True
        if not selected:
            unknown_separate_scope = True
            continue
        left, right = min(pair[0] for pair in selected), max(pair[1] for pair in selected)
        separate["scope_windows"].append({"mechanic_id": mechanic_id, "started_at": stamp(left), "ended_at": stamp(right)})
        misc = union_duration([item for item in scoped("sessions") if item.get("session_type") == "misc"], left, right)
        attendance = union_duration(scoped("attendance"), left, right)
        breaks = union_duration(scoped("breaks"), left, right)
        busy = union_duration([*scoped("sessions"), *scoped("breaks")], left, right)
        incomplete = own_open or not attendance_covers(left, right, scoped("attendance")) or any(
            not item.get("ended_at") or item.get("deleted_at") for item in [*scoped("sessions"), *scoped("attendance"), *scoped("breaks")]
            if intersects(left, right, item))
        if not separate["scope_windows"][:-1]:
            separate.update(misc_seconds=0, idle_seconds=0, break_seconds=0, time_status="complete")
        separate["misc_seconds"] += misc
        separate["break_seconds"] += breaks
        if incomplete:
            separate["time_status"] = "partial"
            separate["idle_seconds"] = None
        elif separate["idle_seconds"] is not None:
            separate["idle_seconds"] += max(0, attendance - busy)
    if unknown_separate_scope:
        separate.update(misc_seconds=None, idle_seconds=None, break_seconds=None,
                        time_status="partial" if separate["scope_windows"] else "unavailable")
    return row, sessions, allocations, separate
