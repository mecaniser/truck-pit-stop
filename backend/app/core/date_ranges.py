"""Report date-range presets: this/last year, quarter, month, and week, plus
an explicit custom from/to range. Mirrors the preset list shop-management
competitors expose on their Reports pages, so garage owners get the same
familiar shortcuts (This Year, Last Month, etc.) instead of always typing
exact dates."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo


REPORT_DATE_PRESETS = {
    "this_year",
    "last_year",
    "this_quarter",
    "last_quarter",
    "this_month",
    "last_month",
    "this_week",
    "last_week",
    "custom",
}


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date  # inclusive


def _quarter_start(d: date) -> date:
    q_month = ((d.month - 1) // 3) * 3 + 1
    return date(d.year, q_month, 1)


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def resolve_date_range(
    preset: str,
    tenant_timezone: str,
    custom_from: Optional[date] = None,
    custom_to: Optional[date] = None,
) -> DateRange:
    """Resolve a report date-range preset to concrete start/end dates (inclusive),
    evaluated in the tenant's own timezone so "today" means the shop's today,
    not the server's UTC today."""
    tz = ZoneInfo(tenant_timezone or "America/New_York")
    today = datetime.now(tz).date()

    if preset == "custom":
        if not custom_from or not custom_to:
            raise ValueError("custom_from and custom_to are required when preset='custom'")
        return DateRange(start=custom_from, end=custom_to)

    if preset == "this_week":
        start = today - timedelta(days=today.weekday())
        return DateRange(start=start, end=today)
    if preset == "last_week":
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(days=7)
        end = this_week_start - timedelta(days=1)
        return DateRange(start=start, end=end)

    if preset == "this_month":
        start = today.replace(day=1)
        return DateRange(start=start, end=today)
    if preset == "last_month":
        this_month_start = today.replace(day=1)
        end = this_month_start - timedelta(days=1)
        start = end.replace(day=1)
        return DateRange(start=start, end=end)

    if preset == "this_quarter":
        start = _quarter_start(today)
        return DateRange(start=start, end=today)
    if preset == "last_quarter":
        this_q_start = _quarter_start(today)
        end = this_q_start - timedelta(days=1)
        start = _quarter_start(end)
        return DateRange(start=start, end=end)

    if preset == "this_year":
        start = date(today.year, 1, 1)
        return DateRange(start=start, end=today)
    if preset == "last_year":
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)
        return DateRange(start=start, end=end)

    raise ValueError(f"Unknown date range preset: {preset!r}")
