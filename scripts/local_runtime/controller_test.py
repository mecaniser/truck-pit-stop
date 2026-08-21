from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.local_runtime.controller import ControllerError, RuntimeController, Worktree, _assert_secret_free, parser, redact


SHA_A = "a" * 40
SHA_B = "b" * 40


class FixtureController(RuntimeController):
    def __init__(self, root: Path, **kwargs):
        super().__init__(
            config_home=root / "config", state_home=root / "state",
            script_root=root / "repo", frontend_port=25173, api_port=28000,
            deadline=0.05, **kwargs,
        )
        self.target = Worktree(root / "repo", "codex/db037-fixture", SHA_A)
        self.calls: list[str] = []
        self.frontend_occupied = False
        self.api_occupied = False

    def registered_worktrees(self):
        return [self.target, Worktree(self.target.path.parent / "main", "main", SHA_B)]

    def common_git_dir(self, root):
        return self.target.path.parent / ".git"

    def resolve_target(self, requested):
        self.calls.append("resolve")
        if Path(requested).resolve() != self.target.path.resolve():
            raise ControllerError("not registered")
        return self.target

    def schema_preflight(self, config, target):
        self.calls.append("schema")
        return "118_authenticated_presentation"

    def occupancy(self):
        return ([101] if self.frontend_occupied else [], [202] if self.api_occupied else [])

    def listeners(self, port):
        if port == self.frontend_port:
            return [101] if self.frontend_occupied else []
        return [202] if self.api_occupied else []

    def verify_runtime(self, state, config):
        return (state.get("trusted", True), [] if state.get("trusted", True) else ["fixture mismatch"])

    def stop_verified(self, state, config):
        healthy, reasons = self.verify_runtime(state, config)
        if not healthy:
            raise ControllerError("refusing to stop unverified runtime: " + "; ".join(reasons))
        self.calls.append("stop:" + state["runtime"]["sha"])
        self.frontend_occupied = self.api_occupied = False

    def start_runtime(self, target, config, repo_head):
        self.calls.append("start:" + target.sha)
        self.frontend_occupied = self.api_occupied = True
        return {
            "schema": 1, "phase": "healthy", "runtime": target.public(),
            "migration_head": repo_head, "frontend": {"pid": 101},
            "api": {"id": "fixture"}, "recorded_at": 1,
        }


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "repo").mkdir()
        (self.root / "main").mkdir()
        self.controller = FixtureController(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def config(self):
        return {
            "schema": 1, "common_git_dir": str(self.root / ".git"),
            "main_worktree": str(self.root / "main"), "compose_project": "fixture",
            "api_service": "api",
        }

    def state(self, *, trusted=True):
        return {
            "schema": 1, "phase": "healthy", "runtime": self.controller.target.public(),
            "migration_head": "118_authenticated_presentation", "frontend": {"pid": 101},
            "api": {"id": "fixture"}, "recorded_at": 1, "trusted": trusted,
        }

    def persist(self, state=None):
        self.controller.atomic_write(self.controller.config_path, self.config())
        self.controller.atomic_write(self.controller.state_path, state or self.state())

    def test_cli_surface_is_exact(self):
        self.assertEqual(parser().parse_args(["status", "--json"]).command, "status")
        self.assertTrue(parser().parse_args(["switch", "/tmp/x", "--dry-run"]).dry_run)
        self.assertTrue(parser().parse_args(["switch-main", "--dry-run"]).dry_run)
        self.assertEqual(parser().parse_args(["stop"]).command, "stop")

    def test_fixed_public_ports(self):
        controller = RuntimeController(config_home=self.root, state_home=self.root, script_root=self.root / "repo")
        self.assertEqual((controller.frontend_port, controller.api_port), (5173, 8000))

    def test_atomic_state_is_private_and_secret_free(self):
        self.controller.atomic_write(self.controller.state_path, {"schema": 1, "phase": "stopped"})
        self.assertEqual(stat.S_IMODE(self.controller.state_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.controller.state_path.parent.stat().st_mode), 0o700)

    def test_state_rejects_secret_keys(self):
        with self.assertRaisesRegex(ControllerError, "secret-shaped"):
            self.controller.atomic_write(self.controller.state_path, {"schema": 1, "access_token": "canary"})
        self.assertFalse(self.controller.state_path.exists())

    def test_state_rejects_secret_values(self):
        with self.assertRaisesRegex(ControllerError, "secret-shaped"):
            _assert_secret_free({"error": "Authorization: Bearer canary-secret"})

    def test_redaction_covers_bearer_query_and_url_userinfo(self):
        value = redact("Bearer abc token=def https://user:pass@example.test")
        self.assertNotIn("abc", value)
        self.assertNotIn("def", value)
        self.assertNotIn("user:pass", value)

    def test_metadata_location_inside_worktree_is_refused(self):
        controller = FixtureController(self.root)
        controller.state_path = self.root / "repo" / ".state.json"
        with self.assertRaisesRegex(ControllerError, "outside every worktree"):
            controller.atomic_write(controller.state_path, {"schema": 1})

    def test_status_missing_metadata_never_adopts_ports(self):
        self.controller.frontend_occupied = self.controller.api_occupied = True
        result = self.controller.status()
        self.assertFalse(result["managed"])
        self.assertFalse(result["healthy"])
        self.assertTrue(result["frontend_port"])

    def test_status_revalidates_recorded_runtime(self):
        self.persist()
        self.controller.frontend_occupied = self.controller.api_occupied = True
        self.assertTrue(self.controller.status()["healthy"])

    def test_status_reports_identity_drift(self):
        self.persist(self.state(trusted=False))
        self.controller.frontend_occupied = self.controller.api_occupied = True
        result = self.controller.status()
        self.assertFalse(result["healthy"])
        self.assertIn("fixture mismatch", result["reasons"])

    def test_dry_run_has_no_filesystem_or_runtime_mutation(self):
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        result = self.controller.switch(self.root / "repo", dry_run=True)
        after = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(self.controller.calls, ["resolve", "schema"])
        self.assertTrue(result["dry_run"])

    def test_mixed_source_refuses_before_mutation(self):
        self.controller.frontend_occupied = True
        with self.assertRaisesRegex(ControllerError, "mixed runtime ownership"):
            self.controller.switch(self.root / "repo", dry_run=True)
        self.assertEqual(self.controller.calls, ["resolve", "schema"])

    def test_unknown_listener_refuses_unchanged(self):
        self.controller.frontend_occupied = self.controller.api_occupied = True
        with self.assertRaisesRegex(ControllerError, "no trusted controller state"):
            self.controller.switch(self.root / "repo", dry_run=True)
        self.assertTrue(self.controller.frontend_occupied)
        self.assertTrue(self.controller.api_occupied)

    def test_identity_mismatch_refuses_unchanged(self):
        self.persist(self.state(trusted=False))
        self.controller.frontend_occupied = self.controller.api_occupied = True
        with self.assertRaisesRegex(ControllerError, "ownership refused"):
            self.controller.switch(self.root / "repo", dry_run=True)
        self.assertTrue(self.controller.frontend_occupied)

    def test_migration_mismatch_stops_before_occupancy(self):
        def mismatch(config, target):
            raise ControllerError("migration mismatch")
        self.controller.schema_preflight = mismatch
        self.controller.occupancy = mock.Mock(side_effect=AssertionError("must not inspect cutover after mismatch"))
        with self.assertRaisesRegex(ControllerError, "migration mismatch"):
            self.controller.switch(self.root / "repo", dry_run=True)

    def test_successful_switch_records_exact_fixture(self):
        result = self.controller.switch(self.root / "repo")
        self.assertEqual(result["runtime"], self.controller.target.public())
        self.assertEqual(self.controller.calls, ["resolve", "schema", "resolve", "start:" + SHA_A, "resolve"])
        raw = self.controller.state_path.read_text()
        self.assertIn("codex/db037-fixture", raw)
        self.assertIn(SHA_A, raw)
        self.assertNotIn("token", raw.lower())

    def test_stop_only_stops_verified_joint_runtime(self):
        self.persist()
        self.controller.frontend_occupied = self.controller.api_occupied = True
        result = self.controller.stop()
        self.assertEqual(result["phase"], "stopped")
        self.assertEqual(self.controller.calls, ["stop:" + SHA_A])

    def test_stop_refuses_untrusted_runtime(self):
        self.persist(self.state(trusted=False))
        self.controller.frontend_occupied = self.controller.api_occupied = True
        with self.assertRaisesRegex(ControllerError, "unverified"):
            self.controller.stop()
        self.assertTrue(self.controller.frontend_occupied)

    def test_failed_cutover_attempts_prior_rollback_once(self):
        prior_target = Worktree(self.root / "repo", "codex/db037-fixture", SHA_A)
        self.persist(self.state())
        self.controller.frontend_occupied = self.controller.api_occupied = True
        calls = 0
        original_start = self.controller.start_runtime
        def fail_then_restore(target, config, head):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ControllerError("new runtime failed")
            return original_start(target, config, head)
        self.controller.start_runtime = fail_then_restore
        with self.assertRaisesRegex(ControllerError, "prior runtime was restored"):
            self.controller.switch(self.root / "repo")
        self.assertEqual(calls, 2)
        self.assertEqual(json.loads(self.controller.state_path.read_text())["phase"], "rolled_back")

    def test_target_is_revalidated_under_lock_and_before_healthy_record(self):
        self.controller.switch(self.root / "repo")
        self.assertEqual(self.controller.calls.count("resolve"), 3)

    def test_lock_time_target_change_refuses_before_stop(self):
        self.persist()
        self.controller.frontend_occupied = self.controller.api_occupied = True
        changed = Worktree(self.root / "repo", "codex/db037-fixture", SHA_B)
        self.controller.resolve_target = mock.Mock(side_effect=[self.controller.target, changed])
        with self.assertRaisesRegex(ControllerError, "changed before cutover"):
            self.controller.switch(self.root / "repo")
        self.assertNotIn("stop:" + SHA_A, self.controller.calls)

    def test_exec_replacement_refuses_stop(self):
        state = self.state()
        state["frontend"] = {"pid": 101, "pgid": 101, "started": "fixed", "command": "vite", "cwd": str(self.root / "repo/frontend")}
        controller = RuntimeController(config_home=self.root / "c", state_home=self.root / "s", script_root=self.root / "repo")
        controller.resolve_target = mock.Mock(return_value=self.controller.target)
        controller.listeners = mock.Mock(return_value=[101])
        controller.process_identity = mock.Mock(return_value={**state["frontend"], "command": "hostile replacement"})
        controller.container_identity = mock.Mock(return_value={"id": "fixture", "started": None, "bind_source": None, "project": None, "service": None})
        healthy, reasons = controller.verify_runtime(state, self.config())
        self.assertFalse(healthy)
        self.assertIn("frontend command mismatch", reasons)

    def test_compose_up_then_readiness_failure_stops_exact_target_api(self):
        controller = RuntimeController(config_home=self.root / "c", state_home=self.root / "s", script_root=self.root / "repo")
        target = self.controller.target
        process = mock.Mock(pid=777)
        controller.runner.popen = mock.Mock(return_value=process)
        controller._compose = mock.Mock(side_effect=[
            subprocess.CompletedProcess([], 0, stdout=""),
            subprocess.CompletedProcess([], 0, stdout=""),
            subprocess.CompletedProcess([], 0, stdout="new-api\n"),
        ])
        controller._wait_port = mock.Mock(side_effect=ControllerError("readiness failed"))
        controller._inspect_api_container = mock.Mock(return_value={"id": "new-api"})
        controller.runner.run = mock.Mock(return_value=subprocess.CompletedProcess([], 0, stdout=""))
        with mock.patch("os.getpgid", return_value=777), mock.patch("os.killpg"):
            with self.assertRaisesRegex(ControllerError, "readiness failed"):
                controller.start_runtime(target, self.config(), "118_authenticated_presentation")
        controller.runner.run.assert_called_once_with(["docker", "stop", "new-api"])

    def test_denies_root_home_parent_bare_symlink_and_nested_non_worktree(self):
        controller = RuntimeController(config_home=self.root / "c", state_home=self.root / "s", script_root=self.root / "repo")
        registered = Worktree(self.controller.target.path.resolve(), self.controller.target.branch, self.controller.target.sha)
        controller.registered_worktrees = mock.Mock(return_value=[registered])
        with self.assertRaisesRegex(ControllerError, "root, user home"):
            controller.resolve_target("/")
        with mock.patch("pathlib.Path.home", return_value=self.root):
            with self.assertRaisesRegex(ControllerError, "root, user home"):
                controller.resolve_target(self.root)
        with self.assertRaisesRegex(ControllerError, "repository parent"):
            controller.resolve_target(self.root)
        nested = self.root / "repo" / "nested"
        nested.mkdir()
        with self.assertRaisesRegex(ControllerError, "registered worktree"):
            controller.resolve_target(nested.resolve())
        alias = self.root / "alias"
        alias.symlink_to(self.root / "repo")
        with self.assertRaisesRegex(ControllerError, "symlinked"):
            controller.resolve_target(alias)
        controller.git = mock.Mock(side_effect=lambda root, *args, **kwargs: "true" if args == ("rev-parse", "--is-bare-repository") else "")
        with self.assertRaisesRegex(ControllerError, "bare repositories"):
            controller.resolve_target((self.root / "repo").resolve())

    def test_unsafe_rollback_leaves_stopped(self):
        self.persist(self.state())
        self.controller.frontend_occupied = self.controller.api_occupied = True
        self.controller.start_runtime = mock.Mock(side_effect=ControllerError("start failed"))
        self.controller.resolve_target = mock.Mock(side_effect=[self.controller.target, self.controller.target, ControllerError("prior dirty")])
        with self.assertRaisesRegex(ControllerError, "rollback failed"):
            self.controller.switch(self.root / "repo")
        self.assertEqual(self.controller.start_runtime.call_count, 1)
        self.assertEqual(json.loads(self.controller.state_path.read_text())["phase"], "rollback_failed")

    def test_lock_refuses_concurrent_controller(self):
        with self.controller.lock():
            with self.assertRaisesRegex(ControllerError, "another local-runtime"):
                with self.controller.lock():
                    pass

    @unittest.skipUnless(os.name == "posix", "POSIX disposable listener evidence")
    def test_disposable_listener_inspection_uses_non_product_port(self):
        import socket
        try:
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
        except PermissionError:
            self.skipTest("sandbox forbids disposable loopback listeners")
        process = subprocess.Popen(
            ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=self.root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            controller = RuntimeController(config_home=self.root / "c", state_home=self.root / "s", script_root=self.root / "repo", frontend_port=port, api_port=port + 1)
            for _ in range(50):
                if process.pid in controller.listeners(port):
                    break
                import time
                time.sleep(0.02)
            self.assertIn(process.pid, controller.listeners(port))
            identity = controller.process_identity(process.pid)
            self.assertEqual(Path(identity["cwd"]), self.root)
        finally:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
