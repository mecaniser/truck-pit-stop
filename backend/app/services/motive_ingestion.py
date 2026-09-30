"""Bounded REST measurement ingestion and durable signature-verified wakeups."""

import hashlib
import hmac
import json
import math
from datetime import timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.core import motive_crypto
from app.db.models.customer import Customer
from app.db.models.motive_oauth import (
    MotiveConnection,
    MotiveFault,
    MotiveHistorySample,
    MotiveWebhookReceipt,
)
from app.db.models.tenant import Tenant
from app.services.motive_client import MotiveProviderError, identifier, safe_text

ACTIONS = frozenset(
    {
        "vehicle_location_received",
        "vehicle_location_updated",
        "vehicle_upserted",
        "fault_code_opened",
        "fault_code_closed",
    }
)
METRICS = (
    "virtual_odometer_miles",
    "true_odometer_miles",
    "virtual_engine_hours",
    "true_engine_hours",
)


def timestamp(value):
    from datetime import datetime

    if not isinstance(value, str):
        raise TypeError("Invalid observation time")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Invalid observation time")
    return result.astimezone(timezone.utc)


def optional_number(value, maximum):
    if value is None:
        return None
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not 0 <= value <= maximum
    ):
        raise ValueError("Invalid measurement")
    return float(value)


