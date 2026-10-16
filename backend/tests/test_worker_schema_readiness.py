from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.commands import worker_schema_readiness as gate


URL = "postgresql://synthetic:DO_NOT_LOG_THIS@127.0.0.1:1/disposable"


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=0.0, sleeps=[])

    def sleep(seconds):
        clock.sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(gate, "time", SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep))
    monkeypatch.setattr(gate, "_expected_heads", lambda: {"installed_head"})
    return clock


def test_stale_schema_waits_then_allows_startup(clock, monkeypatch):
    states = iter(["schema_not_ready", "unavailable", "ready"])
    attempts = []

    def probe(url, heads, timeout):
        attempts.append((heads, timeout))
        return next(states)

    monkeypatch.setattr(gate, "_probe_process", probe)
    gate.wait_for_worker_schema(URL, total_wait=5, retry_seconds=1, probe_timeout=2)
    assert clock.now == 2
    assert attempts == [({"installed_head"}, 2)] * 3


@pytest.mark.parametrize("state", ["schema_not_ready", "unavailable"])
def test_missing_stale_or_unreachable_database_exhausts_bounded_wait(clock, monkeypatch, caplog, state):
    attempts = []

    def probe(url, heads, timeout):
        attempts.append(timeout)
        clock.now += min(0.5, timeout)
        return state

    monkeypatch.setattr(gate, "_probe_process", probe)
    with pytest.raises(SystemExit) as exc:
        gate.wait_for_worker_schema(URL, total_wait=3, retry_seconds=1, probe_timeout=2)
    assert exc.value.code == 78
    assert clock.now == 3
    assert all(0 < duration <= 2 for duration in attempts)
    assert "DO_NOT_LOG_THIS" not in caplog.text
    assert "deadline exhausted" in caplog.text


def test_late_success_does_not_unlock_worker(clock, monkeypatch):
    def late(*args):
        clock.now = 5
        return "ready"

    monkeypatch.setattr(gate, "_probe_process", late)
    with pytest.raises(SystemExit):
        gate.wait_for_worker_schema(URL, total_wait=5)


@pytest.mark.parametrize("failure", ["configuration", "probe"])
def test_unrecoverable_failure_aborts_without_retry(clock, monkeypatch, failure):
    probe = MagicMock(return_value="fatal")
    monkeypatch.setattr(gate, "_probe_process", probe)
    url = "invalid-secret-url" if failure == "configuration" else URL
    with pytest.raises(SystemExit) as exc:
        gate.wait_for_worker_schema(url)
    assert exc.value.code == 78
    assert clock.sleeps == []
    assert probe.call_count == (0 if failure == "configuration" else 1)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_deadline_is_configuration_failure(clock, timeout):
    with pytest.raises(SystemExit):
        gate.wait_for_worker_schema(URL, total_wait=timeout)


@pytest.mark.parametrize("missing", [False, True])
def test_probe_sets_actual_connection_readonly_and_timeouts_and_disposes(monkeypatch, missing):
    import sqlalchemy
    from app.commands import schema_preflight

    connection = MagicMock()
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    create = MagicMock(return_value=engine)
    monkeypatch.setattr(sqlalchemy, "create_engine", create)
    monkeypatch.setattr(schema_preflight, "verify_database", lambda conn, heads: None)
    inspector = SimpleNamespace(get_columns=lambda table: [
        {"name": name} for name in gate.REQUIRED_COLUMNS[table]
        if not (missing and name == "pricing_labor_rate")
    ])
    monkeypatch.setattr(sqlalchemy, "inspect", lambda conn: inspector)

    assert gate._probe_database(URL, {"installed_head"}) == ("schema_not_ready" if missing else "ready")
    options = create.call_args.kwargs["connect_args"]
    assert options["connect_timeout"] == 3
    assert options["options"] == (
        "-c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=1000"
    )
    assert str(connection.execute.call_args.args[0]) == "SET TRANSACTION READ ONLY"
    connection.rollback.assert_called_once()
    engine.dispose.assert_called_once()


def test_child_output_and_failures_never_surface_credentials(monkeypatch, caplog):
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        stdout='{"state":"ready","error":"DO_NOT_LOG_THIS"}',
        stderr="SQL failed with DO_NOT_LOG_THIS", returncode=0,
    ))
    assert gate._probe_process(URL, {"installed_head"}, 1) == "fatal"
    assert "DO_NOT_LOG_THIS" not in caplog.text


