"""Supported conversion-event contract and durable signed webhook delivery."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.paid_invoice_webhook_crypto import decrypt_paid_invoice_webhook_secret
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.session import AsyncSessionLocal
from app.services.provider_outbox_service import ProviderDeliveryError, enqueue_email_notification


CONVERSION_EVENT_TYPES = {
    "repair_order.paid",
    "repair_order.payment_refunded",
    "repair_order.payment_voided",
    "repair_order.payment_adjusted",
}
PAID_INVOICE_WEBHOOK_EVENT = "repair_order.paid"  # compatibility export


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(value) -> float:
    return float(Decimal(value or 0).quantize(Decimal("0.01")))


def service_lines(invoice: Invoice) -> list[dict]:
    snapshot = invoice.line_items_snapshot or {}
    lines = []
    for item in snapshot.get("labor", []):
        lines.append({"name": item.get("description") or "Labor", "quantity": float(item.get("hours") or 1), "amount": _money(item.get("total_cost"))})
    for item in snapshot.get("parts", []):
        lines.append({"name": item.get("name") or "Part", "quantity": float(item.get("quantity") or 1), "amount": _money(item.get("total_price"))})
    return lines


def attribution(order: RepairOrder) -> dict:
    return {
        "lead_source_channel": order.lead_source_channel,
        "external_lead_id": order.external_lead_id,
        "callrail_call_id": order.callrail_call_id,
        "gclid": order.google_click_id,
        "gbraid": order.gbraid,
        "wbraid": order.wbraid,
        "landing_page_url": order.landing_page_url,
        "utm_source": order.utm_source,
        "utm_medium": order.utm_medium,
        "utm_campaign": order.utm_campaign,
        "utm_term": order.utm_term,
        "utm_content": order.utm_content,
    }


def conversion_payload(*, event_id: UUID, event_type: str, tenant: Tenant, invoice: Invoice, order: RepairOrder, customer: Optional[Customer], occurred_at: Optional[datetime] = None, total_amount=None) -> dict:
    timestamp = occurred_at or _now()
    return {
        "event_id": str(event_id),
        "event_type": event_type,
        "occurred_at": timestamp.isoformat(),
        "shop_id": str(tenant.id),
        "repair_order_id": order.order_number,
        "invoice_id": str(invoice.id),
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "currency": "USD",
        "total_amount": _money(invoice.total_amount if total_amount is None else total_amount),
        "service_lines": service_lines(invoice),
        "customer": {"email": customer.email if customer else invoice.recipient_email, "phone": customer.phone if customer else invoice.recipient_phone},
        "attribution": attribution(order),
    }


async def enqueue_conversion_event(db: AsyncSession, *, tenant: Optional[Tenant], invoice: Invoice, order: RepairOrder, customer: Optional[Customer], event_type: str, idempotency_key: str, total_amount=None) -> Optional[ProviderOutboxEvent]:
    if event_type not in CONVERSION_EVENT_TYPES:
        raise ValueError("Unsupported conversion event type")
    if not tenant or not tenant.paid_invoice_webhook_enabled or not tenant.paid_invoice_webhook_url or not tenant.paid_invoice_webhook_secret_encrypted:
        return None
    if not order.id or not order.order_number or order.deleted_at is not None:
        return None
    if event_type == "repair_order.paid" and (invoice.status != InvoiceStatus.PAID or order.status != RepairOrderStatus.PAID or Decimal(invoice.total_amount or 0) <= 0):
        return None
    event_id = uuid4()
    event = ProviderOutboxEvent(
        id=event_id, tenant_id=tenant.id, event_type=event_type, aggregate_type="invoice", aggregate_id=invoice.id,
        payload=conversion_payload(event_id=event_id, event_type=event_type, tenant=tenant, invoice=invoice, order=order, customer=customer, total_amount=total_amount),
        idempotency_key=idempotency_key, status=ProviderOutboxStatus.PENDING.value, available_at=_now(),
    )
    db.add(event)
    return event


async def enqueue_paid_invoice_webhook(db: AsyncSession, *, tenant: Optional[Tenant], invoice: Invoice, order: RepairOrder, customer: Optional[Customer]) -> Optional[ProviderOutboxEvent]:
    return await enqueue_conversion_event(db, tenant=tenant, invoice=invoice, order=order, customer=customer, event_type="repair_order.paid", idempotency_key=f"repair-order-paid:{invoice.id}")


async def _claim(db: AsyncSession, limit: int) -> list[tuple[UUID, str]]:
    now = _now()
    due = or_(
        and_(ProviderOutboxEvent.status == ProviderOutboxStatus.PENDING.value, ProviderOutboxEvent.available_at <= now),
        and_(ProviderOutboxEvent.status == ProviderOutboxStatus.PROCESSING.value, ProviderOutboxEvent.locked_until <= now),
    )
    rows = (await db.execute(select(ProviderOutboxEvent).where(ProviderOutboxEvent.event_type.in_(CONVERSION_EVENT_TYPES), due).order_by(ProviderOutboxEvent.available_at).limit(limit).with_for_update(skip_locked=True))).scalars()
    claims = []
    for event in rows:
        token = uuid4().hex
        event.status, event.lock_token, event.locked_at = ProviderOutboxStatus.PROCESSING.value, token, now
        event.locked_until, event.last_attempt_at = now + timedelta(seconds=settings.PROVIDER_OUTBOX_LEASE_SECONDS), now
        event.attempt_count += 1
        claims.append((event.id, token))
    await db.commit()
    return claims


def _retry_delay(attempt: int) -> timedelta:
    return timedelta(seconds=min(settings.PROVIDER_OUTBOX_RETRY_BASE_SECONDS * 2 ** max(attempt - 1, 0), settings.PROVIDER_OUTBOX_RETRY_MAX_SECONDS))


async def _deliver(tenant: Tenant, event: ProviderOutboxEvent) -> tuple[Optional[str], int]:
    if not tenant.paid_invoice_webhook_enabled or not tenant.paid_invoice_webhook_url or not tenant.paid_invoice_webhook_secret_encrypted:
        raise ProviderDeliveryError("Conversion webhook is disabled or incomplete", retryable=False)
    body = json.dumps(event.payload, separators=(",", ":"), sort_keys=True).encode()
    secret = decrypt_paid_invoice_webhook_secret(tenant.paid_invoice_webhook_secret_encrypted)
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.PAID_INVOICE_WEBHOOK_TIMEOUT_SECONDS)) as client:
            response = await client.post(tenant.paid_invoice_webhook_url, content=body, headers={"Content-Type": "application/json", "User-Agent": "dieselbridge-conversion-webhook/1.0", "Idempotency-Key": event.idempotency_key, "X-DieselBridge-Event": event.event_type, "X-DieselBridge-Signature": f"sha256={signature}"})
        event.last_response_code = response.status_code
        if response.status_code >= 400:
            raise ProviderDeliveryError(f"Webhook returned HTTP {response.status_code}", retryable=response.status_code == 429 or response.status_code >= 500)
        return response.headers.get("X-Request-Id"), response.status_code
    except ProviderDeliveryError:
        raise
    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        raise ProviderDeliveryError("Webhook network request failed", retryable=True) from exc


async def _disable_and_notify(db: AsyncSession, tenant: Tenant, event: ProviderOutboxEvent) -> None:
    tenant.paid_invoice_webhook_enabled = False
    admins = (await db.execute(select(User).where(User.tenant_id == tenant.id, User.role.in_((UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)), User.is_active.is_(True)))).scalars().all()
    recipients = {user.email for user in admins if user.email}
    if tenant.email:
        recipients.add(tenant.email)
    for recipient in recipients:
        await enqueue_email_notification(db, tenant_id=tenant.id, aggregate_type="conversion_webhook", aggregate_id=event.id, idempotency_key=f"conversion-webhook-disabled:{event.id}:{hashlib.sha256(recipient.encode()).hexdigest()[:12]}", recipient=recipient, subject="DieselBridge conversion webhook disabled", body="<p>Your conversion webhook was disabled after repeated delivery failures. Review the delivery history, correct the endpoint, then enable and replay the event.</p>", template_name="conversion_webhook_disabled", sender_name="DieselBridge")


async def process_due_paid_invoice_webhooks(*, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal, batch_size: Optional[int] = None) -> dict[str, int]:
    async with session_factory() as db:
        claims = await _claim(db, batch_size or settings.PROVIDER_OUTBOX_BATCH_SIZE)
    result = {"claimed": len(claims), "succeeded": 0, "retried": 0, "dead": 0}
    for event_id, token in claims:
        async with session_factory() as db:
            event = await db.get(ProviderOutboxEvent, event_id)
            tenant = await db.get(Tenant, event.tenant_id) if event else None
            if not event or not tenant or event.lock_token != token:
                continue
            try:
                provider_id, code = await _deliver(tenant, event)
                event.status, event.completed_at, event.provider_message_id, event.last_response_code = ProviderOutboxStatus.SUCCEEDED.value, _now(), provider_id, code
                event.last_error = None
                result["succeeded"] += 1
            except Exception as exc:
                retryable = not isinstance(exc, ProviderDeliveryError) or exc.retryable
                event.last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                if retryable and event.attempt_count < settings.PROVIDER_OUTBOX_MAX_ATTEMPTS:
                    event.status, event.available_at = ProviderOutboxStatus.PENDING.value, _now() + _retry_delay(event.attempt_count)
                    result["retried"] += 1
                else:
                    event.status, event.completed_at = ProviderOutboxStatus.DEAD.value, _now()
                    await _disable_and_notify(db, tenant, event)
                    result["dead"] += 1
            event.lock_token = event.locked_until = None
            await db.commit()
    return result
