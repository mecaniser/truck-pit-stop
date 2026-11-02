"""Supported conversion-event contract and durable signed webhook delivery."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

import anyio
import httpx
from sqlalchemy import and_, case, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.paid_invoice_webhook_crypto import PaidInvoiceWebhookCryptoError, decrypt_paid_invoice_webhook_secret
from app.core.webhook_destination import (
    WebhookDestinationError,
    WebhookDestinationResolutionTimeout,
    resolve_webhook_destination,
)
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoiceSettlement, InvoicePaymentLedgerEvent
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.session import AsyncSessionLocal
from app.services.conversion_pii_retention_service import (
    CONVERSION_EVENT_TYPES,
    SHOP_HISTORY_EVENT,
    ETS_OUTCOME_EVENTS,
    conversion_event_must_expire,
    expire_conversion_event,
)
from app.services.provider_outbox_service import ProviderDeliveryError, enqueue_email_notification
from app.services.shop_history_source import history_allowed_tenants


PAID_INVOICE_WEBHOOK_EVENT = "repair_order.paid"  # compatibility export


class ConversionDeliveryPaused(Exception):
    """Delivery is suspended; captured work and retry budget stay intact."""


class ConversionEventPrivacyExpired(Exception):
    """Raised when privacy expiry forbids starting or finishing delivery."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(value) -> float:
    return float(Decimal(value or 0).quantize(Decimal("0.01")))


def conversion_signature(secret: str, timestamp: str, body: bytes) -> str:
    signed = timestamp.encode("ascii") + b"." + body
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def verify_conversion_signature(*, secret: str, timestamp: str, body: bytes, signature: str, now: Optional[datetime] = None, tolerance_seconds: Optional[int] = None) -> bool:
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int((now or _now()).timestamp())
    tolerance = tolerance_seconds or settings.PAID_INVOICE_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS
    if abs(current - sent_at) > tolerance:
        return False
    supplied = signature.removeprefix("sha256=")
    expected = conversion_signature(secret, timestamp, body)
    return hmac.compare_digest(supplied, expected)


def service_lines(invoice: Invoice) -> list[dict]:
    snapshot = invoice.line_items_snapshot or {}
    lines = []
    for item in snapshot.get("labor", []):
        lines.append({"name": item.get("description") or "Labor", "quantity": float(item.get("hours") or 1), "amount": _money(item.get("total_cost"))})
    for item in snapshot.get("parts", []):
        lines.append({"name": item.get("name") or "Part", "quantity": float(item.get("quantity") or 1), "amount": _money(item.get("total_price"))})
    return lines


