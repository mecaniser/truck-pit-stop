from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.labor import Labor
from app.db.models.mechanic_time import (
    MechanicAttendanceAudit,
    MechanicAttendanceSession,
    MechanicBreakSession,
    MechanicIdleAlertStreak,
    MechanicSessionType,
    MechanicTimeSession,
    MechanicTimeSessionAudit,
    MiscWorkCategory,
)
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole


MISC_CATEGORIES = {m.value for m in MiscWorkCategory}
TIMER_STOP_REASONS = {
    "manual",
    "auto_switch",
    "auto_complete_work",
    "auto_midnight",
    "hold",
    "resume_from_hold",
    "clock_out",
    "break_start",
    "manager_control",
    "manager_edit",
    "manager_delete",
}

ATTENDANCE_END_SOURCES = {
    "manual_clock_out",
    "manager_clock_out",
    "auto_midnight",
}

BREAK_END_SOURCES = {
    "manual_break_end",
    "manager_break_end",
    "clock_out",
    "auto_midnight",
    "auto_timer_start",
}

SUGGESTED_NEXT_ACTIONS = {
    "clock_in",
    "end_break",
    "continue_ro",
    "stop_misc_pick_ro",
    "start_assigned_ro",
    "start_misc",
    "clock_out",
}


@dataclass
class DayWindow:
    timezone_name: str
    local_date: date
    day_start_local: datetime
    day_end_local: datetime
    day_start_utc: datetime
    day_end_utc: datetime


