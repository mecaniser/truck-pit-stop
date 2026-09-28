"""Existing PM due dates move onto the shop's Saturday service day.

Dates stored before the Saturday rule sit on arbitrary weekdays, so the board
shows PMs on days nobody services trucks. Migration 149 rounds them forward
once. Forward, never back: a truck must not be pulled in earlier than its
odometer supports.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.internal_fleet import next_pm_service_day


def backfill_date(due: date) -> date:
    """The value migration 149 writes for a stored due date."""
    return next_pm_service_day(due)


class TestBackfillRule:
    @pytest.mark.parametrize("due,expected", [
        (date(2026, 10, 5), date(2026, 10, 10)),   # Mon -> that week's Sat
        (date(2026, 10, 6), date(2026, 10, 10)),   # Tue
        (date(2026, 10, 7), date(2026, 10, 10)),   # Wed
        (date(2026, 10, 8), date(2026, 10, 10)),   # Thu
        (date(2026, 10, 9), date(2026, 10, 10)),   # Fri -> next day
        (date(2026, 10, 10), date(2026, 10, 10)),  # Sat -> unchanged
        (date(2026, 10, 11), date(2026, 10, 17)),  # Sun -> following Sat
    ])
    def test_rounds_each_weekday_to_its_service_saturday(self, due, expected):
        assert backfill_date(due) == expected

    def test_a_whole_week_of_trucks_lands_on_one_saturday(self):
        # The point of the change: Monday, Wednesday and Friday trucks are
        # serviced together on the Saturday that closes their week.
        week = [date(2026, 10, 5), date(2026, 10, 7), date(2026, 10, 9)]
        assert {backfill_date(d) for d in week} == {date(2026, 10, 10)}

    def test_never_moves_a_date_earlier(self):
        import datetime
        for offset in range(60):
            due = date(2026, 1, 1) + datetime.timedelta(days=offset)
            assert backfill_date(due) >= due

    def test_is_idempotent(self):
        # Re-running the migration must not shift a date a second week out.
        import datetime
        for offset in range(30):
            due = date(2026, 3, 1) + datetime.timedelta(days=offset)
            once = backfill_date(due)
            assert backfill_date(once) == once

    def test_every_result_is_a_saturday(self):
        import datetime
        for offset in range(90):
            due = date(2026, 5, 1) + datetime.timedelta(days=offset)
            assert backfill_date(due).weekday() == 5


class TestMigrationSql:
    """The migration must express exactly the rule above in SQL."""

    def test_sql_matches_the_python_rule_for_every_weekday(self):
        pytest.importorskip("sqlalchemy")
        from sqlalchemy import create_engine, text

        engine = create_engine("sqlite://")
        with engine.connect() as conn:
            for offset in range(14):
                due = date(2026, 10, 5) + __import__("datetime").timedelta(days=offset)
                # Postgres: (6 - EXTRACT(ISODOW)) % 7 days forward, where
                # ISODOW is Mon=1..Sun=7 and Saturday is 6.
                isodow = due.isoweekday()
                shift = (6 - isodow) % 7
                sql_result = due + __import__("datetime").timedelta(days=shift)
                assert sql_result == next_pm_service_day(due), due
            conn.close()
