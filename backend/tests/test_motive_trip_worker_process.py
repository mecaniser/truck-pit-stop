"""Process boundaries: an unresolved receipt prevents fresh provider collection."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.motive_sync import run_trip_worker as worker


class TripProcessTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MOTIVE_TRIPS_COMMIT": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_disabled_saving_does_not_recover_with_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prior" / "receipt.json"
            path.parent.mkdir()
            path.touch(mode=0o600)
            for evidence in [path.with_name("source.json"), Path(str(path) + ".normalized.json")]:
                evidence.touch(mode=0o600)
                evidence.write_text("{}")
            path.write_text(json.dumps({"stage": "commit_pending", "mode": "commit"}))
            with (
                patch.dict(os.environ, {"MOTIVE_TRIPS_COMMIT": "false"}),
                patch.object(worker.subprocess, "run") as call,
                self.assertRaisesRegex(RuntimeError, "saving is disabled"),
            ):
                worker.recover_pending(Path(directory))
            call.assert_not_called()

    def test_failed_recovery_prevents_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prior" / "receipt.json"
            path.parent.mkdir()
            path.touch(mode=0o600)
            for evidence in [path.with_name("source.json"), Path(str(path) + ".normalized.json")]:
                evidence.touch(mode=0o600)
                evidence.write_text("{}")
            path.write_text(json.dumps({"stage": "commit_pending", "mode": "commit"}))
            with (
                patch.dict(os.environ, {"MOTIVE_TRIPS_STATE_DIR": directory}),
                patch.object(
                    worker.subprocess,
                    "run",
                    side_effect=subprocess.CalledProcessError(1, "recover"),
                ) as call,
                self.assertRaises(subprocess.CalledProcessError),
            ):
                worker.main()
            self.assertEqual(call.call_count, 1)
            self.assertIn("--recover", call.call_args.args[0])
            self.assertEqual(len(list(Path(directory).glob("*/receipt.json"))), 1)

    def test_success_requires_verified_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prior" / "receipt.json"
            path.parent.mkdir()
            path.touch(mode=0o600)
            for evidence in [path.with_name("source.json"), Path(str(path) + ".normalized.json")]:
                evidence.touch(mode=0o600)
                evidence.write_text("{}")
            path.write_text(json.dumps({"stage": "committed", "mode": "commit"}))
            with (
                patch.object(worker.subprocess, "run"),
                self.assertRaisesRegex(RuntimeError, "unverified"),
            ):
                worker.recover_pending(Path(directory))

            def reconcile(*args, **kwargs):
                path.write_text(json.dumps({"stage": "verified"}))

            with patch.object(worker.subprocess, "run", side_effect=reconcile) as call:
                worker.recover_pending(Path(directory))
                self.assertEqual(call.call_count, 1)
            with patch.object(worker.subprocess, "run") as call:
                worker.recover_pending(Path(directory))
                call.assert_not_called()


if __name__ == "__main__":
    unittest.main()

class CatchupProcessTests(unittest.TestCase):
    def test_nested_uncertain_day_recovered_while_prior_verified_day_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root/'run'/'2026-10-19', root/'run'/'2026-10-20'
            for path, stage in [(first, 'verified'), (second, 'commit_pending')]:
                path.mkdir(parents=True)
                for name, value in [('receipt.json', {'mode': 'commit', 'stage': stage}), ('source.json', {}), ('receipt.json.normalized.json', {})]:
                    evidence = path/name
                    evidence.touch(mode=0o600)
                    evidence.write_text(json.dumps(value))
            initial = (first/'receipt.json').read_bytes()
            def recovered(command, **kwargs):
                self.assertEqual(command[-1], str(second/'receipt.json'))
                (second/'receipt.json').write_text(json.dumps({'mode': 'commit', 'stage': 'verified'}))
            with patch.dict(os.environ, {'MOTIVE_TRIPS_COMMIT': 'true'}), patch.object(worker.subprocess, 'run', side_effect=recovered) as call:
                worker.recover_pending(root)
                self.assertEqual(call.call_count, 1)
            self.assertEqual((first/'receipt.json').read_bytes(), initial)

    def test_baseline_change_stops_before_browser_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bound = worker.trip_coverage.scope('tenant', 'actor', 'KT8934277', '77 CARGO LLC', '2026-04-01')
            path = root/'coverage-scope.json'
            path.touch(mode=0o600); path.write_text(json.dumps(bound))
            with patch.dict(os.environ, {'MOTIVE_TRIPS_STATE_DIR': directory, 'MOTIVE_SYNC_TENANT_ID':'tenant', 'MOTIVE_SYNC_ACTOR_ID':'actor', 'MOTIVE_COMPANY_ID':'KT8934277', 'MOTIVE_COMPANY_LABEL':'77 CARGO LLC', 'MOTIVE_TRIPS_BASELINE':'2026-10-19'}), patch.object(worker, 'read_process') as call, self.assertRaisesRegex(ValueError, 'scope changed'):
                worker.main()
            call.assert_not_called()

    def test_real_node_python_day_timeout_preserves_prior_and_recovers_pending(self):
        """Real process boundary, fixture importer; DB semantics covered separately."""
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root/'fixture'/'scripts'/'motive_sync'
            package.mkdir(parents=True)
            (package.parent/'__init__.py').write_text('')
            (package/'__init__.py').write_text('')
            (package/'trip_runner.py').write_text('''import argparse,json,time,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--receipt');p.add_argument('--commit',action='store_true');p.add_argument('--recover',action='store_true');p.add_argument('--rejection-nonce');a=p.parse_args()
source=json.loads(Path(a.input).read_text()); receipt=Path(a.receipt)
assert a.commit and source['complete'] and source['company_verified_after']
normalized=Path(str(receipt)+'.normalized.json'); normalized.write_text('{}');normalized.chmod(0o600)
receipt.write_text(json.dumps({'mode':'commit','stage':'commit_pending'}));receipt.chmod(0o600)
if not a.recover and source['windows'][0]['start']=='2026-10-20':time.sleep(10)
receipt.write_text(json.dumps({'mode':'commit','stage':'verified'}))
''')
            run = root/'state'/'run'; run.mkdir(parents=True)
            collector = Path(worker.__file__).with_name('collect_trips.cjs')
            script = root/'process.cjs'
            script.write_text("const {importDay}=require("+json.dumps(str(collector))+");\nconst output="+json.dumps(str(run/'source.json'))+";\nimportDay(output,{}, {}, {start:'2026-10-19'}, {start:'2026-10-19',end:'2026-10-19'});\ntry {importDay(output,{}, {}, {start:'2026-10-20'}, {start:'2026-10-20',end:'2026-10-20'},{timeout:500});process.exit(2);}catch(e){if(e.message!=='trip_import_failed')throw e;}\n")
            env = {'MOTIVE_TRIPS_COMMIT':'true','MOTIVE_TRIPS_PYTHON':sys.executable,'PYTHONPATH':str(root/'fixture')}
            with patch.dict(os.environ, env):
                subprocess.run(['node', str(script)], check=True, timeout=10, cwd=root)
                first = run/'2026-10-19'/'receipt.json'
                second = run/'2026-10-20'/'receipt.json'
                original = first.read_bytes()
                self.assertEqual(json.loads(second.read_text())['stage'], 'commit_pending')
                # Child -m resolution uses only the fixture package; no database/network.
                previous = os.getcwd()
                try:
                    os.chdir(root)
                    worker.recover_pending(root/'state')
                finally:
                    os.chdir(previous)
                self.assertEqual(json.loads(second.read_text())['stage'], 'verified')
                self.assertEqual(first.read_bytes(), original)
