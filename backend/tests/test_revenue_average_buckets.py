from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.api.v1.endpoints import reports
from app.api.v1.endpoints.reports import _revenue_buckets, _revenue_interval
from app.core.date_ranges import DateRange
from app.db.models.user import UserRole


@pytest.mark.parametrize("preset,start,end,expected", [
    ("this_week", date(2026, 10, 19), date(2026, 10, 19), "day"),
    ("last_month", date(2026, 9, 1), date(2026, 9, 30), "day"),
    ("this_quarter", date(2026, 10, 1), date(2026, 10, 19), "week"),
    ("last_year", date(2025, 1, 1), date(2025, 12, 31), "month"),
    ("custom", date(2026, 1, 1), date(2026, 1, 31), "day"),
    ("custom", date(2026, 1, 1), date(2026, 2, 1), "week"),
    ("custom", date(2026, 1, 1), date(2026, 4, 30), "week"),
    ("custom", date(2026, 1, 1), date(2026, 5, 1), "month"),
])
def test_revenue_interval_follows_report_period(preset, start, end, expected):
    assert _revenue_interval(preset, DateRange(start, end)) == expected


def test_daily_buckets_include_zero_days_and_leap_day():
    buckets = _revenue_buckets(DateRange(date(2024, 2, 28), date(2024, 3, 1)), "day")
    assert [row[2] for row in buckets] == ["Feb 28", "Feb 29", "Mar 1"]
    assert len(buckets) == 3  # the UI's mean includes a zero-revenue day


def test_weekly_buckets_cover_partial_edges():
    buckets = _revenue_buckets(DateRange(date(2026, 10, 1), date(2026, 10, 19)), "week")
    assert buckets[0][:2] == (date(2026, 9, 28), date(2026, 10, 4))
    assert buckets[-1][:2] == (date(2026, 10, 19), date(2026, 10, 25))
    assert len(buckets) == 4


def test_monthly_buckets_cover_partial_edges_and_year_boundary():
    buckets = _revenue_buckets(DateRange(date(2025, 12, 15), date(2026, 2, 3)), "month")
    assert buckets == [
        (date(2025, 12, 15), date(2025, 12, 31), "Dec 2025"),
        (date(2026, 1, 1), date(2026, 1, 31), "Jan 2026"),
        (date(2026, 2, 1), date(2026, 2, 28), "Feb 2026"),
    ]


def test_shop_local_payment_day_places_receipt_in_selected_daily_bucket():
    rng = DateRange(date(2026, 10, 18), date(2026, 10, 19), "America/New_York")
    receipt = datetime(2026, 10, 19, 1, 0, tzinfo=timezone.utc)
    assert rng.local_date(receipt) == date(2026, 10, 18)
    assert _revenue_buckets(rng, "day")[0][0] == rng.local_date(receipt)


@pytest.mark.asyncio
@pytest.mark.parametrize("preset,end,second_day,expected_interval,expected_points", [
    ("custom", date(2026, 1, 3), 3, "day", ["10.00", "0.00", "20.00"]),
    ("last_year", date(2026, 12, 31), 3, "month", ["30.00"] + ["0.00"] * 11),
])
async def test_dashboard_revenue_trend_preserves_cash_total_tenant_scope_and_zero_buckets(
    monkeypatch, preset, end, second_day, expected_interval, expected_points,
):
    tenant_id = uuid4()
    order_id = uuid4()
    invoice_id = uuid4()
    rng = DateRange(date(2026, 1, 1), end, "UTC")
    monkeypatch.setattr(reports, "_resolve_range", AsyncMock(return_value=rng))
    payments = [
        SimpleNamespace(amount=Decimal("10.00"), created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        SimpleNamespace(amount=Decimal("20.00"), created_at=datetime(2026, 1, second_day, tzinfo=timezone.utc)),
    ]
    invoice = SimpleNamespace(
        id=invoice_id, total_amount=Decimal("30.00"), tax_amount=Decimal("0.00"),
        shop_supplies_amount=Decimal("0.00"), service_fee_amount=Decimal("0.00"),
    )
    order = SimpleNamespace(id=order_id, total_parts_cost=Decimal("0.00"), total_labor_cost=Decimal("30.00"))
    empty = SimpleNamespace(all=lambda: [])
    db = SimpleNamespace(execute=AsyncMock(side_effect=[
        SimpleNamespace(all=lambda: [(payment, invoice, order) for payment in payments]),
        empty, empty, empty, SimpleNamespace(scalar=lambda: Decimal("0.00")),
    ]))
    user = SimpleNamespace(role=UserRole.GARAGE_OWNER, tenant_id=tenant_id)

    result = await reports.get_reports_dashboard(preset, None, None, db, user)

    assert result.revenue_interval == expected_interval
    assert Decimal(result.revenue.value) == Decimal("30.00")
    assert [Decimal(point.value) for point in result.revenue.trend] == [Decimal(value) for value in expected_points]
    query = str(db.execute.call_args_list[0].args[0].compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert f"invoices.tenant_id = '{tenant_id}'" in query
    assert "payments.status = 'completed'" in query
