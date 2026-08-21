from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event

from app.api.v1.endpoints import dashboard
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None


class _FakeDB:
    def __init__(self, results):
        self._results = iter(results)
        self.execute_count = 0

    async def execute(self, _statement):
        self.execute_count += 1
        return next(self._results)


def _summary() -> dict:
    return {
        "date": "2026-07-22",
        "timezone": "America/New_York",
        "shift_start_local": "08:00",
        "shift_end_local": "18:00",
        "core_target_minutes": 480,
        "tracked_minutes": 0,
        "ro_minutes": 0,
        "misc_minutes": 0,
        "overtime_minutes": 0,
        "utilization_percent": 0.0,
        "efficiency_percent": None,
        "book_hours": 0.0,
        "actual_ro_hours": 0.0,
        "active_session": None,
        "attendance_active": False,
        "attendance_started_at": None,
        "attendance_ended_at": None,
        "break_active": False,
        "break_started_at": None,
        "attendance_minutes": 0,
        "break_minutes": 0,
        "idle_minutes": 0,
        "late_arrival_minutes": 0,
        "early_leave_minutes": 0,
        "flex_budget_minutes": 120,
        "flex_used_minutes": 0,
        "flex_remaining_minutes": 120,
        "flex_overrun_minutes": 0,
        "core_gap_minutes": 480,
        "core_countdown_elapsed_minutes": 0,
        "core_countdown_remaining_minutes": 480,
        "tracked_vs_attendance_gap_minutes": 0,
        "work_coverage_percent": None,
    }


@pytest.mark.asyncio
async def test_team_mechanics_board_does_not_compute_unused_history(monkeypatch):
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Test Shop",
        slug=f"test-{tenant_id.hex[:8]}",
        timezone="America/New_York",
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
    )
    db = _FakeDB([_ScalarResult([mechanic]), _ScalarResult([tenant]), _ScalarResult([])])

    async def _compute_day_summary(*_args, **_kwargs):
        return _summary()

    async def _recommendation(*_args, **_kwargs):
        return {
            "assigned_ready_orders_count": 0,
            "untimed_in_progress_orders_count": 0,
            "held_orders_count": 0,
            "held_orders": [],
            "recommended_order_id": None,
            "recommended_order_number": None,
            "suggested_next_action": "clock_in",
        }

    async def _unexpected_trend(*_args, **_kwargs):
        raise AssertionError("team board must not compute per-mechanic history")

    monkeypatch.setattr(dashboard, "compute_day_summary", _compute_day_summary)
    monkeypatch.setattr(dashboard, "compute_next_action_recommendation", _recommendation)
    monkeypatch.setattr(dashboard, "compute_7day_trend", _unexpected_trend)

    response = await dashboard.get_team_mechanics_board(db=db, current_user=manager)

    assert db.execute_count == 3
    assert len(response.mechanics) == 1
    assert response.mechanics[0].trend_7_days == []


@pytest.mark.asyncio
async def test_dashboard_stats_stays_within_query_budget(db_session):
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Query Budget Shop",
        slug=f"budget-{tenant_id.hex[:8]}",
        timezone="America/New_York",
    )
    manager = User(
        id=uuid4(),
        tenant_id=tenant_id,
        role=UserRole.GARAGE_OWNER,
        email="budget-owner@example.com",
        hashed_password="hashed-password",
        first_name="Budget",
        last_name="Owner",
        is_active=True,
    )
    db_session.add_all([tenant, manager])
    await db_session.commit()

    query_count = 0

    def _count_query(*_args):
        nonlocal query_count
        query_count += 1

    sync_engine = db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _count_query)
    try:
        response = await dashboard.get_dashboard_stats(db=db_session, current_user=manager)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _count_query)

    assert response.total_customers == 0
    assert response.total_repair_orders == 0
    assert query_count == 12


@pytest.mark.asyncio
async def test_dashboard_action_queue_stays_within_query_budget(db_session):
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Action Queue Shop",
        slug=f"action-queue-{tenant_id.hex[:8]}",
        timezone="America/New_York",
    )
    manager = User(
        id=uuid4(),
        tenant_id=tenant_id,
        role=UserRole.GARAGE_OWNER,
        email="action-queue-owner@example.com",
        hashed_password="hashed-password",
        first_name="Action",
        last_name="Owner",
        is_active=True,
    )
    db_session.add_all([tenant, manager])
    await db_session.commit()

    query_count = 0

    def _count_query(*_args):
        nonlocal query_count
        query_count += 1

    sync_engine = db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _count_query)
    try:
        response = await dashboard.get_dashboard_action_queue(db=db_session, current_user=manager)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _count_query)

    assert response.orders_needing_action == []
    assert response.orders_on_floor == []
    assert response.orders_ready_to_close == []
    # One tenant lookup plus the four action-lane queries. Keep the home screen
    # bounded as the tenant's historical orders grow.
    assert query_count == 5


