import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('supervisor', Path(__file__).with_name('supervisor.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SupervisorSafety(unittest.TestCase):
    def test_only_owned_slots_can_be_deleted(self):
        for name in ('db-ci-base', 'default', 'elis250-ci', 'db-ci-worker-5', 'db-ci-worker-1/../../base'):
            with self.subTest(name=name), patch.object(s, 'command') as run:
                with self.assertRaises(ValueError):
                    s.destroy(name)
                run.assert_not_called()

    def test_capacity_bounds(self):
        s.validate_capacity(2, 4, 8)
        s.validate_capacity(4, 2, 8)
        for profile in ((4, 4, 8), (5, 1, 4), (4, 2, 16), (0, 2, 8)):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                s.validate_capacity(*profile)

    def test_four_owned_slots_only(self):
        self.assertTrue(s.owned('db-ci-worker-4'))
        self.assertFalse(s.owned('db-ci-worker-40'))

    def test_drain_preserves_current_workers_and_prevents_replacement(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            drain = Path(directory) / 'drain'
            drain.touch()
            with patch.object(s.STOP, 'is_set', side_effect=[False, True]), \
                 patch.object(s.STOP, 'wait'), patch.object(s, 'cycle') as cycle, \
                 patch.object(s, 'destroy') as destroy:
                s.worker('db-ci-worker-1', 2, 8, drain)
            cycle.assert_not_called()
            destroy.assert_not_called()

    def test_firewall_failure_prevents_registration(self):
        with patch.object(s, 'destroy'), patch.object(s, 'command'), \
             patch.object(s, 'guest', side_effect=RuntimeError('firewall absent')), \
             patch.object(s, 'api') as api:
            with self.assertRaises(RuntimeError):
                s.cycle('db-ci-worker-1')
            api.assert_not_called()

    def test_identity_failure_prevents_registration(self):
        with patch.object(s, 'destroy'), patch.object(s, 'command'), \
             patch.object(s, 'guest', side_effect=[None, RuntimeError('runner has sudo')]), \
             patch.object(s, 'api') as api:
            with self.assertRaises(RuntimeError):
                s.cycle('db-ci-worker-1')
            api.assert_not_called()

    def test_clone_ports_and_token_transport(self):
        with patch.object(s, 'destroy'), patch.object(s, 'command') as run, \
             patch.object(s, 'guest') as guest, \
             patch.object(s, 'api', return_value={'token': 'registration-canary'}), \
             patch.object(s.STOP, 'wait', return_value=True):
            s.cycle('db-ci-worker-1', 2, 8)
            self.assertIn('--cpus=2', run.call_args_list[0].args[0])
            self.assertIn('--memory=8', run.call_args_list[0].args[0])
            self.assertIn('--ssh-port=0', run.call_args_list[0].args[0])
            self.assertIn('--mount-none', run.call_args_list[0].args[0])
            registration = guest.call_args_list[2]
            self.assertIn('ACTIONS_RUNNER_INPUT_TOKEN', registration.args[-1])
            self.assertNotIn('registration-canary', str(registration.args))
            self.assertEqual(registration.kwargs['data'], 'registration-canary')
            self.assertIn('--ephemeral', registration.args[-1])

    def test_failed_cleanup_prevents_reusing_guest(self):
        with patch.object(s, 'destroy', side_effect=RuntimeError('cannot delete')), \
             patch.object(s, 'command') as run, patch.object(s, 'api') as api:
            with self.assertRaises(RuntimeError):
                s.cycle('db-ci-worker-1')
            run.assert_not_called()
            api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