def attribution(order: RepairOrder, *, schema_version: int = 1) -> dict:
    result = {
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
    if schema_version == 2:
        result["elis_opportunity_id"] = str(order.elis_opportunity_id) if order.elis_opportunity_id else None
    return result


def conversion_payload(*, event_id: UUID, event_type: str, tenant: Tenant, invoice: Invoice, order: RepairOrder, customer: Optional[Customer], occurred_at: Optional[datetime] = None, total_amount=None) -> dict:
    timestamp = occurred_at or _now()
    version = tenant.paid_invoice_webhook_payload_version or 1
    result = {
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
        "attribution": attribution(order, schema_version=version),
    }
    if version == 2:
        result.update(
            schema_version=2, source_system="dieselbridge", source_revision=str(event_id),
            repair_order_uuid=str(order.id), repair_order_number=order.order_number,
            value_basis="invoice_settled" if event_type == PAID_INVOICE_WEBHOOK_EVENT else "measurement_adjustment",
            amount_semantics="snapshot" if event_type == PAID_INVOICE_WEBHOOK_EVENT else "delta",
        )
    return result


def native_invoice_outcome_predicate():
    """Native source creation proof, not proof of cash or processor settlement."""
    return and_(
        Invoice.source.is_(None),
        RepairOrder.source.is_(None),
        exists().where(
            InvoiceSettlement.invoice_id == Invoice.id,
            InvoiceSettlement.tenant_id == Invoice.tenant_id,
            InvoiceSettlement.customer_id == RepairOrder.customer_id,
            InvoiceSettlement.legacy_reconciliation_status == "native",
        ),
    )


async def native_settled_amount(db: AsyncSession, *, tenant: Tenant, invoice: Invoice,
                                order: RepairOrder) -> Decimal | None:
    """Fail closed on status-only paid rows; never synthesize settlement time.

    This checks the native ledger in the same transaction as capture. Imported
    history and existing outbox events are not converted or re-enqueued here.
    """
    if (invoice.paid_at is None or invoice.paid_at.tzinfo is None
            or invoice.paid_at.utcoffset() is None or invoice.paid_at > _now()
            or invoice.deleted_at is not None):
        return None
    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == tenant.id,
        InvoiceSettlement.invoice_id == invoice.id,
        InvoiceSettlement.customer_id == order.customer_id,
        InvoiceSettlement.legacy_reconciliation_status == "native",
        InvoiceSettlement.deleted_at.is_(None),
    ))
    if (settlement is None or settlement.currency != "USD"
            or settlement.customer_id != order.customer_id or settlement.deleted_at is not None):
        return None
    from app.services.invoice_settlement_service import invoice_money_snapshot
    principal = Decimal(settlement.principal_total or 0)
    confirmed = Decimal(settlement.confirmed_principal or 0)
    if (principal <= 0 or principal != invoice_money_snapshot(invoice)[0]
            or confirmed != principal or Decimal(settlement.refund_pending or 0) != 0):
        return None
    await db.flush()  # Session disables autoflush; include this transaction's ledger append.
    events = list((await db.scalars(select(InvoicePaymentLedgerEvent).where(
        InvoicePaymentLedgerEvent.tenant_id == tenant.id,
        InvoicePaymentLedgerEvent.invoice_id == invoice.id,
        InvoicePaymentLedgerEvent.settlement_id == settlement.id,
        InvoicePaymentLedgerEvent.customer_id == order.customer_id,
    ).order_by(InvoicePaymentLedgerEvent.sequence))).all())
    if (not events or [event.sequence for event in events]
            != list(range(1, int(settlement.last_event_sequence or 0) + 1))):
        return None
    if sum((Decimal(event.principal_delta or 0) for event in events), Decimal(0)) != confirmed:
        return None
    fees = Decimal(0)
    confirmed_event = False
    for event in events:
        # Corrections require their own reconciliation; do not infer net fees.
        if (Decimal(event.principal_delta or 0) < 0
                or Decimal(event.refund_pending_delta or 0) != 0
                or any(word in event.event_type for word in ("refund", "dispute", "reversal"))):
            return None
        if event.event_type in {"payment_confirmed", "cash_payment_confirmed", "credit_applied"} and Decimal(event.principal_delta or 0) > 0:
            confirmed_event = True
            if event.event_type == "payment_confirmed":
                evidence = event.evidence_snapshot or {}
                try:
                    fee = Decimal(evidence["earned_card_fee"])
                    fee_tax = Decimal(evidence["earned_card_fee_tax"])
                except (KeyError, TypeError, ValueError, ArithmeticError):
                    return None
                if not fee.is_finite() or not fee_tax.is_finite() or fee < 0 or fee_tax < 0:
                    return None
                fees += fee + fee_tax
    return (principal + fees).quantize(Decimal("0.01")) if confirmed_event else None


