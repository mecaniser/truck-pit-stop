"""Tenant-scoped, signed ELIS intake selection; never accepts a browser URL."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import anyio
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.core.paid_invoice_webhook_crypto import decrypt_paid_invoice_webhook_secret, PaidInvoiceWebhookCryptoError
from app.core.webhook_destination import resolve_webhook_destination, WebhookDestinationError
from app.db.models.tenant import Tenant
from app.services.paid_invoice_webhook_service import conversion_signature


class OriginatingCallOptionsRequest(BaseModel):
    customer_id: UUID


class OriginatingCallOption(BaseModel):
    reference_token: str = Field(min_length=1, max_length=4096)
    call_id: UUID
    opportunity_id: UUID
    started_at: datetime
    contact_label: str = Field(max_length=160)
    service_summary: str = Field(max_length=1000)
    expires_at: datetime


class OriginatingCallOptions(BaseModel):
    options: list[OriginatingCallOption] = Field(max_length=100)


class IntakeReservation(BaseModel):
    repair_order_uuid: UUID
    elis_opportunity_id: UUID
    callrail_call_id: str = Field(min_length=1, max_length=255)


def intake_url(tenant: Tenant, operation: str) -> str:
    if (not tenant.paid_invoice_webhook_enabled or tenant.paid_invoice_webhook_delivery_paused
            or not tenant.paid_invoice_webhook_url or not tenant.paid_invoice_webhook_secret_encrypted):
        raise HTTPException(409, "Call intake connection is not configured or is paused")
    parsed = urlsplit(tenant.paid_invoice_webhook_url)
    if (operation not in {"candidates", "reserve"} or parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.path.rstrip("/") != "/events/shop-outcome"):
        raise HTTPException(409, "Call intake connection is not configured for ELIS")
    return urlunsplit((parsed.scheme, parsed.netloc, f"/events/repair-intake/{operation}", "", ""))


async def _request(tenant: Tenant, operation: str, **fields) -> dict:
    url = intake_url(tenant, operation)
    request_id = str(uuid4())
    event = f"repair_intake.{operation}"
    body = json.dumps({"schema_version": 1, "shop_id": str(tenant.id), "request_id": request_id,
                       "event_type": event, **fields}, separators=(",", ":"), sort_keys=True).encode()
    try:
        # A total deadline also bounds a trickling response and DNS resolution.
        with anyio.fail_after(12):
            secret = decrypt_paid_invoice_webhook_secret(tenant.paid_invoice_webhook_secret_encrypted)
            destination = await resolve_webhook_destination(url, dns_timeout_seconds=3)
            timestamp = str(int(datetime.now(timezone.utc).timestamp()))
            async with httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False) as client:
                pinned = httpx.URL(destination.original_url).copy_with(host=destination.addresses[0])
                async with client.stream("POST", pinned, content=body, headers={
                    "Host": destination.host_header, "Content-Type": "application/json",
                    "Idempotency-Key": request_id, "X-DieselBridge-Event": event,
                    "X-DieselBridge-Timestamp": timestamp,
                    "X-DieselBridge-Signature": f"sha256={conversion_signature(secret, timestamp, body)}",
                }, extensions={"sni_hostname": destination.tls_hostname}) as response:
                    if response.status_code == 409:
                        raise HTTPException(409, "This call selection is no longer available; refresh the call list")
                    if response.status_code != 200:
                        raise HTTPException(502, "Call intake service is unavailable; please retry")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > 131072:
                            raise ValueError("Oversized response")
                    return json.loads(chunks)
    except (httpx.HTTPError, TimeoutError, WebhookDestinationError, PaidInvoiceWebhookCryptoError,
            ValueError, TypeError) as exc:
        raise HTTPException(502, "Call intake service is unavailable; please retry") from exc


async def originating_call_options(tenant: Tenant, customer_phone: str | None) -> OriginatingCallOptions:
    try:
        return OriginatingCallOptions.model_validate(await _request(tenant, "candidates", customer_phone=customer_phone or None))
    except ValidationError as exc:
        raise HTTPException(502, "Call intake returned an invalid response") from exc


async def reserve_originating_call(tenant: Tenant, actor_id: UUID, reference_token: str) -> IntakeReservation:
    try:
        return IntakeReservation.model_validate(await _request(tenant, "reserve", actor_id=str(actor_id), reference_token=reference_token))
    except ValidationError as exc:
        raise HTTPException(502, "Call intake returned an invalid response") from exc
