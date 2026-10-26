"""Resume private read tasks only. A receipt always takes precedence over reads."""

import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_read_groups = set()


def _stop_group(pid):
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS can reparent terminated descendants before reaping their group,
        # returning EPERM after our successful SIGTERM. Linux runtime failures
        # remain fatal; process-tree tests also check that no child stays alive.
        if sys.platform != "darwin":
            raise


def install_signals(observer=None):
    def stop(signum, _frame):
        if observer is not None:
            observer.shutdown(signum)
        for pid in tuple(_read_groups):
            _stop_group(pid)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def read_process(command, *, timeout, check=True, env=None, observer=None):
    """Bound the whole read-only Node/Chromium group, including orphaned children."""
    started = time.monotonic()
    try:
        process = subprocess.Popen(command, env=env, start_new_session=True)
    except OSError as error:
        if observer is not None:
            observer.child_result(error=error, elapsed_ms=(time.monotonic()-started)*1000)
        raise
    _read_groups.add(process.pid)
    try:
        try:
            result = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            if observer is not None:
                observer.child_result(error=error, elapsed_ms=(time.monotonic()-started)*1000)
            raise
        if observer is not None:
            observer.child_result(result=result, elapsed_ms=(time.monotonic()-started)*1000)
        if check and result:
            raise subprocess.CalledProcessError(result, command)
        return subprocess.CompletedProcess(command, result)
    finally:
        _stop_group(process.pid)
        process.wait(timeout=5)
        _read_groups.discard(process.pid)


def collection_directory(state: Path, *, max_age_seconds=1800, now=None):
    now = now or datetime.now(UTC)
    for directory in sorted(state.iterdir(), reverse=True):
        if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f-]{36}", directory.name):
            continue
        if directory.is_symlink() or not directory.is_dir():
            continue
        if directory.stat().st_mode & 0o077:
            raise ValueError("Collection directory is not private")
        # An uncertain import must use the existing receipt recovery path. Never
        # overwrite its source by running the collector on that directory again.
        if (directory / "receipt.json").exists() or (
            directory / "receipt.json"
        ).is_symlink():
            continue
        source, tasks = directory / "source.json", directory / "source.json.tasks.json"
        if not source.exists() or not tasks.exists():
            continue
        for path in (source, tasks):
            if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
                raise ValueError("Collection checkpoint is not private")
            if path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("Collection checkpoint exceeds limit")
        saved = json.loads(tasks.read_text())
        started = datetime.fromisoformat(saved["created_at"])
        age = (now - started).total_seconds()
        if not 0 <= age <= max_age_seconds:
            continue
        if json.loads(source.read_text()).get("complete") is not False:
            continue
        failure = directory / "source.json.failure.json"
        if failure.exists():
            if (
                failure.is_symlink()
                or failure.stat().st_size > 1024
                or failure.stat().st_mode & 0o077
            ):
                raise ValueError("Collection failure marker is not private")
            if json.loads(failure.read_text()).get("retryable") is not True:
                continue
        return directory
    directory = state / (now.strftime("%Y%m%dT%H%M%SZ") + "-" + str(uuid4()))
    directory.mkdir(mode=0o700)
    return directory


def entry(main, observer=None):
    install_signals(observer)
    print(json.dumps({"stage": "worker_start"}), flush=True)
    try:
        main()
    except Exception as error:  # noqa: BLE001 - service logs must not reveal provider/DB values
        if observer is not None:
            observer.failed(error)
        print(
            json.dumps({"stage": "worker_failed", "reason": "worker_execution_failed"}),
            flush=True,
        )
        raise SystemExit(1) from None