def _safe_zoneinfo(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("America/New_York")


def validate_timezone_name(tz_name: str) -> str:
    if not tz_name:
        raise ValueError("Timezone is required")
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Invalid timezone") from exc
    return tz_name


def validate_local_time_str(value: str) -> str:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        raise ValueError("Expected HH:MM time format")
    return value


def _parse_local_time(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def _manager_action_requires_reason(actor_role: str, manager_reason: Optional[str]) -> None:
    if actor_role in (UserRole.GARAGE_OWNER.value, UserRole.GARAGE_ADMIN.value):
        if not (manager_reason or "").strip():
            raise ValueError("Manager reason is required for this action")


def _session_snapshot(session: Optional[MechanicTimeSession]) -> Optional[dict[str, Any]]:
    if not session:
        return None
    misc_raw = getattr(session, "misc_category", None)
    misc_value = misc_raw.value if hasattr(misc_raw, "value") else (str(misc_raw) if misc_raw else None)
    return {
        "id": str(session.id),
        "tenant_id": str(session.tenant_id),
        "mechanic_id": str(session.mechanic_id),
        "repair_order_id": str(session.repair_order_id) if session.repair_order_id else None,
        "session_type": session.session_type.value if hasattr(session.session_type, "value") else str(session.session_type),
        "misc_category": misc_value,
        "note": session.note,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "started_by_user_id": str(session.started_by_user_id) if session.started_by_user_id else None,
        "stopped_by_user_id": str(session.stopped_by_user_id) if session.stopped_by_user_id else None,
        "stop_reason": session.stop_reason,
        "deleted_at": session.deleted_at.isoformat() if session.deleted_at else None,
    }


def _attendance_snapshot(session: Optional[MechanicAttendanceSession]) -> Optional[dict[str, Any]]:
    if not session:
        return None
    return {
        "id": str(session.id),
        "tenant_id": str(session.tenant_id),
        "mechanic_id": str(session.mechanic_id),
        "local_date": session.local_date.isoformat() if session.local_date else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "started_by_user_id": str(session.started_by_user_id) if session.started_by_user_id else None,
        "ended_by_user_id": str(session.ended_by_user_id) if session.ended_by_user_id else None,
        "start_source": session.start_source,
        "end_source": session.end_source,
        "note": session.note,
        "snapshot_timezone": session.snapshot_timezone,
        "snapshot_core_target_minutes": session.snapshot_core_target_minutes,
        "snapshot_shift_start_local": session.snapshot_shift_start_local,
        "snapshot_shift_end_local": session.snapshot_shift_end_local,
        "deleted_at": session.deleted_at.isoformat() if session.deleted_at else None,
    }


def _break_snapshot(session: Optional[MechanicBreakSession]) -> Optional[dict[str, Any]]:
    if not session:
        return None
    return {
        "id": str(session.id),
        "tenant_id": str(session.tenant_id),
        "mechanic_id": str(session.mechanic_id),
        "attendance_session_id": str(session.attendance_session_id),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "started_by_user_id": str(session.started_by_user_id) if session.started_by_user_id else None,
        "ended_by_user_id": str(session.ended_by_user_id) if session.ended_by_user_id else None,
        "start_source": session.start_source,
        "end_source": session.end_source,
        "note": session.note,
        "deleted_at": session.deleted_at.isoformat() if session.deleted_at else None,
    }


def _effective_core_target_minutes(mechanic: User, tenant: Tenant) -> int:
    if mechanic.core_hours_target_minutes_override and mechanic.core_hours_target_minutes_override > 0:
        return mechanic.core_hours_target_minutes_override
    return int(tenant.default_core_hours_minutes or 480)


def _effective_shift_window(mechanic: User, tenant: Tenant) -> tuple[str, str]:
    start = mechanic.shift_start_local_override or tenant.default_shift_start_local or "08:00"
    end = mechanic.shift_end_local_override or tenant.default_shift_end_local or "18:00"
    return start, end


def _compute_day_window(tz_name: str, target_date: Optional[date] = None) -> DayWindow:
    tz = _safe_zoneinfo(tz_name)
    now_local = datetime.now(tz)
    local_date = target_date or now_local.date()
    day_start_local = datetime.combine(local_date, time.min, tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    return DayWindow(
        timezone_name=tz_name,
        local_date=local_date,
        day_start_local=day_start_local,
        day_end_local=day_end_local,
        day_start_utc=day_start_local.astimezone(timezone.utc),
        day_end_utc=day_end_local.astimezone(timezone.utc),
    )


def _overlap_seconds(
    start: datetime,
    end: Optional[datetime],
    range_start: datetime,
    range_end: datetime,
    now_utc: Optional[datetime] = None,
) -> int:
    actual_end = end or now_utc or datetime.now(timezone.utc)
    if actual_end <= range_start or start >= range_end:
        return 0
    overlap_start = max(start, range_start)
    overlap_end = min(actual_end, range_end)
    if overlap_end <= overlap_start:
        return 0
    return int((overlap_end - overlap_start).total_seconds())


async def _create_audit(
    db: AsyncSession,
    *,
    tenant_id,
    session_id,
    mechanic_id,
    actor_user_id,
    actor_role: str,
    action: str,
    manager_reason: Optional[str] = None,
    before_snapshot: Optional[dict[str, Any]] = None,
    after_snapshot: Optional[dict[str, Any]] = None,
) -> MechanicTimeSessionAudit:
    audit = MechanicTimeSessionAudit(
        tenant_id=tenant_id,
        session_id=session_id,
        mechanic_id=mechanic_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        manager_reason=manager_reason,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
    )
    db.add(audit)
    return audit


async def _create_attendance_audit(
    db: AsyncSession,
    *,
    tenant_id,
    attendance_session_id=None,
    break_session_id=None,
    mechanic_id,
    actor_user_id,
    actor_role: str,
    action: str,
    manager_reason: Optional[str] = None,
    before_snapshot: Optional[dict[str, Any]] = None,
    after_snapshot: Optional[dict[str, Any]] = None,
) -> MechanicAttendanceAudit:
    audit = MechanicAttendanceAudit(
        tenant_id=tenant_id,
        attendance_session_id=attendance_session_id,
        break_session_id=break_session_id,
        mechanic_id=mechanic_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        manager_reason=manager_reason,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
    )
    db.add(audit)
    return audit


async def get_active_session(
    db: AsyncSession,
    *,
    tenant_id,
    mechanic_id,
) -> Optional[MechanicTimeSession]:
    result = await db.execute(
        select(MechanicTimeSession).where(
            and_(
                MechanicTimeSession.tenant_id == tenant_id,
                MechanicTimeSession.mechanic_id == mechanic_id,
                MechanicTimeSession.ended_at.is_(None),
                MechanicTimeSession.deleted_at.is_(None),
            )
        )
    )
    return result.scalar_one_or_none()


async def get_active_attendance_session(
    db: AsyncSession,
    *,
    tenant_id,
    mechanic_id,
) -> Optional[MechanicAttendanceSession]:
    result = await db.execute(
        select(MechanicAttendanceSession).where(
            and_(
                MechanicAttendanceSession.tenant_id == tenant_id,
                MechanicAttendanceSession.mechanic_id == mechanic_id,
                MechanicAttendanceSession.ended_at.is_(None),
                MechanicAttendanceSession.deleted_at.is_(None),
            )
        )
    )
    return result.scalar_one_or_none()


async def get_active_break_session(
    db: AsyncSession,
    *,
    tenant_id,
    mechanic_id,
) -> Optional[MechanicBreakSession]:
    result = await db.execute(
        select(MechanicBreakSession).where(
            and_(
                MechanicBreakSession.tenant_id == tenant_id,
                MechanicBreakSession.mechanic_id == mechanic_id,
                MechanicBreakSession.ended_at.is_(None),
                MechanicBreakSession.deleted_at.is_(None),
            )
        )
    )
    return result.scalar_one_or_none()


async def resolve_idle_streak(
    db: AsyncSession,
    *,
    tenant_id,
    mechanic_id,
    local_date: Optional[date] = None,
    resolved_at: Optional[datetime] = None,
) -> None:
    query = [
        MechanicIdleAlertStreak.tenant_id == tenant_id,
        MechanicIdleAlertStreak.mechanic_id == mechanic_id,
        MechanicIdleAlertStreak.is_active.is_(True),
        MechanicIdleAlertStreak.deleted_at.is_(None),
    ]
    if local_date is not None:
        query.append(MechanicIdleAlertStreak.local_date == local_date)
    result = await db.execute(select(MechanicIdleAlertStreak).where(and_(*query)))
    streaks = result.scalars().all()
    for streak in streaks:
        streak.is_active = False
        streak.resolved_at = resolved_at or datetime.now(timezone.utc)


@dataclass
class ClockOutResult:
    attendance_session: MechanicAttendanceSession
    stopped_timer_session: Optional[MechanicTimeSession]
    ended_break_session: Optional[MechanicBreakSession]


@dataclass
class BreakStartResult:
    break_session: MechanicBreakSession
    stopped_timer_session: Optional[MechanicTimeSession]


async def clock_in(
    db: AsyncSession,
    *,
    tenant: Tenant,
    mechanic: User,
    actor_user: User,
    note: Optional[str] = None,
    manager_reason: Optional[str] = None,
    started_at: Optional[datetime] = None,
    start_source: str = "manual_clock_in",
) -> MechanicAttendanceSession:
    _manager_action_requires_reason(actor_user.role.value, manager_reason)
    existing = await get_active_attendance_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
    )
    if existing:
        raise ValueError("Mechanic is already clocked in")

    now_utc = started_at or datetime.now(timezone.utc)
    tz_name = tenant.timezone or "America/New_York"
    tz = _safe_zoneinfo(tz_name)
    local_date = now_utc.astimezone(tz).date()
    shift_start_local, shift_end_local = _effective_shift_window(mechanic, tenant)

    session = MechanicAttendanceSession(
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        local_date=local_date,
        started_at=now_utc,
        started_by_user_id=actor_user.id,
        start_source=start_source,
        note=note,
        snapshot_timezone=tz_name,
        snapshot_core_target_minutes=_effective_core_target_minutes(mechanic, tenant),
        snapshot_shift_start_local=shift_start_local,
        snapshot_shift_end_local=shift_end_local,
    )
    db.add(session)
    await db.flush()

    await _create_attendance_audit(
        db,
        tenant_id=tenant.id,
        attendance_session_id=session.id,
        mechanic_id=mechanic.id,
        actor_user_id=actor_user.id,
        actor_role=actor_user.role.value,
        action="clock_in",
        manager_reason=manager_reason,
        before_snapshot=None,
        after_snapshot=_attendance_snapshot(session),
    )
    return session


async def ensure_attendance_started(
    db: AsyncSession,
    *,
    tenant: Tenant,
    mechanic: User,
    actor_user: User,
    manager_reason: Optional[str] = None,
    started_at: Optional[datetime] = None,
    start_source: str = "auto_first_timer",
) -> tuple[MechanicAttendanceSession, bool]:
    existing = await get_active_attendance_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
    )
    if existing:
        return existing, False
    session = await clock_in(
        db,
        tenant=tenant,
        mechanic=mechanic,
        actor_user=actor_user,
        manager_reason=manager_reason,
        started_at=started_at,
        start_source=start_source,
    )
    return session, True


async def end_active_break_session(
    db: AsyncSession,
    *,
    tenant_id,
    mechanic_id,
    actor_user: User,
    manager_reason: Optional[str] = None,
    note: Optional[str] = None,
    ended_at: Optional[datetime] = None,
    end_source: str = "manual_break_end",
) -> Optional[MechanicBreakSession]:
    if end_source not in BREAK_END_SOURCES:
        raise ValueError("Invalid break end source")
    _manager_action_requires_reason(actor_user.role.value, manager_reason)

    session = await get_active_break_session(
        db,
        tenant_id=tenant_id,
        mechanic_id=mechanic_id,
    )
    if not session:
        return None

    now_utc = ended_at or datetime.now(timezone.utc)
    before = _break_snapshot(session)
    session.ended_at = now_utc
    session.ended_by_user_id = actor_user.id
    session.end_source = end_source
    if note is not None:
        session.note = note

    await _create_attendance_audit(
        db,
        tenant_id=session.tenant_id,
        attendance_session_id=session.attendance_session_id,
        break_session_id=session.id,
        mechanic_id=session.mechanic_id,
        actor_user_id=actor_user.id,
        actor_role=actor_user.role.value,
        action="break_end",
        manager_reason=manager_reason,
        before_snapshot=before,
        after_snapshot=_break_snapshot(session),
    )
    return session


async def clock_out(
    db: AsyncSession,
    *,
    tenant: Tenant,
    mechanic: User,
    actor_user: User,
    note: Optional[str] = None,
    manager_reason: Optional[str] = None,
    ended_at: Optional[datetime] = None,
    end_source: str = "manual_clock_out",
) -> ClockOutResult:
    if end_source not in ATTENDANCE_END_SOURCES:
        raise ValueError("Invalid attendance end source")
    _manager_action_requires_reason(actor_user.role.value, manager_reason)

    attendance = await get_active_attendance_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
    )
    if not attendance:
        raise ValueError("Mechanic is not clocked in")

    now_utc = ended_at or datetime.now(timezone.utc)
    stopped_timer = await stop_active_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        actor_user=actor_user,
        stop_reason="clock_out",
        manager_reason=manager_reason,
        stopped_at=now_utc,
    )
    ended_break = await end_active_break_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        actor_user=actor_user,
        manager_reason=manager_reason,
        ended_at=now_utc,
        end_source="clock_out",
    )

    before = _attendance_snapshot(attendance)
    attendance.ended_at = now_utc
    attendance.ended_by_user_id = actor_user.id
    attendance.end_source = end_source
    if note is not None:
        attendance.note = note

    await _create_attendance_audit(
        db,
        tenant_id=attendance.tenant_id,
        attendance_session_id=attendance.id,
        mechanic_id=attendance.mechanic_id,
        actor_user_id=actor_user.id,
        actor_role=actor_user.role.value,
        action="clock_out",
        manager_reason=manager_reason,
        before_snapshot=before,
        after_snapshot=_attendance_snapshot(attendance),
    )
    await resolve_idle_streak(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        local_date=attendance.local_date,
        resolved_at=now_utc,
    )

    return ClockOutResult(
        attendance_session=attendance,
        stopped_timer_session=stopped_timer,
        ended_break_session=ended_break,
    )


