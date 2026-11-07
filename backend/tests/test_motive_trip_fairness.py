"""Durable scheduling intent is fair under one-day capacity, never coverage."""
import json
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest

from scripts.motive_sync import trip_coverage as c, run_trip_worker as worker
from scripts.motive_sync.trip_runner import immutable_json


def scope():
    return c.scope('tenant', 'actor', 'company', 'Synthetic', '2026-10-01')


def reserve(root, expected, stamp, examined=None, **kwargs):
    history = c.automatic_history(root, expected, stamp)
    plan = c.plan_days(expected, stamp.astimezone(c.ZONE).date(), examined or {},
                       history=history, **kwargs)
    run = root / stamp.strftime('%Y%m%dT%H%M%SZ')
    run.mkdir(mode=0o700)
    immutable_json(run / 'plan.json', plan)
    if not kwargs.get('start') and not kwargs.get('end'):
        immutable_json(run / 'automatic-selection.json', c.selection_marker(plan, run.name, stamp))
    return plan


def test_six_one_day_capacity_restarts_progress_both_lanes(tmp_path):
    expected = scope()
    stamp = datetime(2026, 11, 7, 14, tzinfo=timezone.utc)
    examined = {}
    selections = []
    for index in range(6):
        # Read disk again each run; only one first date finishes before timeout.
        plan = reserve(tmp_path, expected, stamp + timedelta(minutes=index), examined)
        first = plan['days'][0]
        selections.append(first)
        examined[first] = {'status': 'verified' if first != '2026-11-07' else 'provisional',
                           'source_read_at': stamp.isoformat(), 'verified_at': stamp.isoformat()}
        assert len(plan['days']) <= 14
        assert any(d < '2026-11-05' for d in plan['days'][:2])
        assert any(d >= '2026-11-05' for d in plan['days'][:2])
    assert selections == ['2026-10-01', '2026-11-05', '2026-10-02',
                          '2026-11-06', '2026-10-03', '2026-11-07']


def test_rejected_first_days_rotate_and_later_unstarted_slots_are_not_markers(tmp_path):
    stamp = datetime(2026, 11, 7, 14, tzinfo=timezone.utc)
    plans = [reserve(tmp_path, scope(), stamp + timedelta(minutes=i), limit=3) for i in range(6)]
    assert [p['days'][0] for p in plans] == ['2026-10-01', '2026-11-05', '2026-10-02',
                                          '2026-11-06', '2026-10-03', '2026-11-07']
    assert c.verified_days(tmp_path, scope()) == {}
    assert c.summarize(scope(), {}, stamp.date())['complete_through'] is None
    assert all(len(p['days']) == 3 for p in plans)


def test_unresolved_days_rotate_when_unseen_backlog_drained(tmp_path):
    expected = {**scope(), 'baseline': '2026-11-01'}
    stamp = datetime(2026, 11, 7, 14, tzinfo=timezone.utc)
    examined = {f'2026-11-0{i}': {'status': 'examined_with_exclusions',
                 'verified_at': f'2026-11-0{i}T12:00:00Z'} for i in range(1, 5)}
    firsts = [reserve(tmp_path, expected, stamp+timedelta(minutes=i), examined)['days'][0] for i in range(6)]
    assert firsts[::2] == ['2026-11-01', '2026-11-02', '2026-11-03']


def test_explicit_ranges_do_not_change_automatic_first_lane_or_attempts(tmp_path):
    stamp = datetime(2026, 11, 7, 14, tzinfo=timezone.utc)
    reserve(tmp_path, scope(), stamp)
    manual = reserve(tmp_path, scope(), stamp+timedelta(minutes=1),
                     start='2026-10-03', end='2026-10-05')
    assert manual['days'] == ['2026-10-03', '2026-10-04', '2026-10-05']
    later = reserve(tmp_path, scope(), stamp+timedelta(minutes=2))
    assert later['days'][0] == '2026-11-05'
    assert len(c.automatic_history(tmp_path, scope(), stamp+timedelta(minutes=3))) == 2


@pytest.mark.parametrize('change', [
    {'scope': {**scope(), 'tenant_id': 'foreign'}}, {'version': True},
    {'first_day': '2026-10-02'}, {'first_lane': 'recent'}, {'run_id': 'other'},
    {'created_at': '2026-11-08T00:00:00Z'}, {'created_at': '2026-11-07T14:00:00'},
    {'plan_sha256': 'changed'}, {'unexpected': True},
])
def test_corrupt_or_foreign_marker_fails_closed(tmp_path, change):
    stamp = datetime(2026, 11, 7, 14, tzinfo=timezone.utc)
    reserve(tmp_path, scope(), stamp)
    path = next(tmp_path.glob('*/automatic-selection.json'))
    value = json.loads(path.read_text()); value.update(change)
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        c.automatic_history(tmp_path, scope(), stamp)


