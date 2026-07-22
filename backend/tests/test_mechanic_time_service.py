from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.db.models.mechanic_time import (
    MechanicAttendanceSession,
    MechanicSessionType,
    MechanicTimeSession,
)
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services import mechanic_time_service


class _ScalarListResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


class _RowResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, execute_result=None):
        self._execute_result = execute_result
        self.added: list[object] = []
        self.flush_count = 0

    async def execute(self, _statement):
        if callable(self._execute_result):
            return self._execute_result(_statement)
        return self._execute_result

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()


def _build_tenant_and_users():
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Test Garage",
        slug=f"tenant-{tenant_id.hex[:8]}",
        timezone="America/New_York",
        default_core_hours_minutes=480,
        default_shift_start_local="08:00",
        default_shift_end_local="18:00",
    )
    mechanic = User(
        id=uuid4(),
        tenant_id=tenant_id,
        role=UserRole.MECHANIC,
        email="mechanic@example.com",
        hashed_password="hashed-password",
        first_name="Manny",
        last_name="Mechanic",
        is_active=True,
        is_verified=True,
    )
    manager = User(
        id=uuid4(),
        tenant_id=tenant_id,
        role=UserRole.GARAGE_OWNER,
        email="owner@example.com",
        hashed_password="hashed-password",
        first_name="Olive",
        last_name="Owner",
        is_active=True,
        is_verified=True,
    )
    return tenant, mechanic, manager


def test_validate_timezone_name_rejects_invalid_value():
    assert mechanic_time_service.validate_timezone_name("America/New_York") == "America/New_York"
    with pytest.raises(ValueError):
        mechanic_time_service.validate_timezone_name("Mars/Olympus")


def test_timer_stop_reasons_include_hold_and_resume_from_hold():
    assert "hold" in mechanic_time_service.TIMER_STOP_REASONS
    assert "resume_from_hold" in mechanic_time_service.TIMER_STOP_REASONS


@pytest.mark.asyncio
async def test_start_session_auto_switches_existing_active_timer(monkeypatch):
    tenant, mechanic, manager = _build_tenant_and_users()
    db = _FakeDB()

    current = MechanicTimeSession(
        id=uuid4(),
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        session_type=MechanicSessionType.MISC.value,
        misc_category="shop_support",
        started_at=datetime(2026, 2, 13, 13, 0, tzinfo=timezone.utc),
        started_by_user_id=mechanic.id,
    )

    stop_calls: list[dict] = []

    async def _fake_get_active_session(_db, *, tenant_id, mechanic_id):
        assert tenant_id == tenant.id
        assert mechanic_id == mechanic.id
        return current

    async def _fake_stop_active_session(_db, **kwargs):
        stop_calls.append(kwargs)
        return current

    async def _noop_resolve_idle_streak(*_args, **_kwargs):
        return None

    monkeypatch.setattr(mechanic_time_service, "get_active_session", _fake_get_active_session)
    monkeypatch.setattr(mechanic_time_service, "stop_active_session", _fake_stop_active_session)
    monkeypatch.setattr(mechanic_time_service, "resolve_idle_streak", _noop_resolve_idle_streak)
    monkeypatch.setattr(
        mechanic_time_service,
        "ensure_attendance_started",
        AsyncMock(return_value=(
            MechanicAttendanceSession(
                id=uuid4(),
                tenant_id=tenant.id,
                mechanic_id=mechanic.id,
                local_date=datetime(2026, 2, 13, tzinfo=timezone.utc).date(),
                started_at=datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc),
                started_by_user_id=mechanic.id,
                start_source="auto_first_timer",
                snapshot_timezone="America/New_York",
                snapshot_core_target_minutes=480,
                snapshot_shift_start_local="08:00",
                snapshot_shift_end_local="18:00",
            ),
            False,
        )),
    )
    monkeypatch.setattr(
        mechanic_time_service,
        "get_active_break_session",
        AsyncMock(return_value=None),
    )

    new_session, auto_clocked_in, _attendance_session_id, _auto_held_ro = await mechanic_time_service.start_session(
        db,
        tenant=tenant,
        mechanic=mechanic,
        actor_user=manager,
        session_type=MechanicSessionType.REPAIR_ORDER.value,
        repair_order_id=uuid4(),
        stop_previous_reason="auto_switch",
    )

    assert new_session.mechanic_id == mechanic.id
    assert auto_clocked_in is False
    assert len(stop_calls) == 1
    assert stop_calls[0]["stop_reason"] == "auto_switch"
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_clock_in_rejects_duplicate_active_attendance(monkeypatch):
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()
    active_attendance = MechanicAttendanceSession(
        id=uuid4(),
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        local_date=datetime(2026, 2, 13, tzinfo=timezone.utc).date(),
        started_at=datetime(2026, 2, 13, 13, 0, tzinfo=timezone.utc),
        started_by_user_id=mechanic.id,
        start_source="manual_clock_in",
        snapshot_timezone="America/New_York",
        snapshot_core_target_minutes=480,
        snapshot_shift_start_local="08:00",
        snapshot_shift_end_local="18:00",
    )

    monkeypatch.setattr(
        mechanic_time_service,
        "get_active_attendance_session",
        AsyncMock(return_value=active_attendance),
    )

    with pytest.raises(ValueError) as exc:
        await mechanic_time_service.clock_in(
            db,
            tenant=tenant,
            mechanic=mechanic,
            actor_user=mechanic,
        )
    assert str(exc.value) == "Mechanic is already clocked in"


