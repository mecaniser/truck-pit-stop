import json
from pathlib import Path
import tempfile
import unittest

from run_backend_tests import REPO, critical_files


class PartitionTests(unittest.TestCase):
    def test_missing_unsafe_duplicate_and_overlapping_patterns_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/test_one.py").write_text("")
            for patterns in ([], ["tests/missing.py"], ["tests/../test_one.py"],
                             ["tests/test_one.py"] * 2, ["tests/test_*.py", "tests/test_one.py"]):
                with self.subTest(patterns=patterns), self.assertRaises(ValueError):
                    critical_files(root, patterns)

    def test_backend_manifest_partitions_every_discoverable_test_file(self):
        root = REPO / "backend"
        patterns = json.loads((REPO / ".github/critical-tests.json").read_text())["backend"]
        critical = set(critical_files(root, patterns))
        all_files = {str(p.relative_to(root)) for p in root.rglob("*.py")
                     if (p.name.startswith("test_") or p.name.endswith("_test.py"))
                     and not any(part.startswith(".") or part in ("node_modules", "venv", "__pycache__") for part in p.relative_to(root).parts)}
        self.assertTrue(critical and critical < all_files)
        remaining = all_files - critical
        self.assertFalse(critical & remaining)
        self.assertEqual(critical | remaining, all_files)


if __name__ == "__main__":
    unittest.main()