async def start_break(
    db: AsyncSession,
    *,
    tenant: Tenant,
    mechanic: User,
    actor_user: User,
    note: Optional[str] = None,
    manager_reason: Optional[str] = None,
    started_at: Optional[datetime] = None,
    start_source: str = "manual_break_start",
) -> BreakStartResult:
    _manager_action_requires_reason(actor_user.role.value, manager_reason)

    attendance = await get_active_attendance_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
    )
    if not attendance:
        raise ValueError("Mechanic must be clocked in to start break")
    existing_break = await get_active_break_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
    )
    if existing_break:
        raise ValueError("Mechanic is already on break")

    now_utc = started_at or datetime.now(timezone.utc)
    stopped_timer = await stop_active_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        actor_user=actor_user,
        stop_reason="break_start",
        manager_reason=manager_reason,
        stopped_at=now_utc,
    )

    session = MechanicBreakSession(
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_session_id=attendance.id,
        started_at=now_utc,
        started_by_user_id=actor_user.id,
        start_source=start_source,
        note=note,
    )
    db.add(session)
    await db.flush()

    await _create_attendance_audit(
        db,
        tenant_id=tenant.id,
        attendance_session_id=attendance.id,
        break_session_id=session.id,
        mechanic_id=mechanic.id,
        actor_user_id=actor_user.id,
        actor_role=actor_user.role.value,
        action="break_start",
        manager_reason=manager_reason,
        before_snapshot=None,
        after_snapshot=_break_snapshot(session),
    )
    await resolve_idle_streak(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        local_date=attendance.local_date,
        resolved_at=now_utc,
    )

    return BreakStartResult(
        break_session=session,
        stopped_timer_session=stopped_timer,
    )


async def end_break(
    db: AsyncSession,
    *,
    tenant: Tenant,
    mechanic: User,
    actor_user: User,
    manager_reason: Optional[str] = None,
    note: Optional[str] = None,
    ended_at: Optional[datetime] = None,
    end_source: str = "manual_break_end",
) -> MechanicBreakSession:
    session = await end_active_break_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        actor_user=actor_user,
        manager_reason=manager_reason,
        note=note,
        ended_at=ended_at,
        end_source=end_source,
    )
    if not session:
        raise ValueError("Mechanic is not on break")
    return session


async def start_session(
    db: AsyncSession,
    *,
    tenant: Tenant,
    mechanic: User,
    actor_user: User,
    session_type: str,
    repair_order_id=None,
    misc_category: Optional[str] = None,
    note: Optional[str] = None,
    manager_reason: Optional[str] = None,
    started_at: Optional[datetime] = None,
    stop_previous_reason: str = "auto_switch",
) -> tuple[MechanicTimeSession, bool, str]:
    if session_type not in {MechanicSessionType.REPAIR_ORDER.value, MechanicSessionType.MISC.value}:
        raise ValueError("Invalid session type")
    if session_type == MechanicSessionType.REPAIR_ORDER.value and not repair_order_id:
        raise ValueError("repair_order_id is required for repair_order sessions")
    if session_type == MechanicSessionType.MISC.value:
        if misc_category and misc_category not in MISC_CATEGORIES:
            raise ValueError("Invalid misc category")
    else:
        misc_category = None
    _manager_action_requires_reason(actor_user.role.value, manager_reason)

    now_utc = started_at or datetime.now(timezone.utc)
    attendance_session, auto_clocked_in = await ensure_attendance_started(
        db,
        tenant=tenant,
        mechanic=mechanic,
        actor_user=actor_user,
        manager_reason=manager_reason,
        started_at=now_utc,
        start_source="auto_first_timer",
    )
    active_break = await get_active_break_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
    )
    if active_break:
        await end_active_break_session(
            db,
            tenant_id=tenant.id,
            mechanic_id=mechanic.id,
            actor_user=actor_user,
            manager_reason=manager_reason,
            ended_at=now_utc,
            end_source="auto_timer_start",
        )

    current = await get_active_session(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
    )
    if current:
        await stop_active_session(
            db,
            tenant_id=tenant.id,
            mechanic_id=mechanic.id,
            actor_user=actor_user,
            stop_reason=stop_previous_reason,
            manager_reason=manager_reason,
            stopped_at=now_utc,
        )

    session = MechanicTimeSession(
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        repair_order_id=repair_order_id,
        session_type=session_type,
        misc_category=misc_category,
        note=note,
        started_at=now_utc,
        started_by_user_id=actor_user.id,
    )
    db.add(session)
    await db.flush()

    await _create_audit(
        db,
        tenant_id=tenant.id,
        session_id=session.id,
        mechanic_id=mechanic.id,
        actor_user_id=actor_user.id,
        actor_role=actor_user.role.value,
        action="start",
        manager_reason=manager_reason,
        before_snapshot=None,
        after_snapshot=_session_snapshot(session),
    )

    day_window = _compute_day_window(tenant.timezone or "America/New_York")
    await resolve_idle_streak(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        local_date=day_window.local_date,
        resolved_at=now_utc,
    )
    return session, auto_clocked_in, str(attendance_session.id)


