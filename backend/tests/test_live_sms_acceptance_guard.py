"""No real provider calls: exercise the one-recipient acceptance budget."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import pytest

spec = importlib.util.spec_from_file_location('live_acceptance_guard', Path(__file__).resolve().parents[2] / 'scripts/communications_live_acceptance.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

@pytest.fixture
def approved(tmp_path, monkeypatch):
    plan = dict(recipient='+15005550101', sender='+15005550001', body='Test only', event='one-event')
    monkeypatch.setattr(module, 'APPROVED_RECIPIENT_SHA256', module.hashlib.sha256(plan['recipient'].encode()).hexdigest())
    ledger = tmp_path / 'guard.sqlite'
    module.initialize_guard(plan, ledger)
    return plan, ledger

@pytest.mark.parametrize('field,value', [('to_number','+15005550102'),('from_number','+15005550002'),('body','Different text')])
def test_other_recipient_sender_or_body_never_claims(approved, field, value):
    plan, ledger = approved
    args = dict(to_number=plan['recipient'], from_number=plan['sender'], body=plan['body'])
    args[field] = value
    with pytest.raises(RuntimeError):
        module.claim_provider_call(plan, **args, ledger=ledger)
    with sqlite3.connect(ledger) as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0

def test_changed_plan_does_not_expand_allowlist(approved):
    plan, ledger = approved
    changed = {**plan, 'recipient': '+15005550102'}
    with pytest.raises(RuntimeError):
        module.claim_provider_call(changed, to_number=changed['recipient'], from_number=changed['sender'], body=changed['body'], ledger=ledger)

def test_concurrent_claim_and_restart_allow_exactly_one_call(approved):
    plan, ledger = approved
    def claim():
        try:
            module.claim_provider_call(plan, to_number=plan['recipient'], from_number=plan['sender'], body=plan['body'], ledger=ledger)
            return True
        except sqlite3.IntegrityError:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _: claim(), range(4))) == 1
    assert not claim()  # Separate connection, permanent budget after crash/restart.
    with sqlite3.connect(ledger) as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 1


def test_new_plan_cannot_authorize_different_recipient(approved, tmp_path):
    plan, _ = approved
    with pytest.raises(RuntimeError):
        module.initialize_guard({**plan, 'recipient': '+15005550102'}, tmp_path / 'other.sqlite')


def test_status_plan_validation_rejects_changed_body(approved):
    plan, ledger = approved
    with pytest.raises(RuntimeError):
        module.validate_plan({**plan, 'body': 'changed'}, ledger)
