"""PM projection lands on the shop's PM day.

The shop does PM work on Saturdays. A projected due date of Wednesday is not a
day anyone will service the truck, so the projection rounds to the first
Saturday on or after the raw date - never before it, so the truck is never
scheduled earlier than the mileage supports.
"""
from __future__ import annotations

from datetime import date

from app.services.internal_fleet import PM_AVG_MILES_PER_DAY, project_pm_due_date


def _weekday(d: date) -> int:
    return d.weekday()  # Monday=0 ... Saturday=5


class TestProjectionLandsOnSaturday:
    def test_midweek_projection_moves_to_the_following_saturday(self):
        # 600 mi/day: 3000 miles remaining is 5 days out.
        # Mon 2026-10-05 + 5 days = Sat 2026-10-10, already a Saturday.
        due = project_pm_due_date(103000, 100000, from_date=date(2026, 10, 5))
        assert due == date(2026, 10, 10)

    def test_a_wednesday_projection_moves_forward_not_back(self):
        # Mon 2026-10-05 + 2 days = Wed 2026-10-07 -> Sat 2026-10-10.
        due = project_pm_due_date(101200, 100000, from_date=date(2026, 10, 5))
        assert due == date(2026, 10, 10)
        assert _weekday(due) == 5

    def test_a_sunday_projection_waits_a_full_week(self):
        # Mon 2026-10-05 + 6 days = Sun 2026-10-11. The next Saturday is the 17th.
        due = project_pm_due_date(103600, 100000, from_date=date(2026, 10, 5))
        assert due == date(2026, 10, 17)
        assert _weekday(due) == 5

    def test_a_saturday_projection_is_left_alone(self):
        due = project_pm_due_date(103000, 100000, from_date=date(2026, 10, 5))
        assert _weekday(due) == 5

    def test_every_projected_date_is_a_saturday(self):
        # Across a full week of start days and a range of mileages, the result
        # is always the shop's PM day.
        for start_offset in range(7):
            for miles in (600, 1200, 5000, 12000, 25000):
                due = project_pm_due_date(
                    100000 + miles, 100000, from_date=date(2026, 10, 5) + __import__('datetime').timedelta(days=start_offset)
                )
                assert _weekday(due) == 5, (start_offset, miles, due)

    def test_never_lands_before_the_raw_due_date(self):
        # Rounding forward protects the mileage contract: the truck is never
        # asked to come in sooner than the odometer supports.
        import datetime
        for miles in range(600, 12000, 600):
            raw = date(2026, 10, 5) + datetime.timedelta(days=-(-miles // PM_AVG_MILES_PER_DAY))
            due = project_pm_due_date(100000 + miles, 100000, from_date=date(2026, 10, 5))
            assert due >= raw


class TestOverdueSchedulesTheNextSaturday:
    def test_overdue_on_mileage_books_the_next_saturday(self):
        # Overdue used to project to today, which is rarely a PM day.
        due = project_pm_due_date(99000, 100000, from_date=date(2026, 10, 7))
        assert due == date(2026, 10, 10)

    def test_overdue_on_a_saturday_books_that_same_day(self):
        due = project_pm_due_date(99000, 100000, from_date=date(2026, 10, 10))
        assert due == date(2026, 10, 10)


class TestUnchangedBehaviour:
    def test_no_mileage_target_still_projects_nothing(self):
        assert project_pm_due_date(None, 100000, from_date=date(2026, 10, 5)) is None