async def stop_active_session(
    db: AsyncSession,
    *,
    tenant_id,
    mechanic_id,
    actor_user: User,
    stop_reason: str = "manual",
    manager_reason: Optional[str] = None,
    stopped_at: Optional[datetime] = None,
) -> Optional[MechanicTimeSession]:
    if stop_reason not in TIMER_STOP_REASONS:
        raise ValueError("Invalid stop reason")
    _manager_action_requires_reason(actor_user.role.value, manager_reason)

    session = await get_active_session(
        db,
        tenant_id=tenant_id,
        mechanic_id=mechanic_id,
    )
    if not session:
        return None

    now_utc = stopped_at or datetime.now(timezone.utc)
    before = _session_snapshot(session)
    session.ended_at = now_utc
    session.stopped_by_user_id = actor_user.id
    session.stop_reason = stop_reason

    await _create_audit(
        db,
        tenant_id=session.tenant_id,
        session_id=session.id,
        mechanic_id=session.mechanic_id,
        actor_user_id=actor_user.id,
        actor_role=actor_user.role.value,
        action="stop",
        manager_reason=manager_reason,
        before_snapshot=before,
        after_snapshot=_session_snapshot(session),
    )
    return session


async def edit_session(
    db: AsyncSession,
    *,
    session: MechanicTimeSession,
    actor_user: User,
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None,
    note: Optional[str] = None,
    misc_category: Optional[str] = None,
    manager_reason: Optional[str] = None,
) -> MechanicTimeSession:
    _manager_action_requires_reason(actor_user.role.value, manager_reason)
    before = _session_snapshot(session)

    if misc_category is not None:
        if misc_category and misc_category not in MISC_CATEGORIES:
            raise ValueError("Invalid misc category")
        session.misc_category = misc_category
    if started_at is not None:
        session.started_at = started_at
    if ended_at is not None:
        session.ended_at = ended_at
    if note is not None:
        session.note = note

    if session.ended_at and session.ended_at <= session.started_at:
        raise ValueError("ended_at must be greater than started_at")

    await _create_audit(
        db,
        tenant_id=session.tenant_id,
        session_id=session.id,
        mechanic_id=session.mechanic_id,
        actor_user_id=actor_user.id,
        actor_role=actor_user.role.value,
        action="edit",
        manager_reason=manager_reason,
        before_snapshot=before,
        after_snapshot=_session_snapshot(session),
    )
    return session


async def delete_session(
    db: AsyncSession,
    *,
    session: MechanicTimeSession,
    actor_user: User,
    manager_reason: Optional[str] = None,
    deleted_at: Optional[datetime] = None,
) -> MechanicTimeSession:
    _manager_action_requires_reason(actor_user.role.value, manager_reason)
    before = _session_snapshot(session)

    now_utc = deleted_at or datetime.now(timezone.utc)
    if session.ended_at is None:
        session.ended_at = now_utc
        session.stopped_by_user_id = actor_user.id
        session.stop_reason = "manager_delete"
    session.deleted_at = now_utc

    await _create_audit(
        db,
        tenant_id=session.tenant_id,
        session_id=session.id,
        mechanic_id=session.mechanic_id,
        actor_user_id=actor_user.id,
        actor_role=actor_user.role.value,
        action="delete",
        manager_reason=manager_reason,
        before_snapshot=before,
        after_snapshot=_session_snapshot(session),
    )
    return session


async def _compute_book_hours_for_orders(
    db: AsyncSession,
    *,
    order_ids: list,
) -> float:
    if not order_ids:
        return 0.0
    order_ids_unique = list(set(order_ids))

    labor_result = await db.execute(
        select(
            Labor.repair_order_id,
            func.coalesce(func.sum(Labor.hours), 0),
        )
        .where(Labor.repair_order_id.in_(order_ids_unique))
        .group_by(Labor.repair_order_id)
    )
    labor_by_order = {
        row[0]: float(row[1] or 0)
        for row in labor_result.all()
    }

    missing_orders = [oid for oid in order_ids_unique if labor_by_order.get(oid, 0) <= 0]
    if missing_orders:
        ro_result = await db.execute(
            select(RepairOrder.id, RepairOrder.internal_notes).where(RepairOrder.id.in_(missing_orders))
        )
        for order_id, internal_notes in ro_result.all():
            fallback_hours = 0.0
            if internal_notes:
                try:
                    parsed = json.loads(internal_notes)
                    selected_services = parsed.get("selected_services", [])
                    for svc in selected_services:
                        duration_minutes = svc.get("duration_minutes")
                        if duration_minutes:
                            fallback_hours += float(duration_minutes) / 60.0
                except Exception:
                    fallback_hours = 0.0
            labor_by_order[order_id] = fallback_hours

    return float(sum(labor_by_order.values()))


def _clip_interval(
    start: datetime,
    end: Optional[datetime],
    range_start: datetime,
    range_end: datetime,
    now_utc: Optional[datetime] = None,
) -> Optional[tuple[datetime, datetime]]:
    actual_end = end or now_utc or datetime.now(timezone.utc)
    clipped_start = max(start, range_start)
    clipped_end = min(actual_end, range_end)
    if clipped_end <= clipped_start:
        return None
    return clipped_start, clipped_end


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda item: item[0])
    merged: list[tuple[datetime, datetime]] = [ordered[0]]
    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _sum_interval_seconds(intervals: list[tuple[datetime, datetime]]) -> int:
    return int(sum((end - start).total_seconds() for start, end in intervals))


def _sum_overlap_seconds(
    base_interval: tuple[datetime, datetime],
    intervals: list[tuple[datetime, datetime]],
) -> int:
    if not intervals:
        return 0
    base_start, base_end = base_interval
    total = 0
    for start, end in intervals:
        overlap_start = max(base_start, start)
        overlap_end = min(base_end, end)
        if overlap_end > overlap_start:
            total += int((overlap_end - overlap_start).total_seconds())
    return total


