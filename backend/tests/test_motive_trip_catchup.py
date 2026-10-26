"""Catchup cannot infer coverage from row presence or skip an earlier hole."""
import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from scripts.motive_sync import trip_coverage as c
from scripts.motive_sync import trip_runner
from tests.test_motive_trip_worker import source


def scope():
    return c.scope('tenant', 'actor', 'KT8934277', '77 CARGO LLC', '2026-04-01')


def test_outage_and_holes_and_bound():
    today = date(2026, 10, 26)
    seen = {'2026-04-02': {'status': 'verified', 'verified_at': '2026-10-25'}}
    plan = c.plan_days(scope(), today, seen, 14)
    assert len(plan['days']) == 14
    assert plan['days'][0] == '2026-04-01'
    assert '2026-04-02' not in plan['days']
    assert plan['days'][-3:] == ['2026-10-24', '2026-10-25', '2026-10-26']
    assert c.summarize(scope(), seen, today)['complete_through'] is None


def test_explicit_backfill_limits():
    today = date(2026, 10, 26)
    assert c.plan_days(scope(), today, {}, start='2026-10-19', end='2026-10-20')['days'] == ['2026-10-19', '2026-10-20']
    for start, end in [('2026-03-31', '2026-04-01'), ('2026-10-01', '2026-10-26'), ('2026-10-26', '2026-10-27')]:
        with pytest.raises(ValueError):
            c.plan_days(scope(), today, {}, start=start, end=end)
    with pytest.raises(ValueError):
        c.plan_days(scope(), today, {}, 32)


def test_excluded_day_does_not_starve_backlog():
    seen = {'2026-04-01': {'status': 'examined_with_exclusions', 'verified_at': '2026-10-25'}}
    assert c.plan_days(scope(), date(2026, 10, 26), seen)['days'][0] == '2026-04-02'
    assert c.summarize(scope(), seen, date(2026, 10, 26))['unresolved_days'] == ['2026-04-01']


def test_oldest_unresolved_revisited_when_backlog_drains():
    expected = {**scope(), 'baseline': '2026-10-21'}
    seen = {f'2026-10-{d}': {'status': 'examined_with_exclusions', 'verified_at': f'2026-10-{d}'} for d in (21, 22, 23)}
    assert c.plan_days(expected, date(2026, 10, 26), seen, 4)['days'][0] == '2026-10-21'


def test_historical_source_requires_bound_exact_plan(monkeypatch):
    stamp = datetime.now(timezone.utc)
    document = source(stamp)
    old = (stamp.astimezone(c.ZONE).date()-timedelta(days=8)).isoformat()
    document['windows'] = [{**document['windows'][0], 'start': old, 'end': old, 'rows': [], 'status': 'empty', 'expected_total': 0, 'footerShown': 0}]
    document['plan'] = {'version': 1, 'scope': scope(), 'days': [old]}
    monkeypatch.setenv('MOTIVE_SYNC_TENANT_ID', 'tenant')
    monkeypatch.setenv('MOTIVE_SYNC_ACTOR_ID', 'actor')
    trip_runner.validate_source(document, '77 CARGO LLC', 'KT8934277', stamp)
    document['plan']['scope']['tenant_id'] = 'other'
    with pytest.raises(ValueError, match='scope'):
        trip_runner.validate_source(document, '77 CARGO LLC', 'KT8934277', stamp)


def save_evidence(root, day='2026-10-19', mapping='mapping'):
    expected = scope()
    coverage = dict(scope=expected, day=day, status='verified', providers=[], mapping_sha256=mapping)
    source = dict(plan={'version': 1, 'scope': expected, 'days': [day]}, windows=[{'start': day, 'end': day}], complete=True, company_verified_before=True, company_verified_after=True)
    normalized = dict(coverage=coverage, rows=[], source_sha256=c.digest(source), **{k: expected[k] for k in ('tenant_id', 'actor_id', 'company_id', 'company_label')})
    receipt = dict(coverage=coverage, mode='commit', committed=True, stage='verified', source_sha256=c.digest(source), normalized_sha256=c.digest(normalized), rows=[], readback_verified=0, replay_unchanged=0, verified_at='2026-10-26T00:00:00Z', tenant_id='tenant', actor_id='actor')
    directory = root/'run'/day
    directory.mkdir(parents=True)
    for name, value in [('source.json', source), ('receipt.json.normalized.json', normalized), ('receipt.json', receipt)]:
        path = directory/name
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    return directory


