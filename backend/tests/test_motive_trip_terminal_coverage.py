"""Authorization exclusions are settled only with closed, current-scope proof."""
import json
from datetime import date

import pytest
from scripts.motive_sync import trip_coverage as c
from tests.test_motive_trip_catchup import save_evidence, scope


def excluded(day='2026-04-01'):
    return dict(day=day, status='examined_with_exclusions', verified_at='2026-10-26T00:00:00Z',
        source_read_at='2026-10-25T23:59:00Z', providers=[dict(provider_vehicle_id='5981300',
        status='ineligible', eligibility='outside_membership', eligible_count=0,
        eligible_from='2026-10-16T21:42:51Z', exclusions=['outside_membership'])])


def test_terminal_days_do_not_take_retry_slots_and_cursors_remain_distinct():
    expected = {**scope(), 'baseline': '2026-10-20'}
    examined = {f'2026-10-{d}': excluded(f'2026-10-{d}') for d in (20,21,22)}
    for value in examined.values():
        value['providers'][0]['eligible_from'] = '2026-10-24T04:00:00Z'
    plan = c.plan_days(expected, date(2026,10,26), examined)
    assert plan['days'] == ['2026-10-23','2026-10-24','2026-10-25','2026-10-26']
    summary = c.summarize(expected, examined, date(2026,10,26))
    assert summary['complete_through'] is None and summary['reconciled_through'] == '2026-10-22'
    assert summary['unresolved_days'] == [] and summary['ineligible_days'] == sorted(examined)
    assert c.plan_days(expected, date(2026,10,26), examined, start='2026-10-20', end='2026-10-21')['days'] == ['2026-10-20','2026-10-21']


def test_mixed_full_day_saved_empty_and_ineligible_are_terminal():
    item = excluded()
    item['providers'] += [dict(provider_vehicle_id='2', status='verified_saved', eligibility='full_day', eligible_count=3, exclusions=[]),
                          dict(provider_vehicle_id='3', status='verified_empty', eligibility='full_day', eligible_count=0, exclusions=[])]
    assert c.terminal_ineligible(item['day'], item)
    assert item['providers'][0]['exclusions'] == ['outside_membership']


@pytest.mark.parametrize('change', [
    {'status':'unresolved'}, {'eligibility':'partial_day'}, {'eligible_count':1},
    {'eligible_count':False}, {'eligible_from':'2026-04-01T23:00:00Z'},
    {'eligible_from':'2026-04-02T04:00:00'}, {'eligible_from':None},
    {'exclusions':['outside_membership','ongoing']}, {'exclusions':['conflicting_source_identity']},
    {'provider_vehicle_id':None},
])
def test_uncertain_or_partly_eligible_provider_never_terminal(change):
    item = excluded(); item['providers'][0].update(change)
    assert not c.terminal_ineligible(item['day'], item)


@pytest.mark.parametrize('status', ['provisional','unresolved','examined'])
def test_other_day_status_never_promoted(status):
    item=excluded();item['status']=status
    assert not c.terminal_ineligible(item['day'],item)


def test_any_partial_or_missing_provider_blocks_terminal_day():
    item=excluded()
    item['providers'].append(dict(provider_vehicle_id='2', status='verified_saved', eligibility='partial_day', eligible_count=2, exclusions=[]))
    assert not c.terminal_ineligible(item['day'],item)
    item['providers'][-1]={'provider_vehicle_id':None,'status':'unresolved','exclusions':['absent_from_source_directory']}
    assert not c.terminal_ineligible(item['day'],item)


@pytest.mark.parametrize('day,end', [('2026-11-01','2026-11-02T05:00:00Z'),('2026-03-08','2026-03-09T04:00:00Z')])
def test_dst_day_end_requires_source_closure(day,end):
    item=excluded(day);item['providers'][0]['eligible_from']=end;item['source_read_at']=end
    assert c.terminal_ineligible(day,item)
    from datetime import datetime,timedelta
    item['source_read_at']=(datetime.fromisoformat(end.replace('Z','+00:00'))-timedelta(seconds=1)).isoformat()
    assert not c.terminal_ineligible(day,item)
    item.pop('source_read_at')
    assert not c.terminal_ineligible(day,item)


def rewrite_terminal(directory, day, mapping):
    source=json.loads((directory/'source.json').read_text())
    source['windows'][0]['source_read_at']='2026-10-25T23:59:00Z'
    normalized=json.loads((directory/'receipt.json.normalized.json').read_text())
    coverage={**excluded(day),'scope':scope(),'mapping_sha256':mapping}
    coverage.pop('verified_at');coverage.pop('source_read_at')
    normalized.update(coverage=coverage,source_sha256=c.digest(source))
    receipt=json.loads((directory/'receipt.json').read_text())
    receipt.update(coverage=coverage,source_sha256=c.digest(source),normalized_sha256=c.digest(normalized))
    for name,value in [('source.json',source),('receipt.json.normalized.json',normalized),('receipt.json',receipt)]:
        (directory/name).write_text(json.dumps(value))


def test_terminal_classification_uses_hash_bound_source_and_mapping_invalidation(tmp_path):
    first=save_evidence(tmp_path,'2026-04-01',mapping='old')
    rewrite_terminal(first,'2026-04-01','old')
    found=c.verified_days(tmp_path,scope())
    assert c.terminal_ineligible('2026-04-01',found['2026-04-01'])
    second=save_evidence(tmp_path,'2026-10-20',mapping='new')
    receipt=json.loads((second/'receipt.json').read_text());receipt['verified_at']='2026-10-26T01:00:00Z'
    (second/'receipt.json').write_text(json.dumps(receipt))
    assert '2026-04-01' not in c.verified_days(tmp_path,scope())
