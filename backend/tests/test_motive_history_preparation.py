"""Pure offline collector preparation tests; run with unittest, no database."""
import copy
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("prepare", Path(__file__).parents[1] / "scripts" / "prepare_motive_trip_history.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
NOW = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {"tenant_id": "tenant-example", "company_label": "Example Fleet", "vehicles": [{"provider_vehicle_id": "123", "vin": "1M8GDM9AXKP042788", "unit": "101", "effective_from": "2026-07-22T20:13:45+00:00"}]}
        self.raw = {"cells": ["", "09/28/2026 09:00 AM\nExample City, NC", "09/28/2026 10:00 AM\nOther City, NC", "40.25\n1h 0m 0s"], "links": ["#/fleetview/vehicles/summary/123"]}
        self.doc = {"tenant_id": "tenant-example", "company_label": "Example Fleet", "windows": [{"start": "2026-09-28", "end": "2026-09-28", "source_read_at": "2026-10-03T19:00:00+00:00", "status": "captured", "rows": [self.raw]}]}

    def run_rows(self, prior=None):
        return MODULE.normalize(self.doc, self.mapping, prior, NOW)

    def test_measured_values_null_metrics_and_dedupe(self):
        self.doc["windows"][0]["rows"].append(copy.deepcopy(self.raw))
        rows, report = self.run_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["started_at"], "2026-09-28T13:00:00+00:00")
        self.assertEqual(rows[0]["distance_miles"], 40.25)
        self.assertIsNone(rows[0]["metrics"])
        self.assertEqual(report["coverage"], "partial")

    def test_frozen_prior_metrics_and_read_time(self):
        rows, _ = self.run_rows()
        rows[0]["metrics"] = {"estimate_baseline_mpg": 6.5}
        original = copy.deepcopy(rows)
        self.doc["windows"][0]["source_read_at"] = "2026-10-03T20:00:00+00:00"
        prepared, report = self.run_rows({"rows": rows})
        self.assertEqual(prepared, original)
        self.assertEqual(report["replayed"], 1)

    def test_conflict_quarantines_all_versions(self):
        changed = copy.deepcopy(self.raw)
        changed["cells"][3] = "41.25\n1h 0m 0s"
        self.doc["windows"][0]["rows"].append(changed)
        rows, report = self.run_rows()
        self.assertEqual(rows, [])
        self.assertEqual(report["exclusions"][0]["reason"], "conflicting_source_identity")

    def test_prior_conflict_is_not_overwritten(self):
        prior, _ = self.run_rows()
        self.raw["cells"][3] = "42\n1h 0m 0s"
        self.assertEqual(self.run_rows({"rows": prior})[0], [])

    def test_outside_membership(self):
        self.mapping["vehicles"][0]["effective_from"] = "2026-09-29T00:00:00+00:00"
        rows, report = self.run_rows()
        self.assertFalse(rows)
        self.assertEqual(report["exclusions"][0]["reason"], "outside_membership")

    def test_partial_is_not_importable(self):
        self.doc["windows"][0]["status"] = "partial"
        rows, report = self.run_rows()
        self.assertFalse(rows)
        self.assertEqual(report["exclusions"][0]["reason"], "partial_window")

    def test_empty_window_and_no_batches(self):
        self.doc["windows"][0].update(status="empty", rows=[])
        rows, report = self.run_rows()
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "new"
            MODULE.write_outputs(target, rows, report)
            self.assertEqual(json.loads((target / "report.json").read_text())["batches"], [])
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            self.assertEqual((target / "report.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                MODULE.write_outputs(target, rows, report)

    def test_empty_with_rows_fails(self):
        self.doc["windows"][0]["status"] = "empty"
        with self.assertRaises(ValueError):
            self.run_rows()

    def test_wrong_tenant_company_and_duplicate_mapping(self):
        for key in ("tenant_id", "company_label"):
            changed = copy.deepcopy(self.mapping)
            changed[key] = "wrong"
            with self.assertRaises(ValueError):
                MODULE.normalize(self.doc, changed, now=NOW)
        self.mapping["vehicles"].append(copy.deepcopy(self.mapping["vehicles"][0]))
        with self.assertRaises(ValueError):
            self.run_rows()

    def test_dst_ambiguous_and_nonexistent(self):
        for clock in ("11/01/2026 01:30 AM", "03/08/2026 02:30 AM"):
            with self.assertRaises(ValueError):
                MODULE.endpoint(clock + "\nExample")

    def test_future_source_read_fails_document(self):
        self.doc["windows"][0]["source_read_at"] = "2026-10-04T00:00:00+00:00"
        with self.assertRaises(ValueError):
            self.run_rows()

    def test_unknown_vehicle_and_invalid_duration(self):
        self.raw["links"] = ["#/fleetview/vehicles/summary/999"]
        self.assertEqual(self.run_rows()[1]["exclusions"][0]["reason"], "unverified_vehicle")
        self.raw["links"] = ["#/fleetview/vehicles/summary/123"]
        self.raw["cells"][3] = "40\n1h 99m 0s"
        self.assertFalse(self.run_rows()[0])

    def test_minute_completion_requires_full_minute(self):
        self.doc["windows"][0]["source_read_at"] = "2026-09-28T14:00:30+00:00"
        self.assertFalse(self.run_rows()[0])

    def test_vehicle_links_fail_closed(self):
        for links in (["https://unrelated.example/123"],
                      ["#/fleetview/vehicles/summary/123", "#/fleetview/vehicles/summary/999"],
                      ["https://evil.example/#/fleetview/vehicles/summary/123"]):
            self.raw["links"] = links
            self.assertFalse(self.run_rows()[0])

    def test_mileage_grouping(self):
        self.raw["cells"][3] = "4,0.25\n1h 0m 0s"
        self.assertFalse(self.run_rows()[0])
        self.raw["cells"][3] = "1,040.25\n1h 0m 0s"
        self.assertEqual(self.run_rows()[0][0]["distance_miles"], 1040.25)

    def test_batches_maximum(self):
        rows, report = self.run_rows()
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "new"
            MODULE.write_outputs(target, rows * 1001, report)
            self.assertEqual(len(json.loads((target / "batch-0001.json").read_text())["rows"]), 1000)
            self.assertEqual(len(json.loads((target / "batch-0002.json").read_text())["rows"]), 1)


if __name__ == "__main__":
    unittest.main()