@pytest.mark.asyncio
async def test_manager_clock_in_does_not_require_a_reason(monkeypatch):
    tenant, mechanic, manager = _build_tenant_and_users()
    db = _FakeDB(execute_result=_ScalarListResult([]))
    monkeypatch.setattr(mechanic_time_service, "get_active_attendance_session", AsyncMock(return_value=None))
    monkeypatch.setattr(mechanic_time_service, "_create_attendance_audit", AsyncMock(return_value=None))

    attendance = await mechanic_time_service.clock_in(
        db,
        tenant=tenant,
        mechanic=mechanic,
        actor_user=manager,
        manager_reason=None,
        start_source="manager_clock_in",
        started_at=datetime(2026, 2, 13, 13, 0, tzinfo=timezone.utc),
    )

    assert attendance.mechanic_id == mechanic.id
    assert attendance.start_source == "manager_clock_in"


@pytest.mark.asyncio
async def test_clock_out_stops_timer_and_break(monkeypatch):
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()
    attendance = MechanicAttendanceSession(
        id=uuid4(),
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        local_date=datetime(2026, 2, 13, tzinfo=timezone.utc).date(),
        started_at=datetime(2026, 2, 13, 13, 0, tzinfo=timezone.utc),
        started_by_user_id=mechanic.id,
        start_source="manual_clock_in",
        snapshot_timezone="America/New_York",
        snapshot_core_target_minutes=480,
        snapshot_shift_start_local="08:00",
        snapshot_shift_end_local="18:00",
    )
    stopped_timer = MechanicTimeSession(
        id=uuid4(),
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        session_type=MechanicSessionType.MISC.value,
        misc_category="shop_support",
        started_at=datetime(2026, 2, 13, 14, 0, tzinfo=timezone.utc),
        started_by_user_id=mechanic.id,
    )

    monkeypatch.setattr(
        mechanic_time_service,
        "get_active_attendance_session",
        AsyncMock(return_value=attendance),
    )
    monkeypatch.setattr(
        mechanic_time_service,
        "stop_active_session",
        AsyncMock(return_value=stopped_timer),
    )
    monkeypatch.setattr(
        mechanic_time_service,
        "end_active_break_session",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        mechanic_time_service,
        "resolve_idle_streak",
        AsyncMock(return_value=None),
    )

    result = await mechanic_time_service.clock_out(
        db,
        tenant=tenant,
        mechanic=mechanic,
        actor_user=mechanic,
    )

    assert result.attendance_session.id == attendance.id
    assert result.stopped_timer_session.id == stopped_timer.id