async def enqueue_conversion_event(db: AsyncSession, *, tenant: Optional[Tenant], invoice: Invoice, order: RepairOrder, customer: Optional[Customer], event_type: str, idempotency_key: str, total_amount=None) -> Optional[ProviderOutboxEvent]:
    if getattr(invoice, "accounting_policy", None) == "source_collection_hold":
        return None
    if event_type not in CONVERSION_EVENT_TYPES:
        raise ValueError("Unsupported conversion event type")
    if not tenant or not tenant.paid_invoice_webhook_enabled or not tenant.paid_invoice_webhook_url or not tenant.paid_invoice_webhook_secret_encrypted:
        return None
    if invoice.tenant_id != tenant.id or order.tenant_id != tenant.id or (customer and customer.tenant_id != tenant.id):
        raise ValueError("Conversion event resources must belong to the same shop")
    if customer and customer.id != order.customer_id:
        raise ValueError("Conversion customer does not belong to the repair order")
    if invoice.repair_order_id != order.id:
        raise ValueError("Conversion event invoice does not belong to the repair order")
    if not order.id or not order.order_number or order.deleted_at is not None:
        return None
    if event_type == "repair_order.paid" and (invoice.status != InvoiceStatus.PAID or order.status != RepairOrderStatus.PAID or Decimal(invoice.total_amount or 0) <= 0):
        return None
    if tenant.paid_invoice_webhook_payload_version == 2:
        if invoice.source is not None or order.source is not None:
            return None
        native_id = await db.scalar(select(InvoiceSettlement.id).where(
            InvoiceSettlement.tenant_id == tenant.id,
            InvoiceSettlement.invoice_id == invoice.id,
            InvoiceSettlement.customer_id == order.customer_id,
            InvoiceSettlement.legacy_reconciliation_status == "native",
        ))
        if native_id is None:
            return None
    existing_query = select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.tenant_id == tenant.id,
        ProviderOutboxEvent.event_type == event_type,
        ProviderOutboxEvent.idempotency_key == idempotency_key,
    )
    existing = (await db.execute(existing_query)).scalar_one_or_none()
    if existing:
        if existing.aggregate_id != invoice.id:
            raise ValueError("Conversion event identity belongs to another invoice")
        return existing
    if tenant.paid_invoice_webhook_payload_version == 2 and event_type == PAID_INVOICE_WEBHOOK_EVENT:
        total_amount = await native_settled_amount(db, tenant=tenant, invoice=invoice, order=order)
        if total_amount is None:
            return None
    event_id = uuid4()
    event = ProviderOutboxEvent(
        id=event_id, tenant_id=tenant.id, event_type=event_type, aggregate_type="invoice", aggregate_id=invoice.id,
        payload=conversion_payload(event_id=event_id, event_type=event_type, tenant=tenant, invoice=invoice, order=order, customer=customer, total_amount=total_amount),
        idempotency_key=idempotency_key, status=ProviderOutboxStatus.PENDING.value, available_at=_now(),
    )
    try:
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        existing = (await db.execute(existing_query)).scalar_one_or_none()
        if existing is None or existing.aggregate_id != invoice.id:
            raise
        return existing
    return event


async def enqueue_paid_invoice_webhook(db: AsyncSession, *, tenant: Optional[Tenant], invoice: Invoice, order: RepairOrder, customer: Optional[Customer]) -> Optional[ProviderOutboxEvent]:
    return await enqueue_conversion_event(db, tenant=tenant, invoice=invoice, order=order, customer=customer, event_type="repair_order.paid", idempotency_key=f"repair-order-paid:{invoice.id}")


