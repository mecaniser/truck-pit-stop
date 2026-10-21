"""Bounded same-tenant reads. Sensitive notes/provider fields are never selected."""
from datetime import datetime, timezone
from collections import Counter
from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from app.db.models.customer import Customer
from app.db.models.repair_order import RepairOrder
from app.db.models.user import User
from app.db.models.tenant import Tenant
from app.db.models.labor import Labor
from app.db.models.inventory import PartsUsage, Inventory
from app.db.models.invoice import Invoice
from app.db.models.invoice_charge_adjustment import InvoiceChargeAdjustment
from app.db.models.invoice_settlement import CustomerCreditEntry, PaymentOverpayment, PaymentRefund, PaymentProviderDispute, InvoicePaymentAttempt
from app.db.models.payment import Payment
from app.db.models.parts_operations import VendorReturnLine, VendorReturn
from app.db.models.mechanic_time import MechanicTimeSession, MechanicTimeSessionAudit, MechanicAttendanceSession, MechanicBreakSession, MechanicAttendanceAudit
from app.db.models.labor_cost import TechnicianCostPolicyRevision, JobCostReview
from .calculation import canonical, digest, moment, intersects, relevant_attendance_audits

BASE = "id tenant_id created_at updated_at deleted_at"


async def read(db, model, fields, tenant_id, *where, cap=20000):
    names = list(dict.fromkeys(fields.split()))
    statement = select(*(getattr(model, name) for name in names)).where(model.tenant_id == tenant_id, *where).order_by(model.id).limit(cap + 1)
    rows = [dict(row) for row in (await db.execute(statement)).mappings()]
    if len(rows) > cap:
        raise HTTPException(413, "A1 source exceeds safe read limit")
    # Enum values and UUIDs have one stable identity across JSON and DB reads.
    return [{key: None if value is None else value.value if hasattr(value, "value") else str(value) if key.endswith("_id") or key == "id" else value
             for key, value in row.items()} for row in rows]


