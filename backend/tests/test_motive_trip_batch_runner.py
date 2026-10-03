"""Offline transport/receipt tests; never invokes Railway."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('runner', Path(__file__).parents[2] / 'scripts' / 'run_motive_trip_batches.py')
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class BatchRunnerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        directory = Path(self.root.name)
        self.path = directory / 'input.json'
        self.path.write_text(json.dumps({'rows': [{'provider_vehicle_id': '123', 'started_at': '2026-10-01T12:00:00Z'}]}))
        self.args = argparse.Namespace(input=str(self.path), tenant_id='828acd84-38bf-4a66-8fa1-cdf076f4e241', actor_id='92059ce6-9b62-4963-9282-b0338b36d26e', project='p', environment='e', service='s', sha='a'*40, receipt=str(directory/'receipt.json'), railway='/path/railway', apply=False)

    def success(self, command, **kwargs):
        self.assertEqual(command[:2], ['/path/railway', 'ssh'])
        self.assertTrue(kwargs['capture_output'])
        result = {'status': 'success', 'committed': self.args.apply, 'mode': 'apply' if self.args.apply else 'dry_run', 'sha': self.args.sha, 'rows': [{'action': 'created' if self.args.apply else 'would_create', 'trip_id': 'example'}]}
        return subprocess.CompletedProcess(command, 0, RUNNER.MARKER+json.dumps(result), 'ignored private diagnostic')

    def test_dry_run_receipt_private_and_counts_only(self):
        result = RUNNER.execute(self.args, self.success)
        self.assertEqual(result['actions'], {'would_create': 1})
        self.assertNotIn('trip_id', json.dumps(result))
        saved = Path(self.args.receipt)
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        content = json.loads(saved.read_text())
        self.assertFalse(content['committed'])
        self.assertNotIn('diagnostic', saved.read_text())
        self.assertEqual(len(content['input_sha256']), 64)

    def test_apply_and_existing_receipt_not_overwritten(self):
        self.args.apply = True
        self.assertTrue(RUNNER.execute(self.args, self.success)['committed'])
        with self.assertRaises(FileExistsError):
            RUNNER.execute(self.args, lambda *a, **kw: self.fail('must not run'))

    def test_transport_failure_has_unknown_commit_no_diagnostics(self):
        def failure(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, 'private payload', 'private secret')
        result = RUNNER.execute(self.args, failure)
        self.assertIsNone(result['committed'])
        self.assertEqual(result['status'], 'transport_failed')
        self.assertNotIn('private secret', Path(self.args.receipt).read_text())

    def test_timeout_is_unknown(self):
        def timeout(*a, **kw):
            raise subprocess.TimeoutExpired('private command', 600)
        self.assertIsNone(RUNNER.execute(self.args, timeout)['committed'])

    def test_wrong_sha_receipt_rejected(self):
        def mismatch(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, RUNNER.MARKER+json.dumps({'sha': 'b'*40, 'mode': 'dry_run'}), '')
        self.assertEqual(RUNNER.execute(self.args, mismatch)['status'], 'transport_failed')

    def test_duplicate_and_naive_input_rejected_before_transport(self):
        row = {'provider_vehicle_id': '123', 'started_at': '2026-10-01T12:00:00Z'}
        with self.assertRaises(ValueError):
            RUNNER.validate_input({'rows': [row, dict(row, started_at='2026-10-01T08:00:00-04:00')]})
        with self.assertRaises(ValueError):
            RUNNER.validate_input({'rows': [dict(row, started_at='2026-10-01T12:00:00')]})

    def test_remote_program_compiles_and_guards_present(self):
        command = RUNNER.remote_command([{'example': 1}], self.args)
        import shlex
        code = shlex.split(command[-1])[-1]
        compile(code, '<remote>', 'exec')
        self.assertIn('await authorize(db,TENANT,ACTOR)', code)
        self.assertIn("row['action']!='unchanged'", code)
        self.assertIn("RAILWAY_GIT_COMMIT_SHA", code)
        self.assertNotIn('run_corrections', code)
        self.assertIn('await db.rollback()', code)
        self.assertLess(code.index('before=await fingerprint(db)'), code.index('await run_import'))
        self.assertLess(code.index("if any(row['action']!='unchanged'"), code.index('await db.commit()'))


if __name__ == '__main__':
    unittest.main()
