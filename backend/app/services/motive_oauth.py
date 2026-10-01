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
    # User may be a global identity; the selected tenant is authenticated context.
    tenant_id = actor.tenant_id
    current = (
        await db.execute(
            select(User)
            .where(User.id == actor.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not current or not current.is_active or current.deleted_at is not None:
        raise HTTPException(403, "Administrator access required")
    staff = (
        current.role in (UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN)
        and current.tenant_id == tenant_id
    )
    if not staff:
        from app.db.models.motive_oauth import MotiveFleetAdminGrant
        from app.db.models.user_customer_link import UserCustomerLink

        if (
            current.role != UserRole.CUSTOMER
            or getattr(actor, "customer_id", None) != company_id
        ):
            raise HTTPException(403, "Administrator access required")
        link = (
            await db.execute(
                select(UserCustomerLink.id).where(
                    UserCustomerLink.user_id == current.id,
                    UserCustomerLink.tenant_id == tenant_id,
                    UserCustomerLink.customer_id == company_id,
                    UserCustomerLink.deleted_at.is_(None),
                )
            )
        ).first()
        grant = (
            await db.execute(
                select(MotiveFleetAdminGrant.id).where(
                    MotiveFleetAdminGrant.user_id == current.id,
                    MotiveFleetAdminGrant.tenant_id == tenant_id,
                    MotiveFleetAdminGrant.fleet_customer_id == company_id,
                    MotiveFleetAdminGrant.revoked_at.is_(None),
                    MotiveFleetAdminGrant.deleted_at.is_(None),
                )
            )
        ).first()
        if not link or not grant:
            raise HTTPException(403, "grant_required")
    company = (
        await db.execute(
            select(Customer)
            .join(Tenant, Tenant.id == Customer.tenant_id)
            .where(
                Customer.id == company_id,
                Customer.tenant_id == tenant_id,
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
    from app.services.motive_ingestion import clear_remote_data

    await clear_remote_data(db, remote)
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
        from app.db.models.motive_oauth import (
            MotiveFault,
            MotiveHistorySample,
            MotiveWebhookReceipt,
        )

        row.reconciliation_cutoff_at = None
        row.webhook_enabled = False
        row.webhook_generation += 1
        row.webhook_id = row.encrypted_webhook_secret = None
        row.webhook_last_received_at = row.webhook_verified_at = (
            row.last_reconciled_at
        ) = None
        await db.execute(
            delete(MotiveHistorySample).where(
                MotiveHistorySample.connection_id == row.id
            )
        )
        await db.execute(delete(MotiveFault).where(MotiveFault.connection_id == row.id))
        await db.execute(
            update(MotiveWebhookReceipt)
            .where(
                MotiveWebhookReceipt.connection_id == row.id,
                MotiveWebhookReceipt.status == "pending",
            )
            .values(status="discarded", processed_at=now())
        )
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


async def sync(db, row, client=None, actor=None):
    """Caller holds connection lock; successful bounded stages commit independently."""
    from app.services import motive_ingestion as ingestion

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
    if not row.reconciliation_cutoff_at or utc(
        row.reconciliation_cutoff_at
    ) < stamp - timedelta(days=30):
        row.reconciliation_cutoff_at = stamp
    cutoff = utc(row.reconciliation_cutoff_at)
    counts = {"discovered": 0, "mapped": 0, "updated": 0, "rejected": 0}
    client = client or MotiveClient()
    rotated_credentials = {}
    try:
        if row.next_sync_at and utc(row.next_sync_at) > stamp:
            raise HTTPException(429, "Motive sync is cooling down; try again later")
        if not set(SCOPES.split()).issubset(row.scopes.split()):
            raise MotiveProviderError("insufficient_scope")

        async def work():
            async def rotate():
                token = await refresh(row, client)
                for field in (
                    "encrypted_tokens",
                    "token_expires_at",
                    "token_key_version",
                ):
                    rotated_credentials[field] = getattr(row, field)
                return token

            refreshed = not row.token_expires_at or utc(
                row.token_expires_at
            ) <= stamp + timedelta(seconds=120)
            token = (
                await rotate()
                if refreshed
                else motive_crypto.decrypt(
                    row.encrypted_tokens, row.id, row.tenant_id, row.fleet_customer_id
                )["access_token"]
            )

            async def provider(method, *args):
                nonlocal token, refreshed
                try:
                    return await method(token, *args)
                except MotiveProviderError as exc:
                    if exc.code != "reauthorization_required" or refreshed:
                        raise
                    token, refreshed = await rotate(), True
                    return await method(token, *args)

            inventory = await provider(client.inventory)
            gateways = await provider(client.gateways)
            locations = await provider(client.vehicles)
            current_locations = {
                identifier(v["id"]): v.get("current_location") for v in locations
            }
            assigned = {}
            for device in gateways:
                if not device.get("vehicle"):
                    continue
                vid = identifier(device["vehicle"]["id"])
                if vid in assigned:
                    raise MotiveProviderError("ambiguous_gateway")
                assigned[vid] = device
            normalized = []
            for raw in inventory:
                if (
                    raw.get("company_id") is not None
                    and identifier(raw["company_id"]) != row.provider_company_id
                ):
                    raise MotiveProviderError("company_mismatch")
                vid = identifier(raw["id"])
                device = assigned.get(vid)
                embedded = raw.get("eld_device")
                if embedded and (
                    not device or identifier(embedded["id"]) != identifier(device["id"])
                ):
                    raise MotiveProviderError("ambiguous_gateway")
                status = safe_text(raw.get("status"), 24)
                if status not in {"active", "deactivated"}:
                    raise MotiveProviderError("invalid_inventory")
                normalized.append(
                    (
                        vid,
                        safe_text(raw.get("number"), 120),
                        safe_text(raw.get("vin"), 17),
                        status,
                        identifier(device["id"]) if device else None,
                        safe_text(device.get("identifier"), 120) if device else None,
                        safe_text(device.get("model"), 120) if device else None,
                        current_locations.get(vid),
                    )
                )
            if actor:
                await authorize(db, actor, row.fleet_customer_id)
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
            for (
                vid,
                number,
                vin,
                status,
                gateway_id,
                gateway_identifier,
                gateway_model,
                raw_point,
            ) in normalized:
                remote = remotes.get(vid)
                if remote is None:
                    remote = MotiveRemoteVehicle(
                        id=uuid4(),
                        tenant_id=row.tenant_id,
                        connection_id=row.id,
                        provider_vehicle_id=vid,
                        discovered_at=stamp,
                    )
                    db.add(remote)
                    remotes[vid] = remote
                elif remote.gateway_id != gateway_id and remote.vehicle_id:
                    await ingestion.clear_remote_data(db, remote)
                    remote.vehicle_id = remote.mapped_at = remote.mapped_by_user_id = (
                        None
                    )
                remote.number, remote.vin, remote.provider_status = number, vin, status
                remote.gateway_id, remote.gateway_identifier, remote.gateway_model = (
                    gateway_id,
                    gateway_identifier,
                    gateway_model,
                )
                remote.discovered_at = stamp
                counts["discovered"] += 1
                if remote.vehicle_id not in trucks or status != "active":
                    await ingestion.clear_remote_data(db, remote)
                    continue
                counts["mapped"] += 1
                try:
                    point = parse_point(raw_point, stamp)
                except MotiveProviderError:
                    counts["rejected"] += 1
                    continue
                if point and (
                    not remote.mapped_at
                    or point["located_at"] < utc(remote.mapped_at)
                    or remote.vehicle_id
                    not in {
                        v.id for v in await active_trucks(db, row, point["located_at"])
                    }
                ):
                    counts["rejected"] += 1
                    continue
                if point and (
                    remote.located_at is None
                    or point["located_at"] > utc(remote.located_at)
                ):
                    for field, value in point.items():
                        setattr(remote, field, value)
                    remote.received_at = stamp
                    counts["updated"] += 1
                elif (
                    point
                    and point["located_at"] == utc(remote.located_at)
                    and any(
                        getattr(remote, field) != value
                        for field, value in point.items()
                        if field != "located_at"
                    )
                ):
                    counts["rejected"] += 1
            seen_ids = {v[0] for v in normalized}
            for vid, remote in remotes.items():
                if vid not in seen_ids:
                    remote.provider_status = "missing"
                    await ingestion.clear_remote_data(db, remote)
            await db.flush()
            eligible = [
                r
                for r in remotes.values()
                if r.vehicle_id in trucks
                and r.provider_status == "active"
                and r.gateway_id
                and r.mapped_at
                and utc(r.mapped_at) <= cutoff
            ]
            eligible.sort(
                key=lambda r: (
                    utc(r.history_cursor_at)
                    if r.history_cursor_at
                    else utc(r.mapped_at),
                    str(r.id),
                )
            )
            # Five vehicles per run, oldest cursor first. A partial fleet is explicit continuation.
            pending = [
                r
                for r in eligible
                if not r.history_cursor_at
                or utc(r.history_cursor_at) < cutoff
                or not r.fault_cursor_at
                or utc(r.fault_cursor_at) < cutoff
            ]
            for remote in pending[:5]:
                lower = max(utc(remote.mapped_at), stamp - timedelta(days=30))
                covered = (
                    utc(remote.history_cursor_at) if remote.history_cursor_at else lower
                )
                start = max(lower, covered - timedelta(minutes=5))
                end = min(cutoff, start + timedelta(days=1))
                history = await provider(
                    client.history, remote.provider_vehicle_id, start, end, start
                )
                if actor:
                    await authorize(db, actor, row.fleet_customer_id)
                async with db.begin_nested():
                    await ingestion.ingest_history(
                        db, row, remote, history, start, end, stamp
                    )
                fault_lower = (
                    max(lower, utc(remote.fault_cursor_at) - timedelta(minutes=5))
                    if remote.fault_cursor_at
                    else lower
                )
                fault_end = min(cutoff, fault_lower + timedelta(days=1))
                faults = await provider(
                    client.faults,
                    remote.provider_vehicle_id,
                    fault_lower,
                    fault_end,
                    fault_lower,
                )
                if actor:
                    await authorize(db, actor, row.fleet_customer_id)
                async with db.begin_nested():
                    await ingestion.ingest_faults(
                        db, row, remote, faults, fault_end, stamp
                    )
            complete = all(
                r.history_cursor_at
                and utc(r.history_cursor_at) >= cutoff
                and r.fault_cursor_at
                and utc(r.fault_cursor_at) >= cutoff
                for r in eligible
            )
            if not complete:
                raise MotiveProviderError("reconciliation_incomplete")

        if actor:
            # Preserve the connection lock while rolling back data if the actor
            # loses authorization during provider I/O. Rotated credentials belong
            # to the fleet and must survive for its other administrators.
            transaction = await db.begin_nested()
            try:
                await asyncio.wait_for(work(), timeout=20)
            except HTTPException:
                await transaction.rollback()
                await db.refresh(row)
                for field, value in rotated_credentials.items():
                    setattr(row, field, value)
                await db.commit()
                raise
            except (MotiveProviderError, ValueError, KeyError, TypeError, TimeoutError):
                await transaction.commit()
                raise
            else:
                await transaction.commit()
        else:
            await asyncio.wait_for(work(), timeout=20)
        (
            row.last_sync_at,
            row.last_reconciled_at,
            row.last_sync_counts,
            row.last_error_code,
        ) = stamp, cutoff, counts, None
        row.status, row.failure_count = "connected", 0
        row.reconciliation_cutoff_at = None
        row.next_sync_at = stamp + timedelta(minutes=5)
    except (MotiveProviderError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        code = exc.code if isinstance(exc, MotiveProviderError) else "invalid_response"
        row.last_error_code = code
        row.status = (
            "connected"
            if code == "reconciliation_incomplete"
            else "reconnect_required"
            if code
            in ("reauthorization_required", "reconnect_required", "insufficient_scope")
            else "provider_error"
        )
        row.failure_count = (
            0 if code == "reconciliation_incomplete" else row.failure_count + 1
        )
        row.next_sync_at = stamp + timedelta(
            seconds=60
            if code == "reconciliation_incomplete"
            else max(
                getattr(exc, "retry_after", 0),
                min(3600, 60 * 2 ** min(row.failure_count, 5)),
            )
            + secrets.randbelow(30)
        )
    await db.commit()
    return {
        "status": row.status,
        "counts": counts,
        "completed_at": stamp
        if row.status == "connected" and not row.last_error_code
        else None,
    }


async def purge(db):
    from app.services.fleet_telemetry import purge as purge_manual
    await purge_manual(db)
    from app.db.models.motive_oauth import (
        MotiveFault,
        MotiveHistorySample,
        MotiveWebhookReceipt,
    )

    async def execute(statement):
        return await db.execute(
            statement.execution_options(synchronize_session="fetch")
        )

    cutoff = now() - timedelta(days=30)
    await execute(
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
    await execute(
        delete(MotiveHistorySample).where(MotiveHistorySample.observed_at < cutoff)
    )
    await execute(
        delete(MotiveFault).where(
            or_(
                MotiveFault.received_at < cutoff,
                (MotiveFault.status == "closed")
                & (MotiveFault.last_observed_at < cutoff),
            )
        )
    )
    await execute(
        delete(MotiveWebhookReceipt).where(MotiveWebhookReceipt.received_at < cutoff)
    )
    await execute(
        update(MotiveRemoteVehicle)
        .where(MotiveRemoteVehicle.metrics_observed_at < cutoff)
        .values(
            metrics_observed_at=None,
            metrics_received_at=None,
            virtual_odometer_miles=None,
            true_odometer_miles=None,
            virtual_engine_hours=None,
            true_engine_hours=None,
        )
    )
    await execute(
        delete(MotiveAuthorization).where(
            MotiveAuthorization.expires_at < now() - timedelta(days=1)
        )
    )
    await db.commit()
