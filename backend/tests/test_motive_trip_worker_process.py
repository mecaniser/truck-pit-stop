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
