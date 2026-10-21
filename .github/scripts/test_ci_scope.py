import subprocess
import tempfile
import unittest
from pathlib import Path

from ci_scope import backend_required, changed_paths, classify


class ScopeTests(unittest.TestCase):
    def test_frontend_with_documentation_skips_backend(self):
        self.assertFalse(backend_required(["frontend/src/App.tsx", "docs/RELEASE.md", "README.md"]))

    def test_non_frontend_and_unknown_paths_run_backend(self):
        for paths in (
            [], ["backend/app/main.py", "frontend/src/App.tsx"],
            ["e2e/tests/smoke.spec.ts", "frontend/src/App.tsx"],
            [".github/workflows/quality.yml", "frontend/src/App.tsx"],
            ["backend/README.md", "frontend/src/App.tsx"],
            ["railway.json", "frontend/src/App.tsx"],
        ):
            with self.subTest(paths=paths):
                self.assertTrue(backend_required(paths))

    def test_markdown_only_omits_application_suites(self):
        self.assertEqual(
            {"backend_required": False, "frontend_required": False, "smoke_required": False},
            classify(["docs/RELEASE.md", "README.md"]),
        )

    def test_ui_retains_all_frontend_and_smoke_checks(self):
        self.assertEqual(
            {"backend_required": False, "frontend_required": True, "smoke_required": True},
            classify(["frontend/src/App.tsx", "docs/RELEASE.md"]),
        )

    def test_frontend_source_tests_and_public_assets_keep_ui_scope(self):
        for path in ("frontend/src/__tests__/App.test.tsx", "frontend/public/logo.svg", "frontend/index.html"):
            with self.subTest(path=path):
                self.assertEqual(
                    {"backend_required": False, "frontend_required": True, "smoke_required": True},
                    classify([path, "docs/RELEASE.md"]),
                )

    def test_frontend_dependencies_and_tooling_require_all_suites(self):
        for path in (
            "frontend/package.json", "frontend/package-lock.json", "frontend/vite.config.ts",
            "frontend/tsconfig.json", "frontend/eslint.config.js", "frontend/.npmrc",
            "frontend/scripts/run-critical-tests.mjs", "frontend/test/setup.ts",
            ".github/workflows/quality.yml", ".github/critical-tests.json",
        ):
            with self.subTest(path=path):
                self.assertTrue(all(classify(["frontend/src/App.tsx", path]).values()))

    def test_unknown_or_unsafe_paths_fail_closed(self):
        for path in (
            "docs/fixture.py", "docs/config.json", "backend/README.md", "scripts/build.md",
            ".github/scripts/ci_scope.py", "requirements.txt", "railway.json",
            "frontend/../backend/main.py", "/frontend/App.tsx", "frontend/evil\\path",
            "docs/RELEASE.md\nbackend/app.py", "README.MD", "docs/.env",
        ):
            with self.subTest(path=path):
                self.assertTrue(all(classify(["frontend/src/App.tsx", path]).values()))

    def test_missing_git_revision_fails_closed_cli(self):
        result = subprocess.run(
            ["python3", str(Path(__file__).with_name("ci_scope.py")),
             "--base", "missing-ci-base", "--head", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        for key in ("backend_required", "frontend_required", "smoke_required"):
            self.assertIn(f"{key}=true", result.stdout)
        self.assertIn("fail closed", result.stdout)

    def test_backend_deletion_and_moves_cannot_hide_in_allowed_paths(self):
        for destination in ("frontend/shared.txt", "docs/shared.md", None):
            with self.subTest(destination=destination):
                self._assert_backend_change(destination)

    def _assert_backend_change(self, destination):
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
            if destination:
                (root / destination).parent.mkdir(parents=True)
                (root / "backend" / "shared.txt").rename(root / destination)
            else:
                (root / "backend" / "shared.txt").unlink()
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "move"], check=True)
            head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            paths = self._paths_in_repo(root, base, head)
            self.assertEqual({"backend/shared.txt"} | ({destination} if destination else set()), set(paths))
            self.assertTrue(all(classify(paths).values()))

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