def test_actual_hung_probe_child_is_killed_within_deadline(monkeypatch, tmp_path):
    run = subprocess.run
    pid_file = tmp_path / "probe.pid"
    code = f"import os,time; from pathlib import Path; Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(60)"

    def hang(args, **kwargs):
        return run([sys.executable, "-c", code], **kwargs)

    monkeypatch.setattr(gate.subprocess, "run", hang)
    started = time.monotonic()
    assert gate._probe_process(URL, {"installed_head"}, 0.2) == "unavailable"
    assert time.monotonic() - started < 3
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_actual_unreachable_probe_is_bounded_and_sanitized():
    started = time.monotonic()
    assert gate._probe_process(URL, gate._expected_heads(), 5) == "unavailable"
    assert time.monotonic() - started < 6


def test_web_task_import_does_not_run_gate_or_start_probe():
    code = """
import json,sys,types
module=types.ModuleType('app.commands.worker_schema_readiness')
def forbidden(*args,**kwargs):raise AssertionError('Web imports must not wait')
module.wait_for_worker_schema=forbidden
sys.modules[module.__name__]=module
import app.tasks
print(json.dumps({'imported':True}))
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=gate.BACKEND_ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"imported": True}


@pytest.mark.parametrize("mode", ["transition", "timeout", "unexpected"])
def test_installed_celery_signal_gates_blueprint_before_beat_pool_and_consumer(mode):
    # Exercise installed WorkController + Signal.send in a fresh process. The
    # blueprint spy prevents any real Beat, Pool, broker or task from starting.
    code = """
import json,sys
from types import SimpleNamespace
import celery
from celery.worker.worker import WorkController
from app.tasks import celery_app,settings
from app.commands import worker_schema_readiness as gate
assert celery.__version__=='5.3.4'
mode=sys.argv[1];events=[];clock=[0.0]
settings.DATABASE_URL='postgresql://synthetic:DO_NOT_LOG_THIS@127.0.0.1:1/disposable'
celery_app.conf.broker_url='memory://';celery_app.conf.imports=()
gate._expected_heads=lambda:{'installed_head'}
gate.time=SimpleNamespace(monotonic=lambda:clock[0],sleep=lambda s:clock.__setitem__(0,clock[0]+s))
def probe(*args):
 events.append('probe')
 return 'ready' if mode=='transition' and len(events)==2 else 'schema_not_ready'
gate._probe_process=probe
wait=gate.wait_for_worker_schema
def controlled(url):
 if mode=='unexpected':raise RuntimeError('DO_NOT_LOG_THIS')
 return wait(url,total_wait=2,retry_seconds=1)
gate.wait_for_worker_schema=controlled
def blueprint(self,parent,**kwargs):events.append('bootsteps')
WorkController.Blueprint.apply=blueprint
try:
 WorkController(app=celery_app,pool='solo',concurrency=1,beat=True,without_heartbeat=True,without_gossip=True,without_mingle=True)
 outcome='started';exit_code=0
except SystemExit as exc:outcome='stopped';exit_code=exc.code
print(json.dumps({'version':celery.__version__,'outcome':outcome,'exit_code':exit_code,'events':events}))
"""
    result = subprocess.run([sys.executable, "-c", code, mode], cwd=gate.BACKEND_ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "DO_NOT_LOG_THIS" not in result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["version"] == "5.3.4"
    if mode == "transition":
        assert evidence["events"] == ["probe", "probe", "bootsteps"]
        assert evidence["outcome"] == "started"
    else:
        assert "bootsteps" not in evidence["events"]
        assert evidence["outcome"] == "stopped"
        assert evidence["exit_code"] == 78


def test_probe_has_no_task_provider_or_application_settings_imports():
    code = """
import json,sys
from app.commands import worker_schema_readiness as gate
assert gate._expected_heads()
state=gate._probe_database('postgresql://synthetic:DO_NOT_LOG_THIS@127.0.0.1:1/disposable',{'head'})
for name in sys.modules:
 assert not name.startswith(('app.tasks','app.services','app.core.config')),name
print(json.dumps({'state':state}))
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=gate.BACKEND_ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"state": "unavailable"}


def test_invalid_postgres_driver_is_fatal_configuration():
    assert gate._probe_database("postgresql+nonexistentdriver://unused/unused", {"head"}) == "fatal"