async def load(db, tenant_id, orders):
    ids = [row["id"] for row in orders]
    if not ids:
        return {"orders": [], "reviews": [], "policies": [], "mechanics": []}
    # SQL UUID columns receive UUID objects, independent of driver coercion.
    from uuid import UUID
    order_ids = [UUID(value) for value in ids]
    timezone_value = (await db.execute(select(Tenant.timezone).where(Tenant.id == tenant_id))).scalar_one()
    data = {"orders": orders, "shop_timezone": timezone_value}
    data["customers"] = await read(db, Customer, BASE + " first_name last_name company_name is_internal_fleet", tenant_id,
                                   Customer.id.in_([UUID(row["customer_id"]) for row in orders]))
    data["labor"] = await read(db, Labor, BASE + " repair_order_id description hours hourly_rate total_cost line_type vendor_cost mechanic_id", tenant_id, Labor.repair_order_id.in_(order_ids))
    data["parts"] = await read(db, PartsUsage, BASE + " repair_order_id inventory_id quantity unit_cost unit_price total_price source_line_id", tenant_id, PartsUsage.repair_order_id.in_(order_ids))
    data["inventory"] = await read(db, Inventory, BASE + " sku name", tenant_id,
                                   Inventory.id.in_([UUID(row["inventory_id"]) for row in data["parts"]]))
    data["invoices"] = await read(db, Invoice, BASE + " repair_order_id billed_customer_id invoice_number status is_internal voided_at supersedes_invoice_id source accounting_policy subtotal discount_amount total_amount tax_amount service_fee_amount shop_supplies_amount line_items_snapshot", tenant_id, Invoice.repair_order_id.in_(order_ids))
    historical_order_ids = {row["id"] for row in orders if row.get("source") == "easy_truck_shop_import"}
    historical_order_ids.update(row["repair_order_id"] for row in data["invoices"]
        if row.get("source") == "easy_truck_shop_import" or row.get("accounting_policy") == "historical_export_hold")
    native_order_ids = [UUID(value) for value in ids if value not in historical_order_ids]
    candidates = await read(db, MechanicTimeSession, BASE + " mechanic_id repair_order_id labor_id labor_id_snapshot session_type started_at ended_at stop_reason stopped_by_user_id", tenant_id, MechanicTimeSession.repair_order_id.in_(native_order_ids))
    mechanic_ids = {row["mechanic_id"] for row in candidates}
    mechanic_uuids = [UUID(value) for value in mechanic_ids]
    data["mechanics"] = await read(db, User, BASE + " first_name last_name role is_active", tenant_id, User.id.in_(mechanic_uuids))
    data["sessions"] = candidates
    data["attendance"], data["breaks"], data["time_audits"], data["attendance_audits"] = [], [], [], []
    if candidates:
        try:
            start = min(moment(row["started_at"]) for row in candidates)
            end = max(moment(row["ended_at"]) if row["ended_at"] else datetime.now(timezone.utc) for row in candidates)
        except (ValueError, TypeError):
            raise HTTPException(503, "A1 source timestamps unavailable")
        for key, model, fields in (
            ("sessions", MechanicTimeSession, "mechanic_id repair_order_id labor_id labor_id_snapshot session_type started_at ended_at stop_reason stopped_by_user_id"),
            ("attendance", MechanicAttendanceSession, "mechanic_id started_at ended_at start_source end_source snapshot_timezone"),
            ("breaks", MechanicBreakSession, "mechanic_id attendance_session_id started_at ended_at start_source end_source"),
        ):
            conditions = [model.mechanic_id.in_(mechanic_uuids), model.started_at <= end,
                          or_(model.ended_at.is_(None), model.ended_at >= start, model.ended_at <= model.started_at)]
            if key == "sessions":
                conditions = [or_(model.repair_order_id.in_(native_order_ids), and_(*conditions))]
            data[key] = await read(db, model, BASE + " " + fields, tenant_id, *conditions)
        data["time_audits"] = await read(db, MechanicTimeSessionAudit, BASE + " mechanic_id session_id actor_user_id actor_role action before_snapshot after_snapshot", tenant_id,
                                         MechanicTimeSessionAudit.mechanic_id.in_(mechanic_uuids), cap=50000)
        data["attendance_audits"] = await read(db, MechanicAttendanceAudit, BASE + " mechanic_id attendance_session_id break_session_id actor_user_id actor_role action before_snapshot after_snapshot", tenant_id,
                                               MechanicAttendanceAudit.mechanic_id.in_(mechanic_uuids), cap=50000)
        # Audit snapshots can contain private note/reason prose. Keep material
        # time/identity markers only, never notes or actor account fields.
        audit_keys = {"id", "mechanic_id", "repair_order_id", "labor_id", "labor_id_snapshot", "session_type", "started_at", "ended_at", "deleted_at", "stop_reason", "attendance_session_id", "start_source", "end_source"}
        for audit in [*data["time_audits"], *data["attendance_audits"]]:
            for key in ("before_snapshot", "after_snapshot"):
                value = audit.get(key)
                audit[key] = {name: value[name] for name in sorted(audit_keys & value.keys())} if isinstance(value, dict) else None
    policies = await read(db, TechnicianCostPolicyRevision,
        "id tenant_id mechanic_id version supersedes_id policy created_at approved_by_user_id request_sha256", tenant_id,
        TechnicianCostPolicyRevision.mechanic_id.in_(mechanic_uuids), cap=20000)
    if any(count > 1000 for count in Counter(row["mechanic_id"] for row in policies).values()):
        raise HTTPException(413, "A1 policy history exceeds safe read limit")
    data["policies"] = policies
    data["reviews"] = await read(db, JobCostReview,
        "id tenant_id order_id version supersedes_id business_classification approved_by_user_id reason source_fingerprint policy_heads_digest calculation_version time_capture reviewed_exception_ids snapshot created_at", tenant_id,
        JobCostReview.order_id.in_(order_ids))
    invoice_ids = [UUID(row["id"]) for row in data["invoices"]]
    data["adjustments"] = await read(db, InvoiceChargeAdjustment, BASE + " invoice_id version request_hash evidence", tenant_id, InvoiceChargeAdjustment.invoice_id.in_(invoice_ids))
    data["payments"] = await read(db, Payment, BASE + " invoice_id status amount source", tenant_id, Payment.invoice_id.in_(invoice_ids))
    data["refunds"] = await read(db, PaymentRefund, BASE + " invoice_id amount state overpayment_id", tenant_id, PaymentRefund.invoice_id.in_(invoice_ids))
    attempts = await read(db, InvoicePaymentAttempt, BASE + " invoice_id state", tenant_id, InvoicePaymentAttempt.invoice_id.in_(invoice_ids))
    data["attempts"] = attempts
    data["disputes"] = await read(db, PaymentProviderDispute, BASE + " attempt_id state reversed_principal_amount disputed_gross_amount", tenant_id,
                                  PaymentProviderDispute.attempt_id.in_([UUID(row["id"]) for row in attempts]))
    # Bound the whole same-tenant graph so cross-customer/source descendants
    # cannot be omitted by filtering only target_invoice_id.
    data["credits"] = await read(db, CustomerCreditEntry,
        "id tenant_id customer_id entry_type amount origin_overpayment_id target_invoice_id source_entry_id occurred_at", tenant_id)
    data["overpayments"] = await read(db, PaymentOverpayment, BASE + " invoice_id customer_id settlement_id state amount consented_at", tenant_id)
    returns = await read(db, VendorReturnLine, BASE + " vendor_return_id inventory_id quantity actual_credit", tenant_id,
                          VendorReturnLine.inventory_id.in_([UUID(row["inventory_id"]) for row in data["parts"]]))
    data["return_lines"] = returns
    data["returns"] = await read(db, VendorReturn, BASE + " status kind credited_at version", tenant_id,
                                 VendorReturn.id.in_([UUID(row["vendor_return_id"]) for row in returns]))
    return data


