import copy
import json
from datetime import datetime, timezone
import pytest
from scripts.motive_sync.trip_populated_proof import valid_populated_proof
from scripts.motive_sync import trip_runner, trip_coverage
from tests.test_motive_trip_worker import source
from tests.test_motive_trip_catchup import save_evidence, scope
from tests.test_motive_trip_empty_proof import bind_source
from tests.motive_populated_fixture import prove


def test_valid_and_legacy_source_preimport():
    document = source()
    assert valid_populated_proof(document['windows'][0])
    del document['windows'][0]['populated_proof']
    with pytest.raises(ValueError, match='Populated response identity proof'):
        trip_runner.validate_source(document, '77 CARGO LLC', 'KT8934277', datetime.now(timezone.utc))


@pytest.mark.parametrize('change', [
    {'total': 2}, {'total': True}, {'response_identity_count': 2}, {'identity_sha256': '0'*64},
    {'origin': 'https://other.example'}, {'start': '2026-01-01'}, {'epoch': 'invalid'},
    {'first_observed_at': '2099-01-01T00:00:00Z'}, {'last_observed_at': '2000-01-01T00:00:00Z'},
    {'response_count': 0}, {'per_page': 0},
])
def test_invalid_populated_proof(change):
    window = source()['windows'][0]
    window['populated_proof'].update(change)
    assert not valid_populated_proof(window)


def test_identity_mismatch_equal_count():
    window = source()['windows'][0]
    window['rows'][0]['links'] = ['#/fleetview/vehicles/summary/999']
    assert not valid_populated_proof(window)


def test_legacy_populated_reopens_without_reviving_old_mapping(tmp_path):
    old = save_evidence(tmp_path, mapping='old')
    window = source()['windows'][0]
    window.update(start='2026-10-19', end='2026-10-19', source_read_at='2026-10-25T00:00:00Z')
    window['rows'][0]['cells'][1] = '10/19/2026 01:00 PM\nFixture'
    prove(window);bind_source(old, window)
    assert '2026-10-19' in trip_coverage.verified_days(tmp_path, scope())
    new = save_evidence(tmp_path, day='2026-10-20', mapping='new')
    legacy=copy.deepcopy(window);legacy.update(start='2026-10-20',end='2026-10-20');legacy.pop('populated_proof');bind_source(new,legacy)
    path=new/'receipt.json';receipt=json.loads(path.read_text());receipt['verified_at']='2026-10-26T01:00:00Z';path.write_text(json.dumps(receipt))
    assert trip_coverage.verified_days(tmp_path, scope()) == {}
    assert (old/'source.json').exists() and (new/'receipt.json').exists()


def test_ambiguous_dst_departure_rejected():
    window = source()['windows'][0]
    window['rows'][0]['cells'][1] = '11/01/2026 01:30 AM\nFixture'
    assert not valid_populated_proof(window)


def test_existing_timestamp_formats_have_identical_digest_and_importer_identity():
    from scripts.motive_sync.trip_populated_proof import row_identity, identities_digest
    from scripts.prepare_motive_trip_history import endpoint
    numeric = {'links': ['#/fleetview/vehicles/summary/1'], 'cells': ['', '09/01/2026 09:00 AM\nFixture']}
    named = copy.deepcopy(numeric)
    named['cells'][1] = 'Sep 1, 2026, 09:00 AM\nFixture'
    assert row_identity(named) == row_identity(numeric) == ['1', '2026-09-01T09:00']
    assert identities_digest([named]) == identities_digest([numeric])
    assert endpoint(named['cells'][1]) == endpoint(numeric['cells'][1])
    with pytest.raises(ValueError, match='Duplicate'):
        identities_digest([numeric, named])
    named['cells'][1] = 'Sep 1, 2026, 09:00 AM'
    assert row_identity(named) == row_identity(numeric)
    with pytest.raises(ValueError, match='missing_endpoint_location'):
        endpoint(named['cells'][1])


@pytest.mark.parametrize('clock', [
    'Feb 30, 2026, 09:00 AM', 'Sep 1, 2026, 00:00 AM', 'Sep 1, 2026, 13:00 PM',
    'September 1, 2026, 09:00 AM', 'Sep 1, 2026 09:00 AM',
    'Nov 1, 2026, 01:30 AM', 'Mar 8, 2026, 02:30 AM',
])
def test_named_invalid_and_dst_departures_reject(clock):
    from scripts.motive_sync.trip_populated_proof import row_identity
    with pytest.raises(ValueError):
        row_identity({'links': ['#/fleetview/vehicles/summary/1'], 'cells': ['', clock]})