def test_verified_evidence_rebuild_and_tamper(tmp_path):
    directory = save_evidence(tmp_path)
    assert c.verified_days(tmp_path, scope())['2026-10-19']['status'] == 'verified'
    (directory/'source.json').write_text('{}')
    with pytest.raises(ValueError, match='evidence mismatch'):
        c.verified_days(tmp_path, scope())


def test_dry_or_unverified_receipt_cannot_close_day(tmp_path):
    directory = save_evidence(tmp_path)
    path = directory/'receipt.json'
    value = json.loads(path.read_text())
    value['stage'] = 'committed'
    path.write_text(json.dumps(value))
    assert c.verified_days(tmp_path, scope()) == {}


def test_changed_mapping_invalidates_old_certification(tmp_path):
    first = save_evidence(tmp_path, mapping='old')
    second = save_evidence(tmp_path, '2026-10-20', mapping='new')
    path = second/'receipt.json'
    value = json.loads(path.read_text()); value['verified_at'] = '2026-10-26T01:00:00Z'; path.write_text(json.dumps(value))
    assert list(c.verified_days(tmp_path, scope())) == ['2026-10-20']

@pytest.mark.asyncio
async def test_per_day_commit_replay_scope_and_provisional(_db_engine, db_session, monkeypatch, tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from tests.test_db036_fleet_telemetry import prepared
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = datetime.now(timezone.utc)-timedelta(days=30)
    await db_session.commit()
    expected = c.scope(actor.tenant_id, actor.id, 'KT8934277', '77 CARGO LLC', '2026-04-01')
    monkeypatch.setenv('MOTIVE_SYNC_TENANT_ID', str(actor.tenant_id))
    monkeypatch.setenv('MOTIVE_SYNC_ACTOR_ID', str(actor.id))
    factory = async_sessionmaker(_db_engine, expire_on_commit=False)
    document = source()
    today = datetime.now(c.ZONE).date()
    day = (today-timedelta(days=1)).isoformat()
    document['windows'][0].update(start=day, end=day)
    document['plan'] = {'version': 1, 'scope': expected, 'days': [day]}
    directory = tmp_path/'run'/day
    directory.mkdir(parents=True)
    trip_runner.immutable_json(directory/'source.json', document)
    args = factory, document, actor.tenant_id, actor.id, '77 CARGO LLC', 'KT8934277'
    receipt = await trip_runner.run(*args, directory/'receipt.json', True)
    assert receipt['coverage']['status'] == 'verified'
    assert receipt['coverage']['providers'][0]['status'] == 'verified_saved'
    assert c.verified_days(tmp_path, expected)[day]['status'] == 'verified'
    recovered = await trip_runner.recover(*args, directory/'receipt.json')
    assert recovered['rows'][0]['action'] == 'unchanged'
    assert recovered['rows'][0]['trip_id'] == receipt['rows'][0]['trip_id']
    # Empty current-day capture cannot certify zero activity for the full day.
    document = source()
    document['windows'][0].update(start=today.isoformat(), end=today.isoformat(), rows=[], status='empty', expected_total=0, footerShown=0)
    document['plan'] = {'version': 1, 'scope': expected, 'days': [today.isoformat()]}
    receipt = await trip_runner.run(factory, document, actor.tenant_id, actor.id, '77 CARGO LLC', 'KT8934277', tmp_path/'today.json', True)
    assert receipt['coverage']['status'] == 'provisional'
    assert receipt['coverage']['providers'][0]['status'] == 'provisional'


@pytest.mark.asyncio
async def test_absent_authorized_truck_remains_unresolved(_db_engine, db_session, monkeypatch, tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from tests.test_db036_fleet_telemetry import prepared
    actor, vehicle, member = await prepared(db_session, monkeypatch)
    member.effective_from = datetime.now(timezone.utc)-timedelta(days=30)
    await db_session.commit()
    monkeypatch.setenv('MOTIVE_SYNC_TENANT_ID', str(actor.tenant_id))
    monkeypatch.setenv('MOTIVE_SYNC_ACTOR_ID', str(actor.id))
    document = source()
    day = (datetime.now(c.ZONE).date()-timedelta(days=1)).isoformat()
    document['windows'][0].update(start=day, end=day, rows=[], status='empty', expected_total=0, footerShown=0)
    document['vehicles'][0]['vin'] = None
    document['plan'] = {'version': 1, 'scope': c.scope(actor.tenant_id, actor.id, 'KT8934277', '77 CARGO LLC', '2026-04-01'), 'days': [day]}
    receipt = await trip_runner.run(async_sessionmaker(_db_engine, expire_on_commit=False), document, actor.tenant_id, actor.id, '77 CARGO LLC', 'KT8934277', tmp_path/'absent.json', True)
    assert receipt['coverage']['status'] == 'examined_with_exclusions'
    assert any(p.get('vehicle_id') == str(vehicle.id) and p['exclusions'] == ['absent_from_source_directory'] for p in receipt['coverage']['providers'])


def test_mapping_order_is_irrelevant_but_identity_changes_invalidate():
    groups = [
        [{'provider_vehicle_id': '2', 'vin': 'vin2'}, {'provider_vehicle_id': '1', 'vin': 'vin1'}],
        [{'provider_vehicle_id': '2', 'effective_from': '2026-07-22'}, {'provider_vehicle_id': '1', 'effective_from': '2026-07-23'}],
        [{'provider_vehicle_id': '2', 'membership_id': 'm2', 'effective_to': None}, {'provider_vehicle_id': '1', 'membership_id': 'm1', 'effective_to': None}],
        [{'vehicle_id': 'v2', 'membership_id': 'm2'}, {'vehicle_id': 'v1', 'membership_id': 'm1'}],
    ]
    expected = c.mapping_digest(*groups)
    assert c.mapping_digest(*[list(reversed(rows)) for rows in groups]) == expected
    changed = copy.deepcopy(groups)
    changed[0][0]['vin'] = 'replacement'
    assert c.mapping_digest(*changed) != expected
    changed = copy.deepcopy(groups)
    changed[2][0]['effective_to'] = '2026-10-26'
    assert c.mapping_digest(*changed) != expected


def test_source_observation_controls_closed_day_across_dst():
    assert not c.day_closed('2026-10-25', '2026-10-26T03:59:59+00:00')
    assert c.day_closed('2026-10-25', '2026-10-26T04:00:00+00:00')
    assert not c.day_closed('2026-11-01', '2026-11-02T04:59:59+00:00')
    assert c.day_closed('2026-11-01', '2026-11-02T05:00:00+00:00')


@pytest.mark.asyncio
async def test_midnight_import_cannot_close_pre_midnight_capture(db_session, monkeypatch):
    from tests.test_db036_fleet_telemetry import prepared
    actor, _, member = await prepared(db_session, monkeypatch)
    member.effective_from = datetime.now(timezone.utc)-timedelta(days=30)
    await db_session.commit()
    today = datetime.now(c.ZONE).date()
    day = (today-timedelta(days=1)).isoformat()
    document = source()
    read = datetime.combine(today, datetime.min.time(), c.ZONE)-timedelta(seconds=1)
    document['windows'][0].update(start=day, end=day, source_read_at=read.isoformat(), rows=[], status='empty', expected_total=0, footerShown=0)
    document['plan'] = {'version': 1, 'scope': c.scope(actor.tenant_id, actor.id, 'KT8934277', '77 CARGO LLC', '2026-04-01'), 'days': [day]}
    _, report = await trip_runner.prepare(db_session, document, actor.tenant_id, actor.id, datetime.combine(today, datetime.min.time(), c.ZONE)+timedelta(minutes=1))
    assert report['coverage']['status'] == 'provisional'
    assert report['coverage']['providers'][0]['status'] == 'provisional'

@pytest.mark.asyncio
@pytest.mark.parametrize('boundary,eligibility,status', [('after', 'outside_membership', 'ineligible'), ('within', 'partial_day', 'verified_empty')])
async def test_empty_source_reports_membership_eligibility(db_session, monkeypatch, boundary, eligibility, status):
    from tests.test_db036_fleet_telemetry import prepared
    actor, _, member = await prepared(db_session, monkeypatch)
    today = datetime.now(c.ZONE).date()
    day = today-timedelta(days=2)
    member.effective_from = datetime.combine(day + timedelta(days=1) if boundary == 'after' else day, datetime.min.time(), c.ZONE) + timedelta(hours=12)
    await db_session.commit()
    document = source()
    document['windows'][0].update(start=day.isoformat(), end=day.isoformat(), rows=[], status='empty', expected_total=0, footerShown=0)
    document['plan'] = {'version': 1, 'scope': c.scope(actor.tenant_id, actor.id, 'KT8934277', '77 CARGO LLC', '2026-04-01'), 'days': [day.isoformat()]}
    _, report = await trip_runner.prepare(db_session, document, actor.tenant_id, actor.id, datetime.now(timezone.utc))
    assert report['coverage']['providers'][0]['eligibility'] == eligibility
    assert report['coverage']['providers'][0]['status'] == status
