from datetime import date, datetime, timezone
import pytest
from app.core.date_ranges import DateRange, resolve_date_range

@pytest.mark.parametrize('zone,day,hours,start_hour', [
    ('America/New_York', date(2026, 9, 12), 24, 4),
    ('America/New_York', date(2026, 3, 8), 23, 5),
    ('America/New_York', date(2026, 11, 1), 25, 4),
    ('America/Chicago', date(2026, 9, 12), 24, 5),
    ('UTC', date(2026, 9, 12), 24, 0),
])
def test_local_day_utc_boundaries(zone, day, hours, start_hour):
    rng = resolve_date_range('custom', zone, day, day)
    assert rng.utc_start.hour == start_hour
    assert (rng.utc_end - rng.utc_start).total_seconds() == hours * 3600
    assert rng.local_date(rng.utc_start) == day
    assert rng.local_date(rng.utc_end) != day

def test_september_evening_receipt_stays_on_shop_day():
    rng = DateRange(date(2026, 9, 12), date(2026, 9, 12))
    receipt = datetime(2026, 9, 13, 0, 14, tzinfo=timezone.utc)
    assert rng.utc_start <= receipt < rng.utc_end
    assert rng.local_date(receipt) == date(2026, 9, 12)
    assert not rng.utc_start <= datetime(2026, 9, 13, 4, tzinfo=timezone.utc) < rng.utc_end

def test_positive_offset_crosses_previous_utc_day():
    rng = resolve_date_range('custom', 'Asia/Tokyo', date(2026, 9, 12), date(2026, 9, 12))
    assert rng.utc_start == datetime(2026, 9, 11, 15, tzinfo=timezone.utc)
