"""DB131: shop-zone scheduling, canonical overdue scope and private evidence."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func, delete

from app.api.v1.endpoints import repair_orders as routes, dashboard
from app.db.models.repair_order import RepairOrder, RepairOrderStatus as Status
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.repair_order_read_model import RepairOrderReadModel
from app.db.models.user import UserRole
from app.middleware.idempotency import IdempotencyMiddleware
from app.schemas.repair_order import RepairOrderResponse
from app.schemas.repair_order_schedule import RepairOrderScheduleUpdate as Update
from app.services import repair_order_schedule as schedules, operation_execution as ops
from test_operation_execution import seed as execution_seed
from test_order_value_summaries import _seed_shop, _headers

NOW = datetime(2026, 10, 16, 22, tzinfo=UTC)


def body(order, **changes):
    return Update.model_validate({"expected_updated_at": ops.utc(order.updated_at),
        "timezone": "America/New_York", "scheduled_start_local": "2026-10-16T08:00",
        "promised_finish_local": "2026-10-16T17:00", **changes})


async def seed(db):
    a = await execution_seed(db)
    await db.refresh(a.order)
    return a


async def fails(status, code, call):
    with pytest.raises(HTTPException) as exc:
        await call
    assert exc.value.status_code == status
    if code:
        assert exc.value.detail["code"] == code
    return exc.value


@pytest.mark.parametrize("value", ["", "2026-10-16", "2026-02-30T09:00", "2026-10-16T08:00Z", "2026-10-16T08:00:00", "2026-10-16T25:00", "2026-10-16T8:00", " 2026-10-16T08:00", "2026-10-16T08:00-04:00"])
def test_exact_wall_time_schema(value):
    with pytest.raises(ValidationError):
        body(SimpleNamespace(updated_at=NOW), scheduled_start_local=value)


@pytest.mark.parametrize("extra", [
    {"expected_updated_at": "2026-10-16T22:00:00"}, {"scheduled_start_fold": True},
    {"scheduled_start_fold": 2}, {"scheduled_start_fold": "1"},
    {"scheduled_start_local": None, "scheduled_start_fold": 0}, {"tenant_id": str(uuid4())},
])
def test_schema_rejects_unsafe_fields(extra):
    with pytest.raises(ValidationError):
        body(SimpleNamespace(updated_at=NOW), **extra)


def test_requires_complete_pair_and_aware_version():
    for key in ["scheduled_start_local", "promised_finish_local", "expected_updated_at", "timezone"]:
        payload = body(SimpleNamespace(updated_at=NOW)).model_dump()
        del payload[key]
        with pytest.raises(ValidationError):
            Update.model_validate(payload)
    assert not IdempotencyMiddleware._should_apply({"type": "http", "method": "PATCH", "path": f"/api/v1/repair-orders/{uuid4()}/schedule"})


def test_dst_roundtrips_gap_overlap_and_fold_validation():
    zone = ZoneInfo("America/New_York")
    with pytest.raises(HTTPException) as gap:
        schedules.resolve_wall("2026-03-08T02:30", None, zone, "scheduled_start_local")
    assert gap.value.detail["code"] == "schedule_time_nonexistent"
    with pytest.raises(HTTPException) as overlap:
        schedules.resolve_wall("2026-11-01T01:30", None, zone, "promised_finish_local")
    assert overlap.value.detail["field"] == "promised_finish_local"
    assert overlap.value.detail["choices"] == [
        {"fold": 0, "utc": "2026-11-01T05:30:00+00:00", "utc_offset": "-04:00"},
        {"fold": 1, "utc": "2026-11-01T06:30:00+00:00", "utc_offset": "-05:00"}]
    for fold, hour in [(0, 5), (1, 6)]:
        instant = schedules.resolve_wall("2026-11-01T01:30", fold, zone, "scheduled_start_local")
        assert instant == datetime(2026, 11, 1, hour, 30, tzinfo=UTC)
        assert schedules.local_fields(instant, zone) == ("2026-11-01T01:30", fold)
    assert schedules.local_fields(datetime(2026, 10, 16, 12, tzinfo=UTC), zone) == ("2026-10-16T08:00", None)
    with pytest.raises(HTTPException) as inappropriate:
        schedules.resolve_wall("2026-10-16T08:00", 1, zone, "scheduled_start_local")
    assert inappropriate.value.detail["code"] == "schedule_fold_invalid"
    with pytest.raises(HTTPException) as out_of_range:
        schedules.resolve_wall("9999-12-31T23:59", None, zone, "promised_finish_local")
    assert out_of_range.value.detail["code"] == "schedule_time_out_of_range"


@pytest.mark.parametrize("status", list(Status))
def test_shared_overdue_boundary_and_lifecycle(status):
    order = SimpleNamespace(status=status, promised_finish_at=NOW, deleted_at=None, vehicle_released_at=None)
    assert not schedules.is_overdue(order, NOW)
    assert schedules.is_overdue(order, NOW + timedelta(microseconds=1)) == (status in schedules.OVERDUE_STATUSES)
    order.hold_reason = "waiting_for_parts"
    order.work_completed_at = NOW - timedelta(hours=1)
    assert schedules.is_overdue(order, NOW + timedelta(seconds=1)) == (status in schedules.OVERDUE_STATUSES)
    order.vehicle_released_at = NOW
    assert not schedules.is_overdue(order, NOW + timedelta(seconds=1))
    order.vehicle_released_at = None
    order.deleted_at = NOW
    assert not schedules.is_overdue(order, NOW + timedelta(seconds=1))


@pytest.mark.asyncio
async def test_save_clear_noop_audit_broadcast_and_no_execution_side_effect(db_session, monkeypatch):
    a = await seed(db_session)
    monkeypatch.setattr(schedules, "now_utc", lambda: NOW)
    broadcast = AsyncMock()
    monkeypatch.setattr(routes, "broadcast_repair_order_update", broadcast)
    before = (a.order.status, a.order.work_started_at, a.order.total_cost)
    first = await routes.update_repair_order_schedule(a.order.id, body(a.order), db_session, a.owner)
    assert first.scheduled_start_at == datetime(2026, 10, 16, 12, tzinfo=UTC)
    assert first.promised_finish_at == datetime(2026, 10, 16, 21, tzinfo=UTC)
    assert first.scheduled_start_local == "2026-10-16T08:00" and first.is_overdue and first.can_edit
    second = await routes.update_repair_order_schedule(a.order.id, body(a.order), db_session, a.owner)
    assert second.updated_at == first.updated_at
    assert broadcast.await_count == 1
    assert not broadcast.await_args.kwargs["send_to_customer"]
    assert not broadcast.await_args.kwargs["notify_status_change"]
    event = (await db_session.scalars(select(RepairOrderHistoryEvent))).one()
    assert event.event_type == "schedule_changed" and event.actor_user_id == a.owner.id
    assert json.loads(event.detail)["current"]["promised_finish_at"] == "2026-10-16T21:00:00+00:00"
    assert json.loads(event.detail)["previous"]["scheduled_start_at"] is None
    cleared = await routes.update_repair_order_schedule(a.order.id, body(a.order, scheduled_start_local=None), db_session, a.owner)
    assert cleared.scheduled_start_at is None and cleared.promised_finish_at is not None
    cleared = await routes.update_repair_order_schedule(a.order.id, body(a.order, scheduled_start_local=None, promised_finish_local=None), db_session, a.owner)
    assert cleared.promised_finish_at is None and not cleared.is_overdue
    assert (a.order.status, a.order.work_started_at, a.order.total_cost) == before


@pytest.mark.asyncio
async def test_monotonic_precise_versions_and_stale_uncertain_retry(db_session):
    a = await seed(db_session)
    a.order.updated_at = NOW + timedelta(days=20, microseconds=123456)
    await db_session.commit()
    original = body(a.order)
    _, first, _ = await schedules.update(db_session, a.order.id, a.owner, original)
    await db_session.commit()
    assert first.updated_at == original.expected_updated_at + timedelta(microseconds=1)
    await fails(409, "schedule_changed", schedules.update(db_session, a.order.id, a.owner, original))
    assert await db_session.scalar(select(func.count(RepairOrderHistoryEvent.id))) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("case,code", [("equal", "schedule_finish_before_start"), ("reversed", "schedule_finish_before_start"), ("zone_changed", "schedule_timezone_changed"), ("zone_invalid", "schedule_timezone_invalid"), ("gap", "schedule_time_nonexistent"), ("overlap", "schedule_time_ambiguous")])
async def test_invalid_write_is_atomic(db_session, case, code):
    a = await seed(db_session)
    changes = {}
    if case == "equal":
        changes["promised_finish_local"] = "2026-10-16T08:00"
    elif case == "reversed":
        changes["promised_finish_local"] = "2026-10-15T08:00"
    elif case == "zone_changed":
        changes["timezone"] = "America/Los_Angeles"
    elif case == "zone_invalid":
        a.tenant.timezone = "Not/AZone"
        await db_session.commit()
    elif case == "gap":
        changes["scheduled_start_local"] = "2026-03-08T02:30"
    else:
        changes["promised_finish_local"] = "2026-11-01T01:30"
    before = a.order.updated_at
    await fails(409 if case.startswith("zone_") else 422, code,
                schedules.update(db_session, a.order.id, a.owner, body(a.order, **changes)))
    assert a.order.scheduled_start_at is None and a.order.promised_finish_at is None
    assert a.order.updated_at == before
    assert await db_session.scalar(select(func.count(RepairOrderHistoryEvent.id))) == 0


@pytest.mark.asyncio
async def test_saved_instant_survives_zone_change_and_preserves_fold(db_session):
    a = await seed(db_session)
    _, saved, _ = await schedules.update(db_session, a.order.id, a.owner,
        body(a.order, scheduled_start_local=None, promised_finish_local="2026-11-01T01:30", promised_finish_fold=1))
    await db_session.commit()
    assert saved.promised_finish_fold == 1
    a.tenant.timezone = "America/Los_Angeles"
    await db_session.commit()
    changed = await schedules.read(db_session, a.order.id, a.owner)
    assert changed.promised_finish_at == saved.promised_finish_at
    assert changed.promised_finish_local == "2026-10-31T23:30" and changed.promised_finish_fold is None


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(UserRole))
async def test_role_boundary_before_lookup(db_session, role):
    a = await seed(db_session)
    actor = SimpleNamespace(role=role, tenant_id=a.tenant.id, id=a.owner.id)
    if role not in ops.STAFF:
        await fails(403, None, schedules.update(db_session, uuid4(), actor, body(a.order)))
    if role not in ops.STAFF | {UserRole.MECHANIC}:
        await fails(403, None, schedules.read(db_session, uuid4(), actor))
    if role in ops.STAFF:
        await fails(404, None, schedules.update(db_session, uuid4(), actor, body(a.order)))


@pytest.mark.asyncio
async def test_tenant_mechanic_and_fleet_scopes(db_session):
    a = await seed(db_session)
    other = SimpleNamespace(role=UserRole.GARAGE_OWNER, tenant_id=uuid4(), id=a.owner.id)
    await fails(404, None, schedules.read(db_session, a.order.id, other))
    await fails(404, None, schedules.update(db_session, a.order.id, other, body(a.order)))
    assert not (await schedules.read(db_session, a.order.id, a.helper)).can_edit
    await fails(403, None, schedules.update(db_session, a.order.id, a.helper, body(a.order)))
    outsider = SimpleNamespace(role=UserRole.MECHANIC, tenant_id=a.tenant.id, id=uuid4())
    await fails(403, None, schedules.read(db_session, a.order.id, outsider))
    fleet = SimpleNamespace(role=UserRole.FLEET_MANAGER, tenant_id=a.tenant.id, id=a.owner.id, first_name="Fleet", last_name="Manager")
    await fails(403, None, schedules.read(db_session, a.order.id, fleet))
    a.order.is_fleet_work = True
    await db_session.commit()
    assert (await schedules.read(db_session, a.order.id, fleet)).can_edit
    await schedules.update(db_session, a.order.id, fleet, body(a.order))


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["completed", "invoiced", "paid", "cancelled", "released", "deleted", "held", "quote_lock", "pricing_lock", "declined"])
async def test_lifecycle_exact_schedule_locks(db_session, case):
    a = await seed(db_session)
    if case in {s.value for s in Status}:
        a.order.status = Status(case)
    elif case == "released":
        a.order.vehicle_released_at = NOW
    elif case == "deleted":
        a.order.deleted_at = NOW
    elif case == "held":
        a.order.hold_reason = "waiting_for_parts"
    else:
        a.order.pricing_locked_at = NOW
        a.order.pricing_lock_reason = "quote_sent" if case == "quote_lock" else "invoice_created"
    await db_session.commit()
    await db_session.refresh(a.order)
    if case == "deleted":
        await fails(404, None, schedules.read(db_session, a.order.id, a.owner))
        await fails(404, None, schedules.update(db_session, a.order.id, a.owner, body(a.order)))
    elif case in {"completed", "invoiced", "paid", "cancelled", "released"}:
        assert not (await schedules.read(db_session, a.order.id, a.owner)).can_edit
        await fails(409, "schedule_locked", schedules.update(db_session, a.order.id, a.owner, body(a.order)))
    else:
        _, saved, _ = await schedules.update(db_session, a.order.id, a.owner, body(a.order))
        assert saved.can_edit


async def schedule_projection(db, orders):
    for order in orders:
        await db.refresh(order)
        projection = await db.get(RepairOrderReadModel, order.id)
        projection.payload = RepairOrderResponse.model_validate(order).model_dump(mode="json")
        projection.status = order.status.value
        projection.is_deleted = bool(order.deleted_at)
    await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", [False, True])
async def test_complete_overdue_paging_count_value_and_tenant_filters(client, db_session, monkeypatch, fallback):
    tenant, owner, customer, vehicle, orders = await _seed_shop(db_session, count=32, total=Decimal("12.34"))
    await _seed_shop(db_session, count=2, total=Decimal("999.00"))
    monkeypatch.setattr(schedules, "now_utc", lambda: NOW)
    for i, order in enumerate(orders):
        order.promised_finish_at = NOW - timedelta(hours=2 if i < 30 else 1)
    orders[0].hold_reason = "waiting_for_parts"
    orders[1].status = Status.PENDING_REVIEW
    orders[1].work_completed_at = NOW - timedelta(minutes=5)
    orders[28].status = Status.DECLINED
    orders[29].status = Status.COMPLETED
    orders[30].vehicle_released_at = NOW
    orders[31].deleted_at = NOW
    await db_session.commit()
    await schedule_projection(db_session, orders)
    if fallback:
        await db_session.execute(delete(RepairOrderReadModel))
        await db_session.commit()
    params = {"overdue": "true", "paginated": "true", "limit": 25, "customer_id": str(customer.id), "vehicle_id": str(vehicle.id)}
    first = await client.get("/api/v1/repair-orders", params=params, headers=_headers(owner, tenant))
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["total"] == 28 and len(data["items"]) == 25
    expected = sorted((o for o in orders if schedules.is_overdue(o, NOW)), key=lambda o: (o.promised_finish_at, o.id))
    assert [r["id"] for r in data["items"]] == [str(o.id) for o in expected[:25]]
    assert all(r["schedule_timezone"] == "America/New_York" and r["is_overdue"] for r in data["items"])
    second = await client.get("/api/v1/repair-orders", params={**params, "skip": 25}, headers=_headers(owner, tenant))
    assert [r["id"] for r in second.json()["items"]] == [str(o.id) for o in expected[25:]]
    counts = await client.get("/api/v1/repair-orders/status-counts", params=params, headers=_headers(owner, tenant))
    assert counts.json() == {"all": 28, "in_progress": 27, "pending_review": 1}
    value = await client.get("/api/v1/repair-orders/value-summary", params=params, headers=_headers(owner, tenant))
    assert value.json()["order_count"] == 28 and value.json()["order_value"] == "345.52"
    for extra in [{"deleted": "true"}, {"customer_id": str(uuid4())}, {"status": "completed"}]:
        result = await client.get("/api/v1/repair-orders", params={**params, **extra}, headers=_headers(owner, tenant))
        assert result.json()["total"] == 0
        value = await client.get("/api/v1/repair-orders/value-summary", params={**params, **extra}, headers=_headers(owner, tenant))
        assert value.json()["order_count"] == 0
    if not fallback:  # Full pg_trgm legacy search also has a real PostgreSQL case.
        result = await client.get("/api/v1/repair-orders", params={**params, "search": orders[0].order_number}, headers=_headers(owner, tenant))
        assert result.json()["total"] == 1
        value = await client.get("/api/v1/repair-orders/value-summary", params={**params, "search": orders[0].order_number}, headers=_headers(owner, tenant))
        assert value.json()["order_count"] == 1 and value.json()["order_value"] == "12.34"


@pytest.mark.asyncio
async def test_generic_customer_routes_mask_schedule_and_history(client, db_session, monkeypatch):
    a = await seed(db_session)
    monkeypatch.setattr(routes, "broadcast_repair_order_update", AsyncMock())
    await routes.update_repair_order_schedule(a.order.id, body(a.order), db_session, a.owner)
    actor = SimpleNamespace(role=UserRole.CUSTOMER, customer_id=a.customer.id, tenant_id=a.tenant.id)
    for loader in [routes.get_repair_order, routes.get_repair_order_workspace, routes.get_repair_order_detail]:
        response = await loader(a.order.id, db_session, actor)
        assert response.scheduled_start_at is None and response.promised_finish_at is None
        assert response.schedule_timezone is None and not response.is_overdue
        if hasattr(response, "history_events"):
            assert not any(e.event_type == "schedule_changed" for e in response.history_events)
    for loader in [routes.list_repair_orders, routes.repair_order_status_counts, routes.repair_order_value_summary]:
        await fails(403, None, loader(customer_id=None, vehicle_id=None, deleted=False, overdue=True, search=None, db=db_session, current_user=actor))


@pytest.mark.asyncio
async def test_workspace_source_dates_override_old_projection_without_backfill(db_session, monkeypatch):
    a = await seed(db_session)
    monkeypatch.setattr(schedules, "now_utc", lambda: NOW)
    payload = RepairOrderResponse.model_validate(a.order).model_dump(mode="json")
    db_session.add(RepairOrderReadModel(repair_order_id=a.order.id, tenant_id=a.tenant.id,
        customer_id=a.customer.id, vehicle_id=a.vehicle.id, status=a.order.status.value,
        is_internal=False, is_deleted=False, created_at=a.order.created_at,
        search_document=a.order.order_number, search_compact=a.order.order_number, payload=payload))
    await db_session.commit()
    await schedules.update(db_session, a.order.id, a.owner, body(a.order))
    await db_session.commit()
    saved = await routes.get_repair_order_workspace(a.order.id, db_session, a.owner)
    assert saved.promised_finish_at == datetime(2026, 10, 16, 21, tzinfo=UTC)
    assert saved.schedule_timezone == "America/New_York" and saved.is_overdue
    queue = await dashboard.get_dashboard_daily_workset(db_session, a.owner)
    row = next(item for item in queue.on_floor.items if item.id == str(a.order.id))
    assert row.is_overdue and row.schedule_timezone == saved.schedule_timezone
    assert row.promised_finish_at.replace(tzinfo=UTC) == saved.promised_finish_at


@pytest.mark.asyncio
async def test_dashboard_masks_schedules_outside_exact_order_scope(db_session, monkeypatch):
    a = await seed(db_session)
    monkeypatch.setattr(schedules, "now_utc", lambda: NOW)
    a.order.promised_finish_at = NOW - timedelta(hours=1)
    other = RepairOrder(tenant_id=a.tenant.id, customer_id=a.customer.id, vehicle_id=a.vehicle.id,
        order_number=f"PRIVATE-{uuid4().hex}", status=Status.IN_PROGRESS,
        promised_finish_at=NOW - timedelta(hours=2), total_cost=Decimal("1.00"))
    db_session.add(other)
    await db_session.commit()
    # Mechanic helper has exact access through an operation assignment only.
    for loader in [dashboard.get_dashboard_action_queue, dashboard.get_dashboard_daily_workset, dashboard.get_dashboard_stats]:
        result = await loader(db_session, a.helper)
        rows = result.on_floor.items if hasattr(result, "on_floor") else result.orders_on_floor
        allowed = next(row for row in rows if row.id == str(a.order.id))
        hidden = next(row for row in rows if row.id == str(other.id))
        assert allowed.is_overdue and allowed.promised_finish_at is not None
        assert hidden.promised_finish_at is None and hidden.scheduled_start_at is None
        assert hidden.schedule_timezone is None and not hidden.is_overdue
        if hasattr(result, "recent_orders"):
            hidden = next(row for row in result.recent_orders if row.id == str(other.id))
            assert hidden.promised_finish_at is None and not hidden.is_overdue
    fleet = SimpleNamespace(role=UserRole.FLEET_MANAGER, tenant_id=a.tenant.id, id=a.owner.id)
    a.order.is_fleet_work = True
    await db_session.commit()
    result = await dashboard.get_dashboard_action_queue(db_session, fleet)
    rows = {row.id: row for row in result.orders_on_floor}
    assert rows[str(a.order.id)].promised_finish_at is not None
    assert rows[str(other.id)].promised_finish_at is None
    driver = SimpleNamespace(role=UserRole.DRIVER, tenant_id=a.tenant.id, id=a.owner.id)
    result = await dashboard.get_dashboard_action_queue(db_session, driver)
    assert all(row.promised_finish_at is None and not row.is_overdue for row in result.orders_on_floor)
