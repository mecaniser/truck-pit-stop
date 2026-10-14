"""DB115: staff holds preserve execution, tenancy, timer history and privacy."""
from datetime import UTC, datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func

from app.api.v1.endpoints import repair_orders as routes
from app.db.models.mechanic_time import (
    MechanicTimeSession, MechanicTimeSessionAudit, MechanicAttendanceSession,
    MechanicAttendanceAudit, MechanicBreakSession,
)
from app.db.models.repair_order import RepairOrder, RepairOrderStatus as Status
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.repair_order_read_model import RepairOrderReadModel
from app.db.models.user import UserRole
from app.schemas.repair_order import RepairOrderResponse
from app.schemas.operation_execution import OperationCompletion, OperationVersion
from app.schemas.staff_work_hold import StaffHoldRequest, StaffReleaseHoldRequest
from app.services import staff_work_hold as holds, operation_execution as ops, mechanic_time_service as times
from test_operation_execution import seed as execution_seed


async def seed(db):
    a = await execution_seed(db)
    await db.refresh(a.order)
    return a


def hold_body(order, **kwargs):
    return StaffHoldRequest(reason="Waiting for parts", expected_updated_at=ops.utc(order.updated_at), **kwargs)


async def error(code, call):
    with pytest.raises(HTTPException) as exc:
        await call
    assert exc.value.status_code == code


@pytest.fixture
def notifications(monkeypatch):
    order, timer = AsyncMock(), AsyncMock()
    monkeypatch.setattr(routes, "broadcast_repair_order_update", order)
    monkeypatch.setattr(routes, "broadcast_mechanic_timer_update", timer)
    return order, timer


@pytest.mark.parametrize("payload", [
    {}, {"reason": "parts"}, {"reason": "parts", "expected_updated_at": "bad"},
    {"reason": "parts", "expected_updated_at": "2026-10-14T00:00:00"},
    {"reason": "parts", "expected_updated_at": None},
    *[{"reason": reason, "expected_updated_at": "2026-10-14T00:00:00Z"}
      for reason in ["", "  \t", None, 7, "a" * 101]],
    {"reason": "parts", "expected_updated_at": "2026-10-14T00:00:00Z", "tenant_id": str(uuid4())},
])
def test_hold_request_rejects_invalid_or_client_owned_fields(payload):
    with pytest.raises(ValidationError):
        StaffHoldRequest.model_validate(payload)


def test_reason_trim_and_aware_timestamp_precision():
    body = StaffHoldRequest(reason="  parts  ", expected_updated_at="2026-10-14T03:00:00.123456+03:00")
    assert body.reason == "parts"
    assert holds.utc(body.expected_updated_at) == datetime(2026, 10, 14, 0, 0, 0, 123456, UTC)
    for payload in [{}, {"expected_updated_at": "2026-10-14T00:00:00"},
                    {"expected_updated_at": "2026-10-14T00:00:00Z", "reason": "extra"}]:
        with pytest.raises(ValidationError):
            StaffReleaseHoldRequest.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,scope", [
    (UserRole.GARAGE_OWNER, None), (UserRole.GARAGE_ADMIN, None),
    (UserRole.RECEPTIONIST, None), (UserRole.FLEET_MANAGER, "is_internal"),
    (UserRole.FLEET_MANAGER, "is_fleet_work"),
])
async def test_authorized_staff_no_timer_hold_release(db_session, notifications, role, scope):
    a = await seed(db_session)
    a.owner.role = role
    if scope:
        setattr(a.order, scope, True)
    await db_session.commit()
    await db_session.refresh(a.order)
    before = ops.utc(a.order.updated_at)
    held = await routes.staff_hold_repair_order(a.order.id, hold_body(a.order), db_session, a.owner)
    assert held.status == Status.IN_PROGRESS and held.stopped_sessions_count == 0
    assert ops.utc(held.updated_at) > before
    assert ops.utc(held.held_at) == ops.utc(held.updated_at)
    released = await routes.staff_release_repair_order_hold(
        a.order.id, StaffReleaseHoldRequest(expected_updated_at=ops.utc(held.updated_at)), db_session, a.owner)
    assert released.hold_reason is None and released.held_at is None
    assert released.stopped_sessions_count == 0 and ops.utc(released.updated_at) > ops.utc(held.updated_at)
    events = (await db_session.scalars(select(RepairOrderHistoryEvent).order_by(RepairOrderHistoryEvent.created_at))).all()
    assert [event.event_type for event in events] == ["work_held", "work_hold_released"]
    assert all(event.actor_user_id == a.owner.id and event.actor_name == "Casey Owner" for event in events)
    assert json.loads(events[1].detail)["previous"]["hold_reason"] == "Waiting for parts"
    assert json.loads(events[1].detail)["previous"]["held_at"] is not None
    assert await db_session.scalar(select(func.count(MechanicTimeSession.id))) == 0
    assert await db_session.scalar(select(func.count(MechanicAttendanceSession.id))) == 0
    assert notifications[0].await_count == 2 and notifications[1].await_count == 0
    assert all(not call.kwargs["send_to_customer"] and not call.kwargs["notify_status_change"]
               for call in notifications[0].await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [role for role in UserRole if role not in ops.STAFF] + [UserRole.FLEET_MANAGER])