async def _claim(db: AsyncSession, limit: int, *, history_only: bool = False) -> tuple[list[tuple[UUID, str]], int]:
    now = _now()
    history_tenants = history_allowed_tenants()
    event_filter = ProviderOutboxEvent.event_type.in_(CONVERSION_EVENT_TYPES)
    if settings.SHOP_HISTORY_CAPTURE_ENABLED and history_tenants:
        event_filter = or_(event_filter, and_(ProviderOutboxEvent.event_type == SHOP_HISTORY_EVENT, ProviderOutboxEvent.tenant_id.in_(history_tenants)))
    from app.services.ets_completed_outcome_source import configured_shops
    ets_tenants = list(configured_shops())
    if ets_tenants:
        event_filter = or_(event_filter, and_(ProviderOutboxEvent.event_type.in_(ETS_OUTCOME_EVENTS), ProviderOutboxEvent.tenant_id.in_(ets_tenants)))
    if history_tenants:
        event_filter = or_(event_filter, and_(ProviderOutboxEvent.event_type.in_(ETS_OUTCOME_EVENTS),
            ProviderOutboxEvent.tenant_id.in_(history_tenants),
            ProviderOutboxEvent.payload["snapshot"]["source"].as_string() == "dieselbridge",
            ProviderOutboxEvent.payload["schema_version"].as_integer() == 2))
    if history_only:
        # A dedicated slot cannot take completion work or bypass the capture allowlist.
        event_filter = and_(event_filter, ProviderOutboxEvent.event_type == SHOP_HISTORY_EVENT)
    due = or_(
        and_(ProviderOutboxEvent.status == ProviderOutboxStatus.PENDING.value, ProviderOutboxEvent.available_at <= now),
        and_(ProviderOutboxEvent.status == ProviderOutboxStatus.PROCESSING.value, ProviderOutboxEvent.locked_until <= now),
    )
    rows = (await db.execute(select(ProviderOutboxEvent).join(Tenant, Tenant.id == ProviderOutboxEvent.tenant_id).where(Tenant.paid_invoice_webhook_enabled.is_(True), Tenant.paid_invoice_webhook_delivery_paused.is_(False), event_filter, due).order_by(case((ProviderOutboxEvent.event_type == SHOP_HISTORY_EVENT, 1), else_=0), ProviderOutboxEvent.available_at).limit(limit).with_for_update(skip_locked=True, of=ProviderOutboxEvent))).scalars()
    claims = []
    expired = 0
    for event in rows:
        if conversion_event_must_expire(
            event,
            current=now,
            safety_margin_seconds=settings.PAID_INVOICE_WEBHOOK_TOTAL_TIMEOUT_SECONDS,
        ):
            expire_conversion_event(event, expired_at=now)
            expired += 1
            continue
        token = uuid4().hex
        event.status, event.lock_token, event.locked_at = ProviderOutboxStatus.PROCESSING.value, token, now
        event.locked_until, event.last_attempt_at = now + timedelta(seconds=settings.PROVIDER_OUTBOX_LEASE_SECONDS), now
        event.attempt_count += 1
        claims.append((event.id, token))
    await db.commit()
    return claims, expired


def _retry_delay(attempt: int) -> timedelta:
    return timedelta(seconds=min(settings.PROVIDER_OUTBOX_RETRY_BASE_SECONDS * 2 ** max(attempt - 1, 0), settings.PROVIDER_OUTBOX_RETRY_MAX_SECONDS))


async def _deliver(tenant: Tenant, event: ProviderOutboxEvent) -> tuple[Optional[str], int]:
    if conversion_event_must_expire(
        event,
        current=_now(),
        safety_margin_seconds=settings.PAID_INVOICE_WEBHOOK_TOTAL_TIMEOUT_SECONDS,
    ):
        raise ConversionEventPrivacyExpired(
            "Conversion payload is expired or redacted"
        )
    try:
        with anyio.fail_after(settings.PAID_INVOICE_WEBHOOK_TOTAL_TIMEOUT_SECONDS):
            return await _deliver_within_budget(tenant, event)
    except TimeoutError as exc:
        raise ProviderDeliveryError(
            "Webhook delivery exceeded its total time budget", retryable=True
        ) from exc