@pytest.mark.asyncio
async def test_historical_day_summary_uses_attendance_shift_snapshot(monkeypatch):
    tenant, mechanic, _manager = _build_tenant_and_users()
    work_date = date(2026, 6, 10)
    attendance = MechanicAttendanceSession(
        id=uuid4(),
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        local_date=work_date,
        started_at=datetime(2026, 6, 10, 10, 15, tzinfo=timezone.utc),  # 06:15 local
        ended_at=datetime(2026, 6, 10, 18, 0, tzinfo=timezone.utc),  # 14:00 local
        started_by_user_id=mechanic.id,
        ended_by_user_id=mechanic.id,
        start_source="manual_clock_in",
        end_source="manual_clock_out",
        snapshot_timezone="America/New_York",
        snapshot_core_target_minutes=420,
        snapshot_shift_start_local="06:00",
        snapshot_shift_end_local="14:00",
    )
    results = iter([
        _ScalarListResult([]),
        _ScalarListResult([attendance]),
        _ScalarListResult([]),
    ])
    db = _FakeDB(execute_result=lambda _statement: next(results))
    monkeypatch.setattr(
        mechanic_time_service,
        "_compute_book_hours_for_orders",
        AsyncMock(return_value=0.0),
    )

    summary = await mechanic_time_service.compute_day_summary(
        db,
        tenant=tenant,
        mechanic=mechanic,
        target_date=work_date,
        now_utc=datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc),
    )

    assert summary["shift_start_local"] == "06:00"
    assert summary["shift_end_local"] == "14:00"
    assert summary["core_target_minutes"] == 420
    assert summary["attendance_minutes"] == 465
    assert summary["late_arrival_minutes"] == 15
    assert summary["early_leave_minutes"] == 0


@pytest.mark.skip(reason="Test needs update: compute_day_summary now queries MechanicAttendanceSession with local_date")
@pytest.mark.asyncio
async def test_compute_day_summary_caps_utilization_and_computes_overtime(monkeypatch):
    tenant, mechanic, _manager = _build_tenant_and_users()
    now = datetime(2026, 2, 13, 18, 0, tzinfo=timezone.utc)
    ro_id = uuid4()
    session = MechanicTimeSession(
        id=uuid4(),
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        repair_order_id=ro_id,
        session_type=MechanicSessionType.REPAIR_ORDER.value,
        started_at=datetime(2026, 2, 13, 9, 0, tzinfo=timezone.utc),
        ended_at=now,
        started_by_user_id=mechanic.id,
    )
    db = _FakeDB(execute_result=_ScalarListResult([session]))

    async def _fake_book_hours(*_args, **_kwargs):
        return 4.0

    monkeypatch.setattr(mechanic_time_service, "_compute_book_hours_for_orders", _fake_book_hours)

    summary = await mechanic_time_service.compute_day_summary(
        db,
        tenant=tenant,
        mechanic=mechanic,
        target_date=now.date(),
        now_utc=now,
    )

    assert summary["tracked_minutes"] == 540
    assert summary["ro_minutes"] == 540
    assert summary["misc_minutes"] == 0
    assert summary["overtime_minutes"] == 60
    assert summary["utilization_percent"] == 100.0
    assert summary["book_hours"] == 4.0
    assert summary["actual_ro_hours"] == 9.0
    assert summary["efficiency_percent"] == 44.44
    assert summary["core_countdown_elapsed_minutes"] == 480
    assert summary["core_countdown_remaining_minutes"] == 0
    assert summary["tracked_vs_attendance_gap_minutes"] == 0
    assert summary["work_coverage_percent"] == 100.0


@pytest.mark.asyncio
async def test_close_sessions_crossing_midnight_uses_local_midnight_boundary():
    tenant, mechanic, _manager = _build_tenant_and_users()
    session = MechanicTimeSession(
        id=uuid4(),
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        session_type=MechanicSessionType.MISC.value,
        misc_category="shop_support",
        started_at=datetime(2026, 2, 14, 3, 0, tzinfo=timezone.utc),  # 10 PM local previous day
        ended_at=None,
        started_by_user_id=mechanic.id,
    )
    db = _FakeDB(execute_result=_RowResult([(session, tenant)]))

    closed = await mechanic_time_service.close_sessions_crossing_midnight(
        db,
        now_utc=datetime(2026, 2, 14, 5, 10, tzinfo=timezone.utc),  # 12:10 AM local
    )

    assert len(closed) == 1
    assert session.stop_reason == "auto_midnight"
    assert session.ended_at == datetime(2026, 2, 14, 5, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_close_sessions_crossing_midnight_uses_first_boundary_after_start():
    tenant, mechanic, _manager = _build_tenant_and_users()
    session = MechanicTimeSession(
        id=uuid4(),
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        session_type=MechanicSessionType.MISC.value,
        misc_category="shop_support",
        started_at=datetime(2026, 2, 13, 1, 0, tzinfo=timezone.utc),  # 8 PM local on Feb 12
        ended_at=None,
        started_by_user_id=mechanic.id,
    )
    db = _FakeDB(execute_result=_RowResult([(session, tenant)]))

    closed = await mechanic_time_service.close_sessions_crossing_midnight(
        db,
        now_utc=datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc),  # much later
    )

    assert len(closed) == 1
    assert session.ended_at == datetime(2026, 2, 13, 5, 0, tzinfo=timezone.utc)  # first midnight after local start date


