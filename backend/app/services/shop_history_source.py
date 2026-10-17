"""Bounded historical context capture, separate from native settlement events.

The invoice foreign key defines one canonical job. ETS operation siblings are
context, never additional invoices or conversion events. No delivery to Google
or financial state mutation occurs here.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSession as Session, async_sessionmaker

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder
from app.db.models.shop_history_cursor import ShopHistoryCursor, ShopHistoryObservation
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.db.session import AsyncSessionLocal
from app.services.conversion_pii_retention_service import SHOP_HISTORY_EVENT

ETS = "easy_truck_shop_import"
ETS_NUMBER = re.compile(r"^(ETS-[0-9]+-[0-9]+)(?:-[0-9]+)?$")


def history_allowed_tenants() -> list[UUID]:
    """Malformed optional history config must never stop native delivery."""
    if not settings.SHOP_HISTORY_CAPTURE_ENABLED:
        return []
    try:
        return [UUID(value.strip()) for value in settings.SHOP_HISTORY_CAPTURE_TENANT_IDS.split(",") if value.strip()]
    except ValueError:
        return []


def _date(value):
    return value.date().isoformat() if value else None


def _status(value):
    return value.value if hasattr(value, "value") else value


def snapshot_revision(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def history_snapshot(*, tenant: Tenant, invoice: Invoice, order: RepairOrder,
                     customer: Customer, vehicle: Vehicle | None,
                     operations: list[RepairOrder], grouping_uncertain: bool = False,
                     settled_amount: Decimal | None = None) -> dict:
    resources = [invoice, order, customer, *operations] + ([vehicle] if vehicle else [])
    if any(resource.tenant_id != tenant.id for resource in resources):
        raise ValueError("History resources must belong to the same tenant")
    if invoice.repair_order_id != order.id or order.customer_id != customer.id or (vehicle and vehicle.id != order.vehicle_id):
        raise ValueError("History resource relationships do not match")
    if invoice.source not in (None, ETS) or order.source not in (None, ETS):
        raise ValueError("Unsupported history source")
    amount = Decimal(invoice.total_amount)
    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid invoice history amount")
    imported = invoice.source == ETS or order.source == ETS
    paid_at = invoice.paid_at
    if paid_at and paid_at.tzinfo is None:
        # Native timestamp columns are timezone-aware; SQLite fixture roundtrip
        # loses that metadata. PostgreSQL supplies aware UTC values.
        paid_at = paid_at.replace(tzinfo=timezone.utc)
    native_paid = not imported and _status(invoice.status) == "paid"
    if native_paid:
        if settled_amount is None:
            paid_at = None
    uncertain = grouping_uncertain or invoice.source != order.source
    uncertain |= any(item.customer_id != order.customer_id or item.vehicle_id != order.vehicle_id for item in operations)
    uncertain |= any(item.deleted_at is not None for item in resources)
    # Bound even worst-case escaped Unicode under the receiver body ceiling.
    # Truncation is explicit and forces review, never matching on shortened text.
    uncertain |= any(item.description and len(item.description) > 500 for item in operations)
    from app.services.account_contact_snapshot import for_history
    from app.services.ets_completed_outcome_source import configured_shops
    source_customer_id = getattr(customer, "ets_external_id", None)
    if not isinstance(source_customer_id, str) or not re.fullmatch(r"[0-9]{1,50}", source_customer_id):
        source_customer_id = None
    contact_snapshot = for_history(getattr(customer, "ets_contact_phone_snapshot", None),
                                   customer_id=source_customer_id, dbn_customer_id=customer.id,
                                   shop_id=configured_shops().get(order.tenant_id), source=customer.source)
    return {
        "source": ETS if imported else "dieselbridge",
        "repair_order_uuid": str(order.id), "repair_order_number": order.order_number,
        "invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number,
        "job_status": _status(order.status), "invoice_status": _status(invoice.status),
        "currency": "USD", "invoice_total": str(amount.quantize(Decimal("0.01"))),
        "completed_date": _date(order.work_completed_at),
        "invoiced_date": invoice.ets_invoiced_at.isoformat() if imported and invoice.ets_invoiced_at else None,
        "paid_date": _date(paid_at.astimezone(timezone.utc)) if paid_at else None,
        "paid_at": paid_at.isoformat() if paid_at and not imported else None,
        "paid_time_precision": ("day" if imported else "instant") if paid_at else "unknown",
        "grouping_uncertain": bool(uncertain),
        "customer": {"id": str(customer.id), "name": customer.company_name or " ".join(filter(None, [customer.first_name, customer.last_name])) or None,
                     "phone": customer.phone, "email": customer.email,
                     **({"source_customer_id": source_customer_id, "contact_phone_snapshot": contact_snapshot}
                        if contact_snapshot is not None else {})},
        "vehicle": {"id": str(vehicle.id) if vehicle else None, "vin": vehicle.vin if vehicle else None, "unit_number": vehicle.unit_number if vehicle else None},
        "operations": [{"repair_order_uuid": str(item.id), "repair_order_number": item.order_number, "description": (item.description[:450] + " [source context truncated; review required]") if item.description and len(item.description) > 500 else item.description}
                       for item in sorted(operations, key=lambda item: (item.order_number, str(item.id)))],
        "attribution": {"elis_opportunity_id": str(order.elis_opportunity_id) if order.elis_opportunity_id else None, "callrail_call_id": order.callrail_call_id},
    }


async def _operations(db: AsyncSession, order: RepairOrder) -> tuple[list[RepairOrder], bool]:
    if order.source != ETS:
        return [order], False
    match = ETS_NUMBER.fullmatch(order.order_number)
    if not match:
        return [order], True
    base = match.group(1)
    # Importer assigns ETS-service-customer and a numbered suffix per operation.
    # Inspect all siblings first; conflicting equipment/customer is held rather
    # than quietly selecting a convenient subset.
    rows = (await db.execute(select(RepairOrder).where(
        RepairOrder.tenant_id == order.tenant_id, RepairOrder.source == ETS,
        or_(RepairOrder.order_number == base, RepairOrder.order_number.like(base + "-%")),
    ).order_by(RepairOrder.order_number, RepairOrder.id).limit(201))).scalars().all()
    exact = [item for item in rows if (m := ETS_NUMBER.fullmatch(item.order_number)) and m.group(1) == base]
    return exact[:200] or [order], len(rows) > 200 or not exact


async def capture_tenant_history(db: Session, tenant: Tenant, *, batch_size: int) -> dict[str, int]:
    """Caller must lock tenant; cursor and outbox commit atomically together."""
    cursor = await db.scalar(select(ShopHistoryCursor).where(ShopHistoryCursor.tenant_id == tenant.id))
    if cursor is None:
        cursor = ShopHistoryCursor(tenant_id=tenant.id)
        db.add(cursor)
        await db.flush()
    known_native = select(ProviderOutboxEvent.id).where(
        ProviderOutboxEvent.tenant_id == tenant.id,
        ProviderOutboxEvent.aggregate_id == RepairOrder.id,
        ProviderOutboxEvent.idempotency_key.like("native-completed:%"),
        ProviderOutboxEvent.event_type.in_(["repair.completed_invoice_snapshot", "repair.completed_invoice_hold"]),
    ).exists()
    public_history = and_(Invoice.is_internal.is_(False), Customer.id.is_not(None),
        or_(Invoice.source.is_(None), Invoice.source == ETS),
        or_(RepairOrder.source.is_(None), RepairOrder.source == ETS))
    query = select(Invoice, RepairOrder, Customer, Vehicle, known_native).join(
        RepairOrder, and_(Invoice.repair_order_id == RepairOrder.id, RepairOrder.tenant_id == tenant.id),
    ).outerjoin(Customer, and_(RepairOrder.customer_id == Customer.id, Customer.tenant_id == tenant.id)).outerjoin(
        Vehicle, and_(RepairOrder.vehicle_id == Vehicle.id, Vehicle.tenant_id == tenant.id),
    ).where(Invoice.tenant_id == tenant.id, or_(public_history, known_native))
    if cursor.last_invoice_id:
        query = query.where(Invoice.id > cursor.last_invoice_id)
    rows = (await db.execute(query.order_by(Invoice.id).limit(batch_size))).all()
    captured = 0
    for invoice, order, customer, vehicle, had_native in rows:
        # Known completion streams must observe invalidation even when current
        # facts no longer qualify for public history or its optional context.
        if order.source is None or had_native:
            from app.services.native_completed_outcome_source import capture_native_order
            await capture_native_order(db, tenant.id, order.id)
        if (invoice.is_internal or customer is None or invoice.source not in (None, ETS)
                or order.source not in (None, ETS)):
            cursor.last_invoice_id = invoice.id
            continue
        operations, uncertain = await _operations(db, order)
        try:
            settled_amount = None
            if invoice.source is None and order.source is None and _status(invoice.status) == "paid":
                from app.services.paid_invoice_webhook_service import native_settled_amount
                settled_amount = await native_settled_amount(db, tenant=tenant, invoice=invoice, order=order)
            snapshot = history_snapshot(tenant=tenant, invoice=invoice, order=order, customer=customer,
                                        vehicle=vehicle, operations=operations, grouping_uncertain=uncertain or vehicle is None, settled_amount=settled_amount)
        except (ValueError, TypeError, InvalidOperation):
            # Record a non-deliverable, non-PII failure instead of allowing one
            # malformed source record to strand the rest of the scan forever.
            failure_key = f"job-history-invalid:{invoice.id}"
            failure = await db.scalar(select(ProviderOutboxEvent.id).where(
                ProviderOutboxEvent.tenant_id == tenant.id,
                ProviderOutboxEvent.idempotency_key == failure_key,
                ProviderOutboxEvent.event_type == "job.history_capture_failed"))
            if failure is None:
                now = datetime.now(timezone.utc)
                db.add(ProviderOutboxEvent(tenant_id=tenant.id, event_type="job.history_capture_failed",
                    aggregate_type="invoice", aggregate_id=invoice.id, idempotency_key=failure_key,
                    payload={"invoice_id": str(invoice.id), "reason": "invalid_source_history"},
                    status=ProviderOutboxStatus.DEAD.value, available_at=now, completed_at=now,
                    last_error="Source history validation failed; source review required"))
            previous = await db.scalar(select(ProviderOutboxEvent).where(
                ProviderOutboxEvent.tenant_id == tenant.id,
                ProviderOutboxEvent.event_type == SHOP_HISTORY_EVENT,
                ProviderOutboxEvent.aggregate_id == invoice.id,
            ).order_by(ProviderOutboxEvent.created_at.desc(), ProviderOutboxEvent.id.desc()).limit(1))
            prior_snapshot = (previous.payload or {}).get("snapshot") if previous else None
            if not prior_snapshot:
                # PII expiry must not be undone by reconstructing old evidence.
                # The durable failed-capture audit is the explicit boundary.
                cursor.last_invoice_id = invoice.id
                continue
            snapshot = deepcopy(prior_snapshot)
            snapshot["grouping_uncertain"] = True
        revision = snapshot_revision(snapshot)
        observation = await db.scalar(select(ShopHistoryObservation).where(
            ShopHistoryObservation.tenant_id == tenant.id,
            ShopHistoryObservation.invoice_id == invoice.id))
        # Tenant lock serializes observations. Cursor, observation and outbox
        # commit together; replay after rollback retains exactly one identity.
        if observation is None or observation.source_revision != revision:
            if observation is None:
                observation = ShopHistoryObservation(tenant_id=tenant.id, invoice_id=invoice.id,
                                                     source_revision=revision, sequence=1)
                db.add(observation)
            else:
                observation.sequence += 1
                observation.source_revision = revision
            key = f"job-history:{invoice.id}:{observation.sequence}:{revision}"
            event_id, now = uuid4(), datetime.now(timezone.utc)
            db.add(ProviderOutboxEvent(id=event_id, tenant_id=tenant.id, event_type=SHOP_HISTORY_EVENT,
                aggregate_type="invoice", aggregate_id=invoice.id, idempotency_key=key,
                status=ProviderOutboxStatus.PENDING.value, available_at=now, created_at=now,
                payload={"schema_version": 2 if "contact_phone_snapshot" in snapshot["customer"] else 1,
                         "event_type": SHOP_HISTORY_EVENT, "event_id": str(event_id),
                         "occurred_at": now.isoformat(), "shop_id": str(tenant.id), "source_system": "dieselbridge",
                         "source_revision": revision, "source_observation": observation.sequence, "snapshot": snapshot}))
            captured += 1
        if order.source == ETS:
            from app.services.ets_completed_outcome_source import capture_imported_order, ETSCompletionHold
            try:
                await capture_imported_order(db, tenant.id, order.id)
            except ETSCompletionHold:
                # Unbound identities cannot become evidence. Freshness gating in
                # ELIS prevents older positive observations remaining usable.
                pass
        cursor.last_invoice_id = invoice.id
    if len(rows) < batch_size:
        cursor.last_invoice_id = None
    cursor.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"scanned": len(rows), "captured": captured}


async def capture_shop_history_batch(*, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal) -> dict[str, int]:
    result = {"scanned": 0, "captured": 0, "tenants": 0}
    if not settings.SHOP_HISTORY_CAPTURE_ENABLED:
        return result
    allowed = history_allowed_tenants()
    if not allowed:
        return result
    async with session_factory() as db:
        # One tenant per run bounds work; oldest cursor wins, so enabled tenants
        # rotate fairly. Tenant lock also serializes overlapping beat deliveries.
        tenant = await db.scalar(select(Tenant).outerjoin(ShopHistoryCursor, ShopHistoryCursor.tenant_id == Tenant.id).where(
            Tenant.id.in_(allowed), Tenant.deleted_at.is_(None),
            Tenant.paid_invoice_webhook_enabled.is_(True), Tenant.paid_invoice_webhook_delivery_paused.is_(False),
            Tenant.paid_invoice_webhook_url.is_not(None), Tenant.paid_invoice_webhook_secret_encrypted.is_not(None),
        ).order_by(ShopHistoryCursor.updated_at.asc().nullsfirst(), Tenant.id).limit(1).with_for_update(skip_locked=True, of=Tenant))
        if tenant:
            counts = await capture_tenant_history(db, tenant, batch_size=settings.SHOP_HISTORY_CAPTURE_BATCH_SIZE)
            result.update(counts, tenants=1)
        await db.commit()
    return result
