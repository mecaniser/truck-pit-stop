from copy import deepcopy
import json
from pathlib import Path
from scripts.easytruck_sync.contact_snapshot import normalize, latest, for_history, digest

ACCOUNT = "123"
DBN = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def raw(**changes):
    value = dict(source_shop_id="shop_test", source_customer_id=ACCOUNT,
                 observed_at="2026-10-10T01:00:00Z", complete=True, reason=None,
                 phones=["(704) 555-1234", "+17045551234", ""])
    return value | changes


def normalized(value=None):
    return normalize(value or raw(), customer_id=ACCOUNT, dbn_customer_id=DBN)


def test_current_set_normalized_and_digest_excludes_timestamp():
    snapshot = normalized()
    assert snapshot["contacts"] == [{"source_contact_id": None, "phone": "+17045551234"}]
    assert snapshot["complete"] and snapshot["reason"] is None
    assert snapshot["semantic_hash"] == normalized(raw(observed_at="2026-10-11T01:00:00Z"))["semantic_hash"]


def test_invalid_nonblank_phone_never_claims_complete():
    result = normalized(raw(phones=["7045551234", "7045551234 ext 5"]))
    assert result["complete"] is False and result["contacts"] == []
    assert result["reason"] == "schema_unsupported"


def test_absent_legacy_capture_cannot_become_fresh():
    assert normalize(None, customer_id=ACCOUNT, dbn_customer_id=DBN) is None
    assert normalize(raw(observed_at="2026-10-10"), customer_id=ACCOUNT, dbn_customer_id=DBN) is None


def test_empty_complete_set_removes_all_phones():
    previous = normalized()
    empty = normalized(raw(phones=[], observed_at="2026-10-11T00:00:00Z"))
    assert latest(previous, empty)["contacts"] == []
    assert empty["complete"]


def test_new_failure_cannot_be_cleared_by_delayed_success_or_failure():
    success = normalized()
    failure = normalized(raw(complete=False, reason="read_unavailable", observed_at="2026-10-12T00:00:00Z"))
    intermediate = normalized(raw(observed_at="2026-10-11T00:00:00Z"))
    assert latest(latest(success, failure), intermediate) == failure
    assert latest(failure, normalized(raw(complete=False, observed_at="2026-10-11T00:00:00Z"))) == failure


def test_equal_time_conflict_remains_a_hold_on_replay():
    a = normalized()
    b = normalized(raw(phones=["7045559999"]))
    hold = latest(a, b)
    assert hold["complete"] is False
    assert latest(hold, b)["complete"] is False
    assert latest(hold, a)["complete"] is False


def test_changed_source_account_is_invalidated_without_old_aliases():
    result = for_history(normalized(), customer_id=None, dbn_customer_id=DBN,
                         shop_id="shop_test", source=None)
    assert result["source_customer_id"] is None
    assert result["complete"] is False and result["contacts"] == []
    assert result["semantic_hash"] == digest(result)


def test_tampered_phone_and_cross_shop_fail_closed():
    value = deepcopy(normalized())
    value["contacts"][0]["phone"] = "+17045550000"
    result = for_history(value, customer_id=ACCOUNT, dbn_customer_id=DBN,
                         shop_id="other_shop", source="easy_truck_shop_import")
    assert result["complete"] is False and result["contacts"] == []


def test_missing_source_identity_can_emit_invalidation():
    value = normalize(raw(), customer_id=None, dbn_customer_id=DBN)
    assert value["source_customer_id"] is None
    assert value["reason"] == "account_mismatch"


def test_future_observation_does_not_poison_watermark():
    assert normalized(raw(observed_at="2099-01-01T00:00:00Z")) is None


def test_shared_consumer_hash_fixture():
    fixture = json.loads((Path(__file__).parent / 'fixtures/account-contact-snapshot-v2.json').read_text())
    assert digest(fixture) == fixture['semantic_hash'] == '3da652b32db3ace1600487ff66260633c0d9d729f0714e2fe72be4b98473f45e'


def test_incomplete_or_cross_account_contact_fields_never_enter_new_customer():
    from scripts.easytruck_sync.import_to_truckpitstop import build_records
    for evidence in [raw(complete=False, reason='page_incomplete'), raw(source_customer_id='999'),
                     raw(observed_at='2099-01-01T00:00:00Z')]:
        row = build_records([{'id':'123','company':'Synthetic Fleet','contacts':[
            {'phone':'7045551234','email':'wrong-account@example.test'}],
            'contact_phone_snapshot':evidence,'vehicles':[]}], DBN)['customers'][0]
        assert row['phone'] is None
        assert row['email'] == 'noemail+123@import.local'
        assert row['contact_snapshot_valid'] is False