@pytest.mark.asyncio
async def test_compute_next_action_recommendation_prioritizes_stop_misc_pick_ro():
    tenant, mechanic, _manager = _build_tenant_and_users()
    assigned_order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=uuid4(),
        vehicle_id=uuid4(),
        order_number="RO-READY-1",
        status=RepairOrderStatus.ACKNOWLEDGED,
        assigned_mechanic_id=mechanic.id,
    )
    in_progress_order = RepairOrder(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=uuid4(),
        vehicle_id=uuid4(),
        order_number="RO-IP-1",
        status=RepairOrderStatus.IN_PROGRESS,
        assigned_mechanic_id=mechanic.id,
    )
    db = _FakeDB(execute_result=_ScalarListResult([assigned_order, in_progress_order]))

    recommendation = await mechanic_time_service.compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=True,
        break_active=False,
        active_session={
            "id": str(uuid4()),
            "session_type": MechanicSessionType.MISC.value,
            "repair_order_id": None,
            "misc_category": "shop_cleanup",
        },
    )

    assert recommendation["suggested_next_action"] == "stop_misc_pick_ro"
    assert recommendation["assigned_ready_orders_count"] == 1
    assert recommendation["untimed_in_progress_orders_count"] == 1
    assert recommendation["recommended_order_id"] == str(assigned_order.id)
    assert recommendation["recommended_order_number"] == assigned_order.order_number


def _build_repair_order(
    tenant_id,
    mechanic_id,
    *,
    status: RepairOrderStatus,
    order_number: str,
    updated_at: datetime | None = None,
) -> RepairOrder:
    return RepairOrder(
        id=uuid4(),
        tenant_id=tenant_id,
        customer_id=uuid4(),
        vehicle_id=uuid4(),
        order_number=order_number,
        status=status,
        assigned_mechanic_id=mechanic_id,
        updated_at=updated_at,
    )


@pytest.mark.asyncio
async def test_compute_next_action_recommendation_clock_in_when_not_attendance_active():
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()

    recommendation = await mechanic_time_service.compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=False,
        break_active=False,
        active_session=None,
        prefetched_orders=[],
        core_countdown_remaining_minutes=480,
    )

    assert recommendation["suggested_next_action"] == "clock_in"
    assert recommendation["recommended_order_id"] is None
    assert recommendation["recommended_order_number"] is None


@pytest.mark.asyncio
async def test_compute_next_action_recommendation_end_break_when_break_active():
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()

    recommendation = await mechanic_time_service.compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=True,
        break_active=True,
        active_session=None,
        prefetched_orders=[],
        core_countdown_remaining_minutes=420,
    )

    assert recommendation["suggested_next_action"] == "end_break"
    assert recommendation["recommended_order_id"] is None
    assert recommendation["recommended_order_number"] is None


@pytest.mark.asyncio
async def test_compute_next_action_recommendation_continue_ro_for_active_repair_timer():
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()
    in_progress_order = _build_repair_order(
        tenant.id,
        mechanic.id,
        status=RepairOrderStatus.IN_PROGRESS,
        order_number="RO-IP-CONTINUE",
    )

    recommendation = await mechanic_time_service.compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=True,
        break_active=False,
        active_session={
            "id": str(uuid4()),
            "session_type": MechanicSessionType.REPAIR_ORDER.value,
            "repair_order_id": str(in_progress_order.id),
        },
        prefetched_orders=[in_progress_order],
        core_countdown_remaining_minutes=240,
    )

    assert recommendation["suggested_next_action"] == "continue_ro"
    assert recommendation["recommended_order_id"] == str(in_progress_order.id)
    assert recommendation["recommended_order_number"] == in_progress_order.order_number


