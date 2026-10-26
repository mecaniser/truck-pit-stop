"""Older empty reports reopen; settled source-bound empty proof is mandatory."""
import json
from datetime import datetime, timedelta, timezone
import pytest
from scripts.motive_sync import trip_coverage as c
from scripts.motive_sync import trip_runner as r
from tests.test_motive_trip_worker import source
from tests.test_motive_trip_catchup import save_evidence, scope


def empty_window(window):
    window.update(status='empty',rows=[],expected_total=0,footerShown=0)
    read=datetime.fromisoformat(window['source_read_at'].replace('Z','+00:00'))
    window['empty_proof']=dict(version=1,date_evidence_kind='visible_date_controls',
        selected_start=window['start'],selected_end=window['end'],loading_absent=True,observations=13,
        first_observed_at=(read-timedelta(seconds=9)).isoformat(),last_observed_at=read.isoformat())
    return window


def test_source_empty_requires_proof():
    stamp=datetime.now(timezone.utc);document=source(stamp)
    window=empty_window(document['windows'][0]);assert c.valid_empty_proof(window)
    r.validate_source(document,'77 CARGO LLC','KT8934277',stamp)
    window.pop('empty_proof')
    with pytest.raises(ValueError,match='empty proof'):
        r.validate_source(document,'77 CARGO LLC','KT8934277',stamp)


@pytest.mark.parametrize('changes',[{'version':0},{'version':True},{'selected_start':'2026-01-01'},
    {'loading_absent':False},{'observations':12},{'observations':True},{'observations':121},
    {'date_evidence_kind':'url_only'},{'first_observed_at':'not-a-date'}])
def test_invalid_proof(changes):
    window=empty_window(source()['windows'][0]);window['empty_proof'].update(changes)
    assert not c.valid_empty_proof(window)


def test_short_future_unbound_or_populated_proof():
    window=empty_window(source()['windows'][0]);proof=window['empty_proof']
    proof['first_observed_at']=proof['last_observed_at'];assert not c.valid_empty_proof(window)
    window=empty_window(source()['windows'][0]);window['source_read_at']=datetime.now(timezone.utc).isoformat()
    assert not c.valid_empty_proof(window)
    window=empty_window(source()['windows'][0]);window['rows']=[{}]
    assert not c.valid_empty_proof(window)


def bind_source(directory,window):
    source_doc=json.loads((directory/'source.json').read_text());source_doc['windows']=[window]
    normalized=json.loads((directory/'receipt.json.normalized.json').read_text());normalized['source_sha256']=c.digest(source_doc)
    receipt=json.loads((directory/'receipt.json').read_text());receipt.update(source_sha256=c.digest(source_doc),normalized_sha256=c.digest(normalized))
    for name,value in [('source.json',source_doc),('receipt.json.normalized.json',normalized),('receipt.json',receipt)]:
        (directory/name).write_text(json.dumps(value))


def test_only_legacy_whole_report_empty_reopens(tmp_path):
    directory=save_evidence(tmp_path)
    window=empty_window(dict(start='2026-10-19',end='2026-10-19',source_read_at='2026-10-25T00:00:00Z'))
    bind_source(directory,window);assert '2026-10-19' in c.verified_days(tmp_path,scope())
    window.pop('empty_proof');bind_source(directory,window)
    assert c.verified_days(tmp_path,scope()) == {}
    # A populated report still proves zero rows for an individual mapped truck.
    window.update(status='captured',rows=[{'fixture':'populated'}],expected_total=1,footerShown=1)
    bind_source(directory,window);assert c.verified_days(tmp_path,scope()) == {}


def test_unproven_latest_empty_still_invalidates_older_mapping(tmp_path):
    old=save_evidence(tmp_path,mapping='old')
    bind_source(old,dict(start='2026-10-19',end='2026-10-19',source_read_at='2026-10-25T00:00:00Z',status='captured',rows=[{'fixture':'populated'}]))
    newer=save_evidence(tmp_path,day='2026-10-20',mapping='new')
    bind_source(newer,dict(start='2026-10-20',end='2026-10-20',source_read_at='2026-10-25T01:00:00Z',status='empty',rows=[]))
    path=newer/'receipt.json';receipt=json.loads(path.read_text());receipt['verified_at']='2026-10-26T01:00:00Z';path.write_text(json.dumps(receipt))
    assert c.verified_days(tmp_path,scope()) == {}


def test_unproven_latest_same_day_does_not_revive_previous_receipt(tmp_path):
    old=save_evidence(tmp_path)
    bind_source(old,dict(start='2026-10-19',end='2026-10-19',source_read_at='2026-10-25T00:00:00Z',status='captured',rows=[{'fixture':'populated'}]))
    newer=tmp_path/'run2'/'2026-10-19';newer.mkdir(parents=True)
    for path in old.iterdir():
        target=newer/path.name;target.write_bytes(path.read_bytes());target.chmod(0o600)
    bind_source(newer,dict(start='2026-10-19',end='2026-10-19',source_read_at='2026-10-25T01:00:00Z',status='empty',rows=[]))
    path=newer/'receipt.json';receipt=json.loads(path.read_text());receipt['verified_at']='2026-10-26T01:00:00Z';path.write_text(json.dumps(receipt))
    assert c.verified_days(tmp_path,scope()) == {}
