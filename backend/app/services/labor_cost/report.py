from datetime import datetime, date, timedelta, time, timezone
from decimal import Decimal
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, func, or_, and_
from app.db.models.repair_order import RepairOrder
from app.db.models.customer import Customer
from app.db.models.labor_cost import JobCostReview
from .calculation import ACTIVATION_DATE, VERSION, derive, digest, stamp, money, canonical, moment, relevant_attendance_audits
from .source import read, load, bundle_for, BASE
from .policy import context, cursor_encode, cursor_decode

ORDER_FIELDS = BASE + " customer_id order_number status source is_internal is_warranty_repair is_pm work_completed_at total_cost"


def detail_response(bundle, activation, override=None):
    row, sessions, allocations, separate = derive(bundle, activation, override)
    policies = []
    for mechanic_id, head in (sorted(bundle["policy_heads"].items()) if row["source_owner"] != "ets_history" else []):
        for segment in head["policy"].get("segments", []):
            policies.append({"mechanic_id": mechanic_id, "policy_revision_id": head["id"], **segment})
    review = bundle.get("review")
    review_view = None if review is None else {key: canonical(review.get(key)) for key in (
        "id", "version", "supersedes_id", "business_classification", "approved_by_user_id", "reason",
        "source_fingerprint", "policy_heads_digest", "calculation_version", "time_capture", "reviewed_exception_ids", "snapshot", "created_at")}
    return {"contract_version": 1, "calculation_version": VERSION, "generated_at": stamp(datetime.now(timezone.utc)),
            "row": row, "source_fingerprint": bundle["source_fingerprint"],
            "policy_heads_digest": bundle["policy_heads_digest"], "review": review_view,
            "sessions": sessions, "policy_segments": policies, "discount_allocation": allocations,
            "separate_shop_time": separate}


async def detail(db, actor, order_id, *, tenant_context=None):
    tenant, zone, activation = tenant_context or await context(db, actor)
    orders = await read(db, RepairOrder, ORDER_FIELDS, tenant.id, RepairOrder.id == order_id, RepairOrder.deleted_at.is_(None), cap=1)
    if not orders:
        raise HTTPException(404, "Job not found")
    sources = await load(db, tenant.id, orders)
    return bundle_for(sources, orders[0]), activation


def summary(rows):
    real = [row for row in rows if row["business_classification"] == "real" and row["source_owner"] == "native"]
    complete = [row for row in real if row["direct_contribution"] is not None]
    result = {"order_count": len(rows), "real_count": len(real),
        "test_count": sum(row["business_classification"] == "test" and row["source_owner"] != "ets_history" for row in rows),
        "unknown_count": sum(row["business_classification"] == "unknown" and row["source_owner"] != "ets_history" for row in rows),
        "history_count": sum(row["source_owner"] == "ets_history" for row in rows),
        "complete_row_count": len(complete), "partial_row_count": sum(row["cost_status"] == "partial" for row in real),
        "unavailable_row_count": sum(row["cost_status"] == "unavailable" for row in real),
        "incomplete_row_count": len(real) - len(complete),
        "reviewed_complete_contribution": money(sum((Decimal(row["direct_contribution"]) for row in complete), Decimal(0))) if complete else None,
        "known_recorded_direct_cost": money(sum((Decimal(row["labor"]["known_cost"]) for row in real if row["labor"]["known_cost"] is not None), Decimal(0))),
        "is_complete": bool(real) and len(complete) == len(real)}
    for key in ("recorded_seconds", "costed_seconds", "unrated_seconds", "pre_activation_seconds", "held_seconds", "open_session_count"):
        result[key] = sum(row["labor"][key] for row in real)
    return result