def content_hash(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


async def clear_remote_data(db, remote):
    from app.services import motive_oauth as oauth

    oauth.clear_point(remote)
    for field in (
        *METRICS,
        "metrics_observed_at",
        "metrics_received_at",
        "history_cursor_at",
        "fault_cursor_at",
        "faults_synced_at",
    ):
        setattr(remote, field, None)
    await db.execute(
        delete(MotiveHistorySample).where(
            MotiveHistorySample.remote_vehicle_id == remote.id
        )
    )
    await db.execute(
        delete(MotiveFault).where(MotiveFault.remote_vehicle_id == remote.id)
    )


async def ingest_history(db, row, remote, records, start, end, received):
    from app.services import motive_oauth as oauth

    parsed = []
    seen = set()
    try:
        for raw in records:
            event_id = safe_text(raw["id"], 120)
            if not event_id or event_id in seen:
                raise ValueError()
            seen.add(event_id)
            observed = timestamp(raw["located_at"])
            if not start <= observed <= end + timedelta(minutes=5):
                raise ValueError()
            if observed < received - timedelta(
                days=30
            ) or observed > received + timedelta(minutes=5):
                raise ValueError()
            if (raw.get("lat") is None) != (raw.get("lon") is None):
                raise ValueError()
            device = raw.get("eld_device")
            if (
                device
                and remote.gateway_id
                and identifier(device["id"]) != remote.gateway_id
            ):
                raise ValueError()
            point = (
                oauth.parse_point(
                    {
                        "located_at": observed.isoformat(),
                        "lat": raw.get("lat"),
                        "lon": raw.get("lon"),
                        "bearing": raw.get("bearing"),
                        "kph": None,
                    },
                    received,
                )
                if raw.get("lat") is not None and raw.get("lon") is not None
                else None
            )
            values = {
                "observed_at": observed,
                "lat": point["lat"] if point else None,
                "lng": point["lng"] if point else None,
                "bearing_degrees": point["bearing"] if point else None,
                "speed_mph": optional_number(raw.get("speed"), 250),
                "virtual_odometer_miles": optional_number(
                    raw.get("odometer"), 100_000_000
                ),
                "true_odometer_miles": optional_number(
                    raw.get("true_odometer"), 100_000_000
                ),
                "virtual_engine_hours": optional_number(
                    raw.get("engine_hours"), 10_000_000
                ),
                "true_engine_hours": optional_number(
                    raw.get("true_engine_hours"), 10_000_000
                ),
            }
            parsed.append((event_id, values, content_hash(values)))
    except (ValueError, TypeError, KeyError, OverflowError, MotiveProviderError):
        raise MotiveProviderError("invalid_history") from None
    accepted = 0
    for event_id, values, fingerprint in parsed:
        observed = values["observed_at"]
        if (
            not remote.mapped_at
            or observed < oauth.utc(remote.mapped_at)
            or remote.vehicle_id
            not in {v.id for v in await oauth.active_trucks(db, row, observed)}
        ):
            continue
        existing = (
            await db.execute(
                select(MotiveHistorySample).where(
                    MotiveHistorySample.remote_vehicle_id == remote.id,
                    MotiveHistorySample.provider_location_id == event_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            if existing.content_sha256 != fingerprint:
                raise MotiveProviderError("history_conflict")
            continue
        db.add(
            MotiveHistorySample(
                tenant_id=row.tenant_id,
                connection_id=row.id,
                remote_vehicle_id=remote.id,
                provider_location_id=event_id,
                mapping_epoch=remote.mapped_at,
                received_at=received,
                content_sha256=fingerprint,
                **values,
            )
        )
        accepted += 1
        if remote.metrics_observed_at is None or observed > oauth.utc(
            remote.metrics_observed_at
        ):
            for field in METRICS:
                setattr(remote, field, values[field])
            remote.metrics_observed_at, remote.metrics_received_at = observed, received
        if values["lat"] is not None and (
            remote.located_at is None or observed > oauth.utc(remote.located_at)
        ):
            remote.located_at, remote.received_at = observed, received
            remote.lat, remote.lng, remote.speed_mph, remote.bearing = (
                values["lat"],
                values["lng"],
                values["speed_mph"],
                values["bearing_degrees"],
            )
    await db.flush()
    remote.history_cursor_at = end
    return accepted


async def ingest_faults(db, row, remote, records, end, received):
    from app.services import motive_oauth as oauth

    parsed = []
    try:
        for raw in records:
            if identifier(raw["vehicle"]["id"]) != remote.provider_vehicle_id or raw[
                "status"
            ] not in {"open", "closed"}:
                raise ValueError()
            first, last = (
                timestamp(raw["first_observed_at"]),
                timestamp(raw["last_observed_at"]),
            )
            if last < first or last > received + timedelta(minutes=5):
                raise ValueError()
            data = {
                "code": safe_text(raw.get("code"), 120),
                "code_label": safe_text(raw.get("code_label"), 120),
                "description": safe_text(raw.get("code_description"), 1000),
                "fmi": safe_text(str(raw["fmi"]), 40)
                if raw.get("fmi") is not None
                else None,
                "status": raw["status"],
                "first_observed_at": first,
                "last_observed_at": last,
            }
            parsed.append((identifier(raw["id"]), data, content_hash(data)))
    except (ValueError, TypeError, KeyError, OverflowError):
        raise MotiveProviderError("invalid_fault") from None
    for fault_id, values, fingerprint in parsed:
        if not remote.mapped_at or values["last_observed_at"] < oauth.utc(
            remote.mapped_at
        ):
            continue
        if remote.vehicle_id not in {
            v.id for v in await oauth.active_trucks(db, row, values["last_observed_at"])
        }:
            continue
        existing = (
            await db.execute(
                select(MotiveFault).where(
                    MotiveFault.connection_id == row.id,
                    MotiveFault.provider_fault_id == fault_id,
                )
            )
        ).scalar_one_or_none()
        if existing and existing.remote_vehicle_id != remote.id:
            raise MotiveProviderError("fault_identity_conflict")
        if existing and values["last_observed_at"] < oauth.utc(
            existing.last_observed_at
        ):
            continue
        # Closing at the same observation time supersedes open. A stale open cannot reopen a closed record.
        if (
            existing
            and values["last_observed_at"] == oauth.utc(existing.last_observed_at)
            and existing.status == "closed"
            and values["status"] == "open"
        ):
            continue
        if existing is None:
            existing = MotiveFault(
                tenant_id=row.tenant_id,
                connection_id=row.id,
                remote_vehicle_id=remote.id,
                provider_fault_id=fault_id,
                mapping_epoch=remote.mapped_at,
            )
            db.add(existing)
        for field, value in values.items():
            setattr(existing, field, value)
        existing.received_at, existing.content_sha256 = received, fingerprint
    await db.flush()
    remote.fault_cursor_at, remote.faults_synced_at = end, received


def webhook_status(row):
    from app.services import motive_oauth as oauth

    if not row or not oauth.configured(row.tenant_id):
        status = "not_configured"
    elif not row.webhook_enabled or not row.encrypted_webhook_secret:
        status = "disabled"
    else:
        status = "receiving" if row.webhook_last_received_at else "awaiting_provider"
    return {
        "status": status,
        "webhook_id": row.webhook_id if row else None,
        "generation": row.webhook_generation if row else None,
        "last_received_at": row.webhook_last_received_at if row else None,
        "last_verified_at": row.webhook_verified_at if row else None,
    }


async def configure_webhook(db, actor, company_id, secret):
    from app.services import motive_oauth as oauth

    await oauth.authorize(db, actor, company_id)
    row = await oauth.connection(db, actor.tenant_id, company_id, True)
    if (
        not row
        or row.status not in {"connected", "provider_error"}
        or not oauth.configured(actor.tenant_id)
    ):
        raise HTTPException(409, "webhook_not_configured")
    if (
        not isinstance(secret, str)
        or not 32 <= len(secret) <= 512
        or not secret.isascii()
    ):
        raise HTTPException(422, "Invalid webhook secret")
    row.webhook_id, row.webhook_generation = uuid4(), row.webhook_generation + 1
    row.encrypted_webhook_secret = motive_crypto.encrypt(
        {"webhook_secret": secret}, row.id, row.tenant_id, row.fleet_customer_id
    )
    row.webhook_enabled = True
    row.webhook_last_received_at = row.webhook_verified_at = None
    await db.execute(
        update(MotiveWebhookReceipt)
        .where(
            MotiveWebhookReceipt.connection_id == row.id,
            MotiveWebhookReceipt.status == "pending",
        )
        .values(status="discarded", processed_at=oauth.now())
    )
    await db.commit()
    return row


async def disable_webhook(db, actor, company_id):
    from app.services import motive_oauth as oauth

    await oauth.authorize(db, actor, company_id)
    row = await oauth.connection(db, actor.tenant_id, company_id, True)
    if row:
        row.webhook_enabled = False
        row.webhook_generation += 1
        row.webhook_id = row.encrypted_webhook_secret = None
        await db.execute(
            update(MotiveWebhookReceipt)
            .where(
                MotiveWebhookReceipt.connection_id == row.id,
                MotiveWebhookReceipt.status == "pending",
            )
            .values(status="discarded", processed_at=oauth.now())
        )
        await db.commit()


async def ingest_webhook(db, webhook_id, generation, raw_body, signature):
    from app.services import motive_oauth as oauth

    if not isinstance(raw_body, bytes) or len(raw_body) > 262144:
        raise HTTPException(413, "Webhook body too large")
    try:
        # NOWAIT keeps durable acknowledgement under Motive's three-second deadline.
        row = (
            await db.execute(
                select(MotiveConnection)
                .join(Tenant, Tenant.id == MotiveConnection.tenant_id)
                .join(
                    Customer,
                    (Customer.id == MotiveConnection.fleet_customer_id)
                    & (Customer.tenant_id == MotiveConnection.tenant_id),
                )
                .where(
                    MotiveConnection.webhook_id == webhook_id,
                    MotiveConnection.webhook_generation == generation,
                    MotiveConnection.webhook_enabled.is_(True),
                    MotiveConnection.status.in_(["connected", "provider_error"]),
                    MotiveConnection.deleted_at.is_(None),
                    Tenant.is_active.is_(True),
                    Tenant.deleted_at.is_(None),
                    Customer.deleted_at.is_(None),
                    (
                        Customer.fleet_enabled.is_(True)
                        | Customer.is_internal_fleet.is_(True)
                    ),
                )
                .with_for_update(nowait=True, of=MotiveConnection)
            )
        ).scalar_one_or_none()
        if (
            not row
            or not oauth.configured(row.tenant_id)
            or not row.encrypted_webhook_secret
        ):
            raise HTTPException(404, "Webhook not found")
        secret = motive_crypto.decrypt(
            row.encrypted_webhook_secret, row.id, row.tenant_id, row.fleet_customer_id
        )["webhook_secret"]
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha1).hexdigest()
        if (
            not isinstance(signature, str)
            or len(signature) != 40
            or not signature.isascii()
            or not hmac.compare_digest(expected, signature.lower())
        ):
            raise HTTPException(403, "Invalid webhook signature")
        # Motive documents both signed JSON arrays and the literal non-JSON probe.
        stripped = raw_body.strip()
        probe = any(stripped == ("[" + action + "]").encode() for action in ACTIONS)
        payload = None if probe else json.loads(raw_body)
        if isinstance(payload, list):
            probe = bool(payload) and all(
                isinstance(action, str) and action in ACTIONS for action in payload
            )
            if not probe:
                raise HTTPException(400, "unsupported_webhook_event")
        if probe:
            row.webhook_verified_at = oauth.now()
            await db.commit()
            return {"status": "verified"}
        if not isinstance(payload, dict) or payload.get("action") not in ACTIONS:
            raise HTTPException(400, "unsupported_webhook_event")
        action = payload["action"]
        if action == "vehicle_upserted":
            provider_vehicle_id = identifier(payload["id"])
            if (
                "company_id" in payload
                and identifier(payload["company_id"]) != row.provider_company_id
            ):
                raise HTTPException(400, "Invalid company identity")
        elif action.startswith("fault_code"):
            provider_vehicle_id = identifier(payload["vehicle"]["id"])
        else:
            provider_vehicle_id = identifier(payload["vehicle_id"])
        object_id = str(payload["id"])
        safe_text(object_id, 120)
        hashed = hashlib.sha256(raw_body).hexdigest()
        exists = (
            await db.execute(
                select(MotiveWebhookReceipt.id).where(
                    MotiveWebhookReceipt.connection_id == row.id,
                    MotiveWebhookReceipt.webhook_generation == generation,
                    MotiveWebhookReceipt.payload_sha256 == hashed,
                )
            )
        ).first()
        if not exists:
            db.add(
                MotiveWebhookReceipt(
                    tenant_id=row.tenant_id,
                    connection_id=row.id,
                    connection_generation=row.generation,
                    webhook_generation=generation,
                    action=action,
                    provider_vehicle_id=provider_vehicle_id,
                    provider_object_id=object_id,
                    payload_sha256=hashed,
                    received_at=oauth.now(),
                    status="pending",
                )
            )
        row.webhook_last_received_at = oauth.now()
        await db.commit()
        return {"status": "duplicate" if exists else "accepted"}
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        await db.rollback()
        raise HTTPException(400, "Invalid webhook payload") from None
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(503, "Webhook temporarily unavailable") from None