async def test_excluded_roles_have_no_writes(db_session, role):
    a = await seed(db_session)
    actor = SimpleNamespace(id=a.owner.id, role=role, tenant_id=a.tenant.id)
    await error(403, holds.transition(db_session, a.order.id, actor, hold_body(a.order)))
    await error(403, holds.transition(db_session, a.order.id, actor,
                StaffReleaseHoldRequest(expected_updated_at=ops.utc(a.order.updated_at)), release=True))
    assert a.order.hold_reason is None
    assert await db_session.scalar(select(func.count(RepairOrderHistoryEvent.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["missing_tenant", "wrong_tenant", "missing", "deleted"])
async def test_tenant_existence_boundary(db_session, case):
    a = await seed(db_session)
    actor = a.owner
    order_id = a.order.id
    if case == "missing_tenant":
        actor = SimpleNamespace(role=UserRole.GARAGE_OWNER, tenant_id=None)
    elif case == "wrong_tenant":
        actor = SimpleNamespace(role=UserRole.GARAGE_OWNER, tenant_id=uuid4())
    elif case == "missing":
        order_id = uuid4()
    else:
        a.order.deleted_at = datetime.now(UTC)
        await db_session.commit()
    await db_session.refresh(a.order)
    await error(400 if case == "missing_tenant" else 404,
                holds.transition(db_session, order_id, actor, hold_body(a.order)))
    assert a.order.hold_reason is None
    assert await db_session.scalar(select(func.count(RepairOrderHistoryEvent.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [value for value in Status if value != Status.IN_PROGRESS])
async def test_wrong_stage_rejects_without_side_effects(db_session, status):
    a = await seed(db_session)
    a.order.status = status
    await db_session.commit()
    await db_session.refresh(a.order)
    await error(409, holds.transition(db_session, a.order.id, a.owner, hold_body(a.order)))
    assert a.order.hold_reason is None
    assert await db_session.scalar(select(func.count(RepairOrderHistoryEvent.id))) == 0


@pytest.mark.asyncio
async def test_stale_replay_locks_and_monotonic_timestamp(db_session, notifications):
    a = await seed(db_session)
    a.order.updated_at = datetime.now(UTC) + timedelta(minutes=1)
    await db_session.commit()
    await db_session.refresh(a.order)
    stale = hold_body(a.order)
    # Equivalent offsets compare as exact instants without millisecond rounding.
    body = StaffHoldRequest(reason="parts", expected_updated_at=stale.expected_updated_at.astimezone(timezone(timedelta(hours=3))))
    a.order.pricing_locked_at = datetime.now(UTC)
    a.order.pricing_lock_reason = "invoice_created"
    await db_session.commit()
    await db_session.refresh(a.order)
    await error(409, holds.transition(db_session, a.order.id, a.owner, hold_body(a.order)))
    a.order.pricing_lock_reason = "quote_sent"
    a.order.updated_at = stale.expected_updated_at
    await db_session.commit()
    await db_session.refresh(a.order)
    order, _ = await holds.transition(db_session, a.order.id, a.owner, body)
    await db_session.commit()
    await db_session.refresh(a.order)
    assert ops.utc(order.updated_at) == stale.expected_updated_at + timedelta(microseconds=1)
    await error(409, holds.transition(db_session, a.order.id, a.owner, stale))
    await error(409, holds.transition(db_session, a.order.id, a.owner, hold_body(a.order)))
    await error(409, holds.transition(db_session, a.order.id, a.owner,
        StaffReleaseHoldRequest(expected_updated_at=stale.expected_updated_at), release=True))
    release = StaffReleaseHoldRequest(expected_updated_at=ops.utc(a.order.updated_at))
    await holds.transition(db_session, a.order.id, a.owner, release, release=True)
    await db_session.commit()
    await db_session.refresh(a.order)
    await error(409, holds.transition(db_session, a.order.id, a.owner, release, release=True))
    await error(409, holds.transition(db_session, a.order.id, a.owner,
        StaffReleaseHoldRequest(expected_updated_at=ops.utc(a.order.updated_at)), release=True))
    assert await db_session.scalar(select(func.count(RepairOrderHistoryEvent.id))) == 2


async def add_timer(db, a, mechanic, *, order=None, line=None, misc=False):
    row = MechanicTimeSession(
        tenant_id=a.tenant.id, mechanic_id=mechanic.id,
        repair_order_id=None if misc else (order or a.order).id,
        session_type="misc" if misc else "repair_order",
        labor_id=line.id if line else None, labor_id_snapshot=line.id if line else None,
        started_at=datetime.now(UTC) - timedelta(minutes=10), started_by_user_id=mechanic.id,
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.asyncio
async def test_hold_stops_only_order_timers_with_actor_and_preserves_execution(db_session, notifications):
    a, b = await seed(db_session), await seed(db_session)
    general = await add_timer(db_session, a, a.lead)
    operation = await add_timer(db_session, a, a.helper, line=a.lines[1])
    foreign = await add_timer(db_session, b, b.lead)
    # Separate same-tenant mechanics keep other-order/misc work running.
    other_order = RepairOrder(tenant_id=a.tenant.id, customer_id=a.customer.id, vehicle_id=a.vehicle.id,
                              order_number=f"other-{uuid4()}", status=Status.IN_PROGRESS)
    db_session.add(other_order)
    await db_session.flush()
    other_timer = await add_timer(db_session, a, a.owner, order=other_order)
    misc = await add_timer(db_session, a, b.helper, misc=True)
    a.order.internal_notes = '{"selected_services": []}'
    a.order.shop_notes = "Internal note unchanged"
    original_lines = [(line.id, line.mechanic_id, line.execution_status, line.execution_version, line.hours, line.total_cost) for line in a.lines]
    await db_session.commit()
    await db_session.refresh(a.order)
    body = hold_body(a.order)
    held = await routes.staff_hold_repair_order(a.order.id, body, db_session, a.owner)
    assert held.stopped_sessions_count == 2
    assert ops.utc(general.ended_at) == ops.utc(operation.ended_at) == ops.utc(held.held_at)
    assert general.stopped_by_user_id == operation.stopped_by_user_id == a.owner.id
    assert general.stop_reason == operation.stop_reason == "hold"
    assert all(timer.ended_at is None for timer in [foreign, other_timer, misc])
    assert original_lines == [(line.id, line.mechanic_id, line.execution_status, line.execution_version, line.hours, line.total_cost) for line in a.lines]
    assert a.order.internal_notes == '{"selected_services": []}' and a.order.shop_notes == "Internal note unchanged"
    audits = (await db_session.scalars(select(MechanicTimeSessionAudit))).all()
    assert len(audits) == 2 and all(row.actor_user_id == a.owner.id for row in audits)
    assert {call.kwargs["mechanic_id"] for call in notifications[1].await_args_list} == {str(a.lead.id), str(a.helper.id)}
    await error(409, ops.timer(db_session, a.order.id, a.lines[1].id, a.helper, OperationVersion(expected_version=0)))
    await error(409, ops.complete(db_session, a.order.id, a.lines[1].id, a.owner, OperationCompletion(expected_version=0, is_completed=True)))
    await error(409, ops.guard_completion(db_session, a.order))
    await routes.staff_release_repair_order_hold(a.order.id, StaffReleaseHoldRequest(expected_updated_at=ops.utc(held.updated_at)), db_session, a.owner)
    assert await db_session.scalar(select(func.count(MechanicTimeSession.id))) == 5
    assert await db_session.scalar(select(func.count(MechanicAttendanceSession.id))) == 0
    assert await db_session.scalar(select(func.count(MechanicAttendanceAudit.id))) == 0
    assert await db_session.scalar(select(func.count(MechanicBreakSession.id))) == 0
    await ops.timer(db_session, a.order.id, a.lines[1].id, a.helper, OperationVersion(expected_version=0))
    await ops.complete(db_session, a.order.id, a.lines[1].id, a.helper, OperationCompletion(expected_version=0, is_completed=True))
    assert a.lines[1].execution_status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["second_timer", "history"])
async def test_failure_rolls_back_all_timer_stops_and_history(db_session, monkeypatch, notifications, failure):
    a = await seed(db_session)
    await add_timer(db_session, a, a.lead)
    await add_timer(db_session, a, a.helper, line=a.lines[1])
    await db_session.commit()
    await db_session.refresh(a.order)
    order_id = a.order.id
    body = hold_body(a.order)
    if failure == "second_timer":
        original = times.stop_active_session
        calls = 0
        async def stop(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected second stop failure")
            return await original(*args, **kwargs)
        monkeypatch.setattr(times, "stop_active_session", stop)
    else:
        original = db_session.add
        def add(instance, *args, **kwargs):
            if isinstance(instance, RepairOrderHistoryEvent):
                raise RuntimeError("injected history failure")
            return original(instance, *args, **kwargs)
        monkeypatch.setattr(db_session, "add", add)
    with pytest.raises(RuntimeError):
        await routes.staff_hold_repair_order(order_id, body, db_session, a.owner)
    fresh = await db_session.get(RepairOrder, order_id)
    assert fresh.hold_reason is None and fresh.held_at is None
    assert await db_session.scalar(select(func.count(MechanicTimeSession.id)).where(MechanicTimeSession.ended_at.is_(None))) == 2
    assert await db_session.scalar(select(func.count(MechanicTimeSessionAudit.id))) == 0
    assert await db_session.scalar(select(func.count(RepairOrderHistoryEvent.id))) == 0
    assert notifications[0].await_count == notifications[1].await_count == 0


@pytest.mark.asyncio
async def test_notification_failure_is_still_committed_and_other_mechanic_notified(db_session, notifications):
    a = await seed(db_session)
    await add_timer(db_session, a, a.lead)
    await add_timer(db_session, a, a.helper, line=a.lines[1])
    await db_session.commit()
    await db_session.refresh(a.order)
    notifications[0].side_effect = RuntimeError("socket down")
    notifications[1].side_effect = [RuntimeError("first socket down"), None]
    held = await routes.staff_hold_repair_order(a.order.id, hold_body(a.order), db_session, a.owner)
    assert held.stopped_sessions_count == 2 and held.hold_reason == "Waiting for parts"
    assert notifications[1].await_count == 2
    await db_session.refresh(a.order)
    assert a.order.hold_reason == "Waiting for parts"
    assert await db_session.scalar(select(func.count(RepairOrderHistoryEvent.id))) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("projected", [False, True])
@pytest.mark.parametrize("status", [Status.IN_PROGRESS, Status.INVOICED])
@pytest.mark.parametrize("role", [UserRole.CUSTOMER, UserRole.DRIVER, UserRole.SUPER_ADMIN])
async def test_all_noninternal_reads_redact_hold_and_actor_history(db_session, notifications, projected, status, role):
    a = await seed(db_session)
    held = await routes.staff_hold_repair_order(a.order.id, hold_body(a.order), db_session, a.owner)
    await routes.staff_release_repair_order_hold(a.order.id,
        StaffReleaseHoldRequest(expected_updated_at=ops.utc(held.updated_at)), db_session, a.owner)
    await routes.staff_hold_repair_order(a.order.id, hold_body(a.order), db_session, a.owner)
    a.order.status = status
    await db_session.flush()
    await db_session.refresh(a.order)
    if projected:
        db_session.add(RepairOrderReadModel(
            repair_order_id=a.order.id, tenant_id=a.tenant.id, customer_id=a.customer.id,
            vehicle_id=a.vehicle.id, status=status.value, is_internal=False, is_deleted=False,
            created_at=a.order.created_at, payload=RepairOrderResponse.model_validate(a.order).model_dump(mode="json"),
        ))
    await db_session.commit()
    await db_session.refresh(a.order)
    customer = SimpleNamespace(role=role, customer_id=a.customer.id, tenant_id=a.tenant.id)
    listing = await routes.list_repair_orders(customer_id=None, vehicle_id=None, status=None, search=None,
        deleted=False, skip=0, limit=100, paginated=False, db=db_session, current_user=customer)
    assert len(listing) == 1
    results = [listing[0]]
    for get in [routes.get_repair_order_workspace, routes.get_repair_order, routes.get_repair_order_detail]:
        results.append(await get(a.order.id, db_session, customer))
        staff = await get(a.order.id, db_session, a.owner)
        assert staff.hold_reason == "Waiting for parts" and staff.held_at is not None
    for item in results:
        assert item.hold_reason is None and item.held_at is None
        assert "Waiting for parts" not in item.model_dump_json()
    assert results[-1].history_events == []
    detail = await routes.get_repair_order_detail(a.order.id, db_session, a.owner)
    assert len(detail.history_events) == 3
    assert {event.event_type for event in detail.history_events} == {"work_held", "work_hold_released"}


@pytest.mark.asyncio
async def test_assigned_mechanic_can_read_staff_hold_and_internal_history(db_session, notifications):
    a = await seed(db_session)
    await routes.staff_hold_repair_order(a.order.id, hold_body(a.order), db_session, a.owner)
    for get in [routes.get_repair_order_workspace, routes.get_repair_order, routes.get_repair_order_detail]:
        response = await get(a.order.id, db_session, a.lead)
        assert response.hold_reason == "Waiting for parts" and response.held_at is not None
    assert response.history_events[0].event_type == "work_held"


@pytest.mark.asyncio
async def test_mechanic_can_still_resume_staff_held_work(db_session, monkeypatch, notifications):
    a = await seed(db_session)
    monkeypatch.setattr(routes, "broadcast_mechanic_attendance_update", AsyncMock())
    await routes.staff_hold_repair_order(a.order.id, hold_body(a.order), db_session, a.owner)
    resumed = await routes.resume_repair_order(a.order.id, db_session, a.lead)
    assert resumed.hold_reason is None
    active = await times.get_active_session(db_session, tenant_id=a.tenant.id, mechanic_id=a.lead.id)
    assert active is not None and active.repair_order_id == a.order.id
    assert await db_session.scalar(select(func.count(MechanicTimeSession.id))) == 1


@pytest.mark.asyncio
async def test_http_auth_validation_minimal_response_and_conflicts(db_session, notifications):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.core.dependencies import get_current_active_user, get_db
    a = await seed(db_session)
    app = FastAPI()
    app.include_router(routes.router, prefix="/repair-orders")
    async def database():
        yield db_session
    app.dependency_overrides[get_db] = database
    actor = SimpleNamespace(id=a.owner.id, tenant_id=a.tenant.id, role=UserRole.GARAGE_OWNER,
                            first_name="Casey", last_name="Owner")
    order_id = a.order.id
    initial = ops.utc(a.order.updated_at).isoformat()
    path = f"/repair-orders/{order_id}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {"reason": "  Awaiting part  ", "expected_updated_at": initial}
        assert (await client.post(f"{path}/staff-hold", json=body)).status_code == 401
        app.dependency_overrides[get_current_active_user] = lambda: actor
        for excluded in [UserRole.MECHANIC, UserRole.CUSTOMER, UserRole.DRIVER, UserRole.SUPER_ADMIN]:
            actor.role = excluded
            assert (await client.post(f"{path}/staff-hold", json=body)).status_code == 403
            assert (await client.post(f"{path}/staff-release-hold", json={"expected_updated_at": initial})).status_code == 403
        actor.role = UserRole.GARAGE_OWNER
        for invalid in [{**body, "reason": " "}, {**body, "actor_id": str(actor.id)},
                        {**body, "expected_updated_at": "2026-10-14T00:00:00"},
                        {"reason": "parts"}]:
            assert (await client.post(f"{path}/staff-hold", json=invalid)).status_code == 422
        held = await client.post(f"{path}/staff-hold", json=body)
        assert held.status_code == 200
        payload = held.json()
        assert set(payload) == {"id", "status", "hold_reason", "held_at", "updated_at", "stopped_sessions_count"}
        assert payload["hold_reason"] == "Awaiting part" and payload["status"] == "in_progress"
        assert (await client.post(f"{path}/staff-hold", json=body)).status_code == 409
        # SQLite strips timezone on reads; production Postgres retains it.
        expected = ops.utc(datetime.fromisoformat(payload["updated_at"])).isoformat()
        release = await client.post(f"{path}/staff-release-hold", json={"expected_updated_at": expected})
        assert release.status_code == 200 and release.json()["hold_reason"] is None
        assert (await client.post(f"{path}/staff-release-hold", json={"expected_updated_at": expected})).status_code == 409
    assert await db_session.scalar(select(func.count(RepairOrderHistoryEvent.id))) == 2


@pytest.mark.asyncio
async def test_hold_release_preserve_financial_checklist_provenance_and_attendance_snapshots(db_session, notifications):
    from app.db.models.labor import Labor
    from app.db.models.recommended_service import RecommendedService
    from app.db.models.recommendation_conversion import RecommendationConversion
    from app.db.models.service_checklist import RepairOrderChecklistItem
    from app.services import service_checklist
    from app.schemas.service_checklist import ChecklistTaskUpdate
    a = await seed(db_session)
    await service_checklist.snapshot_service(db_session, a.order, a.lines[0], a.service, a.owner)
    tasks = await service_checklist.read_checklist(db_session, a.order.id, a.owner)
    await service_checklist.update_task(db_session, a.order.id, tasks.items[0].id, a.owner,
                                       ChecklistTaskUpdate(is_completed=True, expected_version=1))
    rec = RecommendedService(tenant_id=a.tenant.id, repair_order_id=a.order.id,
        description="Prior recommendation", priority="soon", is_resolved=False)
    db_session.add(rec)
    await db_session.flush()
    db_session.add(RecommendationConversion(tenant_id=a.tenant.id, recommendation_id=rec.id,
        source_order_id=a.order.id, source_order_number=a.order.order_number, source_description=rec.description,
        source_priority="soon", vehicle_id=a.vehicle.id, target_order_id=a.order.id,
        target_order_number=a.order.order_number, target_labor_id=a.lines[1].id,
        request_id=uuid4(), request_hash="a" * 64, hours=2, hourly_rate=100, created_by_user_id=a.owner.id))
    now = datetime.now(UTC)
    attendance = MechanicAttendanceSession(tenant_id=a.tenant.id, mechanic_id=a.lead.id,
        local_date=now.date(), started_at=now-timedelta(hours=2), started_by_user_id=a.lead.id,
        snapshot_timezone="UTC", snapshot_core_target_minutes=480,
        snapshot_shift_start_local="08:00", snapshot_shift_end_local="17:00")
    db_session.add(attendance)
    await db_session.flush()
    db_session.add(MechanicBreakSession(tenant_id=a.tenant.id, mechanic_id=a.lead.id,
        attendance_session_id=attendance.id, started_at=now-timedelta(minutes=10), started_by_user_id=a.lead.id))
    a.order.total_cost = 321
    a.order.total_labor_cost = 300
    a.order.total_parts_cost = 21
    a.order.internal_notes = '{"selected_services": [], "discounts": {"labor": 5}}'
    await db_session.commit()
    await db_session.refresh(a.order)
    models = [Labor, RepairOrderChecklistItem, RecommendedService, RecommendationConversion,
              MechanicAttendanceSession, MechanicAttendanceAudit, MechanicBreakSession]
    async def snapshots():
        result = []
        for model in models:
            result.append((await db_session.execute(select(*model.__table__.c).where(model.tenant_id == a.tenant.id))).all())
        columns = [column for column in RepairOrder.__table__.c if column.name not in {"hold_reason", "held_at", "updated_at"}]
        result.append((await db_session.execute(select(*columns).where(RepairOrder.id == a.order.id))).all())
        return result
    before = await snapshots()
    held = await routes.staff_hold_repair_order(a.order.id, hold_body(a.order), db_session, a.owner)
    assert await snapshots() == before
    await routes.staff_release_repair_order_hold(a.order.id,
        StaffReleaseHoldRequest(expected_updated_at=ops.utc(held.updated_at)), db_session, a.owner)
    assert await snapshots() == before


@pytest.mark.asyncio
async def test_reassignment_keeps_staff_hold_reason_out_of_customer_websocket(db_session, monkeypatch):
    from app.core import websocket
    staff_send, customer_send = AsyncMock(), AsyncMock()
    monkeypatch.setattr(websocket.manager, "broadcast_to_tenant", staff_send)
    monkeypatch.setattr(websocket.manager, "send_to_customer", customer_send)
    monkeypatch.setattr(routes, "send_email", AsyncMock())
    monkeypatch.setattr(routes, "send_sms", AsyncMock())
    a = await seed(db_session)
    held = await routes.staff_hold_repair_order(a.order.id, hold_body(a.order), db_session, a.owner)
    assert customer_send.await_count == 0
    staff_send.reset_mock()
    await routes.assign_mechanic(a.order.id,
        routes.AssignMechanicRequest(mechanic_id=a.helper.id), db_session, a.owner)
    staff_send.assert_awaited_once()
    customer_send.assert_awaited_once()
    staff_payload = staff_send.await_args.args[1]
    customer_payload = customer_send.await_args.args[1]
    assert staff_payload["hold_reason"] == held.hold_reason
    assert staff_payload["held_at"] is not None
    assert customer_payload["hold_reason"] is None and customer_payload["held_at"] is None
    assert staff_payload is not customer_payload
    assert customer_payload["status"] == "in_progress"
    assert customer_payload["order_id"] == str(a.order.id)
    assert held.hold_reason not in json.dumps(customer_payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("send_to_customer", [False, True])
async def test_core_order_broadcast_redacts_only_customer_hold_payload(monkeypatch, send_to_customer):
    from app.core import websocket
    staff_send, customer_send = AsyncMock(), AsyncMock()
    monkeypatch.setattr(websocket.manager, "broadcast_to_tenant", staff_send)
    monkeypatch.setattr(websocket.manager, "send_to_customer", customer_send)
    await websocket.broadcast_repair_order_update(
        tenant_id="shop", customer_id="customer", order_id="order", order_number="QA",
        status="in_progress", updated_at="2026-10-14T03:00:00Z",
        hold_reason="Internal supplier problem", held_at="2026-10-14T02:00:00Z",
        send_to_customer=send_to_customer, notify_status_change=False,
    )
    staff_send.assert_awaited_once()
    staff_payload = staff_send.await_args.args[1]
    assert staff_payload["hold_reason"] == "Internal supplier problem"
    assert staff_payload["held_at"] == "2026-10-14T02:00:00Z"
    if send_to_customer:
        customer_send.assert_awaited_once()
        customer_payload = customer_send.await_args.args[1]
        assert customer_payload == {**staff_payload, "hold_reason": None, "held_at": None}
        assert customer_payload is not staff_payload
    else:
        customer_send.assert_not_awaited()