@pytest.mark.parametrize('kind', ['mode', 'symlink', 'directory_symlink', 'plan_tamper', 'malformed'])
def test_private_state_and_plan_binding_fail_closed(tmp_path, kind):
    stamp = datetime(2026, 11, 7, 14, tzinfo=timezone.utc)
    reserve(tmp_path, scope(), stamp)
    path = next(tmp_path.glob('*/automatic-selection.json'))
    if kind == 'mode':
        path.chmod(0o644)
    elif kind == 'symlink':
        saved = path.read_bytes(); path.unlink()
        target = tmp_path/'target'; target.write_bytes(saved); target.chmod(0o600)
        path.symlink_to(target)
    elif kind == 'directory_symlink':
        directory = path.parent
        actual = tmp_path/'actual'; directory.rename(actual)
        directory.symlink_to(actual, target_is_directory=True)
    elif kind == 'plan_tamper':
        path.with_name('plan.json').write_text('{}')
    else:
        path.write_text('{')
    with pytest.raises(ValueError):
        c.automatic_history(tmp_path, scope(), stamp)


def test_legacy_unmarked_plans_do_not_invent_history(tmp_path):
    run = tmp_path/'old'; run.mkdir()
    immutable_json(run/'plan.json', {'old': 'legacy-not-fairness-authority'})
    assert c.automatic_history(tmp_path, scope(), datetime.now(timezone.utc)) == []


def test_recovery_failure_creates_no_selection_or_provider_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv('MOTIVE_TRIPS_STATE_DIR', str(tmp_path))
    def blocked(_):
        raise RuntimeError('Unresolved exact receipt')
    monkeypatch.setattr(worker, 'recover_pending', blocked)
    calls = []
    monkeypatch.setattr(worker, 'read_process', lambda *args, **kwargs: calls.append(args))
    with pytest.raises(RuntimeError, match='Unresolved'):
        worker.main()
    assert not calls and not list(tmp_path.glob('*/automatic-selection.json'))


def test_minimum_maximum_bounds_and_explicit_dst_dates():
    for limit in (3, 14, 31):
        assert len(c.plan_days(scope(), date(2026, 11, 7), {}, limit=limit)['days']) == limit
    for limit in (2, 32):
        with pytest.raises(ValueError):
            c.plan_days(scope(), date(2026, 11, 7), {}, limit=limit)
    assert c.plan_days(scope(), date(2026, 11, 7), {}, start='2026-10-31', end='2026-11-02')['days'] == [
        '2026-10-31', '2026-11-01', '2026-11-02']


def test_closed_verified_skipped_but_provisional_and_mapping_reopened_eligible():
    expected = {**scope(), 'baseline': '2026-11-01'}
    examined = {
        '2026-11-01': {'status': 'verified', 'source_read_at': '2026-11-02T05:00:00Z'},
        '2026-11-05': {'status': 'verified', 'source_read_at': '2026-11-06T05:00:00Z'},
        '2026-11-06': {'status': 'provisional', 'source_read_at': '2026-11-06T23:00:00Z'},
    }
    plan = c.plan_days(expected, date(2026, 11, 7), examined)
    assert '2026-11-01' not in plan['days'] and '2026-11-05' not in plan['days']
    assert '2026-11-06' in plan['days']
    assert c.plan_days(expected, date(2026, 11, 7), {})['days'][0] == '2026-11-01'
    examined['2026-11-01']['source_read_at'] = '2026-11-02T04:59:59Z'
    assert '2026-11-01' in c.plan_days(expected, date(2026, 11, 7), examined)['days']


def test_worker_records_first_intent_before_one_collection_and_restarts(tmp_path, monkeypatch):
    monkeypatch.setenv('MOTIVE_TRIPS_STATE_DIR', str(tmp_path))
    for key, value in dict(MOTIVE_SYNC_TENANT_ID='tenant', MOTIVE_SYNC_ACTOR_ID='actor',
        MOTIVE_COMPANY_ID='company', MOTIVE_COMPANY_LABEL='Synthetic',
        MOTIVE_TRIPS_BASELINE='2026-10-01', MOTIVE_TRIPS_FROM='', MOTIVE_TRIPS_TO='').items():
        monkeypatch.setenv(key, value)
    calls = []
    def fail(command, **kwargs):
        plan_path = kwargs['env']['MOTIVE_TRIPS_PLAN_FILE']
        from pathlib import Path
        marker_path = Path(plan_path).with_name('automatic-selection.json')
        assert marker_path.exists() and marker_path.stat().st_mode & 0o777 == 0o600
        plan = json.loads(Path(plan_path).read_text())
        calls.append(plan['days'][0])
        raise subprocess.CalledProcessError(1, 'synthetic')
    monkeypatch.setattr(worker, 'read_process', fail)
    for _ in range(2):
        with pytest.raises(SystemExit):
            worker.main()
    assert len(calls) == 2
    assert (calls[0] < (datetime.now(c.ZONE).date()-timedelta(days=2)).isoformat()
            and calls[1] >= (datetime.now(c.ZONE).date()-timedelta(days=2)).isoformat())
    assert c.verified_days(tmp_path, scope()) == {}
