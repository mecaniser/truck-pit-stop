"""Real process outcomes and privacy, without browser/provider/database access."""
import json
import os
import signal
import subprocess
import sys

import pytest
from scripts.motive_sync.lifecycle import FuelLifecycle
from scripts.motive_sync.recovery import read_process


def events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


@pytest.mark.parametrize('program,timeout,expected,detail', [
    ('raise SystemExit(17)', 5, 'nonzero_exit', ('exit_code', 17)),
    ('import os,signal;os.kill(os.getpid(),signal.SIGKILL)', 5, 'child_signal', ('signal', 'SIGKILL')),
    ('import time;time.sleep(10)', .1, 'timeout', None),
])
def test_real_child_outcome_before_cleanup(program, timeout, expected, detail, capsys, monkeypatch):
    from scripts.motive_sync import recovery
    observer = FuelLifecycle()
    observer.enter('collection')
    original = recovery._stop_group
    seen = []
    def cleanup(pid):
        captured = events(capsys)
        seen.extend(captured)
        assert captured[-1]['outcome'] == expected
        original(pid)
    monkeypatch.setattr(recovery, '_stop_group', cleanup)
    with pytest.raises(subprocess.SubprocessError):
        read_process([sys.executable, '-c', program], timeout=timeout, observer=observer)
    assert seen[-1]['new_import_started'] is False
    if detail:
        assert seen[-1][detail[0]] == detail[1]
    assert not recovery._read_groups


def test_spawn_error_and_redaction(capsys):
    observer = FuelLifecycle()
    with pytest.raises(OSError):
        read_process(['/missing/PRIVATE_TOKEN'], timeout=1, observer=observer)
    observer.failed(subprocess.CalledProcessError(17, ['PRIVATE_TOKEN'], output='PRIVATE_TOKEN'))
    observer.child_result(error=OSError('PRIVATE_TOKEN'), elapsed_ms=float('inf'))
    observer.emit('worker_outcome', outcome='PRIVATE_TOKEN', signal='PRIVATE_TOKEN', elapsed_ms=float('nan'), private='PRIVATE_TOKEN')
    output = capsys.readouterr().out
    assert 'PRIVATE_TOKEN' not in output
    assert all('elapsed_ms' not in e or 0 <= e['elapsed_ms'] <= 3600000 for e in map(json.loads, output.splitlines()))


@pytest.mark.parametrize('signum', [signal.SIGTERM, signal.SIGINT])
def test_parent_signal_flushes_before_descendant_cleanup(tmp_path, signum):
    pidfile = tmp_path / 'child-pid'
    program = """
import sys
from scripts.motive_sync.lifecycle import FuelLifecycle
from scripts.motive_sync.recovery import entry,read_process
observer=FuelLifecycle()
def main():
 observer.enter('collection')
 read_process([sys.executable,'-c',"import os,time,pathlib;pathlib.Path("+repr(sys.argv[1])+").write_text(str(os.getpid()));time.sleep(30)"],timeout=60,observer=observer)
entry(main,observer=observer)
"""
    process = subprocess.Popen([sys.executable, '-c', program, str(pidfile)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    import time
    try:
        deadline = time.monotonic()+5
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert pidfile.exists()
        child = int(pidfile.read_text())
        process.send_signal(signum)
        output, errors = process.communicate(timeout=5)
        # Existing macOS duplicate cleanup can return EPERM after the child is gone;
        # this diagnostic-only change deliberately does not alter cleanup semantics.
        assert process.returncode in ({128+signum, 1} if sys.platform == 'darwin' else {128+signum}), (output, errors)
        shutdown = [json.loads(line) for line in output.splitlines() if 'shutdown_requested' in line]
        assert len(shutdown) == 1 and shutdown[0]['signal'] == signal.Signals(signum).name
        assert shutdown[0]['phase'] == 'collection' and shutdown[0]['import_outcome'] == 'not_started'
        with pytest.raises(ProcessLookupError):
            os.kill(child, 0)
        assert not errors
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_collection_failure_never_starts_import(tmp_path, monkeypatch, capsys):
    from scripts.motive_sync import run_fuel_worker as worker
    monkeypatch.setenv('MOTIVE_FUEL_STATE_DIR', str(tmp_path))
    calls = []
    def fail(*args, **kwargs):
        kwargs['observer'].child_result(result=17)
        raise subprocess.CalledProcessError(17, ['PRIVATE_TOKEN'])
    monkeypatch.setattr(worker, 'read_process', fail)
    monkeypatch.setattr(worker.subprocess, 'run', lambda *a, **k: calls.append(a))
    with pytest.raises(SystemExit):
        worker.main()
    assert not calls
    assert all(not e.get('new_import_started') for e in events(capsys))


def test_legacy_dry_import_failure_remains_unknown_without_retry(tmp_path, monkeypatch, capsys):
    from scripts.motive_sync import run_fuel_worker as worker
    monkeypatch.setenv('MOTIVE_FUEL_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('MOTIVE_FUEL_COMMIT', 'false')
    monkeypatch.setattr(worker, 'read_process', lambda *a, **k: None)
    calls = []
    def fail(*a, **k):
        calls.append(a)
        raise subprocess.CalledProcessError(17, ['PRIVATE_TOKEN'])
    monkeypatch.setattr(worker.subprocess, 'run', fail)
    with pytest.raises(SystemExit):
        worker.main()
    assert len(calls) == 1
    emitted = events(capsys)
    last = [e for e in emitted if e.get('event') == 'child_outcome'][-1]
    assert last['phase'] == 'import' and last['import_outcome'] == 'unknown' and last['new_import_started']
    assert 'PRIVATE_TOKEN' not in json.dumps(emitted)


def test_recovery_failure_blocks_collection_and_stays_unknown(tmp_path, monkeypatch, capsys):
    from scripts.motive_sync import run_fuel_worker as worker
    monkeypatch.setenv('MOTIVE_FUEL_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('MOTIVE_FUEL_COMMIT', 'true')
    prior = tmp_path/'prior';prior.mkdir();(prior/'receipt.json').write_text(json.dumps({'mode':'commit','stage':'commit_pending'}))
    (prior/'receipt.json').chmod(0o600)
    calls = []
    monkeypatch.setattr(worker, 'read_process', lambda *a, **k: calls.append(a))
    def fail(*a, **k):
        raise subprocess.CalledProcessError(17, ['PRIVATE_TOKEN'])
    monkeypatch.setattr(worker.subprocess, 'run', fail)
    observer=FuelLifecycle(commit_enabled=True)
    with pytest.raises(subprocess.CalledProcessError):
        worker.main(observer)
    assert not calls
    assert observer.recovery_started and observer.recovery_outcome == 'unknown'
    assert observer.new_import_started is False


def test_default_other_worker_has_no_lifecycle_output(capsys):
    read_process([sys.executable, '-c', 'pass'], timeout=5)
    assert capsys.readouterr().out == ''


def test_dry_run_completion_is_not_claimed_as_committed(capsys):
    observer = FuelLifecycle(commit_enabled=False)
    observer.enter('import')
    observer.enter('complete')
    last = events(capsys)[-1]
    assert last['commit_enabled'] is False
    assert last['import_outcome'] == 'runner_completed'
    assert 'verified' not in json.dumps(last)


def test_recovery_verification_does_not_start_new_import(capsys):
    observer = FuelLifecycle(commit_enabled=True)
    observer.enter('recovery')
    observer.recovery_attempt()
    observer.recovery_verified()
    last = events(capsys)[-1]
    assert last['recovery_outcome'] == 'verified' and last['recovery_started']
    assert last['new_import_started'] is False
