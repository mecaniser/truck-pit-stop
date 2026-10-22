"""Configured countdowns and platform exits cannot hide missed executions."""

from datetime import UTC, datetime

from scripts.motive_sync.audit_runs import expected_slot, summarize


def test_daily_slot_detects_missed_run_despite_manual_attempt_the_previous_evening():
    now = datetime(2026, 10, 21, 18, 31, tzinfo=UTC)
    result = summarize(
        "DBN-motive-trips",
        [
            {
                "createdAt": "2026-10-20T21:52:22Z",
                "status": "CRASHED",
                "durationSeconds": 18,
            }
        ],
        now,
    )
    assert "scheduled_execution_missing" in result["alerts"]
    assert result["expected_slot_utc"] == "2026-10-21T09:15:00+00:00"


def test_150_seconds_is_evidence_request_not_an_invented_failure_cause():
    result = summarize(
        "DBN-motive-fuel",
        [
            {
                "createdAt": "2026-10-21T13:31:39Z",
                "status": "CRASHED",
                "durationSeconds": 150,
            }
        ],
        datetime(2026, 10, 21, 18, tzinfo=UTC),
    )
    assert result["alerts"] == [
        "latest_execution_crashed",
        "150_second_exit_needs_startup_evidence",
    ]
    assert result["import_verified"] is None


def test_scheduler_grace_and_utc_rollover():
    assert expected_slot(
        "DBN-motive-sync", datetime(2026, 10, 21, 0, 3, tzinfo=UTC)
    ) == datetime(2026, 10, 20, 23, 55, tzinfo=UTC)
    assert expected_slot(
        "DBN-motive-health", datetime(2026, 10, 21, 0, 31, tzinfo=UTC)
    ) == datetime(2026, 10, 20, 23, 30, tzinfo=UTC)
    result = summarize(
        "DBN-motive-sync",
        [{"createdAt": "2026-10-21T18:25:12Z", "status": "EXITED"}],
        datetime(2026, 10, 21, 18, 31, tzinfo=UTC),
    )
    assert result["alerts"] == []
    assert result["import_verified"] is None
