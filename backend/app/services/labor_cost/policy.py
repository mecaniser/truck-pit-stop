"""Owner metadata transactions, signed cursors and protected response shapes."""
import base64
import hashlib
import hmac
import json
from datetime import datetime, date, timezone, time
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import settings
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.db.models.labor_cost import TechnicianCostPolicyRevision, JobCostReview
from .calculation import ACTIVATION_DATE, canonical, digest, moment, stamp


def authorize(actor):
    if (actor.role != UserRole.GARAGE_OWNER or not actor.tenant_id
            or getattr(actor, "deleted_at", None) is not None or not getattr(actor, "is_active", False)):
        raise HTTPException(403, "Owner cost access required")
    return actor.tenant_id


async def context(db, actor, *, lock=False):
    tenant_id = authorize(actor)
    query = select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active.is_(True), Tenant.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    tenant = (await db.execute(query)).scalar_one_or_none()
    owner = (await db.execute(select(User.id).where(User.id == actor.id, User.tenant_id == tenant_id,
             User.role == UserRole.GARAGE_OWNER, User.is_active.is_(True), User.deleted_at.is_(None)))).scalar_one_or_none()
    if not tenant or not owner:
        raise HTTPException(403, "Owner cost access required")
    try:
        zone = ZoneInfo(tenant.timezone)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise HTTPException(503, "Shop cost timezone unavailable")
    activation = datetime.combine(date.fromisoformat(ACTIVATION_DATE), time.min, tzinfo=zone).astimezone(timezone.utc)
    return tenant, zone, activation


def cursor_encode(scope, position):
    raw = json.dumps({"v": 1, "scope": digest(scope), "position": position}, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(settings.SECRET_KEY.encode(), b"db136:" + raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + signature).decode().rstrip("=")


def cursor_decode(token, scope):
    if token is None:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        if base64.urlsafe_b64encode(decoded).decode().rstrip("=") != token:
            raise ValueError()
        raw, sig = decoded[:-32], decoded[-32:]
        if not hmac.compare_digest(sig, hmac.new(settings.SECRET_KEY.encode(), b"db136:" + raw, hashlib.sha256).digest()):
            raise ValueError()
        value = json.loads(raw)
        if value.get("v") != 1 or value.get("scope") != digest(scope) or not isinstance(value.get("position"), list):
            raise ValueError()
        return value["position"]
    except (ValueError, TypeError, UnicodeError, KeyError):
        raise HTTPException(422, "Invalid cost report cursor")


def display_name(mechanic):
    return " ".join(part for part in (mechanic.first_name, mechanic.last_name) if part).strip() or "Technician"


async def technician(db, tenant_id, identity):
    row = (await db.execute(select(User).where(User.id == identity, User.tenant_id == tenant_id,
                     User.role == UserRole.MECHANIC, User.deleted_at.is_(None)))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Technician not found")
    return row


def rate_response(mechanic, revision):
    return {"mechanic_id": str(mechanic.id), "mechanic_name": display_name(mechanic), "is_active": mechanic.is_active,
            "version": revision.version if revision else 0, "revision_id": str(revision.id) if revision else None,
            "supersedes_id": str(revision.supersedes_id) if revision and revision.supersedes_id else None,
            "policy": revision.policy if revision else None,
            "approved_by_user_id": str(revision.approved_by_user_id) if revision else None,
            "approved_at": stamp(revision.created_at) if revision else None}


async def rate_history(db, tenant_id, mechanic_id):
    rows = list((await db.execute(select(TechnicianCostPolicyRevision).where(
        TechnicianCostPolicyRevision.tenant_id == tenant_id, TechnicianCostPolicyRevision.mechanic_id == mechanic_id)
        .order_by(TechnicianCostPolicyRevision.version.desc()).limit(1001))).scalars())
    if len(rows) > 1000:
        raise HTTPException(413, "Cost policy history exceeds safe read limit")
    return rows


async def append_rate(db, actor, mechanic_id, body, key):
    tenant, zone, activation = await context(db, actor, lock=True)
    mechanic = await technician(db, tenant.id, mechanic_id)
    request_sha = digest(body.model_dump())
    previous_key = (await db.execute(select(TechnicianCostPolicyRevision).where(
        TechnicianCostPolicyRevision.tenant_id == tenant.id, TechnicianCostPolicyRevision.idempotency_key == key))).scalar_one_or_none()
    if previous_key:
        if previous_key.request_sha256 != request_sha or previous_key.approved_by_user_id != actor.id or previous_key.mechanic_id != mechanic_id:
            raise HTTPException(409, "Cost policy changed; refresh before retrying")
        return rate_response(mechanic, previous_key), False
    if not mechanic.is_active:
        raise HTTPException(422, "Inactive technician cannot receive a new policy")
    history = await rate_history(db, tenant.id, mechanic_id)
    prior = history[0] if history else None
    if body.expected_version != (prior.version if prior else 0):
        raise HTTPException(409, "Cost policy changed; refresh before retrying")
    if len(history) == 1000:
        raise HTTPException(413, "Cost policy history exceeds safe read limit")
    if prior:
        # Deliberate replacement after timezone change retains original instant.
        activation = moment(prior.policy["activation_at"])
    segments, previous_end = [], None
    for index, segment in enumerate(body.segments):
        start = moment(segment.effective_from)
        end = moment(segment.effective_to) if segment.effective_to else None
        if (start < activation or end is not None and end <= start
                or index and (previous_end is None or start < previous_end)
                or end is None and index != len(body.segments) - 1):
            raise HTTPException(422, "Invalid cost policy intervals")
        segments.append({**segment.model_dump(), "effective_from": stamp(start), "effective_to": stamp(end) if end else None})
        previous_end = end
    policy = {"policy_version": 1, "currency": "USD", "basis": "owner_declared_loaded_direct",
              "shop_timezone": tenant.timezone, "activation_local_date": ACTIVATION_DATE,
              "activation_at": stamp(activation), "segments": segments, "reason": body.reason}
    revision = TechnicianCostPolicyRevision(tenant_id=tenant.id, mechanic_id=mechanic_id,
        version=body.expected_version + 1, supersedes_id=prior.id if prior else None, policy=policy,
        request_sha256=request_sha, idempotency_key=key, approved_by_user_id=actor.id,
        created_at=datetime.now(timezone.utc))
    db.add(revision)
    await db.flush()
    return rate_response(mechanic, revision), True
