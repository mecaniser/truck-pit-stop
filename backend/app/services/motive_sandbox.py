"""Tenant-scoped fixture persistence; callers own transaction commit/rollback.

No HTTP/provider client or scheduler is registered by this module. Account row
locks serialize ingest and binding changes on PostgreSQL. SQLite is test-only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.motive import (
    MotiveAccount,
    MotiveBinding,
    MotiveIngestionReceipt,
    MotiveLocationSample,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.services.motive_events import (
    InvalidMotiveEvent,
    MotiveLocationEvent,
    verify_and_normalize_location,
    verify_signature,
)

RETENTION = timedelta(days=30)
FUTURE_TOLERANCE = timedelta(minutes=5)
ADMIN_ROLES = (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)


class MotiveNotFound(ValueError):
    def __init__(self):
        super().__init__("Motive resource not found")


class MotiveConflict(ValueError):
    pass


def _utc(value: datetime) -> datetime:
    # SQLite drops timezone metadata; stored instants are always UTC.
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _clock(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("timezone is required")
    return value.astimezone(timezone.utc)


async def _actor(db: AsyncSession, actor: User) -> User:
    current = await db.scalar(
        select(User)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(
            User.id == actor.id,
            User.tenant_id == actor.tenant_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
            User.role.in_(ADMIN_ROLES),
            Tenant.deleted_at.is_(None),
            Tenant.is_active.is_(True),
        )
        .execution_options(populate_existing=True)
    )
    if current is None or current.tenant_id is None:
        raise MotiveNotFound()
    return current


async def _account(
    db: AsyncSession,
    tenant_id: UUID,
    account_id: UUID,
    *,
    for_retention: bool = False,
) -> MotiveAccount:
    query = select(MotiveAccount).where(
        MotiveAccount.id == account_id,
        MotiveAccount.tenant_id == tenant_id,
        MotiveAccount.mode == "fixture",
    )
    if not for_retention:
        query = query.join(Tenant, Tenant.id == MotiveAccount.tenant_id).where(
            MotiveAccount.deleted_at.is_(None),
            Tenant.deleted_at.is_(None),
            Tenant.is_active.is_(True),
        )
    account = await db.scalar(
        query.with_for_update(of=MotiveAccount).execution_options(
            populate_existing=True
        )
    )
    if account is None:
        raise MotiveNotFound()
    return account


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 120:
        raise ValueError("invalid provider identifier")
    identifier = value.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in identifier):
        raise ValueError("invalid provider identifier")
    try:
        identifier.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("invalid provider identifier") from exc
    return identifier


async def create_fixture_account(
    db: AsyncSession,
    *,
    actor: User,
    external_company_id: str,
) -> MotiveAccount:
    actor = await _actor(db, actor)
    await db.scalar(
        select(Tenant.id).where(Tenant.id == actor.tenant_id).with_for_update()
    )
    company = _identifier(external_company_id)
    if not company.startswith("fixture:"):
        raise ValueError("synthetic fixture company identifier required")
    existing = await db.scalar(
        select(MotiveAccount.id).where(MotiveAccount.tenant_id == actor.tenant_id)
    )
    if existing is not None:
        raise MotiveConflict("A Motive account already exists")
    account = MotiveAccount(
        id=uuid4(), tenant_id=actor.tenant_id, external_company_id=company
    )
    db.add(account)
    await db.flush()
    return account


async def set_fixture_enabled(
    db: AsyncSession,
    *,
    actor: User,
    account_id: UUID,
    enabled: bool,
) -> MotiveAccount:
    actor = await _actor(db, actor)
    account = await _account(db, actor.tenant_id, account_id)
    if not isinstance(enabled, bool):
        raise TypeError("enabled must be boolean")
    account.enabled = enabled
    await db.flush()
    return account


async def create_binding(
    db: AsyncSession,
    *,
    actor: User,
    account_id: UUID,
    vehicle_id: UUID,
    provider_vehicle_id: str,
    gateway_id: str | None,
    valid_from: datetime,
    now: datetime | None = None,
) -> MotiveBinding:
    actor = await _actor(db, actor)
    account = await _account(db, actor.tenant_id, account_id)
    start = _clock(valid_from)
    if start > _clock(now):
        raise ValueError("binding cannot start in the future")
    external_id = _identifier(provider_vehicle_id)
    gateway = _identifier(gateway_id) if gateway_id is not None else None
    vehicle = await db.scalar(
        select(Vehicle)
        .where(
            Vehicle.id == vehicle_id,
            Vehicle.tenant_id == actor.tenant_id,
            Vehicle.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if vehicle is None:
        raise MotiveNotFound()
    identities = [
        MotiveBinding.provider_vehicle_id == external_id,
        MotiveBinding.vehicle_id == vehicle_id,
    ]
    if gateway is not None:
        identities.append(MotiveBinding.gateway_id == gateway)
    overlap = await db.scalar(
        select(MotiveBinding.id)
        .where(
            MotiveBinding.tenant_id == actor.tenant_id,
            MotiveBinding.account_id == account.id,
            or_(*identities),
            or_(MotiveBinding.valid_to.is_(None), MotiveBinding.valid_to > start),
        )
        .limit(1)
    )
    if overlap is not None:
        raise MotiveConflict("Binding interval overlaps an existing assignment")
    binding = MotiveBinding(
        id=uuid4(),
        tenant_id=actor.tenant_id,
        account_id=account.id,
        vehicle_id=vehicle.id,
        provider_vehicle_id=external_id,
        gateway_id=gateway,
        valid_from=start,
        verified_by_user_id=actor.id,
    )
    db.add(binding)
    await db.flush()
    return binding


async def close_binding(
    db: AsyncSession,
    *,
    actor: User,
    account_id: UUID,
    binding_id: UUID,
    valid_to: datetime,
    now: datetime | None = None,
) -> MotiveBinding:
    actor = await _actor(db, actor)
    await _account(db, actor.tenant_id, account_id)
    binding = await db.scalar(
        select(MotiveBinding).where(
            MotiveBinding.id == binding_id,
            MotiveBinding.tenant_id == actor.tenant_id,
            MotiveBinding.account_id == account_id,
            MotiveBinding.deleted_at.is_(None),
        )
    )
    if binding is None:
        raise MotiveNotFound()
    end = _clock(valid_to)
    if end <= _utc(binding.valid_from) or end > _clock(now):
        raise ValueError("invalid binding end")
    if binding.valid_to is not None:
        if _utc(binding.valid_to) == end:
            return binding
        raise MotiveConflict("Closed bindings are immutable")
    # Rewriting an interval cannot silently relabel already accepted samples.
    later_sample = await db.scalar(
        select(MotiveLocationSample.id)
        .where(
            MotiveLocationSample.binding_id == binding.id,
            MotiveLocationSample.located_at >= end,
        )
        .limit(1)
    )
    if later_sample is not None:
        raise MotiveConflict("Binding end precedes an accepted observation")
    binding.valid_to = end
    await db.flush()
    return binding


def _fingerprint(event: MotiveLocationEvent) -> str:
    content = {
        "vehicle_id": event.vehicle_id,
        "located_at": event.located_at.isoformat(),
        "lat": event.lat,
        "lng": event.lng,
        "speed_mph": event.speed_mph,
        "bearing_degrees": event.bearing_degrees,
        "virtual_odometer_miles": event.virtual_odometer_miles,
        "engine_hours": event.engine_hours,
    }
    content = {
        k: 0.0 if isinstance(v, float) and v == 0 else v for k, v in content.items()
    }
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class IngestionResult:
    outcome: str
    receipt_id: UUID
    sample_id: UUID | None


async def ingest_fixture_location(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    account_id: UUID,
    raw_body: bytes,
    signature: str,
    fixture_secret: str,
    received_at: datetime | None = None,
) -> IngestionResult:
    now = _clock(received_at)
    account = await _account(db, tenant_id, account_id)
    receipt = MotiveIngestionReceipt(
        id=uuid4(),
        tenant_id=tenant_id,
        account_id=account_id,
        received_at=now,
        signature_state="not_checked",
        payload_sha256=hashlib.sha256(raw_body).hexdigest(),
    )

    async def finish(outcome: str, reason: str | None = None) -> IngestionResult:
        receipt.outcome, receipt.reason = outcome, reason
        db.add(receipt)
        await db.flush()
        return IngestionResult(outcome, receipt.id, receipt.sample_id)

    if not account.enabled:
        return await finish("disabled")
    try:
        verify_signature(raw_body, signature, fixture_secret)
        receipt.signature_state = "verified"
        event = verify_and_normalize_location(
            raw_body,
            signature,
            fixture_secret,
            tenant_id=tenant_id,
            provider_account_id=account_id,
        )
    except InvalidMotiveEvent:
        if receipt.signature_state != "verified":
            receipt.signature_state = "rejected"
        return await finish("invalid", "invalid_event")
    receipt.event_id = event.event_id
    receipt.content_sha256 = _fingerprint(event)
    original = await db.scalar(
        select(MotiveIngestionReceipt).where(
            MotiveIngestionReceipt.tenant_id == tenant_id,
            MotiveIngestionReceipt.account_id == account_id,
            MotiveIngestionReceipt.event_id == event.event_id,
            MotiveIngestionReceipt.outcome == "stored",
        )
    )
    if original is not None:
        if _utc(original.received_at) < now - RETENTION:
            return await finish("invalid", "expired_event_id")
        if original.content_sha256 != receipt.content_sha256:
            return await finish("conflict", "event_content_changed")
        receipt.sample_id = original.sample_id
        return await finish("duplicate")
    if event.located_at < now - RETENTION:
        return await finish("invalid", "expired_observation")
    if event.located_at > now + FUTURE_TOLERANCE:
        return await finish("invalid", "future_observation")
    bindings = list(
        (
            await db.scalars(
                select(MotiveBinding)
                .join(Vehicle, Vehicle.id == MotiveBinding.vehicle_id)
                .where(
                    MotiveBinding.tenant_id == tenant_id,
                    MotiveBinding.account_id == account_id,
                    MotiveBinding.provider_vehicle_id == event.vehicle_id,
                    MotiveBinding.deleted_at.is_(None),
                    MotiveBinding.valid_from <= event.located_at,
                    or_(
                        MotiveBinding.valid_to.is_(None),
                        MotiveBinding.valid_to > event.located_at,
                    ),
                    Vehicle.tenant_id == tenant_id,
                    Vehicle.deleted_at.is_(None),
                )
            )
        ).all()
    )
    if len(bindings) != 1:
        return await finish("unbound", "no_unique_binding")
    account.last_sample_sequence += 1
    sample = MotiveLocationSample(
        id=uuid4(),
        tenant_id=tenant_id,
        account_id=account_id,
        binding_id=bindings[0].id,
        event_id=event.event_id,
        located_at=event.located_at,
        received_at=now,
        lat=event.lat,
        lng=event.lng,
        speed_mph=event.speed_mph,
        bearing_degrees=event.bearing_degrees,
        virtual_odometer_miles=event.virtual_odometer_miles,
        engine_hours=event.engine_hours,
        payload_sha256=event.payload_sha256,
        ingestion_sequence=account.last_sample_sequence,
    )
    db.add(sample)
    await db.flush()
    receipt.sample_id = sample.id
    account.last_successful_sync_at = now
    return await finish("stored")


async def latest_locations(
    db: AsyncSession,
    *,
    actor: User,
    vehicle_ids: list[UUID],
    now: datetime | None = None,
) -> dict[UUID, MotiveLocationSample]:
    actor = await _actor(db, actor)
    cutoff = _clock(now) - RETENTION
    ranked = (
        select(
            MotiveBinding.vehicle_id,
            MotiveLocationSample.id.label("sample_id"),
            func.row_number()
            .over(
                partition_by=MotiveBinding.vehicle_id,
                order_by=(
                    MotiveLocationSample.located_at.desc(),
                    MotiveLocationSample.ingestion_sequence,
                ),
            )
            .label("position"),
        )
        .join(MotiveBinding, MotiveLocationSample.binding_id == MotiveBinding.id)
        .join(MotiveAccount, MotiveBinding.account_id == MotiveAccount.id)
        .join(Vehicle, MotiveBinding.vehicle_id == Vehicle.id)
        .where(
            MotiveLocationSample.tenant_id == actor.tenant_id,
            MotiveBinding.tenant_id == actor.tenant_id,
            MotiveAccount.tenant_id == actor.tenant_id,
            Vehicle.tenant_id == actor.tenant_id,
            Vehicle.deleted_at.is_(None),
            MotiveBinding.vehicle_id.in_(vehicle_ids),
            MotiveAccount.enabled.is_(True),
            MotiveAccount.deleted_at.is_(None),
            MotiveBinding.deleted_at.is_(None),
            MotiveLocationSample.deleted_at.is_(None),
            MotiveLocationSample.located_at >= cutoff,
            MotiveLocationSample.received_at >= cutoff,
        )
        .subquery()
    )
    rows = (
        await db.execute(
            select(ranked.c.vehicle_id, MotiveLocationSample)
            .join(MotiveLocationSample, MotiveLocationSample.id == ranked.c.sample_id)
            .where(ranked.c.position == 1)
        )
    ).all()
    return dict(rows)


async def purge_expired_fixture_data(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    account_id: UUID,
    now: datetime | None = None,
) -> dict[str, int]:
    await _account(db, tenant_id, account_id, for_retention=True)
    cutoff = _clock(now) - RETENTION
    expired = select(MotiveLocationSample.id).where(
        MotiveLocationSample.tenant_id == tenant_id,
        MotiveLocationSample.account_id == account_id,
        or_(
            MotiveLocationSample.located_at < cutoff,
            MotiveLocationSample.received_at < cutoff,
        ),
    )
    await db.execute(
        update(MotiveIngestionReceipt)
        .where(
            MotiveIngestionReceipt.tenant_id == tenant_id,
            MotiveIngestionReceipt.account_id == account_id,
            MotiveIngestionReceipt.sample_id.in_(expired),
        )
        .values(sample_id=None)
    )
    samples = await db.execute(
        delete(MotiveLocationSample).where(MotiveLocationSample.id.in_(expired))
    )
    receipts = await db.execute(
        delete(MotiveIngestionReceipt).where(
            MotiveIngestionReceipt.tenant_id == tenant_id,
            MotiveIngestionReceipt.account_id == account_id,
            MotiveIngestionReceipt.received_at < cutoff,
        )
    )
    await db.flush()
    return {"samples": samples.rowcount, "receipts": receipts.rowcount}
