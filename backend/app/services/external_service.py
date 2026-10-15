"""Transactional outside-shop records and immutable revisions."""
from datetime import UTC, datetime
from hashlib import sha256
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.db.models.external_service import ExternalServiceEvent as Event, ExternalServiceRecord as Record
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.external_service import ExternalServiceFields, ExternalServiceHistoryItem, ExternalServiceHistoryPage, ExternalServiceItem, ExternalServiceMutation, ExternalServicePage
from app.services.service_checklist import actor_name

STAFF_ROLES = frozenset({UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST})
NOT_FOUND = "Vehicle or service record not found"
COLLISION = "This save ID has already been used. Refresh and try again."
STALE = "This service record has changed. Refresh it before saving."


async def load_vehicle(db, vehicle_id, actor, *, write=False):
    if actor.role not in STAFF_ROLES:
        raise HTTPException(403, "Access denied")
    if not actor.tenant_id:
        raise HTTPException(400, "User must be associated with a tenant")
    statement = select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.tenant_id == actor.tenant_id, Vehicle.deleted_at.is_(None)).execution_options(populate_existing=True)
    if write:
        statement = statement.with_for_update(of=Vehicle)
    vehicle = (await db.execute(statement)).scalar_one_or_none()
    if vehicle is None:
        raise HTTPException(404, NOT_FOUND)
    return vehicle


async def load_record(db, vehicle_id, record_id, actor, *, write=False):
    statement = select(Record).where(Record.id == record_id, Record.tenant_id == actor.tenant_id, Record.vehicle_id == vehicle_id, Record.deleted_at.is_(None)).execution_options(populate_existing=True)
    if write:
        statement = statement.with_for_update(of=Record)
    record = (await db.execute(statement)).scalar_one_or_none()
    if record is None:
        raise HTTPException(404, NOT_FOUND)
    return record


def item(record):
    return ExternalServiceItem.model_validate(record)


async def page(db, vehicle_id, actor, *, skip=0, limit=25, include_voided=False, search=None):
    await load_vehicle(db, vehicle_id, actor)
    conditions = [Record.tenant_id == actor.tenant_id, Record.vehicle_id == vehicle_id, Record.deleted_at.is_(None)]
    if not include_voided:
        conditions.append(Record.voided_at.is_(None))
    term = (search or "").strip()
    if term:
        conditions.append(or_(*(field.icontains(term, autoescape=True) for field in (Record.provider_name, Record.description, Record.reference))))
    total = await db.scalar(select(func.count(Record.id)).where(*conditions))
    records = (await db.scalars(select(Record).where(*conditions).order_by(Record.service_date.desc(), Record.created_at.desc(), Record.id.desc()).offset(skip).limit(limit))).all()
    return ExternalServicePage(items=[item(record) for record in records], total=total, has_more=skip + len(records) < total)


async def history(db, vehicle_id, record_id, actor, *, skip=0, limit=25):
    await load_vehicle(db, vehicle_id, actor)
    await load_record(db, vehicle_id, record_id, actor)
    conditions = [Event.tenant_id == actor.tenant_id, Event.record_id == record_id]
    total = await db.scalar(select(func.count(Event.id)).where(*conditions))
    events = (await db.scalars(select(Event).where(*conditions).order_by(Event.version.desc()).offset(skip).limit(limit))).all()
    return ExternalServiceHistoryPage(items=[ExternalServiceHistoryItem.model_validate(event) for event in events], total=total, has_more=skip + len(events) < total)


def request_hash(action, vehicle_id, record_id, body):
    payload = {"action": action, "vehicle_id": str(vehicle_id), "record_id": str(record_id) if record_id else None, "body": body.model_dump(mode="json", exclude={"request_id"})}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def replay(db, vehicle_id, record_id, actor, action, body, digest):
    event = await db.scalar(select(Event).where(Event.tenant_id == actor.tenant_id, Event.request_id == body.request_id))
    if event is None:
        return None
    if event.actor_user_id != actor.id or event.action != action or event.request_hash != digest or (record_id is not None and event.record_id != record_id):
        raise HTTPException(409, COLLISION)
    record = await load_record(db, vehicle_id, event.record_id, actor)
    return ExternalServiceMutation(record=item(record), replayed=True)


async def mutate(db, vehicle_id, actor, body, *, action="create", record_id=None):
    # Vehicle locks serialize writes with permanent vehicle merges. A stale
    # vehicle URL is rejected after a merge; never silently move a write.
    await load_vehicle(db, vehicle_id, actor, write=True)
    digest = request_hash(action, vehicle_id, record_id, body)
    repeated = await replay(db, vehicle_id, record_id, actor, action, body, digest)
    if repeated is not None:
        return repeated
    record = None if action == "create" else await load_record(db, vehicle_id, record_id, actor, write=True)
    if record is not None:
        if record.version != body.expected_version:
            raise HTTPException(409, STALE)
        if action in {"update", "void"} and record.voided_at is not None:
            raise HTTPException(409, "Restore this voided service record before changing it.")
        if action == "restore" and record.voided_at is None:
            raise HTTPException(409, "This service record is already active.")
    if action in {"create", "update"}:
        timezone_name = await db.scalar(select(Tenant.timezone).where(Tenant.id == actor.tenant_id))
        if body.service_date > datetime.now(ZoneInfo(timezone_name or "America/New_York")).date():
            raise HTTPException(422, "Service date cannot be in the future for this shop.")
    now = datetime.now(UTC)
    name = actor_name(actor)
    try:
        # A tenant can save to two different vehicles simultaneously. Protect
        # record + event as a unit if their shared request ID collides.
        async with db.begin_nested():
            if action == "create":
                record = Record(id=uuid4(), tenant_id=actor.tenant_id, vehicle_id=vehicle_id, original_vehicle_id=vehicle_id, version=1,
                                created_by_user_id=actor.id, created_by_name=name, created_at=now, updated_at=now)
                db.add(record)
            else:
                record.version += 1
            if action in {"create", "update"}:
                for field in ExternalServiceFields.model_fields:
                    setattr(record, field, getattr(body, field))
            elif action == "void":
                record.voided_at = now
            elif action == "restore":
                record.voided_at = None
            record.updated_by_user_id = actor.id
            record.updated_by_name = name
            record.updated_at = now
            await db.flush()
            db.add(Event(id=uuid4(), tenant_id=actor.tenant_id, record_id=record.id, request_id=body.request_id, request_hash=digest,
                         version=record.version, action=action, actor_user_id=actor.id, actor_name=name, reason=getattr(body, "reason", None),
                         snapshot=item(record).model_dump(mode="json"), created_at=now, updated_at=now))
            await db.flush()
    except IntegrityError:
        repeated = await replay(db, vehicle_id, record_id, actor, action, body, digest)
        if repeated is not None:
            return repeated
        raise
    return ExternalServiceMutation(record=item(record), replayed=False)