@pytest.mark.asyncio
async def test_dashboard_action_queue_bounds_each_lane_and_marks_overflow(db_session):
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Bounded Queue Shop",
        slug=f"bounded-queue-{tenant_id.hex[:8]}",
        timezone="America/New_York",
    )
    manager = User(
        id=uuid4(),
        tenant_id=tenant_id,
        role=UserRole.GARAGE_OWNER,
        email="bounded-queue-owner@example.com",
        hashed_password="hashed-password",
        first_name="Bounded",
        last_name="Owner",
        is_active=True,
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant_id,
        first_name="Queue",
        last_name="Customer",
        email="queue-customer@example.com",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant_id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2024,
    )
    orders = [
        RepairOrder(
            id=uuid4(),
            tenant_id=tenant_id,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            order_number=f"QUEUE-{number:04d}",
            status=RepairOrderStatus.IN_PROGRESS,
        )
        for number in range(dashboard.ACTION_QUEUE_LANE_LIMIT + 1)
    ]
    db_session.add_all([tenant, manager, customer, vehicle, *orders])
    await db_session.commit()

    response = await dashboard.get_dashboard_action_queue(db=db_session, current_user=manager)

    assert len(response.orders_on_floor) == dashboard.ACTION_QUEUE_LANE_LIMIT
    assert response.orders_on_floor_has_more is True
    assert response.orders_needing_action == []
    assert response.orders_ready_to_close == []


@pytest.mark.asyncio
async def test_dashboard_daily_workset_uses_tenant_local_paid_boundary(db_session):
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name="Daily Workset Shop",
        slug=f"daily-workset-{tenant_id.hex[:8]}",
        timezone="America/New_York",
    )
    manager = User(
        id=uuid4(),
        tenant_id=tenant_id,
        role=UserRole.GARAGE_OWNER,
        email="daily-workset-owner@example.com",
        hashed_password="hashed-password",
        first_name="Daily",
        last_name="Owner",
        is_active=True,
    )
    customer = Customer(
        id=uuid4(),
        tenant_id=tenant_id,
        first_name="Daily",
        last_name="Customer",
        email="daily-workset-customer@example.com",
    )
    vehicle = Vehicle(
        id=uuid4(),
        tenant_id=tenant_id,
        customer_id=customer.id,
        make="Freightliner",
        model="Cascadia",
        year=2024,
    )
    now = datetime.now(timezone.utc)
    closed_today = RepairOrder(
        id=uuid4(),
        tenant_id=tenant_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number="DAILY-CLOSED-TODAY",
        status=RepairOrderStatus.PAID,
    )
    closed_before_today = RepairOrder(
        id=uuid4(),
        tenant_id=tenant_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number="DAILY-CLOSED-YESTERDAY",
        status=RepairOrderStatus.PAID,
    )
    paid_at_missing = RepairOrder(
        id=uuid4(),
        tenant_id=tenant_id,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        order_number="DAILY-PAID-AT-MISSING",
        status=RepairOrderStatus.PAID,
    )
    db_session.add_all([
        tenant,
        manager,
        customer,
        vehicle,
        closed_today,
        closed_before_today,
        paid_at_missing,
        Invoice(
            id=uuid4(),
            tenant_id=tenant_id,
            repair_order_id=closed_today.id,
            invoice_number=f"INV-{uuid4().hex[:12]}",
            status=InvoiceStatus.PAID,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            paid_at=now,
        ),
        Invoice(
            id=uuid4(),
            tenant_id=tenant_id,
            repair_order_id=closed_before_today.id,
            invoice_number=f"INV-{uuid4().hex[:12]}",
            status=InvoiceStatus.PAID,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            paid_at=now - timedelta(days=1),
        ),
        Invoice(
            id=uuid4(),
            tenant_id=tenant_id,
            repair_order_id=paid_at_missing.id,
            invoice_number=f"INV-{uuid4().hex[:12]}",
            status=InvoiceStatus.PAID,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        ),
    ])
    await db_session.commit()

    response = await dashboard.get_dashboard_daily_workset(db=db_session, current_user=manager)

    assert response.timezone == "America/New_York"
    assert response.business_date == now.astimezone(ZoneInfo("America/New_York")).date()
    assert [order.order_number for order in response.closed_today.items] == ["DAILY-CLOSED-TODAY"]
    assert response.closed_today.items[0].paid_at is not None
