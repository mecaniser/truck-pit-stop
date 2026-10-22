"""One reviewed port-aware rehearsal recovery; no live/provider actions."""
import argparse
import copy
import fcntl
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

ROOT = Path.home() / 'mac-hosting/tph-backup-rehearsal-v3'
DIAGNOSTIC_SHA = '54a5916f325262841603bec009c1b3d7c53556c13f319153a47993358134a2c7'
RECORDS = {
    'private/router-diagnostic-started.json': '0003794952cb3b13edcc728fbfbc8ec48111b3f69f02e3786ba0623ed55fd41c',
    'private/router-diagnostic-command.json': 'ce0e938fb1a6dacb1d58e3177f606cf6039001b35aea70f45be4ee13d8ee3789',
    'private/router-diagnostic-failed.json': 'ddb007a74ad91cec5e89f91bba9e66e32fff69bbd0962645318aefc1216df0cb',
    'private/router-diagnostic-stdout.log': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'private/router-diagnostic-stderr.log': '63129cf162b8927bf5e097c0e8d4fb8e54540fbea1caa1331e50729725a95c36',
}
LIMIT = 65536


def check(value, reason):
    if not value: raise RuntimeError(reason)


def sha(data): return hashlib.sha256(data).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def load_dependencies():
    check(ROOT.resolve() == ROOT and not ROOT.is_symlink(), 'Unsafe root')
    path = ROOT / 'diagnostic_router_start.py'
    check(path.resolve() == path and sha(path.read_bytes()) == DIAGNOSTIC_SHA, 'Diagnostic dependency changed')
    spec = importlib.util.spec_from_file_location('reviewed_port_diagnostic', path)
    diagnostic = importlib.util.module_from_spec(spec); spec.loader.exec_module(diagnostic)
    resume, original = diagnostic.load_dependencies()
    return diagnostic, resume, original


def evidence(diagnostic, resume):
    old = diagnostic.prior_attempts(resume)
    for name, expected in RECORDS.items():
        path = ROOT / name
        check(path.resolve() == path and sha(path.read_bytes()) == expected, 'Captured diagnostic evidence changed')
    for suffix in ('completed', 'uncertain'):
        check(not (ROOT / ('private/router-diagnostic-' + suffix + '.json')).exists(), 'Unexpected diagnostic outcome')
    command = json.loads((ROOT / 'private/router-diagnostic-command.json').read_text())
    check(command['result']['exit'] == 1 and command['result']['known_bind_error'] is True and command['result']['uncertain'] is False, 'No definitive captured bind failure')
    check(b'bind: address already in use' in (ROOT / 'private/router-diagnostic-stderr.log').read_bytes().lower(), 'Captured bind error missing')
    return old


def ports():
    result = subprocess.run(['/usr/sbin/lsof', '-nP', '-iTCP:18310', '-sTCP:LISTEN', '-Fpn'], capture_output=True, timeout=8)
    check(result.returncode in (0, 1) and len(result.stdout) <= 8192, 'Port inventory unavailable')
    if result.returncode == 1:
        check(not result.stdout and not result.stderr, 'Port inventory failed')
        return []
    values = []; pid = None
    for line in result.stdout.decode().splitlines():
        if line.startswith('p'): pid = int(line[1:])
        elif line.startswith('n'):
            check(pid is not None, 'Malformed port inventory')
            values.append({'pid': pid, 'listener': line[1:]})
    check(values, 'Empty successful port inventory')
    return values


