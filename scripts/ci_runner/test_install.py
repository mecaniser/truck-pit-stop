import subprocess
import unittest
from unittest.mock import patch

import install


class InstallSafety(unittest.TestCase):
    def test_loaded_service_blocks_install(self):
        with patch.object(install.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            with self.assertRaisesRegex(RuntimeError, 'unload'):
                install.assert_idle('gui/test/com.dieselbridge.ci')
            self.assertEqual(run.call_count, 1)

    def test_api_failure_does_not_assume_idle(self):
        with patch.object(install.subprocess, 'run', side_effect=[
            subprocess.CompletedProcess([], 1), subprocess.CalledProcessError(1, ['gh'])
        ]):
            with self.assertRaises(subprocess.CalledProcessError):
                install.assert_idle('gui/test/com.dieselbridge.ci')

    def test_busy_worker_blocks_install(self):
        with patch.object(install.subprocess, 'run', side_effect=[
            subprocess.CompletedProcess([], 1),
            subprocess.CompletedProcess([], 0, '{"runners":[{"name":"db-ci-worker-4","busy":true}]}')
        ]):
            with self.assertRaisesRegex(RuntimeError, 'busy'):
                install.assert_idle('gui/test/com.dieselbridge.ci')

    def test_running_vm_blocks_install_even_without_registration(self):
        with patch.object(install.subprocess, 'run', side_effect=[
            subprocess.CompletedProcess([], 1),
            subprocess.CompletedProcess([], 0, '{"runners":[]}'),
            subprocess.CompletedProcess([], 0, '{"name":"db-ci-worker-2","status":"Running"}')
        ]):
            with self.assertRaisesRegex(RuntimeError, 'stopped'):
                install.assert_idle('gui/test/com.dieselbridge.ci')

    def test_unrelated_vm_does_not_block_install(self):
        with patch.object(install.subprocess, 'run', side_effect=[
            subprocess.CompletedProcess([], 1),
            subprocess.CompletedProcess([], 0, '{"runners":[]}'),
            subprocess.CompletedProcess([], 0, '{"name":"other-worker","status":"Running"}')
        ]):
            install.assert_idle('gui/test/com.dieselbridge.ci')


if __name__ == '__main__':
    unittest.main()