async def _deliver_within_budget(tenant: Tenant, event: ProviderOutboxEvent) -> tuple[Optional[str], int]:
    if event.event_type in ETS_OUTCOME_EVENTS:
        from app.services.ets_completed_outcome_source import configured_shops
        snapshot = event.payload.get("snapshot") or {}
        if event.payload.get("schema_version") == 2 and snapshot.get("source") == "dieselbridge":
            if tenant.id not in history_allowed_tenants():
                raise ConversionDeliveryPaused()
        else:
            expected = configured_shops().get(tenant.id)
            if not expected or snapshot.get("ets_shop_id") != expected:
                raise ConversionDeliveryPaused()
    if event.event_type == SHOP_HISTORY_EVENT and (
        tenant.id not in history_allowed_tenants()
    ):
        raise ConversionDeliveryPaused()
    if tenant.paid_invoice_webhook_delivery_paused or not tenant.paid_invoice_webhook_enabled:
        raise ConversionDeliveryPaused()
    if not tenant.paid_invoice_webhook_url or not tenant.paid_invoice_webhook_secret_encrypted:
        raise ProviderDeliveryError("Conversion webhook is disabled or incomplete", retryable=False)
    body = json.dumps(event.payload, separators=(",", ":"), sort_keys=True).encode()
    # Validate keyring/decryption before any network work. Operator crypto
    # failures are classified separately by the worker and never charged to a
    # receiver's retry budget.
    secret = decrypt_paid_invoice_webhook_secret(tenant.paid_invoice_webhook_secret_encrypted)
    try:
        destination = await resolve_webhook_destination(
            tenant.paid_invoice_webhook_url,
            dns_timeout_seconds=settings.PAID_INVOICE_WEBHOOK_DNS_TIMEOUT_SECONDS,
        )
    except WebhookDestinationResolutionTimeout as exc:
        raise ProviderDeliveryError(str(exc), retryable=True) from exc
    except WebhookDestinationError as exc:
        raise ProviderDeliveryError(str(exc), retryable=False) from exc
    timestamp = str(int(_now().timestamp()))
    signature = conversion_signature(secret, timestamp, body)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.PAID_INVOICE_WEBHOOK_TIMEOUT_SECONDS),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = None
            last_connect_error = None
            for address in destination.addresses:
                pinned_url = httpx.URL(destination.original_url).copy_with(host=address)
                try:
                    response = await client.request(
                        "POST",
                        pinned_url,
                        content=body,
                        headers={
                            "Host": destination.host_header,
                            "Content-Type": "application/json",
                            "User-Agent": "dieselbridge-conversion-webhook/1.0",
                            "Idempotency-Key": event.idempotency_key,
                            "X-DieselBridge-Event": event.event_type,
                            "X-DieselBridge-Timestamp": timestamp,
                            "X-DieselBridge-Signature": f"sha256={signature}",
                        },
                        extensions={"sni_hostname": destination.tls_hostname},
                    )
                    break
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    last_connect_error = exc
            if response is None:
                raise ProviderDeliveryError("Webhook connection failed for all vetted addresses", retryable=True) from last_connect_error
        if 300 <= response.status_code < 400:
            raise ProviderDeliveryError(
                "Webhook redirects are not accepted",
                retryable=False,
                response_code=response.status_code,
            )
        if response.status_code >= 400:
            raise ProviderDeliveryError(
                f"Webhook returned HTTP {response.status_code}",
                retryable=response.status_code == 429 or response.status_code >= 500,
                response_code=response.status_code,
            )
        return response.headers.get("X-Request-Id"), response.status_code
    except ProviderDeliveryError:
        raise
    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        raise ProviderDeliveryError("Webhook network request failed", retryable=True) from exc


async def _pause_and_notify(db: AsyncSession, tenant: Tenant, event: ProviderOutboxEvent) -> None:
    tenant.paid_invoice_webhook_delivery_paused = True
    admins = (await db.execute(select(User).where(User.tenant_id == tenant.id, User.role.in_((UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)), User.is_active.is_(True)))).scalars().all()
    recipients = {user.email for user in admins if user.email}
    if tenant.email:
        recipients.add(tenant.email)
    for recipient in recipients:
        await enqueue_email_notification(db, tenant_id=tenant.id, aggregate_type="conversion_webhook", aggregate_id=event.id, idempotency_key=f"conversion-webhook-paused:{event.id}:{hashlib.sha256(recipient.encode()).hexdigest()[:12]}", recipient=recipient, subject="DieselBridge conversion webhook paused", body="<p>Your conversion webhook delivery was paused after repeated failures. New events are still captured under the retention policy. Review delivery history, correct the endpoint, resume delivery, then replay the failed event.</p>", template_name="conversion_webhook_paused", sender_name="DieselBridge")


