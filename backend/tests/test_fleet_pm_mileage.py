from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from app.services.fleet_pm import apply_pm_mileage

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def truck(**changes):
    reading = NS(value=660951, unit='mi', source='motive_dashboard_manual',
                 basis='dashboard_unspecified', observed_at=None, captured_at=NOW)
    base = dict(odometer=652767, next_pm_miles=677767, pm_remaining=25000,
                pm_days_remaining=None, work_order=None, status_override=None,
                status='active', telemetry=NS(odometer=reading))
    base.update(changes)
    return NS(**base)


def test_snapshot_counts_down_without_writing_service_or_target():
    t = truck()
    apply_pm_mileage(t, NOW)
    assert t.pm_remaining == 16816
    assert (t.odometer, t.next_pm_miles) == (652767, 677767)
    t.telemetry.odometer.value += 1000
    apply_pm_mileage(t, NOW)
    assert t.pm_remaining == 15816  # recompute, never subtract twice


@pytest.mark.parametrize('change', [dict(value=0), dict(value=-1), dict(value=float('nan')),
    dict(value=float('inf')), dict(value=652766), dict(basis='virtual'),
    dict(unit='h'), dict(captured_at=NOW-timedelta(days=31)),
    dict(captured_at=NOW+timedelta(minutes=6)), dict(captured_at=None),
    dict(source='motive_api', basis='dashboard_unspecified')])
def test_rejected_reading_falls_back(change):
    t = truck()
    t.telemetry.odometer.__dict__.update(change)
    apply_pm_mileage(t, NOW)
    assert t.pm_remaining == 25000


@pytest.mark.parametrize('remaining', [0, -100, 1000])
def test_due_overdue_and_soon(remaining):
    t = truck(next_pm_miles=660951+remaining)
    apply_pm_mileage(t, NOW)
    assert t.pm_remaining == remaining and t.status == 'pm'


def test_api_uses_observation_age_not_recent_receipt():
    t = truck()
    t.telemetry.odometer.source = 'motive_api'
    t.telemetry.odometer.basis = 'calibrated'
    t.telemetry.odometer.observed_at = NOW-timedelta(days=1)
    apply_pm_mileage(t, NOW)
    assert t.pm_remaining == 16816
    t.telemetry.odometer.observed_at = NOW-timedelta(days=31)
    apply_pm_mileage(t, NOW)
    assert t.pm_remaining == 25000


def test_unknown_service_missing_target_dates_and_overrides():
    t = truck(odometer=None)
    apply_pm_mileage(t, NOW)
    assert t.pm_remaining == 16816
    t.next_pm_miles = None
    apply_pm_mileage(t, NOW)
    assert t.pm_remaining is None
    t.pm_days_remaining = 0
    apply_pm_mileage(t, NOW)
    assert t.status == 'pm'
    for change in [dict(status='yard', status_override='yard'), dict(status='shop', work_order=NS())]:
        t.__dict__.update(change)
        apply_pm_mileage(t, NOW)
        assert t.status == change['status']
    t = truck(telemetry=None)
    apply_pm_mileage(t, NOW)
    assert t.pm_remaining == 25000
