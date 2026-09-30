"""Company-scoped lifecycle. Row locks serialize refresh, mapping and disconnect."""

import asyncio
import hashlib
import math
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core import motive_crypto
from app.core.config import settings
from app.db.models.customer import Customer
from app.db.models.motive_oauth import (
    MotiveAuthorization,
    MotiveConnection,
    MotiveRemoteVehicle,
)
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.services.motive_client import (
    AUTHORIZE_URL,
    SCOPES,
    MotiveClient,
    MotiveProviderError,
    identifier,
    safe_text,
)


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def configured(tenant_id):
    try:
        uri = urlsplit(settings.MOTIVE_REDIRECT_URI)
        allowed = {
            x.strip()
            for x in settings.MOTIVE_APPROVED_TENANT_IDS.split(",")
            if x.strip()
        }
        motive_crypto.cipher()
        return bool(
            settings.MOTIVE_ENABLED
            and settings.MOTIVE_CLIENT_ID
            and settings.MOTIVE_CLIENT_SECRET
            and str(tenant_id) in allowed
            and uri.scheme == "https"
            and uri.hostname
            and not uri.username
            and not uri.fragment
            and not uri.query
            and uri.path == "/fleet/motive/callback"
        )
    except ValueError:
        return False


async def authorize(db, actor, company_id):
    actor = (
        await db.execute(
            select(User)
            .where(User.id == actor.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if (
        not actor.is_active
        or actor.deleted_at is not None
        or actor.role not in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
    ):
        raise HTTPException(403, "Administrator access required")
    company = (
        await db.execute(
            select(Customer)
            .join(Tenant, Tenant.id == Customer.tenant_id)
            .where(
                Customer.id == company_id,
                Customer.tenant_id == actor.tenant_id,
                Customer.deleted_at.is_(None),
                or_(
                    Customer.fleet_enabled.is_(True),
                    Customer.is_internal_fleet.is_(True),
                ),
                Tenant.is_active.is_(True),
                Tenant.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not company:
        raise HTTPException(404, "Fleet company not found")
    return company


async def connection(db, tenant_id, company_id, lock=False):
    query = select(MotiveConnection).where(
        MotiveConnection.tenant_id == tenant_id,
        MotiveConnection.fleet_customer_id == company_id,
        MotiveConnection.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update(nowait=True).execution_options(
            populate_existing=True
        )
    try:
        return (await db.execute(query)).scalar_one_or_none()
    except DBAPIError:
        await db.rollback()
        raise HTTPException(409, "Motive connection is busy; try again") from None


def response(row, company_id, tenant_id):
    ready = configured(tenant_id)
    return {
        "fleet_customer_id": company_id,
        "configured": ready,
        "status": (row.status if row else "disconnected")
        if ready
        else "not_configured",
        "company": {"id": row.provider_company_id, "name": row.provider_company_name}
        if row and row.provider_company_id
        else None,
        "last_sync_at": row.last_sync_at if row else None,
        "next_sync_at": row.next_sync_at if row else None,
        "last_sync_error_code": row.last_error_code if row else None,
        "last_sync_counts": row.last_sync_counts if row else None,
        "can_connect": ready,
    }


async def start(db, actor, company_id, session_id):
    company = await authorize(db, actor, company_id)
    if not configured(actor.tenant_id):
        raise HTTPException(503, "Motive connection is not configured")
    # Serialize first creation as well as later reconnects on the stable company row.
    await db.execute(
        select(Customer.id).where(Customer.id == company.id).with_for_update()
    )
    row = await connection(db, actor.tenant_id, company_id, True)
    if not row:
        row = MotiveConnection(
            id=uuid4(),
            tenant_id=actor.tenant_id,
            fleet_customer_id=company_id,
            status="disconnected",
            generation=0,
        )
        db.add(row)
        await db.flush()
    row.generation += 1
    value = secrets.token_urlsafe(32)
    expiry = now() + timedelta(minutes=10)
    db.add(
        MotiveAuthorization(
            tenant_id=actor.tenant_id,
            connection_id=row.id,
            user_id=actor.id,
            generation=row.generation,
            state_hash=digest(value),
            session_hash=digest(session_id),
            expires_at=expiry,
        )
    )
    await db.commit()
    return {
        "authorization_url": AUTHORIZE_URL
        + "?"
        + urlencode(
            {
                "client_id": settings.MOTIVE_CLIENT_ID,
                "redirect_uri": settings.MOTIVE_REDIRECT_URI,
                "response_type": "code",
                "scope": SCOPES,
                "state": value,
            }
        ),
        "expires_at": expiry,
    }


async def callback(
    db, actor, session_id, state, code=None, error=None, client=None, revalidate=None
):
    stamp = now()
    pending = (
        await db.execute(
            select(MotiveAuthorization).where(
                MotiveAuthorization.state_hash == digest(state),
                MotiveAuthorization.tenant_id == actor.tenant_id,
                MotiveAuthorization.user_id == actor.id,
                MotiveAuthorization.session_hash == digest(session_id),
                MotiveAuthorization.consumed_at.is_(None),
                MotiveAuthorization.expires_at > stamp,
            )
        )
    ).scalar_one_or_none()
    if not pending:
        raise HTTPException(400, "Authorization expired or invalid; connect again")
    row = (
        await db.execute(
            select(MotiveConnection).where(MotiveConnection.id == pending.connection_id)
        )
    ).scalar_one()
    await authorize(db, actor, row.fleet_customer_id)
    company_id, connection_id, generation = (
        row.fleet_customer_id,
        row.id,
        pending.generation,
    )
    consumed = await db.execute(
        update(MotiveAuthorization)
        .where(
            MotiveAuthorization.id == pending.id,
            MotiveAuthorization.consumed_at.is_(None),
        )
        .values(consumed_at=stamp)
    )
    await db.commit()  # Code is single-use even if the provider subsequently fails.
    if consumed.rowcount != 1:
        raise HTTPException(400, "Authorization expired or invalid; connect again")
    if error or not code:
        raise HTTPException(400, "Motive authorization was not completed")
    if not configured(actor.tenant_id):
        raise HTTPException(503, "Motive connection is not configured")
    client = client or MotiveClient()
    try:
        tokens = await client.tokens(code=code)
        provider_id, provider_name = await client.company(tokens["access_token"])
    except MotiveProviderError as exc:
        raise HTTPException(502, exc.code) from None
    if revalidate:
        await revalidate()
    row = await connection(db, actor.tenant_id, company_id, True)
    await authorize(db, actor, company_id)
    if not row or row.id != connection_id or row.generation != generation:
        raise HTTPException(409, "Connection changed; connect again")
    if row.provider_company_id and row.provider_company_id != provider_id:
        raise HTTPException(409, "Disconnect before changing the Motive company")
    row.provider_company_id, row.provider_company_name = provider_id, provider_name
    row.encrypted_tokens = motive_crypto.encrypt(
        tokens, row.id, row.tenant_id, row.fleet_customer_id
    )
    row.token_key_version = settings.MOTIVE_TOKEN_ACTIVE_KEY_VERSION
    row.token_expires_at = now() + timedelta(seconds=tokens["expires_in"])
    row.scopes, row.status, row.connected_at = SCOPES, "connected", now()
    row.last_error_code, row.next_sync_at, row.failure_count = None, now(), 0
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            409, "Motive company is already connected in this shop"
        ) from None
    return response(row, company_id, actor.tenant_id)


async def active_trucks(db, row, stamp=None):
    stamp = stamp or now()
    return (
        (
            await db.execute(
                select(Vehicle)
                .join(FleetMembership, FleetMembership.vehicle_id == Vehicle.id)
                .where(
                    Vehicle.tenant_id == row.tenant_id,
                    Vehicle.deleted_at.is_(None),
                    FleetMembership.tenant_id == row.tenant_id,
                    FleetMembership.fleet_customer_id == row.fleet_customer_id,
                    FleetMembership.deleted_at.is_(None),
                    FleetMembership.effective_from <= stamp,
                    or_(
                        FleetMembership.effective_to.is_(None),
                        FleetMembership.effective_to > stamp,
                    ),
                )
            )
        )
        .scalars()
        .unique()
        .all()
    )


def clear_point(remote):
    for field in ("located_at", "received_at", "lat", "lng", "speed_mph", "bearing"):
        setattr(remote, field, None)


async def bind(db, actor, company_id, provider_id, vehicle_id):
    await authorize(db, actor, company_id)
    row = await connection(db, actor.tenant_id, company_id, True)
    if not row or row.status not in (
        "connected",
        "provider_error",
        "reconnect_required",
    ):
        raise HTTPException(404, "Motive vehicle not found")
    remote = (
        await db.execute(
            select(MotiveRemoteVehicle).where(
                MotiveRemoteVehicle.connection_id == row.id,
                MotiveRemoteVehicle.provider_vehicle_id == provider_id,
                MotiveRemoteVehicle.tenant_id == actor.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if not remote:
        raise HTTPException(404, "Motive vehicle not found")
    if vehicle_id and vehicle_id not in {v.id for v in await active_trucks(db, row)}:
        raise HTTPException(404, "Fleet truck not found")
    if remote.vehicle_id == vehicle_id:
        return {
            "provider_vehicle_id": provider_id,
            "vehicle_id": vehicle_id,
            "mapped_at": remote.mapped_at,
        }
    if vehicle_id:
        existing = (
            await db.execute(
                select(MotiveRemoteVehicle.id).where(
                    MotiveRemoteVehicle.tenant_id == row.tenant_id,
                    MotiveRemoteVehicle.vehicle_id == vehicle_id,
                )
            )
        ).first()
        if existing:
            raise HTTPException(409, "Truck already mapped")
    remote.vehicle_id, remote.mapped_at = vehicle_id, now() if vehicle_id else None
    remote.mapped_by_user_id = actor.id
    clear_point(remote)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Truck already mapped") from None
    return {
        "provider_vehicle_id": provider_id,
        "vehicle_id": vehicle_id,
        "mapped_at": remote.mapped_at,
    }


async def disconnect(db, actor, company_id):
    await authorize(db, actor, company_id)
    row = await connection(db, actor.tenant_id, company_id, True)
    if row:
        row.generation += 1
        row.status = "disconnected"
        row.token_key_version = None
        row.encrypted_tokens = row.token_expires_at = row.provider_company_id = (
            row.provider_company_name
        ) = None
        row.last_error_code = row.last_sync_at = row.last_sync_counts = (
            row.next_sync_at
        ) = None
        await db.execute(
            delete(MotiveRemoteVehicle).where(
                MotiveRemoteVehicle.connection_id == row.id
            )
        )
        await db.execute(
            update(MotiveAuthorization)
            .where(
                MotiveAuthorization.connection_id == row.id,
                MotiveAuthorization.consumed_at.is_(None),
            )
            .values(consumed_at=now())
        )
        await db.commit()


async def refresh(row, client):
    try:
        old = motive_crypto.decrypt(
            row.encrypted_tokens, row.id, row.tenant_id, row.fleet_customer_id
        )
    except ValueError:
        raise MotiveProviderError("reconnect_required") from None
    tokens = await client.tokens(refresh_token=old["refresh_token"])
    row.encrypted_tokens = motive_crypto.encrypt(
        tokens, row.id, row.tenant_id, row.fleet_customer_id
    )
    row.token_key_version = settings.MOTIVE_TOKEN_ACTIVE_KEY_VERSION
    row.token_expires_at = now() + timedelta(seconds=tokens["expires_in"])
    return tokens["access_token"]


def parse_point(raw, stamp):
    if raw is None:
        return None
    try:
        if not isinstance(raw, dict):
            raise TypeError()
        located = datetime.fromisoformat(raw["located_at"].replace("Z", "+00:00"))
        if located.tzinfo is None or not stamp - timedelta(
            days=30
        ) <= located <= stamp + timedelta(minutes=5):
            raise ValueError()

        def number(key, lo, hi, optional=False):
            value = raw.get(key)
            if value is None and optional:
                return None
            if (
                type(value) not in (float, int)
                or not math.isfinite(value)
                or not lo <= value <= hi
            ):
                raise ValueError()
            return float(value)

        speed = number("kph", 0, 400, True)
        return {
            "located_at": located,
            "lat": number("lat", -90, 90),
            "lng": number("lon", -180, 180),
            "speed_mph": speed / 1.609344 if speed is not None else None,
            "bearing": number("bearing", 0, 360, True),
        }
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
        raise MotiveProviderError("invalid_location") from None


async def sync(db, row, client=None):
    # Caller must hold row lock through commit, including rotating token refresh.
    if not configured(row.tenant_id) or row.status not in (
        "connected",
        "provider_error",
    ):
        raise HTTPException(409, "Motive connection is not available")
    company = (
        await db.execute(
            select(Customer)
            .join(Tenant, Tenant.id == Customer.tenant_id)
            .where(
                Customer.id == row.fleet_customer_id,
                Customer.tenant_id == row.tenant_id,
                Customer.deleted_at.is_(None),
                Tenant.is_active.is_(True),
                Tenant.deleted_at.is_(None),
                or_(
                    Customer.fleet_enabled.is_(True),
                    Customer.is_internal_fleet.is_(True),
                ),
            )
        )
    ).scalar_one_or_none()
    if not company:
        raise HTTPException(404, "Fleet company not found")
    stamp = now()
    counts = {"discovered": 0, "mapped": 0, "updated": 0, "rejected": 0}
    client = client or MotiveClient()
    try:
        if row.next_sync_at and utc(row.next_sync_at) > stamp:
            raise HTTPException(429, "Motive sync is cooling down; try again later")

        async def fetch():
            refreshed = not row.token_expires_at or utc(
                row.token_expires_at
            ) <= stamp + timedelta(seconds=120)
            token = (
                await refresh(row, client)
                if refreshed
                else motive_crypto.decrypt(
                    row.encrypted_tokens, row.id, row.tenant_id, row.fleet_customer_id
                )["access_token"]
            )
            try:
                return await client.vehicles(token)
            except MotiveProviderError as exc:
                if exc.code != "reauthorization_required" or refreshed:
                    raise
                token = await refresh(row, client)
                return await client.vehicles(token)

        raw_vehicles = await asyncio.wait_for(fetch(), timeout=20)
        # Normalize entire inventory before any inventory writes; invalid pagination cannot partially replace it.
        parsed = [
            (
                identifier(v["id"]),
                safe_text(v.get("number"), 120),
                safe_text(v.get("vin"), 17),
                v.get("current_location"),
            )
            for v in raw_vehicles
        ]
        remotes = {
            v.provider_vehicle_id: v
            for v in (
                await db.execute(
                    select(MotiveRemoteVehicle).where(
                        MotiveRemoteVehicle.connection_id == row.id
                    )
                )
            ).scalars()
        }
        trucks = {v.id for v in await active_trucks(db, row)}
        for provider_id, number, vin, raw in parsed:
            remote = remotes.get(provider_id)
            if remote is None:
                remote = MotiveRemoteVehicle(
                    tenant_id=row.tenant_id,
                    connection_id=row.id,
                    provider_vehicle_id=provider_id,
                    discovered_at=stamp,
                )
                db.add(remote)
            remote.number, remote.vin, remote.discovered_at = number, vin, stamp
            counts["discovered"] += 1
            if remote.vehicle_id not in trucks:
                clear_point(remote)
                continue
            counts["mapped"] += 1
            try:
                point = parse_point(raw, stamp)
            except MotiveProviderError:
                counts["rejected"] += 1
                continue
            if point and remote.vehicle_id not in {
                v.id for v in await active_trucks(db, row, point["located_at"])
            }:
                counts["rejected"] += 1
                continue
            if (
                point
                and remote.mapped_at
                and utc(remote.mapped_at) <= point["located_at"]
            ):
                if remote.located_at is None or point["located_at"] > utc(
                    remote.located_at
                ):
                    for field, value in point.items():
                        setattr(remote, field, value)
                    remote.received_at = stamp
                    counts["updated"] += 1
                elif point["located_at"] == utc(remote.located_at) and any(
                    getattr(remote, field) != value
                    for field, value in point.items()
                    if field != "located_at"
                ):
                    counts["rejected"] += 1
            elif point:
                counts["rejected"] += 1
        row.last_sync_at, row.last_sync_counts, row.last_error_code = (
            stamp,
            counts,
            None,
        )
        row.status, row.failure_count = "connected", 0
        row.next_sync_at = stamp + timedelta(minutes=5)
    except (MotiveProviderError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        code = exc.code if isinstance(exc, MotiveProviderError) else "invalid_response"
        row.last_error_code = code
        row.status = (
            "reconnect_required"
            if code
            in ("reauthorization_required", "reconnect_required", "insufficient_scope")
            else "provider_error"
        )
        row.failure_count += 1
        retry_after = getattr(exc, "retry_after", 0)
        row.next_sync_at = stamp + timedelta(
            seconds=max(retry_after, min(3600, 60 * 2 ** min(row.failure_count, 5)))
            + secrets.randbelow(30)
        )
    await (
        db.commit()
    )  # Persist rotated refresh tokens even if the subsequent inventory request failed.
    return {"status": row.status, "counts": counts, "completed_at": stamp}


async def purge(db):
    cutoff = now() - timedelta(days=30)
    await db.execute(
        update(MotiveRemoteVehicle)
        .where(MotiveRemoteVehicle.located_at < cutoff)
        .values(
            located_at=None,
            received_at=None,
            lat=None,
            lng=None,
            speed_mph=None,
            bearing=None,
        )
    )
    await db.execute(
        delete(MotiveAuthorization).where(
            MotiveAuthorization.expires_at < now() - timedelta(days=1)
        )
    )
    await db.commit()
