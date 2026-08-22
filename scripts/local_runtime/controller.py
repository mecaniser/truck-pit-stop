#!/usr/bin/env python3
"""Safe, single-owner controller for the developer-visible DieselBridge runtime."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import unquote, urlsplit
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 5173
API_HOST = "127.0.0.1"
API_PORT = 8000
SCHEMA_VERSION = 1
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
DATABASE_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,63}$")
SECRET_KEY_RE = re.compile(r"(?i)(authorization|cookie|password|passwd|secret|token|api[_-]?key|credential)")
SECRET_TEXT_RE = re.compile(
    r"(?i)(bearer\s+)[^\s,;]+|((?:token|password|secret|api[_-]?key)=)[^&\s]+|"
    r"([a-z][a-z0-9+.-]*://)[^/@\s]+@"
)


class ControllerError(RuntimeError):
    pass


class TargetCleanupError(ControllerError):
    pass


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SECRET_KEY_RE.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_TEXT_RE.sub(lambda match: (match.group(1) or match.group(2) or match.group(3)) + "[REDACTED]", value)
    return value


def _assert_secret_free(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                raise ControllerError(f"secret-shaped state key refused: {path}.{key}")
            _assert_secret_free(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_secret_free(item, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_TEXT_RE.search(value):
        raise ControllerError(f"secret-shaped state value refused: {path}")


class Runner:
    def run(
        self,
        args: Iterable[str],
        *,
        cwd: Path | None = None,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(list(args), cwd=cwd, env=env, text=True, capture_output=True, check=False)
        if check and result.returncode:
            detail = redact((result.stderr or result.stdout).strip())
            raise ControllerError(f"command failed ({result.returncode}): {detail}")
        return result

    def popen(self, args: Iterable[str], *, cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            list(args), cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str
    sha: str

    def public(self) -> dict[str, str]:
        return {"path": str(self.path), "branch": self.branch, "sha": self.sha}


class RuntimeController:
    def __init__(
        self,
        *,
        runner: Runner | None = None,
        frontend_port: int = FRONTEND_PORT,
        api_port: int = API_PORT,
        config_home: Path | None = None,
        state_home: Path | None = None,
        script_root: Path | None = None,
        deadline: float = 90.0,
    ) -> None:
        self.runner = runner or Runner()
        self.frontend_port = frontend_port
        self.api_port = api_port
        self.script_root = (script_root or Path(__file__).resolve().parents[2]).resolve()
        config_base = config_home or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        state_base = state_home or Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        self.config_path = config_base / "dieselbridge/local-runtime/v1/config.json"
        self.state_path = state_base / "dieselbridge/local-runtime/v1/state.json"
        self.lock_path = state_base / "dieselbridge/local-runtime/v1/controller.lock"
        self.deadline = deadline

    def git(self, root: Path, *args: str, check: bool = True) -> str:
        return self.runner.run(["git", "-C", str(root), *args], check=check).stdout.strip()

    def common_git_dir(self, root: Path) -> Path:
        return Path(self.git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()

    def registered_worktrees(self) -> list[Worktree]:
        raw = self.git(self.script_root, "worktree", "list", "--porcelain")
        entries: list[Worktree] = []
        current: dict[str, str] = {}
        for line in [*raw.splitlines(), ""]:
            if not line:
                if current.get("worktree") and current.get("HEAD") and current.get("branch"):
                    entries.append(Worktree(Path(current["worktree"]).resolve(), current["branch"].removeprefix("refs/heads/"), current["HEAD"]))
                current = {}
            elif " " in line:
                key, value = line.split(" ", 1)
                current[key] = value
        return entries

    def resolve_target(self, requested: str | Path) -> Worktree:
        requested_path = Path(requested).expanduser()
        lexical = requested_path.absolute()
        candidate = requested_path.resolve()
        home = Path.home().resolve()
        if candidate == Path("/") or candidate == home or candidate in self.script_root.parents:
            raise ControllerError("root, user home, and repository parent targets are forbidden")
        if lexical != candidate:
            raise ControllerError("symlinked or escaping target paths are forbidden")
        if not candidate.is_dir():
            raise ControllerError("target must be a worktree directory")
        if self.git(candidate, "rev-parse", "--is-bare-repository", check=False) == "true":
            raise ControllerError("bare repositories are forbidden")
        matches = [item for item in self.registered_worktrees() if item.path == candidate]
        if len(matches) != 1:
            raise ControllerError("target must be one clean, named, registered worktree")
        target = matches[0]
        if self.common_git_dir(target.path) != self.common_git_dir(self.script_root):
            raise ControllerError("target belongs to a different common git directory")
        if not BRANCH_RE.fullmatch(target.branch) or not SHA_RE.fullmatch(target.sha):
            raise ControllerError("target branch or SHA is invalid")
        if self.git(target.path, "status", "--porcelain=v2", "--untracked-files=normal"):
            raise ControllerError("target worktree is dirty")
        head = self.git(target.path, "rev-parse", "HEAD")
        if head != target.sha:
            raise ControllerError("target HEAD changed while it was inspected")
        required = (
            "docker-compose.yml", "docker-compose.dev.yml", "backend/alembic.ini",
            "backend/alembic/versions", "backend/.env", "frontend/package.json",
            "frontend/package-lock.json", "frontend/vite.config.ts", "frontend/node_modules/.bin/vite",
        )
        missing = [name for name in required if not (target.path / name).exists()]
        if missing:
            raise ControllerError("target is not locally runnable; missing: " + ", ".join(missing))
        return target

    def _main_worktree(self) -> Worktree:
        matches = [item for item in self.registered_worktrees() if item.branch == "main"]
        if len(matches) != 1:
            raise ControllerError("exactly one registered main worktree is required")
        return matches[0]

    def bootstrap_config(self) -> dict[str, Any]:
        main = self._main_worktree()
        repository_root = self.common_git_dir(self.script_root).parent
        project = re.sub(r"[^a-z0-9_-]", "-", repository_root.name.lower()).strip("-")
        if not project:
            raise ControllerError("could not derive a safe Compose project name")
        database_name = os.environ.get("DIESELBRIDGE_LOCAL_DB_NAME", "truckpitstop")
        if not DATABASE_NAME_RE.fullmatch(database_name):
            raise ControllerError("configured local database identity is invalid")
        return {
            "schema": SCHEMA_VERSION,
            "common_git_dir": str(self.common_git_dir(self.script_root)),
            "main_worktree": str(main.path),
            "compose_project": project,
            "api_service": "api",
            "database_name": database_name,
        }

    def _validate_storage_location(self, path: Path) -> None:
        resolved_parent = path.parent.resolve()
        for worktree in self.registered_worktrees():
            worktree_path = worktree.path.resolve()
            if Path(os.path.commonpath((resolved_parent, worktree_path))) == worktree_path:
                raise ControllerError("controller state/config must live outside every worktree")

    def atomic_write(self, path: Path, payload: dict[str, Any]) -> None:
        _assert_secret_free(payload)
        self._validate_storage_location(path)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)

    def read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            raise ControllerError(f"controller metadata is unreadable: {redact(str(error))}") from error
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA_VERSION:
            raise ControllerError("controller metadata schema is unsupported")
        _assert_secret_free(payload)
        return payload

    @contextlib.contextmanager
    def lock(self):
        self._validate_storage_location(self.lock_path)
        self.lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ControllerError("another local-runtime operation is active") from error
            yield

    def _repo_head(self, target: Worktree) -> str:
        python = next((path for path in (target.path / ".venv/bin/python", self.script_root / ".venv/bin/python") if path.exists()), None)
        if python is None:
            probe = self.runner.run(["python3", "-c", "import alembic"], check=False)
            if probe.returncode:
                raise ControllerError("an existing Python 3.11 Alembic runtime is required; installation is forbidden")
            python = Path("python3")
        result = self.runner.run([str(python), "-m", "alembic", "heads"], cwd=target.path / "backend")
        heads = [line.split()[0] for line in result.stdout.splitlines() if "(head)" in line]
        if len(heads) != 1:
            raise ControllerError("repository must have exactly one Alembic head")
        return heads[0]

    def _configured_database_name(self, config: dict[str, Any]) -> str:
        database = config.get("database_name")
        if not isinstance(database, str) or not DATABASE_NAME_RE.fullmatch(database):
            raise ControllerError("configured local database identity is invalid")
        return database

    def _database_name_from_url(self, value: str) -> str:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as error:
            raise ControllerError("API database identity is invalid") from error
        database = unquote(parsed.path.lstrip("/"))
        if (
            parsed.scheme not in {"postgresql", "postgresql+asyncpg"}
            or parsed.hostname != "postgres"
            or port not in {None, 5432}
            or parsed.query
            or parsed.fragment
            or not DATABASE_NAME_RE.fullmatch(database)
        ):
            raise ControllerError("API database identity is invalid")
        return database

    def _compose(self, config: dict[str, Any], target: Worktree, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = [
            "docker", "compose", "--project-name", config["compose_project"],
            "--project-directory", str(target.path), "-f", str(target.path / "docker-compose.yml"),
            "-f", str(target.path / "docker-compose.dev.yml"), *args,
        ]
        env = os.environ.copy()
        env["DIESELBRIDGE_LOCAL_DB_NAME"] = self._configured_database_name(config)
        return self.runner.run(command, check=check, env=env)

    def schema_preflight(self, config: dict[str, Any], target: Worktree) -> str:
        repo_head = self._repo_head(target)
        database = self._configured_database_name(config)
        pg = self._compose(
            config, target, "exec", "-T", "postgres", "sh", "-ec",
            'pg_isready -U "$POSTGRES_USER" -d "$1"', "sh", database,
        )
        if "accepting connections" not in pg.stdout:
            raise ControllerError("configured PostgreSQL is not ready")
        db = self._compose(
            config, target, "exec", "-T", "postgres", "sh", "-ec",
            'psql -XAt -U "$POSTGRES_USER" -d "$1" -c "SELECT version_num FROM alembic_version"',
            "sh", database,
        ).stdout.strip().splitlines()
        if db != [repo_head]:
            raise ControllerError(f"migration mismatch: repository={repo_head}, database={db[0] if len(db) == 1 else 'unknown'}")
        redis = self._compose(config, target, "exec", "-T", "redis", "redis-cli", "ping")
        if redis.stdout.strip() != "PONG":
            raise ControllerError("configured Redis is not ready")
        return repo_head

    def listeners(self, port: int) -> list[int]:
        result = self.runner.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"], check=False)
        if result.returncode not in (0, 1):
            raise ControllerError("could not inspect local listener ownership")
        return sorted({int(line[1:]) for line in result.stdout.splitlines() if line.startswith("p") and line[1:].isdigit()})

    def process_identity(self, pid: int) -> dict[str, Any]:
        ps = self.runner.run(["ps", "-p", str(pid), "-o", "pid=,pgid=,lstart=,command="]).stdout.strip()
        if not ps:
            raise ControllerError("frontend process disappeared during inspection")
        parts = ps.split(None, 8)
        if len(parts) < 9:
            raise ControllerError("frontend process identity is incomplete")
        cwd_result = self.runner.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"])
        cwd_lines = [line[1:] for line in cwd_result.stdout.splitlines() if line.startswith("n")]
        if len(cwd_lines) != 1:
            raise ControllerError("frontend cwd could not be verified")
        return {"pid": int(parts[0]), "pgid": int(parts[1]), "started": " ".join(parts[2:7]), "command": " ".join(parts[7:]), "cwd": str(Path(cwd_lines[0]).resolve())}

    def _inspect_api_container(self, container_id: str, config: dict[str, Any], target: Worktree) -> dict[str, Any]:
        raw = self.runner.run(["docker", "inspect", container_id]).stdout
        try:
            item = json.loads(raw)[0]
            labels = item["Config"]["Labels"]
            environment = item["Config"]["Env"]
            ports = item["NetworkSettings"]["Ports"]["8000/tcp"]
            sources = [Path(mount["Source"]).resolve() for mount in item["Mounts"] if mount["Destination"] == "/app" and mount["Type"] == "bind"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise ControllerError("API container metadata is incomplete") from error
        if labels.get("com.docker.compose.project") != config["compose_project"] or labels.get("com.docker.compose.service") != config["api_service"]:
            raise ControllerError("API container project/service ownership mismatch")
        if not isinstance(environment, list) or not all(isinstance(entry, str) for entry in environment):
            raise ControllerError("API container metadata is incomplete")
        database_urls = [entry.split("=", 1)[1] for entry in environment if entry.startswith("DATABASE_URL=")]
        if len(database_urls) != 1 or self._database_name_from_url(database_urls[0]) != self._configured_database_name(config):
            raise ControllerError("API container database identity mismatch")
        if sources != [(target.path / "backend").resolve()]:
            raise ControllerError("API container bind source mismatch")
        if not any(binding.get("HostPort") == str(self.api_port) and binding.get("HostIp") in ("0.0.0.0", "127.0.0.1", "::") for binding in ports or []):
            raise ControllerError("API container published port mismatch")
        return {
            "id": item["Id"],
            "started": item["State"]["StartedAt"],
            "bind_source": str(sources[0]),
            "project": labels["com.docker.compose.project"],
            "service": labels["com.docker.compose.service"],
            "database_name": self._configured_database_name(config),
        }

    def container_identity(self, config: dict[str, Any], target: Worktree) -> dict[str, Any]:
        listing = self.runner.run(["docker", "ps", "--filter", f"publish={self.api_port}", "--format", "{{.ID}}"]).stdout.split()
        if len(listing) != 1:
            raise ControllerError("API port must have exactly one running container owner")
        return self._inspect_api_container(listing[0], config, target)

    def verify_runtime(self, state: dict[str, Any], config: dict[str, Any]) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        try:
            target = self.resolve_target(state["runtime"]["path"])
            if target.sha != state["runtime"]["sha"] or target.branch != state["runtime"]["branch"]:
                reasons.append("recorded worktree identity changed")
            frontend = self.listeners(self.frontend_port)
            if frontend != [state["frontend"]["pid"]]:
                reasons.append("frontend listener identity mismatch")
            else:
                actual = self.process_identity(frontend[0])
                for key in ("pid", "pgid", "started", "command", "cwd"):
                    if actual[key] != state["frontend"][key]:
                        reasons.append(f"frontend {key} mismatch")
            container = self.container_identity(config, target)
            for key in ("id", "started", "bind_source", "project", "service", "database_name"):
                if container[key] != state["api"][key]:
                    reasons.append(f"API {key} mismatch")
        except (ControllerError, KeyError, TypeError) as error:
            reasons.append(str(redact(str(error))))
        return not reasons, reasons

    def occupancy(self) -> tuple[list[int], list[int]]:
        return self.listeners(self.frontend_port), self.listeners(self.api_port)

    def preflight(self, requested: str | Path, config: dict[str, Any]) -> tuple[Worktree, str, dict[str, Any] | None]:
        target = self.resolve_target(requested)
        repo_head = self.schema_preflight(config, target)
        frontend, api = self.occupancy()
        prior = self.read_json(self.state_path)
        if bool(frontend) != bool(api):
            raise ControllerError("mixed runtime ownership refused; ports are unchanged")
        if frontend:
            if not prior:
                raise ControllerError("occupied ports have no trusted controller state; ports are unchanged")
            healthy, reasons = self.verify_runtime(prior, config)
            if not healthy:
                raise ControllerError("occupied runtime ownership refused: " + "; ".join(reasons))
        return target, repo_head, prior

    def _wait_port(self, port: int, occupied: bool) -> None:
        end = time.monotonic() + self.deadline
        while time.monotonic() < end:
            if bool(self.listeners(port)) == occupied:
                return
            time.sleep(0.1)
        raise ControllerError(f"port {port} did not reach the required state")

    def _probe(self, url: str) -> None:
        end = time.monotonic() + self.deadline
        last = "unavailable"
        while time.monotonic() < end:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return
                    last = f"HTTP {response.status}"
            except Exception as error:  # Only redacted status is surfaced.
                last = redact(str(error))
            time.sleep(0.2)
        raise ControllerError(f"health probe failed: {last}")

    def _probe_readiness_once(self) -> None:
        try:
            with urllib.request.urlopen(f"http://{API_HOST}:{self.api_port}/health/ready", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        raise ControllerError("API readiness check failed")

    def _frontend_environment(self, target: Worktree) -> dict[str, str]:
        env = os.environ.copy()
        env.pop("VITE_DIESELBRIDGE_RUNTIME_BRANCH", None)
        env.pop("VITE_DIESELBRIDGE_RUNTIME_SHA", None)
        env["DIESELBRIDGE_RUNTIME_BRANCH"] = target.branch
        env["DIESELBRIDGE_RUNTIME_SHA"] = target.sha
        return env

    def start_runtime(self, target: Worktree, config: dict[str, Any], repo_head: str) -> dict[str, Any]:
        env = self._frontend_environment(target)
        process = self.runner.popen(
            ["npm", "run", "dev", "--", "--host", FRONTEND_HOST, "--port", str(self.frontend_port), "--strictPort"],
            cwd=target.path / "frontend", env=env,
        )
        before_api = set(self._compose(config, target, "ps", "-q", config["api_service"]).stdout.split())
        try:
            self._compose(config, target, "up", "-d", "--no-deps", config["api_service"])
            self._wait_port(self.frontend_port, True)
            self._wait_port(self.api_port, True)
            frontend_pids = self.listeners(self.frontend_port)
            if len(frontend_pids) != 1:
                raise ControllerError("frontend must own exactly one listener")
            frontend = self.process_identity(frontend_pids[0])
            if Path(frontend["cwd"]).resolve() != (target.path / "frontend").resolve():
                raise ControllerError("started frontend cwd mismatch")
            if frontend["pgid"] != os.getpgid(process.pid):
                raise ControllerError("started frontend process-group mismatch")
            api = self.container_identity(config, target)
            self._probe(f"http://{API_HOST}:{self.api_port}/health/ready")
            self._probe(f"http://{FRONTEND_HOST}:{self.frontend_port}/")
            return {"schema": SCHEMA_VERSION, "phase": "healthy", "runtime": target.public(), "migration_head": repo_head, "frontend": frontend, "api": api, "recorded_at": int(time.time())}
        except Exception:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                after_api = set(self._compose(config, target, "ps", "-q", config["api_service"]).stdout.split())
                created = after_api - before_api
                if len(created) > 1:
                    raise ControllerError("multiple newly started target API containers found")
                if created:
                    api = self._inspect_api_container(created.pop(), config, target)
                    self.runner.run(["docker", "stop", api["id"]])
            except Exception as cleanup_error:
                raise TargetCleanupError(f"target API cleanup could not be verified: {redact(str(cleanup_error))}") from cleanup_error
            raise

    def stop_verified(self, state: dict[str, Any], config: dict[str, Any]) -> None:
        healthy, reasons = self.verify_runtime(state, config)
        if not healthy:
            raise ControllerError("refusing to stop unverified runtime: " + "; ".join(reasons))
        os.killpg(state["frontend"]["pgid"], signal.SIGTERM)
        self.runner.run(["docker", "stop", state["api"]["id"]])
        self._wait_port(self.frontend_port, False)
        self._wait_port(self.api_port, False)

    def switch(self, requested: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
        config = self.read_json(self.config_path) or self.bootstrap_config()
        target, repo_head, prior = self.preflight(requested, config)
        plan = {"action": "switch", "dry_run": dry_run, "target": target.public(), "migration_head": repo_head, "prior": prior["runtime"] if prior else None}
        if dry_run:
            return plan
        with self.lock():
            locked_target = self.resolve_target(requested)
            if locked_target != target:
                raise ControllerError("target identity changed before cutover")
            if not self.config_path.exists():
                self.atomic_write(self.config_path, config)
            if prior:
                self.stop_verified(prior, config)
            switching = {"schema": SCHEMA_VERSION, "phase": "switching", "runtime": target.public(), "prior": prior, "recorded_at": int(time.time())}
            self.atomic_write(self.state_path, switching)
            try:
                state = self.start_runtime(target, config, repo_head)
                healthy_target = self.resolve_target(requested)
                if healthy_target != target:
                    raise ControllerError("target identity changed during startup")
                self.atomic_write(self.state_path, state)
                return state
            except Exception as original:
                rollback_error: Exception | None = None
                if prior and not isinstance(original, TargetCleanupError):
                    try:
                        rollback_target = self.resolve_target(prior["runtime"]["path"])
                        if rollback_target.sha != prior["runtime"]["sha"]:
                            raise ControllerError("prior runtime SHA changed")
                        rollback_head = self.schema_preflight(config, rollback_target)
                        restored = self.start_runtime(rollback_target, config, rollback_head)
                        restored["phase"] = "rolled_back"
                        self.atomic_write(self.state_path, restored)
                        raise ControllerError("cutover failed; prior runtime was restored") from original
                    except Exception as error:
                        if isinstance(error, ControllerError) and str(error) == "cutover failed; prior runtime was restored":
                            raise
                        rollback_error = error
                failure = {"schema": SCHEMA_VERSION, "phase": "rollback_failed" if rollback_error else "stopped", "runtime": target.public(), "recorded_at": int(time.time()), "error": str(redact(str(original)))}
                if rollback_error:
                    failure["rollback_error"] = str(redact(str(rollback_error)))
                self.atomic_write(self.state_path, failure)
                raise ControllerError("cutover failed; " + ("rollback failed and ports were left stopped" if rollback_error else "prior runtime was restored" if prior else "ports were left stopped")) from original

    def switch_main(self, *, dry_run: bool = False) -> dict[str, Any]:
        main = self._main_worktree()
        remote = self.git(main.path, "rev-parse", "refs/remotes/origin/main")
        if main.sha != remote:
            raise ControllerError("main worktree must exactly equal the locally known origin/main")
        return self.switch(main.path, dry_run=dry_run)

    def stop(self) -> dict[str, Any]:
        config = self.read_json(self.config_path)
        state = self.read_json(self.state_path)
        if not config or not state or state.get("phase") not in ("healthy", "rolled_back"):
            raise ControllerError("no verified managed runtime is available to stop")
        with self.lock():
            self.stop_verified(state, config)
            stopped = {"schema": SCHEMA_VERSION, "phase": "stopped", "runtime": state["runtime"], "recorded_at": int(time.time())}
            self.atomic_write(self.state_path, stopped)
            return stopped

    def status(self) -> dict[str, Any]:
        config = self.read_json(self.config_path)
        state = self.read_json(self.state_path)
        frontend, api = self.occupancy()
        if not config or not state:
            return {"schema": SCHEMA_VERSION, "managed": False, "phase": "unmanaged", "healthy": False, "frontend_port": bool(frontend), "api_port": bool(api), "reasons": ["controller metadata is absent"]}
        if state.get("phase") not in ("healthy", "rolled_back"):
            return {"schema": SCHEMA_VERSION, "managed": True, "phase": state.get("phase", "unknown"), "healthy": False, "runtime": state.get("runtime"), "frontend_port": bool(frontend), "api_port": bool(api), "reasons": ["runtime is not recorded healthy"]}
        healthy, reasons = self.verify_runtime(state, config)
        if healthy:
            try:
                self._configured_database_name(config)
                target = self.resolve_target(state["runtime"]["path"])
                repo_head = self.schema_preflight(config, target)
                if repo_head != state.get("migration_head"):
                    raise ControllerError("recorded migration head mismatch")
                self._probe_readiness_once()
            except (ControllerError, KeyError, TypeError) as error:
                reasons.append(str(redact(str(error))))
                healthy = False
        return {"schema": SCHEMA_VERSION, "managed": True, "phase": state["phase"], "healthy": healthy, "runtime": state["runtime"], "migration_head": state.get("migration_head"), "frontend_port": bool(frontend), "api_port": bool(api), "reasons": reasons}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="dieselbridge-local")
    commands = result.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("--json", action="store_true")
    switch = commands.add_parser("switch")
    switch.add_argument("worktree")
    switch.add_argument("--dry-run", action="store_true")
    switch_main = commands.add_parser("switch-main")
    switch_main.add_argument("--dry-run", action="store_true")
    commands.add_parser("stop")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    controller = RuntimeController()
    try:
        if args.command == "status":
            payload = controller.status()
        elif args.command == "switch":
            payload = controller.switch(args.worktree, dry_run=args.dry_run)
        elif args.command == "switch-main":
            payload = controller.switch_main(dry_run=args.dry_run)
        else:
            payload = controller.stop()
        if getattr(args, "json", False):
            print(json.dumps(redact(payload), sort_keys=True))
        else:
            print(json.dumps(redact(payload), indent=2, sort_keys=True))
        return 0
    except ControllerError as error:
        print(f"dieselbridge-local: {redact(str(error))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