async def report(db, actor, *, from_date=None, to_date=None, limit=50, cursor=None, q="", scope="all"):
    tenant, zone, activation = await context(db, actor)
    today = datetime.now(timezone.utc).astimezone(zone).date()
    start_date = from_date or today.replace(day=1)
    month_end = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    end_date = to_date or month_end
    if start_date > end_date or (end_date - start_date).days >= 366:
        raise HTTPException(422, "Invalid cost report date range")
    start = datetime.combine(start_date, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    binding = {"tenant": str(tenant.id), "from": str(start_date), "to": str(end_date), "scope": scope, "q": q.casefold()}
    position = cursor_decode(cursor, binding)
    cohort = func.coalesce(RepairOrder.work_completed_at, RepairOrder.created_at)
    conditions = [RepairOrder.deleted_at.is_(None), cohort >= start, cohort < end]
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        customer_query = select(Customer.id).where(Customer.tenant_id == tenant.id,
            or_(Customer.company_name.ilike(pattern, escape="\\"),
                (func.coalesce(Customer.first_name, "") + " " + func.coalesce(Customer.last_name, "")).ilike(pattern, escape="\\")))
        conditions.append(or_(RepairOrder.order_number.ilike(pattern, escape="\\"), RepairOrder.customer_id.in_(customer_query)))
    orders = await read(db, RepairOrder, ORDER_FIELDS, tenant.id, *conditions, cap=2000)
    sources = await load(db, tenant.id, orders)
    rows = [derive(bundle_for(sources, order), activation)[0] for order in orders]
    predicates = {"all": lambda row: True, "real": lambda row: row["business_classification"] == "real" and row["source_owner"] == "native",
                  "test": lambda row: row["business_classification"] == "test" and row["source_owner"] != "ets_history",
                  "history": lambda row: row["source_owner"] == "ets_history",
                  "review": lambda row: row["source_owner"] != "ets_history" and (row["business_classification"] == "unknown" or row["direct_contribution"] is None)}
    rows = [row for row in rows if predicates[scope](row)]
    rows.sort(key=lambda row: (row["cohort_at"], row["order_id"]), reverse=True)
    totals = summary(rows)
    if position is not None:
        if len(position) != 2 or any(not isinstance(value, str) for value in position):
            raise HTTPException(422, "Invalid cost report cursor")
        rows = [row for row in rows if (row["cohort_at"], row["order_id"]) < tuple(position)]
    page, has_more = rows[:limit], len(rows) > limit
    return {"contract_version": 1, "calculation_version": VERSION, "generated_at": stamp(datetime.now(timezone.utc)),
            "shop_timezone": tenant.timezone, "activation_local_date": ACTIVATION_DATE, "activation_at": stamp(activation),
            "from": str(start_date), "to": str(end_date), "next_cursor": cursor_encode(binding, [page[-1]["cohort_at"], page[-1]["order_id"]]) if has_more else None,
            "summary": totals, "rows": page}


async def append_review(db, actor, order_id, body, key):
    tenant_context = await context(db, actor, lock=True)
    tenant = tenant_context[0]
    # Existence/tenant denial precedes idempotency or policy disclosure.
    bundle, activation = await detail(db, actor, order_id, tenant_context=tenant_context)
    if (bundle["order"].get("source") == "easy_truck_shop_import" or any(
            invoice.get("source") == "easy_truck_shop_import" or invoice.get("accounting_policy") == "historical_export_hold"
            for invoice in bundle["invoices"])):
        raise HTTPException(422, "Imported history is outside native cost review")
    request_sha = digest(body.model_dump())
    replay = (await db.execute(select(JobCostReview).where(JobCostReview.tenant_id == tenant.id,
             JobCostReview.idempotency_key == key))).scalar_one_or_none()
    if replay:
        if replay.approved_by_user_id != actor.id or replay.request_sha256 != request_sha or replay.order_id != order_id:
            raise HTTPException(409, "Job cost review changed; refresh before retrying")
        return review_response(replay), False
    prior = bundle.get("review")
    if body.expected_version != (prior["version"] if prior else 0) or body.source_fingerprint != bundle["source_fingerprint"] or body.policy_heads_digest != bundle["policy_heads_digest"]:
        raise HTTPException(409, "Job cost source changed; refresh before retrying")
    corrected_ids = {row["session_id"] for row in bundle["time_audits"] if row.get("action") in {"edit", "delete", "auto_midnight_stop"}}
    allowed = {row["id"] for row in bundle["sessions"] if row.get("repair_order_id") == bundle["order"]["id"]
               and (row.get("deleted_at") or row["id"] in corrected_ids
                    or row.get("stop_reason") not in {None, "manual", "stop", "manual_stop"})}
    for session in bundle["sessions"]:
        if session.get("repair_order_id") == bundle["order"]["id"] and session.get("ended_at"):
            if any(audit.get("action") not in {"clock_in", "clock_out", "break_start", "break_end"}
                   for audit in relevant_attendance_audits(bundle, session, moment(session["started_at"]), moment(session["ended_at"]))):
                allowed.add(session["id"])
    if not set(body.reviewed_exception_ids) <= allowed:
        raise HTTPException(422, "Review exception identity unavailable")
    row = detail_response(bundle, activation, body.model_dump())["row"]
    if body.time_capture == "complete" and row["labor"]["status"] != "complete":
        raise HTTPException(422, "Recorded direct time cannot support completeness")
    if body.time_capture == "no_internal_labor" and row["labor"]["status"] != "not_applicable":
        raise HTTPException(422, "Recorded direct time conflicts with no-internal-labor assertion")
    # A review may retain incomplete financial evidence, but cannot assert a
    # final contribution when source/return/financial holds remain.
    row["review_version"] = body.expected_version + 1
    review = JobCostReview(tenant_id=tenant.id, order_id=order_id, version=body.expected_version + 1,
        supersedes_id=UUID(prior["id"]) if prior else None, business_classification=body.business_classification,
        approved_by_user_id=actor.id, reason=body.reason, source_fingerprint=bundle["source_fingerprint"],
        policy_heads_digest=bundle["policy_heads_digest"], calculation_version=VERSION, time_capture=body.time_capture,
        reviewed_exception_ids=body.reviewed_exception_ids, snapshot=row, request_sha256=request_sha,
        idempotency_key=key, created_at=datetime.now(timezone.utc))
    db.add(review)
    await db.flush()
    return review_response(review), True


def review_response(review):
    return {"contract_version": 1, "review_id": str(review.id), "order_id": str(review.order_id), "version": review.version,
            "supersedes_id": str(review.supersedes_id) if review.supersedes_id else None,
            "business_classification": review.business_classification, "time_capture": review.time_capture,
            "source_fingerprint": review.source_fingerprint, "policy_heads_digest": review.policy_heads_digest,
            "approved_at": stamp(review.created_at), "row": review.snapshot}