def bundle_for(data, order):
    identity = order["id"]
    bundle = {"order": order, "shop_timezone": data["shop_timezone"], "customer": next((row for row in data["customers"] if row["id"] == order["customer_id"]), {})}
    for key in ("labor", "parts", "invoices"):
        bundle[key] = [row for row in data[key] if row["repair_order_id"] == identity]
    inventory_ids = {row["inventory_id"] for row in bundle["parts"]}
    bundle["inventory"] = [row for row in data["inventory"] if row["id"] in inventory_ids]
    own_sessions = [row for row in data["sessions"] if row["repair_order_id"] == identity]
    mechanics = {row["mechanic_id"] for row in own_sessions}
    for key in ("sessions", "attendance", "breaks", "time_audits", "attendance_audits", "mechanics", "policies"):
        bundle[key] = [row for row in data[key] if (row["id"] if key == "mechanics" else row["mechanic_id"]) in mechanics]
    # Separate time is reported over the *whole* declared person window,
    # including gaps between selected timers. Occupancy in those gaps must
    # remain loaded and fingerprinted, even though it does not overlap either
    # selected timer individually. Preserve individual candidate support too
    # for open/deleted/invalid evidence used by direct-cost eligibility.
    person_windows = {}
    for candidate in own_sessions:
        if candidate.get("deleted_at") or not candidate.get("ended_at"):
            continue
        try:
            start, end = moment(candidate["started_at"]), moment(candidate["ended_at"])
            if start >= end:
                continue
            previous = person_windows.get(candidate["mechanic_id"])
            person_windows[candidate["mechanic_id"]] = (min(previous[0], start), max(previous[1], end)) if previous else (start, end)
        except (ValueError, TypeError):
            continue
    def overlaps_own(row):
        window = person_windows.get(row["mechanic_id"])
        if window and intersects(*window, row):
            return True
        for candidate in own_sessions:
            if candidate["mechanic_id"] != row["mechanic_id"]:
                continue
            try:
                start = moment(candidate["started_at"])
                end = moment(candidate["ended_at"]) if candidate.get("ended_at") else datetime.max.replace(tzinfo=timezone.utc)
                if intersects(start, end, row):
                    return True
            except (ValueError, TypeError):
                return True
        return False
    bundle["sessions"] = [row for row in bundle["sessions"] if row.get("repair_order_id") == identity or overlaps_own(row)]
    for key in ("attendance", "breaks"):
        bundle[key] = [row for row in bundle[key] if overlaps_own(row)]
    relevant_session_ids = {row["id"] for row in bundle["sessions"]}
    bundle["time_audits"] = [row for row in bundle["time_audits"] if row.get("session_id") in relevant_session_ids]
    relevant_audits = set()
    for mechanic_id, (start, end) in person_windows.items():
        relevant_audits.update(row["id"] for row in relevant_attendance_audits(bundle, {"mechanic_id": mechanic_id}, start, end))
    for session in own_sessions:
        try:
            start = moment(session["started_at"])
            end = moment(session["ended_at"]) if session.get("ended_at") else datetime.max.replace(tzinfo=timezone.utc)
            relevant_audits.update(row["id"] for row in relevant_attendance_audits(bundle, session, start, end))
        except (ValueError, TypeError):
            relevant_audits.update(row["id"] for row in bundle["attendance_audits"] if row["mechanic_id"] == session["mechanic_id"])
    bundle["attendance_audits"] = [row for row in bundle["attendance_audits"] if row["id"] in relevant_audits]
    invoice_ids = {row["id"] for row in bundle["invoices"]}
    for key in ("adjustments", "payments", "refunds", "attempts", "overpayments"):
        bundle[key] = [row for row in data[key] if row["invoice_id"] in invoice_ids]
    attempt_ids = {row["id"] for row in bundle["attempts"]}
    bundle["disputes"] = [row for row in data["disputes"] if row["attempt_id"] in attempt_ids]
    relevant = {row["id"] for row in data["credits"] if row.get("target_invoice_id") in invoice_ids}
    origins = {row["id"] for row in bundle["overpayments"]}
    # Both ancestors and descendants, including malformed cross-customer edges.
    changed = True
    while changed:
        changed = False
        source_ids = {row.get("source_entry_id") for row in data["credits"] if row["id"] in relevant}
        for row in data["credits"]:
            if row["id"] in source_ids or row.get("source_entry_id") in relevant or row.get("origin_overpayment_id") in origins:
                if row["id"] not in relevant:
                    relevant.add(row["id"])
                    changed = True
    bundle["credits"] = [row for row in data["credits"] if row["id"] in relevant]
    origin_map = {row["id"]: row for row in data["overpayments"]}
    # A funding application whose origin is outside exact job source is not
    # assumed native/compatible. It never creates additional issued revenue.
    bundle["credit_ambiguity"] = any(
        row["customer_id"] != order["customer_id"] or
        (row.get("origin_overpayment_id") and (row["origin_overpayment_id"] not in origin_map
         or origin_map[row["origin_overpayment_id"]]["invoice_id"] not in invoice_ids)) or
        (row.get("source_entry_id") and row["source_entry_id"] not in relevant)
        for row in bundle["credits"])
    return_ids = {row["vendor_return_id"] for row in data["return_lines"] if row["inventory_id"] in inventory_ids}
    bundle["return_lines"] = [row for row in data["return_lines"] if row["vendor_return_id"] in return_ids]
    bundle["returns"] = [row for row in data["returns"] if row["id"] in return_ids]
    heads = {}
    for row in bundle["policies"]:
        if row["mechanic_id"] not in heads or row["version"] > heads[row["mechanic_id"]]["version"]:
            heads[row["mechanic_id"]] = row
    bundle["policy_heads"] = heads
    bundle["policy_heads_digest"] = digest({identity: {"revision_id": row["id"], "version": row["version"], "policy": row["policy"]} for identity, row in heads.items()})
    bundle["source_fingerprint"] = digest({"calculation_version": "db136-v1", **bundle})
    bundle["review"] = max((row for row in data["reviews"] if row["order_id"] == identity), key=lambda row: row["version"], default=None)
    return bundle