def relay_identity(diagnostic, pid):
    source = ROOT / 'tools/relay.py'
    check(source.resolve() == source and sha(source.read_bytes()) == diagnostic.RELAY_SHA, 'Relay source changed')
    command = diagnostic.run_readonly(['/bin/ps', '-p', str(pid), '-o', 'command='])
    started = diagnostic.run_readonly(['/bin/ps', '-p', str(pid), '-o', 'lstart='])
    cwd = diagnostic.run_readonly(['/usr/sbin/lsof', '-nP', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'])
    check(command == diagnostic.PYTHON + ' ' + str(source), 'Relay command changed')
    check([line[1:] for line in cwd.splitlines() if line.startswith('n')] == [str(Path.home())], 'Relay cwd changed')
    check(ports() == [{'pid': pid, 'listener': '127.0.0.1:18310'}], 'Unexpected port owner/binding')
    return {'pid': pid, 'started': started, 'command': command, 'cwd': str(Path.home()), 'source_sha256': diagnostic.RELAY_SHA, 'listener': '127.0.0.1:18310'}


def no_attempt():
    check(not any((ROOT / ('private/router-port-' + name + '.json')).exists() for name in ('started', 'failed', 'uncertain', 'completed')), 'Port recovery already attempted; no retry')


def inspect(diagnostic, resume, original, operator):
    no_attempt(); old = evidence(diagnostic, resume)
    partial = resume.expected_partial(old)
    current = resume.state_snapshot(original, operator, partial)
    relay = diagnostic.relay_snapshot()
    check(relay_identity(diagnostic, relay['pid']) == relay, 'Relay identity disagrees')
    proof = resume.authority_probe(original, current['railway-simulation'])
    return {'schema': 1, 'helper_sha256': sha(Path(__file__).read_bytes()), 'diagnostic_sha256': DIAGNOSTIC_SHA, 'records': {**resume.PROVENANCE, **diagnostic.ATTEMPTS, **RECORDS}, 'partial_runtime': partial, 'state': old['state'], 'protected': old['protected'], 'relay': relay, 'authority_probe': proof, 'ready': proof['ok'], 'start_only': current['router']['id'], 'live_activation': 'forbidden'}


def stop_exact_relay(diagnostic, approved):
    check(relay_identity(diagnostic, approved['pid']) == approved, 'Relay identity changed before TERM')
    os.kill(approved['pid'], signal.SIGTERM)
    for _ in range(50):
        result = subprocess.run(['/bin/ps', '-p', str(approved['pid']), '-o', 'lstart='], capture_output=True, timeout=3)
        if result.returncode == 1:
            check(not ports(), 'Port occupied after accepted relay exit')
            return
        check(result.returncode == 0 and result.stdout.decode().strip() == approved['started'], 'PID changed while awaiting accepted relay exit')
        time.sleep(0.1)
    raise RuntimeError('Accepted relay did not exit; no second signal or router start')


def capture_router_start(diagnostic, original, cid):
    output = {'stdout': bytearray(), 'stderr': bytearray()}; streams = {}; client = None
    timed_out = limited = False
    try:
        for name in output:
            path = ROOT / ('private/router-port-' + name + '.log')
            streams[name] = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb')
        client = subprocess.Popen([*original.D, 'start', cid], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 35
        with selectors.DefaultSelector() as selector:
            selector.register(client.stdout, selectors.EVENT_READ, 'stdout'); selector.register(client.stderr, selectors.EVENT_READ, 'stderr')
            while selector.get_map():
                if time.monotonic() >= deadline: timed_out = True; break
                for key, _ in selector.select(min(0.2, max(0, deadline-time.monotonic()))):
                    data = os.read(key.fileobj.fileno(), 8192)
                    if not data: selector.unregister(key.fileobj); continue
                    available = LIMIT - sum(len(v) for v in output.values())
                    output[key.data].extend(data[:available]); streams[key.data].write(data[:available])
                    if len(data) > available: limited = True; break
                if limited: break
        if timed_out or limited: diagnostic.terminate_client(client)
        else:
            try: client.wait(timeout=max(0.01, deadline-time.monotonic()))
            except subprocess.TimeoutExpired: timed_out = True; diagnostic.terminate_client(client)
        return {'exit': client.returncode, 'timeout': timed_out, 'output_limit': limited, 'uncertain': timed_out or limited, 'known_bind_error': any(text in bytes(output['stderr']).lower() for text in (b'address already in use', b'port is already allocated')), 'capture': {name: {'bytes': len(data), 'sha256': sha(data), 'path': str(ROOT / ('private/router-port-' + name + '.log'))} for name, data in output.items()}}
    finally:
        if client is not None:
            diagnostic.terminate_client(client); client.stdout.close(); client.stderr.close()
        for stream in streams.values(): stream.flush(); os.fsync(stream.fileno()); stream.close()


def restore_relay(diagnostic, original):
    check(not ports(), 'Port remains occupied; no relay restoration or port move')
    source = ROOT / 'tools/relay.py'
    check(sha(source.read_bytes()) == diagnostic.RELAY_SHA, 'Reviewed relay source changed')
    path = ROOT / 'private/router-port-relay.log'
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as log:
        child = subprocess.Popen([diagnostic.PYTHON, str(source)], cwd=Path.home(), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    original.write_once(ROOT / 'private/router-port-relay-launched.json', {'pid': child.pid, 'argv': [diagnostic.PYTHON, str(source)], 'cwd': str(Path.home()), 'source_sha256': diagnostic.RELAY_SHA})
    for _ in range(50):
        check(child.poll() is None, 'Reviewed relay exited; retained log, no retry')
        listeners = ports()
        if listeners:
            check(listeners == [{'pid': child.pid, 'listener': '127.0.0.1:18310'}], 'Unexpected port owner; no kill or port move')
            return relay_identity(diagnostic, child.pid)
        time.sleep(0.1)
    raise RuntimeError('Reviewed relay did not bind; no retry or automatic kill')


def status_get():
    connection = http.client.HTTPConnection('127.0.0.1', 18310, timeout=8)
    try:
        connection.request('GET', '/__backup/status', headers={'Host': 'localhost:18310'})
        response = connection.getresponse(); body = response.read(8193)
        check(response.status == 200 and len(body) <= 8192, 'Restored relay status unavailable')
        value = json.loads(body)
        check(value.get('simulation') is True and value.get('active_site') == 'railway-simulation' and value.get('phase') == 'active' and value.get('epoch') == 5 and value.get('watermark') == 8 and value.get('live_activation') == 'blocked', 'Restored relay status changed')
        return {'httpStatus': 200, 'simulation': True, 'epoch': 5, 'watermark': 8}
    finally: connection.close()


def recover(diagnostic, resume, original, operator, approved):
    check(approved.get('ready') is True and inspect(diagnostic, resume, original, operator) == approved, 'Reviewed port recovery plan changed')
    private = ROOT / 'private'; result = None; new_relay = None
    original.write_once(private / 'router-port-started.json', {'approved_plan_sha256': sha(canonical(approved)), 'start_only': approved['start_only'], 'relay_stop_only': approved['relay']['pid']})
    try:
        evidence(diagnostic, resume)
        resume.state_snapshot(original, operator, approved['partial_runtime'])
        stop_exact_relay(diagnostic, approved['relay'])
        original.write_once(private / 'router-port-relay-stopped.json', {'exact_prior_relay': approved['relay'], 'port_free': True})
        resume.state_snapshot(original, operator, approved['partial_runtime'])
        check(not ports(), 'Port changed before router start')
        result = capture_router_start(diagnostic, original, approved['start_only'])
        observed = diagnostic.immediate_state(operator)
        original.write_once(private / 'router-port-command.json', {'result': result, 'immediate_router_state': observed})
        check(not result['uncertain'], 'Router start outcome uncertain; no retry')
        check(result['exit'] == 0, 'Router start failed; no retry')
        expected = copy.deepcopy(approved['partial_runtime'])
        check(observed['running'] and observed['started'] != expected['router']['started'], 'Authorized router start not observed')
        expected['router'].update(running=True, started=observed['started'], health='healthy')
        for _ in range(45):
            current = diagnostic.immediate_state(operator)
            check(current['running'] and current['started'] == observed['started'], 'Router exited/restarted')
            if current['health'] == 'healthy': break
            time.sleep(1)
        else: raise RuntimeError('Router not healthy; no retry')
        current = resume.state_snapshot(original, operator, expected)
        proof = resume.authority_probe(original, current['railway-simulation']); check(proof['ok'], 'Restored authority proof failed')
        # Internal-network port behavior is observed, never assumed. Any listener
        # (including Docker backend) prevents the explicitly reviewed restoration.
        check(not ports(), 'Port owned after router start; no relay restart or port move')
        new_relay = restore_relay(diagnostic, original)
        original.write_once(private / 'router-port-relay-restored.json', new_relay)
        status = status_get()
        current = resume.state_snapshot(original, operator, expected)
        check(relay_identity(diagnostic, new_relay['pid']) == new_relay, 'Restored relay changed')
        evidence(diagnostic, resume)
        original.write_once(private / 'router-port-completed.json', {'simulation_only': True, 'containers': current, 'state': approved['state'], 'protected_unchanged': True, 'prior_failures_preserved': True, 'router_start': result, 'relay': new_relay, 'authority_probe': proof, 'status': status})
        return {'simulation_only': True, 'router_started_only': True, 'reviewed_relay_restored': True, 'epoch': 5, 'watermark': 8}
    except BaseException as error:
        # Observe preserved boundaries even after a failed/uncertain start. These
        # observations cannot authorize retry or conceal the initiating failure.
        boundaries = {}
        for name, probe in [('state_matches', lambda: original.database_snapshot() == approved['state']), ('protected_matches', lambda: original.protected_snapshot() == approved['protected'])]:
            try: boundaries[name] = probe()
            except Exception: boundaries[name] = False
        try:
            current = original.container_snapshot(operator)
            others = ('mongo', 'railway-simulation', 'mac-backup')
            original.assert_runtime({s: current[s] for s in others}, {s: approved['partial_runtime'][s] for s in others})
            boundaries['other_containers_match'] = True
        except Exception: boundaries['other_containers_match'] = False
        marker = 'router-port-uncertain.json' if result and result.get('uncertain') else 'router-port-failed.json'
        original.write_once(private / marker, {'error_type': type(error).__name__, 'router_start': result, 'restored_relay': new_relay, 'boundaries': boundaries, 'no_retry': True, 'automatic_cleanup': False})
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inspect', 'recover')); parser.add_argument('--approved-plan', type=Path); parser.add_argument('--sha256')
    args = parser.parse_args(); diagnostic, resume, original = load_dependencies(); operator = original.load_operator()
    with (ROOT / 'private/operator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'inspect': result = inspect(diagnostic, resume, original, operator)
        else:
            check(args.approved_plan and args.sha256, 'Reviewed private plan required')
            check(args.approved_plan.resolve() == args.approved_plan and not args.approved_plan.stat().st_mode & 0o077 and sha(args.approved_plan.read_bytes()) == args.sha256, 'Plan path/permissions/hash mismatch')
            result = recover(diagnostic, resume, original, operator, json.loads(args.approved_plan.read_text()))
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as error: raise SystemExit('Port recovery refused: ' + (str(error) if isinstance(error, RuntimeError) else type(error).__name__)) from None
