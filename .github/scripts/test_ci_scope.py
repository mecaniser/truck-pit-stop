import subprocess
import tempfile
import unittest
from pathlib import Path

from ci_scope import backend_required, changed_paths


class ScopeTests(unittest.TestCase):
    def test_frontend_with_documentation_skips_backend(self):
        self.assertFalse(backend_required(["frontend/src/App.tsx", "docs/RELEASE.md", "README.md"]))

    def test_non_frontend_and_unknown_paths_run_backend(self):
        for paths in (
            [], ["docs/RELEASE.md"], ["backend/app/main.py", "frontend/src/App.tsx"],
            ["e2e/tests/smoke.spec.ts", "frontend/src/App.tsx"],
            [".github/workflows/quality.yml", "frontend/src/App.tsx"],
            ["backend/README.md", "frontend/src/App.tsx"],
            ["railway.json", "frontend/src/App.tsx"],
        ):
            with self.subTest(paths=paths):
                self.assertTrue(backend_required(paths))

    def test_rename_from_backend_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "CI test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "ci@example.invalid"], check=True)
            (root / "backend").mkdir()
            (root / "backend" / "shared.txt").write_text("shared\n")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "base"], check=True)
            base = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            (root / "frontend").mkdir()
            (root / "backend" / "shared.txt").rename(root / "frontend" / "shared.txt")
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "move"], check=True)
            head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            self.assertEqual(
                {"backend/shared.txt", "frontend/shared.txt"},
                set(self._paths_in_repo(root, base, head)),
            )

    @staticmethod
    def _paths_in_repo(root, base, head):
        original = Path.cwd()
        try:
            import os
            os.chdir(root)
            return changed_paths(base, head)
        finally:
            os.chdir(original)


if __name__ == "__main__":
    unittest.main()