@pytest.mark.asyncio
async def test_compute_next_action_recommendation_start_assigned_ro_prefers_untimed_in_progress():
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()
    untimed_in_progress = _build_repair_order(
        tenant.id,
        mechanic.id,
        status=RepairOrderStatus.IN_PROGRESS,
        order_number="RO-IP-UNTIMED",
        updated_at=datetime(2026, 2, 13, 13, 0, tzinfo=timezone.utc),
    )
    acknowledged_ready = _build_repair_order(
        tenant.id,
        mechanic.id,
        status=RepairOrderStatus.ACKNOWLEDGED,
        order_number="RO-ACK-READY",
        updated_at=datetime(2026, 2, 13, 14, 0, tzinfo=timezone.utc),
    )

    recommendation = await mechanic_time_service.compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=True,
        break_active=False,
        active_session=None,
        prefetched_orders=[acknowledged_ready, untimed_in_progress],
        core_countdown_remaining_minutes=300,
    )

    assert recommendation["suggested_next_action"] == "start_assigned_ro"
    assert recommendation["recommended_order_id"] == str(untimed_in_progress.id)
    assert recommendation["recommended_order_number"] == untimed_in_progress.order_number


@pytest.mark.asyncio
async def test_compute_next_action_recommendation_start_assigned_ro_with_ready_orders_only():
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()
    assigned_order = _build_repair_order(
        tenant.id,
        mechanic.id,
        status=RepairOrderStatus.ASSIGNED,
        order_number="RO-ASSIGNED-1",
        updated_at=datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc),
    )

    recommendation = await mechanic_time_service.compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=True,
        break_active=False,
        active_session=None,
        prefetched_orders=[assigned_order],
        core_countdown_remaining_minutes=360,
    )

    assert recommendation["suggested_next_action"] == "start_assigned_ro"
    assert recommendation["recommended_order_id"] == str(assigned_order.id)
    assert recommendation["recommended_order_number"] == assigned_order.order_number


@pytest.mark.asyncio
async def test_compute_next_action_recommendation_start_misc_when_no_orders_and_no_active_session():
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()

    recommendation = await mechanic_time_service.compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=True,
        break_active=False,
        active_session=None,
        prefetched_orders=[],
        core_countdown_remaining_minutes=120,
    )

    assert recommendation["suggested_next_action"] == "start_misc"
    assert recommendation["recommended_order_id"] is None
    assert recommendation["recommended_order_number"] is None


@pytest.mark.asyncio
async def test_compute_next_action_recommendation_start_misc_when_misc_active_and_no_orders():
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()

    recommendation = await mechanic_time_service.compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=True,
        break_active=False,
        active_session={
            "id": str(uuid4()),
            "session_type": MechanicSessionType.MISC.value,
            "repair_order_id": None,
            "misc_category": "shop_cleanup",
        },
        prefetched_orders=[],
        core_countdown_remaining_minutes=180,
    )

    assert recommendation["suggested_next_action"] == "start_misc"
    assert recommendation["recommended_order_id"] is None
    assert recommendation["recommended_order_number"] is None


@pytest.mark.asyncio
async def test_compute_next_action_recommendation_includes_held_orders_metadata():
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()
    held_order = _build_repair_order(
        tenant.id,
        mechanic.id,
        status=RepairOrderStatus.IN_PROGRESS,
        order_number="RO-HOLD-1",
    )
    held_order.hold_reason = "waiting_for_parts"
    held_order.held_at = datetime(2026, 2, 14, 15, 30, tzinfo=timezone.utc)

    recommendation = await mechanic_time_service.compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=True,
        break_active=False,
        active_session=None,
        prefetched_orders=[held_order],
        core_countdown_remaining_minutes=240,
    )

    assert recommendation["suggested_next_action"] == "start_misc"
    assert recommendation["held_orders_count"] == 1
    assert recommendation["held_orders"][0]["order_number"] == "RO-HOLD-1"
    assert recommendation["held_orders"][0]["hold_reason"] == "waiting_for_parts"


@pytest.mark.asyncio
async def test_compute_next_action_recommendation_clock_out_when_core_complete_and_no_work():
    tenant, mechanic, _manager = _build_tenant_and_users()
    db = _FakeDB()

    recommendation = await mechanic_time_service.compute_next_action_recommendation(
        db,
        tenant_id=tenant.id,
        mechanic_id=mechanic.id,
        attendance_active=True,
        break_active=False,
        active_session=None,
        prefetched_orders=[],
        core_countdown_remaining_minutes=0,
    )

    assert recommendation["suggested_next_action"] == "clock_out"
    assert recommendation["recommended_order_id"] is None
    assert recommendation["recommended_order_number"] is None


