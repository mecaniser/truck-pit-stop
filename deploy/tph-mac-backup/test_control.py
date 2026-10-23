from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from control import AcceptedProof, Control, DataProof, Refused, StoppedProof

PRIMARY = 'railway-simulation'
BACKUP = 'mac-backup'
OLD = 'a' * 64
NEW = 'b' * 64
AUTHORITY = 'synthetic-shared-mongo-v1'


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name).resolve() / 'control.sqlite3'
        self.control = Control(self.path)
        self.control.initialize(PRIMARY, OLD, authority_id=AUTHORITY)

    def tearDown(self):
        self.directory.cleanup()

    def stopped(self, instance_id):
        return StoppedProof(instance_id, 'fresh-native-inspection')

    def fresh(self, authority, watermark, site, instance_id):
        return DataProof(authority, watermark, site, instance_id, 'f' * 64)

    def accepted(self, row):
        return AcceptedProof(**{key: row[key] for key in
            ('operation_id', 'scope', 'kind', 'business_id', 'payload_sha256')}, provider_receipt='FAKE-accepted-1')

    def switch(self, target=BACKUP, target_id=NEW):
        state = self.control.state()
        self.control.begin_drain(state['site'], state['epoch'])
        return self.control.promote(target, target_id, self.stopped, self.fresh)

    def test_initialization_and_live_activation_refusal(self):
        self.assertEqual(self.control.state()['epoch'], 1)
        self.assertEqual(self.control.state()['watermark'], 0)
        with self.assertRaisesRegex(Refused, 'already_initialized'):
            self.control.initialize(PRIMARY, OLD, authority_id=AUTHORITY)
        with self.assertRaisesRegex(Refused, 'live_activation_forbidden'):
            self.control.activate_live(primary_fenced=True, approved=True)

    def test_admission_replay_and_payload_conflict(self):
        first = self.control.admit(PRIMARY, 1, 'native-1', {'synthetic': True})
        replay = self.control.admit(PRIMARY, 1, 'native-1', {'synthetic': True})
        self.assertTrue(first['dispatch'])
        self.assertFalse(replay['dispatch'])
        self.assertEqual(first['admission_id'], replay['admission_id'])
        with self.assertRaisesRegex(Refused, 'payload_conflict'):
            self.control.admit(PRIMARY, 1, 'native-1', {'synthetic': False})
        self.control.complete(first['admission_id'], 'accepted')
        self.control.complete(first['admission_id'], 'accepted')
        self.assertEqual(self.control.state()['watermark'], 1)

    def test_drain_blocks_pending_admissions_and_new_mutations(self):
        admitted = self.control.admit(PRIMARY, 1, 'native-1')
        transition = self.control.begin_drain(PRIMARY, 1)
        self.assertEqual(transition['expected_old_instance_id'], OLD)
        with self.assertRaisesRegex(Refused, 'not_active'):
            self.control.admit(PRIMARY, 1, 'native-2')
        with self.assertRaisesRegex(Refused, 'inflight_or_unknown'):
            self.control.promote(BACKUP, NEW, self.stopped, self.fresh)
        self.control.complete(admitted['admission_id'], 'accepted')
        switched = self.control.promote(BACKUP, NEW, self.stopped, self.fresh)
        self.assertEqual(switched['site'], BACKUP)
        self.assertEqual(switched['epoch'], 2)
        self.assertEqual(switched['watermark'], 1)

    def test_stale_epoch_and_wrong_writer_refused_after_switch(self):
        self.switch()
        for site, epoch in ((PRIMARY, 1), (PRIMARY, 2), (BACKUP, 1)):
            with self.subTest(site=site, epoch=epoch):
                with self.assertRaisesRegex(Refused, 'stale_or_wrong'):
                    self.control.admit(site, epoch, 'stale')
        self.control.admit(BACKUP, 2, 'valid')

    def test_wrong_stopped_proof_and_boolean_refused(self):
        self.control.begin_drain(PRIMARY, 1)
        for callback in (True, lambda cid: True, lambda cid: StoppedProof(NEW, 'wrong')):
            with self.subTest(callback=callback):
                with self.assertRaises(Refused):
                    self.control.promote(BACKUP, NEW, callback, self.fresh)
                self.assertEqual(self.control.state()['epoch'], 1)

    def test_fresh_shared_authority_and_exact_watermark_required(self):
        admitted = self.control.admit(PRIMARY, 1, 'native-1')
        self.control.complete(admitted['admission_id'], 'accepted')
        self.control.begin_drain(PRIMARY, 1)
        for field, value in (('authority_id', 'stale-copy'), ('watermark', 0),
                             ('target_site', PRIMARY), ('target_instance_id', OLD), ('data_digest', 'missing')):
            with self.subTest(field=field):
                callback = lambda *args: replace(self.fresh(*args), **{field: value})
                with self.assertRaisesRegex(Refused, 'rpo_zero'):
                    self.control.promote(BACKUP, NEW, self.stopped, callback)
                self.assertEqual(self.control.state()['epoch'], 1)
        self.control.promote(BACKUP, NEW, self.stopped, self.fresh)

    def test_unreadable_freshness_observation_cannot_promote(self):
        self.control.begin_drain(PRIMARY, 1)
        def unavailable(*args):
            raise OSError('synthetic unavailable shared data')
        with self.assertRaises(OSError):
            self.control.promote(BACKUP, NEW, self.stopped, unavailable)
        self.assertEqual(self.control.state()['phase'], 'draining')
        self.assertEqual(self.control.state()['epoch'], 1)

    def test_ten_concurrent_claims_produce_one_dispatch(self):
        barrier = threading.Barrier(10)
        def claim(_):
            barrier.wait()
            return self.control.claim_operation(PRIMARY, 1, 'payment', 'synthetic-charge-1', {'amount': 100})
        with ThreadPoolExecutor(max_workers=10) as pool:
            values = list(pool.map(claim, range(10)))
        self.assertEqual(sum(value['dispatch'] for value in values), 1)
        self.assertEqual(len({value['operation_id'] for value in values}), 1)

    def test_effect_replay_survives_restart_and_switch(self):
        first = self.control.claim_operation(PRIMARY, 1, 'sms', 'synthetic-message-1', {'body': 'synthetic'})
        self.control.complete_operation(first['operation_id'], 'accepted', 'FAKE-sms-1')
        self.control = Control(self.path)
        self.switch()
        replay = self.control.claim_operation(BACKUP, 2, 'sms', 'synthetic-message-1', {'body': 'synthetic'})
        self.assertFalse(replay['dispatch'])
        self.assertEqual(replay['provider_receipt'], 'FAKE-sms-1')
        self.assertEqual(self.control.state()['watermark'], 1)
        with self.assertRaisesRegex(Refused, 'payload_conflict'):
            self.control.claim_operation(BACKUP, 2, 'sms', 'synthetic-message-1', {'body': 'changed'})

    def test_unknown_effect_freezes_and_requires_definitive_reconciliation(self):
        claimed = self.control.claim_operation(PRIMARY, 1, 'payment', 'synthetic-charge-1', {'amount': 100})
        self.control.complete_operation(claimed['operation_id'], 'unknown')
        self.assertEqual(self.control.state()['phase'], 'frozen')
        with self.assertRaisesRegex(Refused, 'not_active'):
            self.control.claim_operation(PRIMARY, 1, 'payment', 'synthetic-charge-1', {'amount': 100})
        with self.assertRaisesRegex(Refused, 'requires_reconciliation'):
            self.control.complete_operation(claimed['operation_id'], 'accepted', 'FAKE-charge-1')
        for lookup in (lambda row: None, lambda row: {'not_found': True}, lambda row: True):
            with self.assertRaisesRegex(Refused, 'definitive_accepted'):
                self.control.reconcile_operation(claimed['operation_id'], lookup)
        self.control.begin_drain(PRIMARY, 1)
        with self.assertRaisesRegex(Refused, 'inflight_or_unknown'):
            self.control.promote(BACKUP, NEW, self.stopped, self.fresh)
        result = self.control.reconcile_operation(claimed['operation_id'], self.accepted)
        self.assertEqual(result['watermark'], 1)
        self.control.reconcile_operation(claimed['operation_id'], self.accepted)
        self.assertEqual(self.control.state()['watermark'], 1)
        self.control.promote(BACKUP, NEW, self.stopped, self.fresh)

    def test_reconciliation_requires_exact_operation_and_payload(self):
        claimed = self.control.claim_operation(PRIMARY, 1, 'email', 'email-1', {'subject': 'synthetic'})
        self.control.complete_operation(claimed['operation_id'], 'unknown')
        for field, value in (('operation_id', 'another'), ('scope', 'other'), ('kind', 'sms'),
                             ('business_id', 'other'), ('payload_sha256', '0' * 64)):
            with self.subTest(field=field):
                with self.assertRaisesRegex(Refused, 'proof_mismatch'):
                    self.control.reconcile_operation(claimed['operation_id'],
                        lambda row: replace(self.accepted(row), **{field: value}))

    def test_dispatch_authorization_fails_during_draining(self):
        claimed = self.control.claim_operation(PRIMARY, 1, 'job', 'job-1', {})
        self.control.authorize_dispatch(claimed['operation_id'], PRIMARY, 1)
        self.control.begin_drain(PRIMARY, 1)
        with self.assertRaisesRegex(Refused, 'not_active'):
            self.control.authorize_dispatch(claimed['operation_id'], PRIMARY, 1)
        self.control.complete_operation(claimed['operation_id'], 'rejected')
        self.control.promote(BACKUP, NEW, self.stopped, self.fresh)

    def test_unknown_native_admission_blocks_transfer(self):
        admitted = self.control.admit(PRIMARY, 1, 'native-1')
        self.control.complete(admitted['admission_id'], 'unknown')
        self.control.begin_drain(PRIMARY, 1)
        with self.assertRaisesRegex(Refused, 'inflight_or_unknown'):
            self.control.promote(BACKUP, NEW, self.stopped, self.fresh)

    def test_pending_and_summary_read_only_pre_stop_observations(self):
        self.assertFalse(self.control.pending()['blocked'])
        admitted = self.control.admit(PRIMARY, 1, 'native-1')
        effect = self.control.claim_operation(PRIMARY, 1, 'job', 'job-1', {})
        self.control.begin_drain(PRIMARY, 1)
        pending = self.control.pending()
        self.assertEqual(pending['admissions_pending'], 1)
        self.assertEqual(pending['effects_dispatching'], 1)
        self.assertTrue(pending['blocked'])
        self.control.complete(admitted['admission_id'], 'rejected')
        self.control.complete_operation(effect['operation_id'], 'unknown')
        summary = self.control.summary()
        self.assertEqual(summary['phase'], 'frozen')
        self.assertEqual(summary['effects'], {'unknown': 1})
        self.assertEqual(summary['pending']['effects_unknown'], 1)
        self.assertEqual(summary['watermark'], 0)

    def test_no_automatic_expiry_or_reactivation(self):
        with patch('control.time.time', return_value=10**12):
            self.assertEqual(self.control.state()['site'], PRIMARY)
            self.assertEqual(self.control.state()['epoch'], 1)
        self.control.freeze('operator_review')
        with patch('control.time.time', return_value=10**13):
            with self.assertRaisesRegex(Refused, 'not_active'):
                self.control.admit(PRIMARY, 1, 'native-1')


if __name__ == '__main__':
    unittest.main()
