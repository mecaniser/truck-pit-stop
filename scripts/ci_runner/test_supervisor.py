import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('supervisor', Path(__file__).with_name('supervisor.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SupervisorSafety(unittest.TestCase):
    def test_only_owned_slots_can_be_deleted(self):
        for name in ('db-ci-base', 'default', 'elis250-ci', 'db-ci-worker-3', 'db-ci-worker-1/../../base'):
            with self.subTest(name=name), patch.object(s, 'command') as run:
                with self.assertRaises(ValueError):
                    s.destroy(name)
                run.assert_not_called()

    def test_firewall_failure_prevents_registration(self):
        with patch.object(s, 'destroy'), patch.object(s, 'command'), \
             patch.object(s, 'guest', side_effect=RuntimeError('firewall absent')), \
             patch.object(s, 'api') as api:
            with self.assertRaises(RuntimeError):
                s.cycle('db-ci-worker-1')
            api.assert_not_called()

    def test_failed_cleanup_prevents_reusing_guest(self):
        with patch.object(s, 'destroy', side_effect=RuntimeError('cannot delete')), \
             patch.object(s, 'command') as run, patch.object(s, 'api') as api:
            with self.assertRaises(RuntimeError):
                s.cycle('db-ci-worker-1')
            run.assert_not_called()
            api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