async def compute_day_summary(
    db: AsyncSession,
    *,
    tenant: Tenant,
    mechanic: User,
    target_date: Optional[date] = None,
    now_utc: Optional[datetime] = None,
) -> dict[str, Any]:
    now = now_utc or datetime.now(timezone.utc)
    window = _compute_day_window(tenant.timezone or "America/New_York", target_date)
    tz = _safe_zoneinfo(tenant.timezone or "America/New_York")
    shift_start_raw, shift_end_raw = _effective_shift_window(mechanic, tenant)
    shift_start_local = datetime.combine(window.local_date, _parse_local_time(shift_start_raw), tzinfo=tz)
    shift_end_local = datetime.combine(window.local_date, _parse_local_time(shift_end_raw), tzinfo=tz)
    shift_start_utc = shift_start_local.astimezone(timezone.utc)
    shift_end_utc = shift_end_local.astimezone(timezone.utc)

    result = await db.execute(
        select(MechanicTimeSession).where(
            and_(
                MechanicTimeSession.tenant_id == tenant.id,
                MechanicTimeSession.mechanic_id == mechanic.id,
                MechanicTimeSession.deleted_at.is_(None),
                MechanicTimeSession.started_at < window.day_end_utc,
                or_(
                    MechanicTimeSession.ended_at.is_(None),
                    MechanicTimeSession.ended_at > window.day_start_utc,
                ),
            )
        )
    )
    sessions = result.scalars().all()
    tracked_seconds = 0
    ro_seconds = 0
    misc_seconds = 0
    order_ids: list[Any] = []
    active_session = None
    timer_intervals: list[tuple[datetime, datetime]] = []

    for session in sessions:
        if session.ended_at is None:
            active_session = session
        clipped = _clip_interval(
            session.started_at,
            session.ended_at,
            window.day_start_utc,
            window.day_end_utc,
            now_utc=now,
        )
        if not clipped:
            continue
        interval_seconds = int((clipped[1] - clipped[0]).total_seconds())
        timer_intervals.append(clipped)
        tracked_seconds += interval_seconds
        if session.session_type == MechanicSessionType.REPAIR_ORDER.value:
            ro_seconds += interval_seconds
            if session.repair_order_id:
                order_ids.append(session.repair_order_id)
        else:
            misc_seconds += interval_seconds

    attendance_result = await db.execute(
        select(MechanicAttendanceSession).where(
            and_(
                MechanicAttendanceSession.tenant_id == tenant.id,
                MechanicAttendanceSession.mechanic_id == mechanic.id,
                MechanicAttendanceSession.deleted_at.is_(None),
                MechanicAttendanceSession.started_at < window.day_end_utc,
                or_(
                    MechanicAttendanceSession.ended_at.is_(None),
                    MechanicAttendanceSession.ended_at > window.day_start_utc,
                ),
            )
        )
    )
    attendance_sessions = attendance_result.scalars().all()
    attendance_intervals: list[tuple[datetime, datetime]] = []
    active_attendance = None
    first_attendance_start: Optional[datetime] = None
    last_attendance_end: Optional[datetime] = None
    for attendance in attendance_sessions:
        if attendance.ended_at is None:
            active_attendance = attendance
        clipped = _clip_interval(
            attendance.started_at,
            attendance.ended_at,
            window.day_start_utc,
            window.day_end_utc,
            now_utc=now,
        )
        if not clipped:
            continue
        attendance_intervals.append(clipped)
        first_attendance_start = clipped[0] if first_attendance_start is None else min(first_attendance_start, clipped[0])
        last_attendance_end = clipped[1] if last_attendance_end is None else max(last_attendance_end, clipped[1])
    attendance_intervals = _merge_intervals(attendance_intervals)
    attendance_seconds = _sum_interval_seconds(attendance_intervals)

    break_result = await db.execute(
        select(MechanicBreakSession).where(
            and_(
                MechanicBreakSession.tenant_id == tenant.id,
                MechanicBreakSession.mechanic_id == mechanic.id,
                MechanicBreakSession.deleted_at.is_(None),
                MechanicBreakSession.started_at < window.day_end_utc,
                or_(
                    MechanicBreakSession.ended_at.is_(None),
                    MechanicBreakSession.ended_at > window.day_start_utc,
                ),
            )
        )
    )
    break_sessions = break_result.scalars().all()
    break_intervals: list[tuple[datetime, datetime]] = []
    active_break = None
    for break_session in break_sessions:
        if break_session.ended_at is None:
            active_break = break_session
        clipped = _clip_interval(
            break_session.started_at,
            break_session.ended_at,
            window.day_start_utc,
            window.day_end_utc,
            now_utc=now,
        )
        if not clipped:
            continue
        break_intervals.append(clipped)
    break_intervals = _merge_intervals(break_intervals)
    break_seconds = _sum_interval_seconds(break_intervals)

    merged_cover = _merge_intervals(timer_intervals + break_intervals)
    idle_seconds = 0
    for interval in attendance_intervals:
        interval_seconds = int((interval[1] - interval[0]).total_seconds())
        covered_seconds = _sum_overlap_seconds(interval, merged_cover)
        idle_seconds += max(interval_seconds - covered_seconds, 0)

    core_target_minutes = _effective_core_target_minutes(mechanic, tenant)
    core_target_seconds = max(core_target_minutes, 1) * 60
    utilization = min((tracked_seconds / core_target_seconds) * 100.0, 100.0)
    overtime_seconds = max(tracked_seconds - core_target_seconds, 0)
    actual_ro_hours = ro_seconds / 3600.0
    book_hours = await _compute_book_hours_for_orders(db, order_ids=order_ids)
    efficiency = None
    if actual_ro_hours > 0 and book_hours > 0:
        efficiency = round((book_hours / actual_ro_hours) * 100.0, 2)

    shift_duration_seconds = max(int((shift_end_utc - shift_start_utc).total_seconds()), 0)
    flex_budget_minutes = max((shift_duration_seconds // 60) - core_target_minutes, 0)

    late_arrival_seconds = 0
    if first_attendance_start and first_attendance_start > shift_start_utc:
        late_arrival_seconds = int((first_attendance_start - shift_start_utc).total_seconds())
    elif not first_attendance_start and now > shift_start_utc:
        late_arrival_seconds = int((min(now, shift_end_utc) - shift_start_utc).total_seconds()) if shift_end_utc > shift_start_utc else 0

    early_leave_seconds = 0
    if last_attendance_end:
        if last_attendance_end < shift_end_utc and (not active_attendance):
            cutoff = min(now, shift_end_utc)
            if cutoff > last_attendance_end:
                early_leave_seconds = int((cutoff - last_attendance_end).total_seconds())

    flex_used_minutes = int((late_arrival_seconds + early_leave_seconds + break_seconds + idle_seconds) // 60)
    flex_remaining_minutes = max(flex_budget_minutes - flex_used_minutes, 0)
    flex_overrun_minutes = max(flex_used_minutes - flex_budget_minutes, 0)
    core_gap_minutes = max(core_target_minutes - int(tracked_seconds // 60), 0)
    attendance_minutes_int = int(attendance_seconds // 60)
    tracked_minutes_int = int(tracked_seconds // 60)
    core_countdown_elapsed_minutes = min(attendance_minutes_int, core_target_minutes)
    core_countdown_remaining_minutes = max(core_target_minutes - attendance_minutes_int, 0)
    tracked_vs_attendance_gap_minutes = max(attendance_minutes_int - tracked_minutes_int, 0)
    work_coverage_percent = round((tracked_minutes_int / attendance_minutes_int) * 100.0, 1) if attendance_minutes_int > 0 else None

    return {
        "date": window.local_date.isoformat(),
        "timezone": tenant.timezone or "America/New_York",
        "shift_start_local": shift_start_raw,
        "shift_end_local": shift_end_raw,
        "core_target_minutes": core_target_minutes,
        "tracked_minutes": tracked_minutes_int,
        "ro_minutes": int(ro_seconds // 60),
        "misc_minutes": int(misc_seconds // 60),
        "overtime_minutes": int(overtime_seconds // 60),
        "utilization_percent": round(utilization, 2),
        "efficiency_percent": efficiency,
        "book_hours": round(book_hours, 2),
        "actual_ro_hours": round(actual_ro_hours, 2),
        "active_session": _session_snapshot(active_session),
        "attendance_active": active_attendance is not None,
        "attendance_started_at": active_attendance.started_at.isoformat() if active_attendance else (first_attendance_start.isoformat() if first_attendance_start else None),
        "attendance_ended_at": None if active_attendance else (last_attendance_end.isoformat() if last_attendance_end else None),
        "break_active": active_break is not None,
        "break_started_at": active_break.started_at.isoformat() if active_break else None,
        "attendance_minutes": attendance_minutes_int,
        "break_minutes": int(break_seconds // 60),
        "idle_minutes": int(idle_seconds // 60),
        "late_arrival_minutes": int(max(late_arrival_seconds, 0) // 60),
        "early_leave_minutes": int(max(early_leave_seconds, 0) // 60),
        "flex_budget_minutes": int(flex_budget_minutes),
        "flex_used_minutes": int(flex_used_minutes),
        "flex_remaining_minutes": int(flex_remaining_minutes),
        "flex_overrun_minutes": int(flex_overrun_minutes),
        "core_gap_minutes": int(core_gap_minutes),
        "core_countdown_elapsed_minutes": int(core_countdown_elapsed_minutes),
        "core_countdown_remaining_minutes": int(core_countdown_remaining_minutes),
        "tracked_vs_attendance_gap_minutes": int(tracked_vs_attendance_gap_minutes),
        "work_coverage_percent": work_coverage_percent,
    }


def _status_value(status: Any) -> str:
    if hasattr(status, "value"):
        return status.value
    return str(status)


def _oldest_order_first_key(order: RepairOrder) -> datetime:
    return order.updated_at or order.created_at or datetime.min.replace(tzinfo=timezone.utc)


async def compute_next_action_recommendation(
    db: AsyncSession,
    *,
    tenant_id,
    mechanic_id,
    attendance_active: bool,
    break_active: bool,
    active_session: Optional[dict[str, Any]],
    core_countdown_remaining_minutes: Optional[int] = None,
    prefetched_orders: Optional[list[RepairOrder]] = None,
) -> dict[str, Any]:
    # Keep logic in sync with frontend recommendation derivation used in MechanicPortalPage.
    if prefetched_orders is None:
        ro_result = await db.execute(
            select(RepairOrder).where(
                and_(
                    RepairOrder.tenant_id == tenant_id,
                    RepairOrder.assigned_mechanic_id == mechanic_id,
                    RepairOrder.deleted_at.is_(None),
                    RepairOrder.status.in_(
                        [
                            RepairOrderStatus.ASSIGNED,
                            RepairOrderStatus.ACKNOWLEDGED,
                            RepairOrderStatus.IN_PROGRESS,
                        ]
                    ),
                )
            )
        )
        orders = ro_result.scalars().all()
    else:
        orders = prefetched_orders

    active_session_type = (active_session or {}).get("session_type")
    active_ro_id = str((active_session or {}).get("repair_order_id")) if (active_session or {}).get("repair_order_id") else None

    assigned_ready_orders = sorted(
        [
            order
            for order in orders
            if _status_value(order.status) in (RepairOrderStatus.ASSIGNED.value, RepairOrderStatus.ACKNOWLEDGED.value)
        ],
        key=lambda order: (
            0 if _status_value(order.status) == RepairOrderStatus.ACKNOWLEDGED.value else 1,
            _oldest_order_first_key(order),
        ),
    )
    untimed_in_progress_orders = sorted(
        [
            order
            for order in orders
            if _status_value(order.status) == RepairOrderStatus.IN_PROGRESS.value
            and str(order.id) != active_ro_id
            and not getattr(order, "hold_reason", None)  # exclude held ROs
        ],
        key=_oldest_order_first_key,
    )
    orders_by_id = {str(order.id): order for order in orders}

    suggested_next_action = "start_misc"
    recommended_order: Optional[RepairOrder] = None

    if not attendance_active:
        suggested_next_action = "clock_in"
    elif break_active:
        suggested_next_action = "end_break"
    elif active_session_type == MechanicSessionType.REPAIR_ORDER.value:
        suggested_next_action = "continue_ro"
        if active_ro_id:
            recommended_order = orders_by_id.get(active_ro_id)
    elif active_session_type == MechanicSessionType.MISC.value and assigned_ready_orders:
        suggested_next_action = "stop_misc_pick_ro"
        recommended_order = assigned_ready_orders[0]
    elif not active_session and untimed_in_progress_orders:
        suggested_next_action = "start_assigned_ro"
        recommended_order = untimed_in_progress_orders[0]
    elif not active_session and assigned_ready_orders:
        suggested_next_action = "start_assigned_ro"
        recommended_order = assigned_ready_orders[0]
    elif (
        not active_session
        and not untimed_in_progress_orders
        and not assigned_ready_orders
        and core_countdown_remaining_minutes is not None
        and core_countdown_remaining_minutes <= 0
    ):
        suggested_next_action = "clock_out"
    else:
        suggested_next_action = "start_misc"

    if suggested_next_action not in SUGGESTED_NEXT_ACTIONS:
        suggested_next_action = "start_misc"

    held_orders = sorted(
        [
            order
            for order in orders
            if _status_value(order.status) == RepairOrderStatus.IN_PROGRESS.value
            and getattr(order, "hold_reason", None)
        ],
        key=_oldest_order_first_key,
    )
    held_orders_count = len(held_orders)

    return {
        "assigned_ready_orders_count": len(assigned_ready_orders),
        "untimed_in_progress_orders_count": len(untimed_in_progress_orders),
        "held_orders_count": held_orders_count,
        "held_orders": [
            {
                "id": str(order.id),
                "order_number": order.order_number,
                "hold_reason": order.hold_reason,
                "held_at": order.held_at.isoformat() if getattr(order, "held_at", None) else None,
            }
            for order in held_orders
        ],
        "recommended_order_id": str(recommended_order.id) if recommended_order else None,
        "recommended_order_number": recommended_order.order_number if recommended_order else None,
        "suggested_next_action": suggested_next_action,
    }


ATTENTION_PRIORITY_RED = "red"
ATTENTION_PRIORITY_YELLOW = "yellow"
ATTENTION_PRIORITY_GREEN = "green"

ATTENTION_REASON_LABELS: dict[str, str] = {
    "idle_extended": "Idle over 15 min — no active timer",
    "untimed_in_progress": "In-progress RO has no timer running",
    "clocked_out_during_shift": "Clocked out during shift window",
    "misc_with_ro_waiting": "On misc timer with assigned RO waiting",
    "break_extended": "On break over 20 min",
    "low_coverage": "Work coverage below 60%",
    "ro_on_hold": "Repair order on hold",
}


def compute_attention_priority(
    *,
    summary: dict[str, Any],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    """Derive a red/yellow/green attention priority from already-computed summary + recommendation.

    No DB access needed — purely derived from the two dicts.
    """
    reasons: list[str] = []
    attendance_active = bool(summary.get("attendance_active"))
    break_active = bool(summary.get("break_active"))
    idle_minutes = int(summary.get("idle_minutes") or 0)
    attendance_minutes = int(summary.get("attendance_minutes") or 0)
    work_coverage = summary.get("work_coverage_percent")
    active_session = summary.get("active_session")
    core_countdown_remaining = int(summary.get("core_countdown_remaining_minutes") or 0)
    suggested = recommendation.get("suggested_next_action", "start_misc")
    untimed_count = int(recommendation.get("untimed_in_progress_orders_count") or 0)
    break_minutes = int(summary.get("break_minutes") or 0)

    # --- Red conditions ---
    # Clocked out during shift (has core time remaining, never clocked in or already clocked out)
    if not attendance_active and core_countdown_remaining > 0:
        reasons.append("clocked_out_during_shift")

    # Idle > 15 min (clocked in, no active timer, not on break)
    if attendance_active and not break_active and not active_session and idle_minutes >= 15:
        reasons.append("idle_extended")

    # Untimed in-progress RO (work is happening without time tracking)
    if untimed_count > 0:
        reasons.append("untimed_in_progress")

    if reasons:
        return {
            "attention_priority": ATTENTION_PRIORITY_RED,
            "attention_reasons": reasons,
        }

    # --- Yellow conditions ---
    held_count = int(recommendation.get("held_orders_count") or 0)
    if held_count > 0:
        reasons.append("ro_on_hold")

    if suggested == "stop_misc_pick_ro":
        reasons.append("misc_with_ro_waiting")

    if break_active and break_minutes >= 20:
        reasons.append("break_extended")

    if attendance_active and attendance_minutes >= 15 and work_coverage is not None and work_coverage < 60.0:
        reasons.append("low_coverage")

    if reasons:
        return {
            "attention_priority": ATTENTION_PRIORITY_YELLOW,
            "attention_reasons": reasons,
        }

    return {
        "attention_priority": ATTENTION_PRIORITY_GREEN,
        "attention_reasons": [],
    }


async def compute_7day_trend(
    db: AsyncSession,
    *,
    tenant: Tenant,
    mechanic: User,
    end_date: Optional[date] = None,
) -> list[dict[str, Any]]:
    tz = _safe_zoneinfo(tenant.timezone or "America/New_York")
    end_local_date = end_date or datetime.now(tz).date()
    out: list[dict[str, Any]] = []
    for delta in range(6, -1, -1):
        d = end_local_date - timedelta(days=delta)
        summary = await compute_day_summary(
            db,
            tenant=tenant,
            mechanic=mechanic,
            target_date=d,
        )
        out.append(summary)
    return out


async def fetch_tenant_and_mechanic(
    db: AsyncSession,
    *,
    tenant_id,
    mechanic_id,
) -> tuple[Tenant, User]:
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise ValueError("Tenant not found")
    mech_result = await db.execute(
        select(User).where(
            and_(
                User.id == mechanic_id,
                User.tenant_id == tenant_id,
                User.role == UserRole.MECHANIC,
            )
        )
    )
    mechanic = mech_result.scalar_one_or_none()
    if not mechanic:
        raise ValueError("Mechanic not found")
    return tenant, mechanic


async def close_sessions_crossing_midnight(
    db: AsyncSession,
    *,
    now_utc: Optional[datetime] = None,
) -> list[MechanicTimeSession]:
    now = now_utc or datetime.now(timezone.utc)
    result = await db.execute(
        select(MechanicTimeSession, Tenant)
        .join(Tenant, Tenant.id == MechanicTimeSession.tenant_id)
        .where(
            and_(
                MechanicTimeSession.ended_at.is_(None),
                MechanicTimeSession.deleted_at.is_(None),
            )
        )
    )
    rows = result.all()
    closed: list[MechanicTimeSession] = []

    for session, tenant in rows:
        tz = _safe_zoneinfo(tenant.timezone or "America/New_York")
        start_local = session.started_at.astimezone(tz)
        now_local = now.astimezone(tz)
        midnight_local = datetime.combine(start_local.date() + timedelta(days=1), time.min, tzinfo=tz)
        if now_local < midnight_local:
            continue
        midnight_utc = midnight_local.astimezone(timezone.utc)
        if midnight_utc <= session.started_at:
            continue
        before = _session_snapshot(session)
        session.ended_at = midnight_utc
        session.stop_reason = "auto_midnight"
        session.stopped_by_user_id = None
        await _create_audit(
            db,
            tenant_id=session.tenant_id,
            session_id=session.id,
            mechanic_id=session.mechanic_id,
            actor_user_id=session.mechanic_id,
            actor_role=UserRole.MECHANIC.value,
            action="auto_midnight_stop",
            manager_reason=None,
            before_snapshot=before,
            after_snapshot=_session_snapshot(session),
        )
        closed.append(session)
    return closed


async def close_breaks_crossing_midnight(
    db: AsyncSession,
    *,
    now_utc: Optional[datetime] = None,
) -> list[MechanicBreakSession]:
    now = now_utc or datetime.now(timezone.utc)
    result = await db.execute(
        select(MechanicBreakSession, Tenant)
        .join(Tenant, Tenant.id == MechanicBreakSession.tenant_id)
        .where(
            and_(
                MechanicBreakSession.ended_at.is_(None),
                MechanicBreakSession.deleted_at.is_(None),
            )
        )
    )
    rows = result.all()
    closed: list[MechanicBreakSession] = []
    for session, tenant in rows:
        tz = _safe_zoneinfo(tenant.timezone or "America/New_York")
        start_local = session.started_at.astimezone(tz)
        now_local = now.astimezone(tz)
        midnight_local = datetime.combine(start_local.date() + timedelta(days=1), time.min, tzinfo=tz)
        if now_local < midnight_local:
            continue
        midnight_utc = midnight_local.astimezone(timezone.utc)
        if midnight_utc <= session.started_at:
            continue
        before = _break_snapshot(session)
        session.ended_at = midnight_utc
        session.ended_by_user_id = session.mechanic_id
        session.end_source = "auto_midnight"
        await _create_attendance_audit(
            db,
            tenant_id=session.tenant_id,
            attendance_session_id=session.attendance_session_id,
            break_session_id=session.id,
            mechanic_id=session.mechanic_id,
            actor_user_id=session.mechanic_id,
            actor_role=UserRole.MECHANIC.value,
            action="auto_midnight_break_end",
            before_snapshot=before,
            after_snapshot=_break_snapshot(session),
        )
        closed.append(session)
    return closed


async def close_attendance_crossing_midnight(
    db: AsyncSession,
    *,
    now_utc: Optional[datetime] = None,
) -> list[MechanicAttendanceSession]:
    now = now_utc or datetime.now(timezone.utc)
    result = await db.execute(
        select(MechanicAttendanceSession, Tenant)
        .join(Tenant, Tenant.id == MechanicAttendanceSession.tenant_id)
        .where(
            and_(
                MechanicAttendanceSession.ended_at.is_(None),
                MechanicAttendanceSession.deleted_at.is_(None),
            )
        )
    )
    rows = result.all()
    closed: list[MechanicAttendanceSession] = []
    for session, tenant in rows:
        tz = _safe_zoneinfo(tenant.timezone or "America/New_York")
        start_local = session.started_at.astimezone(tz)
        now_local = now.astimezone(tz)
        midnight_local = datetime.combine(start_local.date() + timedelta(days=1), time.min, tzinfo=tz)
        if now_local < midnight_local:
            continue
        midnight_utc = midnight_local.astimezone(timezone.utc)
        if midnight_utc <= session.started_at:
            continue
        before = _attendance_snapshot(session)
        session.ended_at = midnight_utc
        session.ended_by_user_id = session.mechanic_id
        session.end_source = "auto_midnight"
        await _create_attendance_audit(
            db,
            tenant_id=session.tenant_id,
            attendance_session_id=session.id,
            mechanic_id=session.mechanic_id,
            actor_user_id=session.mechanic_id,
            actor_role=UserRole.MECHANIC.value,
            action="auto_midnight_clock_out",
            before_snapshot=before,
            after_snapshot=_attendance_snapshot(session),
        )
        closed.append(session)
    return closed


async def evaluate_idle_alerts(
    db: AsyncSession,
    *,
    now_utc: Optional[datetime] = None,
    threshold_minutes: int = 30,
) -> list[dict[str, Any]]:
    now = now_utc or datetime.now(timezone.utc)
    mech_result = await db.execute(
        select(User, Tenant)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(
            and_(
                User.role == UserRole.MECHANIC,
                User.is_active.is_(True),
                User.tenant_id.is_not(None),
            )
        )
    )
    rows = mech_result.all()
    alerts: list[dict[str, Any]] = []

    for mechanic, tenant in rows:
        tz = _safe_zoneinfo(tenant.timezone or "America/New_York")
        now_local = now.astimezone(tz)
        local_date = now_local.date()

        shift_start_raw, shift_end_raw = _effective_shift_window(mechanic, tenant)
        shift_start = datetime.combine(local_date, _parse_local_time(shift_start_raw), tzinfo=tz)
        shift_end = datetime.combine(local_date, _parse_local_time(shift_end_raw), tzinfo=tz)
        if shift_start >= shift_end:
            await resolve_idle_streak(
                db,
                tenant_id=tenant.id,
                mechanic_id=mechanic.id,
                local_date=local_date,
                resolved_at=now,
            )
            continue

        # Outside monitoring window
        if not (shift_start <= now_local <= shift_end):
            await resolve_idle_streak(
                db,
                tenant_id=tenant.id,
                mechanic_id=mechanic.id,
                local_date=local_date,
                resolved_at=now,
            )
            continue

        active_attendance = await get_active_attendance_session(
            db,
            tenant_id=tenant.id,
            mechanic_id=mechanic.id,
        )
        if not active_attendance:
            await resolve_idle_streak(
                db,
                tenant_id=tenant.id,
                mechanic_id=mechanic.id,
                local_date=local_date,
                resolved_at=now,
            )
            continue

        active_break = await get_active_break_session(
            db,
            tenant_id=tenant.id,
            mechanic_id=mechanic.id,
        )
        if active_break:
            await resolve_idle_streak(
                db,
                tenant_id=tenant.id,
                mechanic_id=mechanic.id,
                local_date=local_date,
                resolved_at=now,
            )
            continue

        summary = await compute_day_summary(
            db,
            tenant=tenant,
            mechanic=mechanic,
            target_date=local_date,
            now_utc=now,
        )
        if summary["tracked_minutes"] >= summary["core_target_minutes"]:
            await resolve_idle_streak(
                db,
                tenant_id=tenant.id,
                mechanic_id=mechanic.id,
                local_date=local_date,
                resolved_at=now,
            )
            continue

        active = await get_active_session(
            db,
            tenant_id=tenant.id,
            mechanic_id=mechanic.id,
        )
        if active:
            await resolve_idle_streak(
                db,
                tenant_id=tenant.id,
                mechanic_id=mechanic.id,
                local_date=local_date,
                resolved_at=now,
            )
            continue

        day_window = _compute_day_window(tenant.timezone or "America/New_York", local_date)
        last_end_result = await db.execute(
            select(func.max(MechanicTimeSession.ended_at)).where(
                and_(
                    MechanicTimeSession.tenant_id == tenant.id,
                    MechanicTimeSession.mechanic_id == mechanic.id,
                    MechanicTimeSession.deleted_at.is_(None),
                    MechanicTimeSession.ended_at.is_not(None),
                    MechanicTimeSession.ended_at >= day_window.day_start_utc,
                    MechanicTimeSession.ended_at <= now,
                )
            )
        )
        last_end = last_end_result.scalar()
        last_break_end_result = await db.execute(
            select(func.max(MechanicBreakSession.ended_at)).where(
                and_(
                    MechanicBreakSession.tenant_id == tenant.id,
                    MechanicBreakSession.mechanic_id == mechanic.id,
                    MechanicBreakSession.deleted_at.is_(None),
                    MechanicBreakSession.ended_at.is_not(None),
                    MechanicBreakSession.ended_at >= day_window.day_start_utc,
                    MechanicBreakSession.ended_at <= now,
                )
            )
        )
        last_break_end = last_break_end_result.scalar()
        idle_from = max(
            shift_start.astimezone(timezone.utc),
            active_attendance.started_at,
            last_end or day_window.day_start_utc,
            last_break_end or day_window.day_start_utc,
        )
        idle_minutes = int((now - idle_from).total_seconds() // 60)

        streak_result = await db.execute(
            select(MechanicIdleAlertStreak).where(
                and_(
                    MechanicIdleAlertStreak.tenant_id == tenant.id,
                    MechanicIdleAlertStreak.mechanic_id == mechanic.id,
                    MechanicIdleAlertStreak.local_date == local_date,
                    MechanicIdleAlertStreak.is_active.is_(True),
                    MechanicIdleAlertStreak.deleted_at.is_(None),
                )
            )
        )
        streak = streak_result.scalar_one_or_none()

        if idle_minutes >= threshold_minutes:
            if not streak:
                streak = MechanicIdleAlertStreak(
                    tenant_id=tenant.id,
                    mechanic_id=mechanic.id,
                    local_date=local_date,
                    started_at=idle_from,
                    alert_sent_at=now,
                    is_active=True,
                )
                db.add(streak)
                await db.flush()
                alerts.append(
                    {
                        "tenant_id": str(tenant.id),
                        "mechanic_id": str(mechanic.id),
                        "mechanic_name": f"{mechanic.first_name} {mechanic.last_name}".strip(),
                        "idle_minutes": idle_minutes,
                        "local_date": local_date.isoformat(),
                    }
                )
        else:
            if streak:
                streak.is_active = False
                streak.resolved_at = now

    return alerts
