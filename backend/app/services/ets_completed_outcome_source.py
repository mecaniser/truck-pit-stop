"""ETS completed invoice evidence, separate from native settlement authority.

A singular embedded invoice does not establish service invoice completeness.
Callers must supply a collector-verified complete manifest; without one this
adapter reports a hold and never manufactures an outcome or a timestamp.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from sqlalchemy import select, text

from scripts.easytruck_sync.source_evidence import latest_source_evidence
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.invoice import Invoice
from app.db.models.tenant import Tenant

ETS_COMPLETED_EVENT = "repair.completed_invoice_snapshot"
ETS_HOLD_EVENT = "repair.completed_invoice_hold"
ETS_EVENTS = {ETS_COMPLETED_EVENT, ETS_HOLD_EVENT}
SOURCE = "easy_truck_shop_import"


class ETSCompletionHold(ValueError):
    """A stable non-PII diagnostic, not permission to guess missing facts."""


def identifier(value):
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
        raise ETSCompletionHold("source_identity_unavailable")
    return value


def amount(value):
    if not isinstance(value, dict) or value.get("currency") != "USD":
        raise ETSCompletionHold("unsupported_currency")
    raw = value.get("amount")
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
        raise ETSCompletionHold("amount_unavailable")
    try:
        parsed = Decimal(str(raw))
        if not parsed.is_finite() or parsed < 0 or parsed != parsed.quantize(Decimal("0.01")):
            raise ETSCompletionHold("amount_precision_or_sign")
    except InvalidOperation as exc:
        raise ETSCompletionHold("amount_unavailable") from exc
    return parsed


def _time(raw, now):
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0 or parsed > now:
            raise ValueError()
    except (AttributeError, ValueError, TypeError) as exc:
        raise ETSCompletionHold("completion_instant_unavailable") from exc
    return parsed.isoformat()


def completed_snapshot(*, tenant_id, order, evidence, ets_shop_id, manifest, observed_at):
    """Build only from a complete current service observation, never payment.date.

    `manifest` must come from a verified source enumeration, not the DB's known
    imported invoices. This phase has no production collector able to assert it.
    """
    if order.tenant_id != tenant_id or order.source != SOURCE or order.deleted_at is not None:
        raise ETSCompletionHold("source_order_mismatch")
    if observed_at.utcoffset() is None:
        raise ETSCompletionHold("observation_time_unavailable")
    if not evidence or len(evidence) > 200:
        raise ETSCompletionHold("source_evidence_unavailable")
    if (not isinstance(manifest, dict) or manifest.get("complete") is not True
            or manifest.get("evidence_kind") != "verified_source_service_invoice_manifest"):
        raise ETSCompletionHold("source_invoice_manifest_unverified")
    shop_id = identifier(ets_shop_id)
    first = evidence[0]
    service_id = identifier(first.get("service_id"))
    internal_id = identifier(first.get("service_internal_id"))
    if not service_id.isdigit() or len(service_id) > 140:
        raise ETSCompletionHold("source_identity_unavailable")
    if not re.fullmatch(rf"ETS-{re.escape(service_id)}-[0-9]+(?:-[0-9]+)?", order.order_number):
        raise ETSCompletionHold("source_service_order_mismatch")
    completed_at = _time(first.get("completed_at_source"), observed_at)
    invoices = []
    ids = set()
    for row in evidence:
        if (row.get("source") != "easy_truck_shop" or row.get("ets_shop_id") != shop_id
                or identifier(row.get("service_id")) != service_id
                or identifier(row.get("service_internal_id")) != internal_id
                or identifier(row.get("invoice_service_id")) != internal_id):
            raise ETSCompletionHold("source_identity_mismatch")
        if row.get("completed") is not True or type(row.get("service_status")) is not int or row["service_status"] != 60:
            raise ETSCompletionHold("service_not_verified_completed")
        if _time(row.get("completed_at_source"), observed_at) != completed_at:
            raise ETSCompletionHold("completion_conflict")
        if str(row.get("invoice_status")) != "10":
            raise ETSCompletionHold("unsupported_invoice_status")
        invoice_id = identifier(row.get("invoice_id"))
        if invoice_id in ids:
            raise ETSCompletionHold("duplicate_invoice")
        ids.add(invoice_id)
        total, balance = amount(row.get("total")), amount(row.get("balance"))
        if total <= 0 or balance != 0:
            raise ETSCompletionHold("invoice_not_fully_paid")
        if row.get("currency") != "USD" or row.get("payment_lines_truncated") is not False:
            raise ETSCompletionHold("allocation_evidence_incomplete")
        lines = row.get("payment_lines")
        if not isinstance(lines, list) or not lines or len(lines) > 200:
            raise ETSCompletionHold("allocation_evidence_incomplete")
        allocations, allocation_ids, allocated = [], set(), Decimal("0")
        for line in lines:
            allocation_id = identifier(line.get("id"))
            if allocation_id in allocation_ids:
                raise ETSCompletionHold("duplicate_allocation")
            allocation_ids.add(allocation_id)
            payment = line.get("payment") or {}
            allocated_amount = amount(line.get("amount"))
            if (str(payment.get("status")) != "20" or str(payment.get("type")) not in {"0", "10"}
                    or str(payment.get("provider")) not in {"0", "1"} or payment.get("canceled") is not False
                    or amount(payment.get("credit_total")) != 0 or amount(payment.get("unapplied_amount")) != 0
                    or allocated_amount <= 0):
                raise ETSCompletionHold("unsupported_payment_state")
            allocated += allocated_amount
            allocations.append({"allocation_id": allocation_id, "payment_id": identifier(payment.get("id")),
                "amount": format(allocated_amount, ".2f"), "currency": "USD", "payment_status": 20,
                "payment_type": int(payment["type"]), "provider": int(payment["provider"]),
                "canceled": False, "credit_total": "0.00", "unapplied_amount": "0.00"})
        if allocated != total:
            raise ETSCompletionHold("allocation_total_mismatch")
        try:
            imported_invoice_uuid = str(UUID(str(row.get("imported_invoice_uuid"))))
        except ValueError as exc:
            raise ETSCompletionHold("source_identity_unavailable") from exc
        invoices.append({"invoice_id": invoice_id, "imported_invoice_uuid": imported_invoice_uuid,
            "invoice_number": identifier(row.get("invoice_number")),
            "invoice_service_internal_id": internal_id, "invoice_status": 10, "currency": "USD",
            "total": format(total, ".2f"), "balance": "0.00", "allocations_complete": True,
            "allocations": sorted(allocations, key=lambda allocation: allocation["allocation_id"])})
    manifest_ids = manifest.get("invoice_ids")
    if not isinstance(manifest_ids, list) or len(manifest_ids) != len(ids) or set(manifest_ids) != ids:
        raise ETSCompletionHold("invoice_manifest_mismatch")
    return {"source": SOURCE, "ets_shop_id": shop_id, "source_job_id": f"ets-service:{service_id}",
        "service_id": service_id, "service_internal_id": internal_id, "repair_order_uuid": str(order.id),
        "completed": True, "service_status": 60, "completed_at": completed_at,
        "time_basis": "source_service_completed_at", "value_basis": "completed_invoice_total",
        "invoice_manifest": {"complete": True, "invoice_ids": sorted(ids),
                             "evidence_kind": "verified_source_service_invoice_manifest"},
        "invoices": sorted(invoices, key=lambda invoice: invoice["invoice_id"]),
        "attribution": {"elis_opportunity_id": str(order.elis_opportunity_id) if order.elis_opportunity_id else None,
                        "callrail_call_id": order.callrail_call_id}}


def _verified_legacy_duplicate_roots(*, order, siblings, invoices, snapshot):
    """Ignore only canceled operation copies of a verified singleton invoice.

    This is a read-time identity rule, never a financial-record correction.
    Legacy copies may be soft-deleted by import cleanup; the canonical invoice
    and operation rows must still be live. Every unrecognized invoice continues
    to participate in the root conflict.
    """
    roots = {invoice.repair_order_id for invoice in invoices}
    verified = snapshot.get("invoices", [])
    if len(verified) != 1 or snapshot.get("invoice_manifest", {}).get("complete") is not True:
        return roots
    source_invoice = verified[0]
    canonical = [invoice for invoice in invoices
                 if invoice.repair_order_id == order.id]
    if len(canonical) != 1:
        return roots
    canonical = canonical[0]
    if (str(canonical.id) != source_invoice["imported_invoice_uuid"]
            or canonical.invoice_number != "ETSINV-" + source_invoice["invoice_number"]
            or canonical.status != "paid" or canonical.deleted_at is not None
            or canonical.total_amount != Decimal(source_invoice["total"])):
        return roots
    sibling_map = {sibling.id: sibling for sibling in siblings}
    retained = set()
    for invoice in invoices:
        sibling = sibling_map.get(invoice.repair_order_id)
        artifact = (
            sibling is not None and sibling.id != order.id
            and sibling.tenant_id == order.tenant_id and sibling.source == SOURCE
            and sibling.deleted_at is None and sibling.customer_id == order.customer_id
            and sibling.vehicle_id == order.vehicle_id
            and re.fullmatch(re.escape(order.order_number) + r"-(?:[2-9]|[1-9][0-9]+)", sibling.order_number)
            and invoice.tenant_id == order.tenant_id and invoice.source == SOURCE
            and invoice.status == "cancelled"
            and invoice.invoice_number == canonical.invoice_number + "-" + sibling.order_number
            and invoice.total_amount == canonical.total_amount
            and invoice.billed_customer_id == canonical.billed_customer_id
        )
        if not artifact:
            retained.add(invoice.repair_order_id)
    return retained


async def persist_completed_observation(db: AsyncSession, *, tenant_id, order_id, evidence,
                                        ets_shop_id, manifest, observed_at, force_hold=None):
    """Persist immutable outbox evidence. Delivery remains independently disabled.

    Caller commits transaction. Tenant lock serializes service observations;
    canonical source identity, not the imported UUID, drives replay identity.
    """
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    if tenant is None:
        raise ETSCompletionHold("tenant_unavailable")
    order = await db.scalar(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.tenant_id == tenant_id))
    if order is None:
        raise ETSCompletionHold("source_order_unavailable")
    if not evidence:
        raise ETSCompletionHold("source_identity_unavailable")
    first = evidence[0]
    service_id, internal_id = identifier(first.get("service_id")), identifier(first.get("service_internal_id"))
    if (not service_id.isdigit() or len(service_id) > 140 or first.get("ets_shop_id") != ets_shop_id or order.source != SOURCE
            or not re.fullmatch(rf"ETS-{re.escape(service_id)}-[0-9]+(?:-[0-9]+)?", order.order_number)):
        raise ETSCompletionHold("source_identity_mismatch")
    captured_at = datetime.now(timezone.utc)
    event_type = ETS_COMPLETED_EVENT
    try:
        if force_hold:
            raise ETSCompletionHold(force_hold)
        snapshot = completed_snapshot(tenant_id=tenant_id, order=order, evidence=evidence,
                                     ets_shop_id=ets_shop_id, manifest=manifest, observed_at=observed_at)
    except ETSCompletionHold as exc:
        reason = str(exc)
        hold_reason = ("evidence_capacity_exceeded" if reason == "evidence_capacity_exceeded" else
                       "evidence_truncated" if reason == "evidence_truncated" else
                       "source_read_unavailable" if reason == "source_read_unavailable" else
                       "invoice_manifest_incomplete" if "manifest" in reason else
                       "source_status_unsupported" if "status" in reason or "state" in reason else
                       "allocations_incomplete" if "allocation" in reason or "paid" in reason else
                       "source_identity_conflict" if "identity" in reason or "conflict" in reason else
                       "source_fields_missing")
        event_type = ETS_HOLD_EVENT
        observed_at = captured_at
        snapshot = {"source": SOURCE, "ets_shop_id": identifier(ets_shop_id),
            "source_job_id": f"ets-service:{service_id}", "service_id": service_id,
            "service_internal_id": internal_id, "repair_order_uuid": str(order.id), "hold_reason": hold_reason}

    # An imported service's operations must all have one customer/vehicle and
    # one canonical invoice root; operation siblings do not create outcomes.
    service_prefix = f"ETS-{snapshot['service_id']}-"
    siblings = list(await db.scalars(select(RepairOrder).where(
        RepairOrder.tenant_id == tenant_id, RepairOrder.source == SOURCE,
        RepairOrder.order_number.like(service_prefix + "%")).limit(201)))
    grouping_conflict = len(siblings) > 200 or any(
        row.deleted_at is not None or row.customer_id != order.customer_id or row.vehicle_id != order.vehicle_id
        for row in siblings)
    roots = set(await db.scalars(select(Invoice.repair_order_id).where(
        Invoice.tenant_id == tenant_id, Invoice.source == SOURCE,
        Invoice.repair_order_id.in_([row.id for row in siblings]))))
    if (not grouping_conflict and roots != {order.id}
            and roots.issubset({row.id for row in siblings}) and event_type == ETS_COMPLETED_EVENT):
        invoices = list(await db.scalars(select(Invoice).where(
            Invoice.tenant_id == tenant_id, Invoice.source == SOURCE,
            Invoice.repair_order_id.in_([row.id for row in siblings]))))
        roots = _verified_legacy_duplicate_roots(
            order=order, siblings=siblings, invoices=invoices, snapshot=snapshot)
    grouping_conflict |= roots != {order.id}
    identity = hashlib.sha256(f"{snapshot['ets_shop_id']}:{snapshot['source_job_id']}".encode()).hexdigest()
    key_prefix = f"ets-completed:{identity}:"
    previous = await db.scalar(select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.tenant_id == tenant_id, ProviderOutboxEvent.event_type.in_(ETS_EVENTS),
        ProviderOutboxEvent.idempotency_key.like(key_prefix + "%"),
    ).order_by(ProviderOutboxEvent.payload["source_observation"].as_integer().desc()).limit(1))
    if previous and not previous.payload.get("snapshot"):
        raise ETSCompletionHold("source_observation_expired")
    grouping_conflict |= bool(previous and previous.payload["snapshot"]["repair_order_uuid"] != str(order.id))
    if grouping_conflict:
        if previous is None:
            raise ETSCompletionHold("canonical_source_root_conflict")
        # Invalidate the previously verified identity; never move its association
        # to whichever conflicting local operation happened to be scanned.
        snapshot = {key: previous.payload["snapshot"][key] for key in (
            "source", "ets_shop_id", "source_job_id", "service_id", "service_internal_id", "repair_order_uuid")}
        snapshot["hold_reason"] = "source_identity_conflict"
        event_type, observed_at = ETS_HOLD_EVENT, captured_at
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if previous:
        prior_observed_at = datetime.fromisoformat(previous.payload["observed_at"].replace("Z", "+00:00"))
        if event_type == ETS_COMPLETED_EVENT and observed_at < prior_observed_at:
            # A cached/late older positive cannot undo a newer diagnostic hold.
            return previous
        if (previous.payload.get("source_revision") == digest
                and (event_type == ETS_HOLD_EVENT or previous.payload.get("observed_at") == observed_at.astimezone(timezone.utc).isoformat())):
            return previous
    sequence = previous.payload["source_observation"] + 1 if previous else 1
    event_id = uuid4()
    event = ProviderOutboxEvent(id=event_id, tenant_id=tenant_id, event_type=event_type,
        aggregate_type="repair_order", aggregate_id=UUID(snapshot["repair_order_uuid"]),
        idempotency_key=f"{key_prefix}{sequence}:{digest}", status=ProviderOutboxStatus.PENDING.value,
        available_at=captured_at, created_at=captured_at,
        payload={"schema_version": 1, "source_system": "dieselbridge", "event_type": event_type,
                 "event_id": str(event_id), "shop_id": str(tenant_id), "occurred_at": snapshot.get("completed_at", observed_at.isoformat()),
                 "observed_at": observed_at.astimezone(timezone.utc).isoformat(), "source_observation": sequence,
                 "source_revision": digest, "snapshot": snapshot})
    db.add(event)
    await db.flush()
    return event


def configured_shops():
    from app.core.config import settings
    if not settings.ETS_COMPLETED_OUTCOMES_ENABLED:
        return {}
    try:
        values = json.loads(settings.ETS_COMPLETED_OUTCOME_SHOPS)
        return {UUID(key): identifier(value) for key, value in values.items()}
    except (ValueError, TypeError, AttributeError):
        return {}


async def capture_imported_order(db: AsyncSession, tenant_id, order_id):
    """Read preserved current source evidence only; no provider calls or financial writes.

    Runs inside the existing bounded history sweep only when explicitly enabled.
    The current collector stores one embedded invoice per service, so multi-invoice
    manifests stay held until every invoice has source evidence on the same root.
    """
    shop_id = configured_shops().get(tenant_id)
    if not shop_id:
        return None
    rows = (await db.execute(text("""SELECT id, ets_source_evidence, deleted_at FROM invoices
        WHERE tenant_id=:tenant_id AND repair_order_id=:order_id AND source=:source
        ORDER BY id"""), {"tenant_id": tenant_id, "order_id": order_id, "source": SOURCE})).all()
    evidence, force_hold = [], None
    for invoice_id, envelope, deleted_at in rows:
        if deleted_at is not None:
            force_hold = "source_status_unsupported"
        observations = (envelope or {}).get("observations", []) if isinstance(envelope, dict) else []
        if not observations:
            force_hold = "source_read_unavailable"
            continue
        if envelope.get("source_read_unavailable_at"):
            force_hold = "source_read_unavailable"
        if envelope.get("revision_capacity_exceeded") or len(observations) > 39:
            force_hold = "evidence_capacity_exceeded"
        row = latest_source_evidence(envelope)
        row["imported_invoice_uuid"] = str(invoice_id)
        evidence.append(row)
    if not evidence:
        # No verified binding exists: never infer it from local names or phone.
        return None
    now = datetime.now(timezone.utc)
    observed = []
    for row in evidence:
        try:
            stamp = datetime.fromisoformat(row["observed_at_source"].replace("Z", "+00:00"))
            if stamp.utcoffset() is None or stamp > now or stamp < now - timedelta(hours=24):
                raise ValueError()
            observed.append(stamp)
        except (KeyError, AttributeError, TypeError, ValueError):
            force_hold = "source_read_unavailable"
    # Source holds describe what the collector could establish now, never value.
    observed_at = min(observed) if len(observed) == len(evidence) else now
    manifest = evidence[0].get("invoice_manifest")
    if any(row.get("invoice_manifest") != manifest for row in evidence):
        manifest = None
    return await persist_completed_observation(db, tenant_id=tenant_id, order_id=order_id, evidence=evidence,
        ets_shop_id=shop_id, manifest=manifest, observed_at=observed_at, force_hold=force_hold)
