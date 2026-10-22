"""One reviewed diagnostic router start; never stop relay or retry containers."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import subprocess
import time

ROOT = Path.home() / 'mac-hosting/tph-backup-rehearsal-v3'
RESUME_SHA = '3d6d84f499f7e097b367774a092f77222b322fc73ec7b71d0a6694deed41ba71'
ATTEMPTS = {
    'private/existing-resume-started.json': 'c45c34bb6fbc466449afb63c25f43558d2934637046a25fed5818405f0b870db',
    'private/existing-resume-failed.json': 'c9157e1405ce5530c18e473cc063e01715d39cb3ba4f209176d9d18c3aeed0b5',
}
RELAY_PID = 67282
RELAY_START = 'Thu Oct 22 01:07:57 2026'
RELAY_SHA = '00baab8fd77d5d395067284f050e643e5d91c72a366a84c654c98fa2dd210193'
PYTHON = '/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python'
CAPTURE_LIMIT = 65536


def check(value, reason):
    if not value: raise RuntimeError(reason)


def sha(data): return hashlib.sha256(data).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def load_dependencies():
    check(ROOT.resolve() == ROOT and not ROOT.is_symlink(), 'Unsafe root')
    path = ROOT / 'resume_existing.py'
    check(path.resolve() == path and sha(path.read_bytes()) == RESUME_SHA, 'Reviewed resume source changed')
    spec = importlib.util.spec_from_file_location('reviewed_resume_dependency', path)
    resume = importlib.util.module_from_spec(spec); spec.loader.exec_module(resume)
    return resume, resume.load_original()


def prior_attempts(resume):
    old = resume.provenance()
    for name, expected in ATTEMPTS.items():
        path = ROOT / name
        check(path.resolve() == path and sha(path.read_bytes()) == expected, 'Consumed resume attempt changed')
    check(not (ROOT / 'private/existing-resume-completed.json').exists(), 'Resume already completed')
    return old


def run_readonly(args):
    result = subprocess.run(args, capture_output=True, timeout=8)
    check(result.returncode == 0 and len(result.stdout) <= 8192, 'Read-only process identity unavailable')
    return result.stdout.decode().strip()


def relay_snapshot():
    source = ROOT / 'tools/relay.py'
    check(source.resolve() == source and sha(source.read_bytes()) == RELAY_SHA, 'Relay source changed')
    start = run_readonly(['/bin/ps', '-p', str(RELAY_PID), '-o', 'lstart='])
    command = run_readonly(['/bin/ps', '-p', str(RELAY_PID), '-o', 'command='])
    cwd = run_readonly(['/usr/sbin/lsof', '-nP', '-a', '-p', str(RELAY_PID), '-d', 'cwd', '-Fn'])
    listeners = run_readonly(['/usr/sbin/lsof', '-nP', '-iTCP:18310', '-sTCP:LISTEN', '-Fpcn'])
    check(start == RELAY_START and command == PYTHON + ' ' + str(source), 'Relay PID/start/command changed')
    check([line[1:] for line in cwd.splitlines() if line.startswith('n')] == [str(Path.home())], 'Relay working directory changed')
    check([line for line in listeners.splitlines() if line.startswith('p')] == ['p' + str(RELAY_PID)] and [line for line in listeners.splitlines() if line.startswith('n')] == ['n127.0.0.1:18310'], 'Loopback port ownership changed')
    return {'pid': RELAY_PID, 'started': start, 'command': command, 'cwd': str(Path.home()), 'source_sha256': RELAY_SHA, 'listener': '127.0.0.1:18310'}


def no_attempt():
    check(not any((ROOT / ('private/router-diagnostic-' + suffix + '.json')).exists() for suffix in ('started', 'failed', 'uncertain', 'completed')), 'Diagnostic already attempted; no retry')


def inspect(resume, original, operator):
    no_attempt()
    old = prior_attempts(resume)
    partial = resume.expected_partial(old)
    current = resume.state_snapshot(original, operator, partial)
    relay = relay_snapshot()
    diagnostic = resume.authority_probe(original, current['railway-simulation'])
    return {'schema': 1, 'helper_sha256': sha(Path(__file__).read_bytes()), 'resume_sha256': RESUME_SHA, 'old_attempts': {**resume.PROVENANCE, **ATTEMPTS}, 'partial_runtime': partial, 'state': old['state'], 'protected': old['protected'], 'relay': relay, 'authority_probe': diagnostic, 'ready': diagnostic['ok'], 'start_only': current['router']['id'], 'live_activation': 'forbidden'}


def terminate_client(client):
    # Only this invocation's Docker CLI child, never daemon/container/relay.
    if client.poll() is None:
        client.terminate()
        try: client.wait(timeout=3)
        except subprocess.TimeoutExpired: client.kill(); client.wait(timeout=3)


def capture_start(original, cid):
    """Bound total pipe data and retain private raw evidence; exactly one start."""
    paths = {name: ROOT / ('private/router-diagnostic-' + name + '.log') for name in ('stdout', 'stderr')}
    streams = {}
    client = None
    output = {'stdout': bytearray(), 'stderr': bytearray()}
    timed_out = limited = False
    try:
        for name, path in paths.items():
            streams[name] = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb')
        client = subprocess.Popen([*original.D, 'start', cid], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 35
        with selectors.DefaultSelector() as selector:
            selector.register(client.stdout, selectors.EVENT_READ, 'stdout'); selector.register(client.stderr, selectors.EVENT_READ, 'stderr')
            while selector.get_map():
                if time.monotonic() >= deadline: timed_out = True; break
                for key, _ in selector.select(min(0.2, max(0, deadline - time.monotonic()))):
                    data = os.read(key.fileobj.fileno(), 8192)
                    if not data: selector.unregister(key.fileobj); continue
                    available = CAPTURE_LIMIT - sum(len(value) for value in output.values())
                    output[key.data].extend(data[:available]); streams[key.data].write(data[:available])
                    if len(data) > available: limited = True; break
                if limited: break
        if timed_out or limited: terminate_client(client)
        else:
            try: client.wait(timeout=max(0.01, deadline-time.monotonic()))
            except subprocess.TimeoutExpired: timed_out = True; terminate_client(client)
        stderr = bytes(output['stderr']).lower()
        # Classify only literal captured error text, never daemon-log inference.
        bind_error = any(text in stderr for text in (b'address already in use', b'port is already allocated', b'bind: address already in use'))
        return {'exit': client.returncode, 'timeout': timed_out, 'output_limit': limited, 'uncertain': timed_out or limited, 'known_bind_error': bind_error, 'capture': {name: {'path': str(paths[name]), 'bytes': len(data), 'sha256': sha(data)} for name, data in output.items()}}
    finally:
        if client is not None:
            terminate_client(client)
            client.stdout.close(); client.stderr.close()
        for stream in streams.values(): stream.flush(); os.fsync(stream.fileno()); stream.close()


def immediate_state(operator):
    value = operator.inspect('router')
    return {'id': value['Id'], 'image': value['Image'], 'running': value['State']['Running'], 'started': value['State']['StartedAt'], 'health': value['State'].get('Health', {}).get('Status'), 'error_sha256': sha(value['State'].get('Error', '').encode())}


def diagnose(resume, original, operator, approved):
    check(approved.get('ready') is True, 'Approved successful authority proof required')
    check(inspect(resume, original, operator) == approved, 'Reviewed diagnostic plan changed')
    private = ROOT / 'private'
    original.write_once(private / 'router-diagnostic-started.json', {'approved_plan_sha256': sha(canonical(approved)), 'start_only': approved['start_only'], 'relay_untouched': True})
    result = None
    observed = None
    try:
        prior_attempts(resume)
        resume.state_snapshot(original, operator, approved['partial_runtime'])
        check(relay_snapshot() == approved['relay'], 'Relay identity changed')
        result = capture_start(original, approved['start_only'])
        observed = immediate_state(operator)
        # Always save captured command result and immediate observation first.
        original.write_once(private / 'router-diagnostic-command.json', {'result': result, 'immediate_router_state': observed})
        check(original.database_snapshot() == approved['state'] and original.protected_snapshot() == approved['protected'], 'Protected/state changed after diagnostic')
        check(relay_snapshot() == approved['relay'], 'Relay changed after diagnostic')
        current = original.container_snapshot(operator)
        other = ('mongo', 'railway-simulation', 'mac-backup')
        original.assert_runtime({name: current[name] for name in other}, {name: approved['partial_runtime'][name] for name in other})
        check(all(current['router'][key] == approved['partial_runtime']['router'][key] for key in ('id', 'image', 'config_sha256', 'host_sha256', 'mounts_sha256')), 'Router immutable boundary changed')
        if result['uncertain']:
            original.write_once(private / 'router-diagnostic-uncertain.json', {'result': result, 'immediate_router_state': observed, 'no_retry': True})
            return {'uncertain': True, 'no_retry': True}
        if result['exit'] != 0:
            # No future start, even when failure has a known error classification.
            original.write_once(private / 'router-diagnostic-failed.json', {'result': result, 'immediate_router_state': observed, 'no_retry': True})
            return {'failed': True, 'exit': result['exit'], 'known_bind_error': result['known_bind_error'], 'no_retry': True}
        expected = json.loads(json.dumps(approved['partial_runtime']))
        check(observed['running'] and observed['started'] != expected['router']['started'], 'Successful command lacks authorized new start')
        expected['router'].update(running=True, started=observed['started'], health='healthy')
        for _ in range(45):
            state = immediate_state(operator)
            check(state['running'] and state['started'] == observed['started'], 'Router exited/restarted')
            if state['health'] == 'healthy': break
            time.sleep(1)
        else: raise RuntimeError('Router not healthy; no retry')
        final = resume.state_snapshot(original, operator, expected)
        diagnostic = resume.authority_probe(original, final['railway-simulation'])
        check(diagnostic['ok'], 'Final read-only authority proof failed')
        resume.state_snapshot(original, operator, expected)
        check(relay_snapshot() == approved['relay'], 'Relay changed at completion')
        original.write_once(private / 'router-diagnostic-completed.json', {'result': result, 'containers': final, 'authority_probe': diagnostic, 'relay_untouched': True, 'protected_unchanged': True, 'prior_failures_preserved': True})
        return {'completed': True, 'router_started_only': True, 'relay_untouched': True}
    except BaseException as error:
        # Existing command/attempt evidence remains; no compensating restart/stop.
        marker = 'router-diagnostic-uncertain.json' if result and result.get('uncertain') else 'router-diagnostic-failed.json'
        original.write_once(private / marker, {'error_type': type(error).__name__, 'result': result, 'immediate_router_state': observed, 'no_retry': True})
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inspect', 'diagnose'))
    parser.add_argument('--approved-plan', type=Path); parser.add_argument('--sha256')
    args = parser.parse_args()
    resume, original = load_dependencies(); operator = original.load_operator()
    with (ROOT / 'private/operator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'inspect': result = inspect(resume, original, operator)
        else:
            check(args.approved_plan and args.sha256, 'Reviewed private plan required')
            check(args.approved_plan.resolve() == args.approved_plan and not args.approved_plan.stat().st_mode & 0o077 and sha(args.approved_plan.read_bytes()) == args.sha256, 'Plan path/permissions/hash mismatch')
            result = diagnose(resume, original, operator, json.loads(args.approved_plan.read_text()))
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as error: raise SystemExit('Diagnostic refused: ' + (str(error) if isinstance(error, RuntimeError) else type(error).__name__)) from None