async def process_due_paid_invoice_webhooks(*, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal, batch_size: Optional[int] = None, history_only: bool = False) -> dict[str, int]:
    async with session_factory() as db:
        if history_only:
            claims, expired_at_claim = await _claim(db, 1, history_only=True)
        else:
            claims, expired_at_claim = await _claim(
                db, batch_size or settings.PROVIDER_OUTBOX_BATCH_SIZE
            )
    result = {"claimed": len(claims), "succeeded": 0, "retried": 0, "dead": 0, "configuration_blocked": 0, "paused": 0, "expired": expired_at_claim}
    for event_id, token in claims:
        # Preflight under the row lock, then release the transaction before
        # external I/O. Retention or erasure may still win while the request is
        # in flight; the token-conditioned completion below will respect it.
        async with session_factory() as db:
            event = (await db.execute(
                select(ProviderOutboxEvent)
                .where(ProviderOutboxEvent.id == event_id)
                .with_for_update()
            )).scalar_one_or_none()
            tenant = await db.get(Tenant, event.tenant_id) if event else None
            if (
                not event
                or not tenant
                or event.lock_token != token
                or event.status != ProviderOutboxStatus.PROCESSING.value
            ):
                continue
            if conversion_event_must_expire(
                event,
                current=_now(),
                safety_margin_seconds=settings.PAID_INVOICE_WEBHOOK_TOTAL_TIMEOUT_SECONDS,
            ):
                expire_conversion_event(event)
                await db.commit()
                result["expired"] += 1
                continue
            if tenant.paid_invoice_webhook_delivery_paused or not tenant.paid_invoice_webhook_enabled:
                event.status = ProviderOutboxStatus.PENDING.value
                event.attempt_count = max(0, event.attempt_count - 1)
                if event.attempt_count == 0:
                    event.last_attempt_at = None
                event.lock_token = event.locked_at = event.locked_until = None
                await db.commit()
                result["paused"] += 1
                continue
            db.expunge(event)
            db.expunge(tenant)
            await db.rollback()

        outcome = None
        failure = None
        try:
            outcome = await _deliver(tenant, event)
        except Exception as exc:
            failure = exc

        async with session_factory() as db:
            event = (await db.execute(
                select(ProviderOutboxEvent)
                .where(
                    ProviderOutboxEvent.id == event_id,
                    ProviderOutboxEvent.status == ProviderOutboxStatus.PROCESSING.value,
                    ProviderOutboxEvent.lock_token == token,
                )
                .with_for_update()
            )).scalar_one_or_none()
            if not event:
                # Retention or erasure already terminalized this attempt.
                continue
            tenant = await db.get(Tenant, event.tenant_id)
            if conversion_event_must_expire(
                event,
                current=_now(),
                safety_margin_seconds=settings.PAID_INVOICE_WEBHOOK_TOTAL_TIMEOUT_SECONDS,
            ) or isinstance(failure, ConversionEventPrivacyExpired):
                expire_conversion_event(event)
                await db.commit()
                result["expired"] += 1
                continue
            try:
                if failure:
                    raise failure
                provider_id, code = outcome
                event.status, event.completed_at, event.provider_message_id, event.last_response_code = ProviderOutboxStatus.SUCCEEDED.value, _now(), provider_id, code
                event.last_error = None
                result["succeeded"] += 1
            except ConversionDeliveryPaused:
                event.attempt_count = max(0, event.attempt_count - 1)
                event.status = ProviderOutboxStatus.PENDING.value
                result["paused"] += 1
            except PaidInvoiceWebhookCryptoError:
                # Operator/keyring failures are not receiver failures. Leave the
                # event pending without consuming its delivery retry budget or
                # disabling the tenant integration.
                event.attempt_count = max(0, event.attempt_count - 1)
                event.status = ProviderOutboxStatus.PENDING.value
                event.available_at = _now() + timedelta(hours=1)
                event.last_error = "Webhook secret configuration is unavailable"
                result["configuration_blocked"] += 1
            except Exception as exc:
                retryable = not isinstance(exc, ProviderDeliveryError) or exc.retryable
                if isinstance(exc, ProviderDeliveryError) and exc.response_code is not None:
                    event.last_response_code = exc.response_code
                event.last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                if retryable and event.attempt_count < settings.PROVIDER_OUTBOX_MAX_ATTEMPTS:
                    event.status, event.available_at = ProviderOutboxStatus.PENDING.value, _now() + _retry_delay(event.attempt_count)
                    result["retried"] += 1
                else:
                    event.status, event.completed_at = ProviderOutboxStatus.DEAD.value, _now()
                    if event.event_type != SHOP_HISTORY_EVENT:
                        await _pause_and_notify(db, tenant, event)
                    result["dead"] += 1
            event.lock_token = event.locked_until = None
            await db.commit()
    return result