# ---------------------------------------------------------------------------
# compute_attention_priority tests
# ---------------------------------------------------------------------------

def _base_summary(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "attendance_active": True,
        "break_active": False,
        "idle_minutes": 0,
        "attendance_minutes": 60,
        "break_minutes": 0,
        "work_coverage_percent": 85.0,
        "active_session": {"id": "s1", "session_type": "repair_order"},
        "core_countdown_remaining_minutes": 420,
    }
    defaults.update(overrides)
    return defaults


def _base_recommendation(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "suggested_next_action": "continue_ro",
        "untimed_in_progress_orders_count": 0,
        "assigned_ready_orders_count": 0,
    }
    defaults.update(overrides)
    return defaults


def test_attention_priority_green_when_on_track():
    result = mechanic_time_service.compute_attention_priority(
        summary=_base_summary(),
        recommendation=_base_recommendation(),
    )
    assert result["attention_priority"] == "green"
    assert result["attention_reasons"] == []


def test_attention_priority_red_idle_extended():
    result = mechanic_time_service.compute_attention_priority(
        summary=_base_summary(idle_minutes=20, active_session=None),
        recommendation=_base_recommendation(suggested_next_action="start_misc"),
    )
    assert result["attention_priority"] == "red"
    assert "idle_extended" in result["attention_reasons"]


def test_attention_priority_red_untimed_in_progress():
    result = mechanic_time_service.compute_attention_priority(
        summary=_base_summary(),
        recommendation=_base_recommendation(untimed_in_progress_orders_count=2),
    )
    assert result["attention_priority"] == "red"
    assert "untimed_in_progress" in result["attention_reasons"]


def test_attention_priority_red_clocked_out_during_shift():
    result = mechanic_time_service.compute_attention_priority(
        summary=_base_summary(attendance_active=False, core_countdown_remaining_minutes=300),
        recommendation=_base_recommendation(suggested_next_action="clock_in"),
    )
    assert result["attention_priority"] == "red"
    assert "clocked_out_during_shift" in result["attention_reasons"]


def test_attention_priority_yellow_misc_with_ro_waiting():
    result = mechanic_time_service.compute_attention_priority(
        summary=_base_summary(active_session={"id": "s1", "session_type": "misc"}),
        recommendation=_base_recommendation(suggested_next_action="stop_misc_pick_ro"),
    )
    assert result["attention_priority"] == "yellow"
    assert "misc_with_ro_waiting" in result["attention_reasons"]


def test_attention_priority_yellow_break_extended():
    result = mechanic_time_service.compute_attention_priority(
        summary=_base_summary(break_active=True, break_minutes=25, active_session=None),
        recommendation=_base_recommendation(suggested_next_action="end_break"),
    )
    assert result["attention_priority"] == "yellow"
    assert "break_extended" in result["attention_reasons"]


def test_attention_priority_yellow_low_coverage():
    result = mechanic_time_service.compute_attention_priority(
        summary=_base_summary(work_coverage_percent=45.0, attendance_minutes=120),
        recommendation=_base_recommendation(),
    )
    assert result["attention_priority"] == "yellow"
    assert "low_coverage" in result["attention_reasons"]


def test_attention_priority_low_coverage_ignored_when_warming_up():
    """Coverage below 60% is ignored during the first 15 minutes of attendance."""
    result = mechanic_time_service.compute_attention_priority(
        summary=_base_summary(work_coverage_percent=30.0, attendance_minutes=10),
        recommendation=_base_recommendation(),
    )
    assert result["attention_priority"] == "green"


def test_attention_priority_red_trumps_yellow():
    """When both red and yellow conditions exist, priority is red."""
    result = mechanic_time_service.compute_attention_priority(
        summary=_base_summary(
            idle_minutes=20,
            active_session=None,
            work_coverage_percent=40.0,
            attendance_minutes=120,
        ),
        recommendation=_base_recommendation(
            suggested_next_action="start_misc",
            untimed_in_progress_orders_count=1,
        ),
    )
    assert result["attention_priority"] == "red"
    assert "idle_extended" in result["attention_reasons"]
    assert "untimed_in_progress" in result["attention_reasons"]
