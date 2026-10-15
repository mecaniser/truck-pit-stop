"""One source predicate and explicit shop-time resolution for staff schedules.

The caller owns the transaction. No money, timers, status or customer messages
are changed. Projection readers join the canonical columns instead of storing a
clock-dependent overdue value or rewriting historical JSON payloads.
"""
from datetime import UTC, datetime, timedelta
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import and_, select

from app.db.models.repair_order import RepairOrder, RepairOrderStatus as Status
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.schemas.repair_order_schedule import RepairOrderScheduleResponse
from app.services import operation_execution
from app.services.service_checklist import actor_name

INTERNAL_EVENT_TYPES = frozenset({"schedule_changed"})
OVERDUE_STATUSES = frozenset({Status.DRAFT, Status.QUOTED, Status.APPROVED, Status.ASSIGNED,
                             Status.ACKNOWLEDGED, Status.IN_PROGRESS, Status.PENDING_REVIEW})
EDITABLE_STATUSES = OVERDUE_STATUSES | {Status.DECLINED}


def now_utc():
    return datetime.now(UTC)


def utc(value):
    return operation_execution.utc(value).astimezone(UTC) if value is not None else None


def can_read(actor):
    return actor.role in operation_execution.STAFF | {UserRole.MECHANIC}


def require_reader(actor):
    if not can_read(actor):
        raise HTTPException(403, "Shop schedule access denied")


def editable(order):
    return (getattr(order, "deleted_at", None) is None
            and getattr(order, "vehicle_released_at", None) is None
            and order.status in EDITABLE_STATUSES)


def overdue_predicate(now):
    return and_(RepairOrder.promised_finish_at.isnot(None), RepairOrder.promised_finish_at < now,
                RepairOrder.deleted_at.is_(None), RepairOrder.vehicle_released_at.is_(None),
                RepairOrder.status.in_(OVERDUE_STATUSES))


def is_overdue(order, now):
    promise = getattr(order, "promised_finish_at", None)
    return bool(promise is not None and utc(promise) < utc(now)
                and getattr(order, "deleted_at", None) is None
                and getattr(order, "vehicle_released_at", None) is None
                and order.status in OVERDUE_STATUSES)


def error(status, code, message, *, field=None, **extra):
    detail = {"code": code, "message": message, **extra}
    if field:
        detail["field"] = field
    raise HTTPException(status, detail)


def valid_timezone(name):
    try:
        return name if isinstance(name, str) and name and ZoneInfo(name) else None
    except (ZoneInfoNotFoundError, ValueError):
        return None


async def tenant_timezone(db, tenant_id, *, required=False):
    name = await db.scalar(select(Tenant.timezone).where(Tenant.id == tenant_id)) if tenant_id else None
    name = valid_timezone(name)
    if required and name is None:
        error(409, "schedule_timezone_invalid", "The shop timezone is invalid. Ask an administrator to correct it before scheduling.")
    return name


def wall_candidates(text, zone):
    wall = datetime.strptime(text, "%Y-%m-%dT%H:%M")
    candidates = {}
    for fold in (0, 1):
        local = wall.replace(tzinfo=zone, fold=fold)
        instant = local.astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == wall:
            candidates[fold] = instant
    return candidates


def resolve_wall(text, fold, zone, field):
    if text is None:
        return None
    try:
        candidates = wall_candidates(text, zone)
    except OverflowError:
        error(422, "schedule_time_out_of_range", "This date cannot be represented in the shop timezone. Choose another date.", field=field)
    if not candidates:
        error(422, "schedule_time_nonexistent", "This time does not exist because the shop clock moves forward. Choose another time.", field=field)
    ambiguous = len(set(candidates.values())) == 2
    if ambiguous and fold is None:
        error(422, "schedule_time_ambiguous", "This time occurs twice when the shop clock moves back. Choose the first or second occurrence.",
              field=field, choices=[{"fold": key, "utc": instant.isoformat(),
                                     "utc_offset": instant.astimezone(zone).strftime("%z")[:3] + ":" + instant.astimezone(zone).strftime("%z")[3:]}
                                    for key, instant in candidates.items()])
    if not ambiguous and fold == 1:
        error(422, "schedule_fold_invalid", "A second occurrence is only valid for a repeated clock hour.", field=field)
    return candidates[fold or 0]


