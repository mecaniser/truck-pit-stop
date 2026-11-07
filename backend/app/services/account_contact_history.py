"""Prioritized daily account evidence, reusing genuine ETS reads and history v2."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import UUID

from sqlalchemy import JSON, String, column, and_, cast, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.repair_order import RepairOrder
from app.db.models.tenant import Tenant
from app.db.models.vehicle import Vehicle
from app.db.session import AsyncSessionLocal
from app.services.account_contact_snapshot import for_history, instant
from app.services.conversion_pii_retention_service import SHOP_HISTORY_EVENT, SIGNED_OUTCOME_EVENT_TYPES
from app.services.shop_history_source import (
    CONTACT_HISTORY_PREFIX, ETS, _operations, enqueue_history_snapshot,
    history_allowed_tenants, history_snapshot,
)


CONTACT_CAPTURE_FAILED = "job.contact_capture_failed"


def contact_observation_key(customer_id: UUID, observation: dict) -> str:
    """Same source read is one immutable identity; same-day changes stay distinct."""
    # semantic_hash covers every contact fact except the original read time.
    return f"{CONTACT_HISTORY_PREFIX}{customer_id.hex}:{observation['observed_at']}:{observation['semantic_hash']}"


def _account_candidates(tenant_id: UUID, shop_id: str, *, now: datetime, batch_size: int):
    evidence = Customer.ets_contact_phone_snapshot
    observed = evidence["observed_at"].as_string()
    # Imported source timestamps are normalized to aware UTC by the collector.
    # Recheck time and the full digest in Python before emitting any evidence.
    key = (literal(CONTACT_HISTORY_PREFIX) + func.replace(cast(Customer.id, String), "-", "")
           + literal(":") + observed + literal(":") + evidence["semantic_hash"].as_string())
    previously_queued = exists().where(
        ProviderOutboxEvent.tenant_id == tenant_id,
        ProviderOutboxEvent.event_type == SHOP_HISTORY_EVENT,
        ProviderOutboxEvent.idempotency_key == key,
    )
    failed_read = exists().where(
        ProviderOutboxEvent.tenant_id == tenant_id,
        ProviderOutboxEvent.event_type == CONTACT_CAPTURE_FAILED,
        ProviderOutboxEvent.aggregate_id == Customer.id,
        ProviderOutboxEvent.payload["source_observed_at"].as_string() == observed,
        ProviderOutboxEvent.payload["source_semantic_hash"].as_string().is_not_distinct_from(evidence["semantic_hash"].as_string()),
    )
    # Group once per tenant, rather than probing all historical JSON per account.
    redactions = select(RepairOrder.customer_id.label("customer_id"),
        func.max(ProviderOutboxEvent.payload["pii_redacted_at"].as_string()).label("redacted_at"),
    ).select_from(ProviderOutboxEvent).join(Invoice, and_(
        ProviderOutboxEvent.aggregate_id == Invoice.id, Invoice.tenant_id == tenant_id,
    )).join(RepairOrder, and_(Invoice.repair_order_id == RepairOrder.id, RepairOrder.tenant_id == tenant_id)).where(
        ProviderOutboxEvent.tenant_id == tenant_id,
        ProviderOutboxEvent.event_type.in_(SIGNED_OUTCOME_EVENT_TYPES),
        ProviderOutboxEvent.payload["pii_redacted_at"].as_string().is_not(None),
    ).group_by(RepairOrder.customer_id).subquery()
    supported_invoice = exists().where(
        Invoice.tenant_id == tenant_id, Invoice.source == ETS,
        Invoice.is_internal.is_(False), Invoice.deleted_at.is_(None),
        RepairOrder.tenant_id == tenant_id, RepairOrder.source == ETS,
        RepairOrder.deleted_at.is_(None), RepairOrder.customer_id == Customer.id,
        Invoice.repair_order_id == RepairOrder.id,
    )
    return select(Customer).outerjoin(redactions, redactions.c.customer_id == Customer.id).where(
        Customer.tenant_id == tenant_id, Customer.source == ETS, Customer.deleted_at.is_(None),
        evidence.is_not(None), observed > (now - timedelta(hours=20)).isoformat(),
        observed <= now.isoformat(), evidence["source_shop_id"].as_string() == shop_id,
        evidence["source_customer_id"].as_string() == Customer.ets_external_id,
        func.replace(evidence["dbn_customer_id"].as_string(), "-", "")
        == func.replace(cast(Customer.id, String), "-", ""),
        supported_invoice, ~previously_queued, ~failed_read,
        or_(redactions.c.redacted_at.is_(None), redactions.c.redacted_at < observed),
    ).order_by(Customer.id).limit(batch_size)


async def _record_invalid_read(db: AsyncSession, tenant: Tenant, customer: Customer, original: dict) -> None:
    """Terminal, non-deliverable diagnostic lets later accounts make progress."""
    fingerprint = hashlib.sha256(json.dumps(original, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    key = f"contact-invalid:{customer.id}:{fingerprint}"
    existing = await db.scalar(select(ProviderOutboxEvent.id).where(
        ProviderOutboxEvent.tenant_id == tenant.id, ProviderOutboxEvent.event_type == CONTACT_CAPTURE_FAILED,
        ProviderOutboxEvent.idempotency_key == key))
    if existing is None:
        now = datetime.now(timezone.utc)
        db.add(ProviderOutboxEvent(tenant_id=tenant.id, event_type=CONTACT_CAPTURE_FAILED,
            aggregate_type="customer", aggregate_id=customer.id, idempotency_key=key,
            status="dead", available_at=now, completed_at=now,
            payload={"source_observed_at": original.get("observed_at"),
                     "source_semantic_hash": original.get("semantic_hash"), "reason": "invalid_source_contact_history"},
            last_error="Source contact history validation failed; source review required"))


async def capture_tenant_account_contacts(db: AsyncSession, tenant: Tenant, *, shop_id: str,
                                         batch_size: int, now: datetime | None = None) -> dict[str, int]:
    """Caller locks tenant, serializing daily and rotating invoice observations."""
    current = now or datetime.now(timezone.utc)
    result = {"scanned": 0, "captured": 0, "invalid": 0}
    customers = list((await db.scalars(_account_candidates(
        tenant.id, shop_id, now=current, batch_size=batch_size))).all())
    for customer in customers:
        result["scanned"] += 1
        original = customer.ets_contact_phone_snapshot
        observation = for_history(original, customer_id=customer.ets_external_id,
            dbn_customer_id=customer.id, shop_id=shop_id, source=customer.source)
        try:
            observed = instant(observation["observed_at"])
            if not current - timedelta(hours=20) < observed <= current or observation != original:
                raise ValueError("Untrusted or stale source contact observation")
            key = contact_observation_key(customer.id, observation)
        except (KeyError, ValueError, TypeError):
            result["invalid"] += 1
            await _record_invalid_read(db, tenant, customer, original)
            continue
        row = (await db.execute(select(Invoice, RepairOrder, Vehicle).join(
            RepairOrder, and_(Invoice.repair_order_id == RepairOrder.id,
                              RepairOrder.tenant_id == tenant.id),
        ).outerjoin(Vehicle, and_(Vehicle.id == RepairOrder.vehicle_id, Vehicle.tenant_id == tenant.id)).where(
            Invoice.tenant_id == tenant.id, Invoice.source == ETS, Invoice.is_internal.is_(False),
            Invoice.deleted_at.is_(None), RepairOrder.source == ETS, RepairOrder.deleted_at.is_(None),
            RepairOrder.customer_id == customer.id,
        ).order_by(Invoice.id).limit(1))).first()
        if row is None:
            continue
        invoice, order, vehicle = row
        operations, uncertain = await _operations(db, order)
        try:
            source_evidence = None
            if settings.ETS_COMPLETED_OUTCOMES_ENABLED:
                source_evidence = await db.scalar(select(column("ets_source_evidence", JSON)).select_from(Invoice).where(
                    Invoice.tenant_id == tenant.id, Invoice.id == invoice.id))
            snapshot = history_snapshot(tenant=tenant, invoice=invoice, order=order,
                customer=customer, vehicle=vehicle, operations=operations,
                grouping_uncertain=uncertain or vehicle is None, ets_source_evidence=source_evidence)
            event = await enqueue_history_snapshot(db, tenant=tenant, invoice=invoice,
                                                   snapshot=snapshot, idempotency_key=key)
        except (ValueError, TypeError, ArithmeticError):
            result["invalid"] += 1
            await _record_invalid_read(db, tenant, customer, original)
            continue
        if event is not None:
            result["captured"] += 1
    await db.flush()
    return result


async def capture_account_contacts_batch(*,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> dict[str, int]:
    result = {"scanned": 0, "captured": 0, "invalid": 0, "tenants": 0}
    from app.services.ets_completed_outcome_source import configured_shops
    shops = configured_shops()
    allowed = history_allowed_tenants()
    if not allowed:
        return result
    remaining = settings.SHOP_HISTORY_CAPTURE_BATCH_SIZE
    for tenant_id in sorted(set(allowed), key=str):
        if remaining <= 0:
            break
        shop_id = shops.get(tenant_id)
        if not shop_id:
            continue
        async with session_factory() as db:
            tenant = await db.scalar(select(Tenant).where(
                Tenant.id == tenant_id, Tenant.deleted_at.is_(None), Tenant.is_active.is_(True),
                Tenant.paid_invoice_webhook_enabled.is_(True),
                Tenant.paid_invoice_webhook_url.is_not(None),
                Tenant.paid_invoice_webhook_secret_encrypted.is_not(None),
            ).with_for_update(skip_locked=True))
            if tenant is None:
                continue
            counts = await capture_tenant_account_contacts(db, tenant, shop_id=shop_id, batch_size=remaining)
            for name, count in counts.items():
                result[name] += count
            result["tenants"] += 1
            remaining -= counts["scanned"]
            await db.commit()
    return result