def local_fields(instant, zone):
    if instant is None:
        return None, None
    local = utc(instant).astimezone(zone)
    text = local.replace(tzinfo=None).isoformat(timespec="minutes")
    ambiguous = len(set(wall_candidates(text, zone).values())) == 2
    return text, local.fold if ambiguous else None


def fields(order, timezone_name, now, *, visible=True):
    return {
        "scheduled_start_at": utc(getattr(order, "scheduled_start_at", None)) if visible else None,
        "promised_finish_at": utc(getattr(order, "promised_finish_at", None)) if visible else None,
        "schedule_timezone": timezone_name if visible else None,
        "is_overdue": is_overdue(order, now) if visible else False,
    }


def response(order, actor, timezone_name, *, now=None):
    zone = ZoneInfo(timezone_name)
    start, start_fold = local_fields(order.scheduled_start_at, zone)
    finish, finish_fold = local_fields(order.promised_finish_at, zone)
    return RepairOrderScheduleResponse(
        id=order.id, timezone=timezone_name,
        scheduled_start_at=utc(order.scheduled_start_at), promised_finish_at=utc(order.promised_finish_at),
        scheduled_start_local=start, promised_finish_local=finish,
        scheduled_start_fold=start_fold, promised_finish_fold=finish_fold,
        updated_at=utc(order.updated_at), is_overdue=is_overdue(order, now or now_utc()),
        can_edit=actor.role in operation_execution.STAFF and editable(order),
    )


async def read(db, order_id, actor):
    require_reader(actor)
    order = await operation_execution.load_order(db, order_id, actor)
    zone = await tenant_timezone(db, actor.tenant_id, required=True)
    return response(order, actor, zone)


async def update(db, order_id, actor, body):
    if actor.role not in operation_execution.STAFF:
        raise HTTPException(403, "Only shop staff can edit the schedule")
    order = await operation_execution.load_order(db, order_id, actor, write=True)
    if not editable(order):
        error(409, "schedule_locked", "This order is read-only. Reopen the work before rescheduling it.")
    previous_version = utc(order.updated_at)
    if utc(body.expected_updated_at) != previous_version:
        error(409, "schedule_changed", "This order changed. Reload the saved schedule before trying again.")
    zone_name = await tenant_timezone(db, actor.tenant_id, required=True)
    if body.timezone != zone_name:
        error(409, "schedule_timezone_changed", "The shop timezone changed. Reload the schedule before saving.")
    zone = ZoneInfo(zone_name)
    start = resolve_wall(body.scheduled_start_local, body.scheduled_start_fold, zone, "scheduled_start_local")
    finish = resolve_wall(body.promised_finish_local, body.promised_finish_fold, zone, "promised_finish_local")
    if start is not None and finish is not None and finish <= start:
        error(422, "schedule_finish_before_start", "Promised finish must be after scheduled start.", field="promised_finish_local")
    previous = {"scheduled_start_at": utc(order.scheduled_start_at), "promised_finish_at": utc(order.promised_finish_at)}
    current = {"scheduled_start_at": start, "promised_finish_at": finish}
    if previous == current:
        return order, response(order, actor, zone_name), False
    stamp = max(now_utc(), previous_version + timedelta(microseconds=1))
    order.scheduled_start_at, order.promised_finish_at = start, finish
    order.updated_at = stamp
    db.add(RepairOrderHistoryEvent(
        tenant_id=order.tenant_id, repair_order_id=order.id,
        event_type="schedule_changed", label="Schedule updated",
        actor_user_id=actor.id, actor_name=actor_name(actor),
        detail=json.dumps({"previous": previous, "current": current, "timezone": zone_name},
                          default=lambda value: value.isoformat()),
    ))
    await db.flush()
    await db.refresh(order)
    return order, response(order, actor, zone_name), True
