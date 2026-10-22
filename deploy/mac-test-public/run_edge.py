"""Run only the isolated test ingress and access gate; public mode is approval-gated."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time

ROOT = Path.home() / 'mac-hosting/test-public'
CADDY = Path.home() / 'mac-hosting/bin/caddy'
HOSTS = ['dieselbridge-test.elisprotech.com', 'tph-test.elisprotech.com']
LAN = '192.168.4.239'


def validate_root():
    if ROOT.is_symlink() or ROOT.resolve() != ROOT or (ROOT / '.owner').read_text() != 'macapps-test-public-v1\n':
        raise RuntimeError('unrecognized_public_test_root')
    if any(path.is_symlink() for path in ROOT.rglob('*')):
        raise RuntimeError('symlink_in_public_test_root')
    if (ROOT / 'private').stat().st_mode & 0o077:
        raise RuntimeError('private_permissions_required')


def ports_free():
    # Bind probes catch wildcard listeners too; never stop a listener we did not spawn.
    for port in (18444, 8088, 8443, 18680):
        with socket.socket() as probe:
            try:
                probe.bind(('0.0.0.0', port))
            except OSError:
                raise RuntimeError('existing_listener_' + str(port)) from None


def adapted_configuration(mode, config, env):
    result = subprocess.run([str(CADDY), 'adapt', '--adapter', 'caddyfile', '--config', str(config)],
                            capture_output=True, timeout=20, env=env)
    if result.returncode:
        raise RuntimeError('caddy_adaptation_failed')
    adapted = json.loads(result.stdout)
    listeners = {value for server in adapted['apps']['http']['servers'].values() for value in server['listen']}
    expected = {'127.0.0.1:18444'} if mode == 'local' else {LAN + ':8088', LAN + ':8443'}
    if listeners != expected or adapted.get('admin', {}).get('disabled') is not True:
        raise RuntimeError('unexpected_caddy_listener_or_admin_configuration')
    if mode == 'local':
        authorities = adapted.get('apps', {}).get('pki', {}).get('certificate_authorities', {})
        if authorities.get('local', {}).get('install_trust') is not False:
            raise RuntimeError('local_machine_trust_installation_must_be_disabled')
    return listeners


def public_authorized(config):
    path = ROOT / 'private/activation.json'
    if path.stat().st_mode & 0o077:
        raise RuntimeError('activation_permissions_required')
    record = json.loads(path.read_text())
    if (record.get('gates_approved') is not True or record.get('router_reservation_verified') is not True
            or record.get('host') != LAN or record.get('hosts') != HOSTS
            or record.get('approved_config_sha256') != hashlib.sha256(config.read_bytes()).hexdigest()):
        raise RuntimeError('public_activation_receipt_missing_or_mismatched')


def stop_children(children):
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
    for child in reversed(children):
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def bounded_log(stream, path):
    """Drain one owned child's output; retain at most two 1-MiB files."""
    limit = 1024 * 1024
    with stream:
        while chunk := stream.read(8192):
            if path.exists() and path.stat().st_size + len(chunk) > limit:
                path.replace(path.with_suffix(path.suffix + '.previous'))
            with path.open('ab') as output:
                output.write(chunk)


def run(mode, seconds):
    validate_root()
    with (ROOT / 'private/edge.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('edge_runner_already_active') from None
        ports_free()
        config = ROOT / ('Caddyfile.local' if mode == 'local' else 'Caddyfile.public.DISABLED')
        if mode == 'public':
            public_authorized(config)
        env = {**os.environ, 'XDG_CONFIG_HOME': str(ROOT / 'private/config'),
               'XDG_DATA_HOME': str(ROOT / 'private/data')}
        listeners = adapted_configuration(mode, config, env)
        stopped = False

        def stop(_signal, _frame):
            nonlocal stopped
            stopped = True

        old_handlers = {number: signal.signal(number, stop) for number in (signal.SIGTERM, signal.SIGINT)}
        children = []
        log_threads = []
        def spawn(command, log_name):
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
            children.append(child)
            thread = threading.Thread(target=bounded_log, args=(child.stdout, ROOT / 'private' / log_name), daemon=True)
            thread.start()
            log_threads.append(thread)
            return child
        started = time.monotonic()
        try:
            gate = spawn([sys.executable, str(Path(__file__).with_name('access_gate.py'))], 'access-gate.log')
            for _ in range(50):
                if stopped or gate.poll() is not None:
                    raise RuntimeError('access_gate_failed_before_edge_start')
                with socket.socket() as probe:
                    probe.settimeout(0.1)
                    if probe.connect_ex(('127.0.0.1', 18680)) == 0:
                        break
                time.sleep(0.1)
            else:
                raise RuntimeError('access_gate_start_timeout')
            spawn([str(CADDY), 'run', '--adapter', 'caddyfile', '--config', str(config)], 'caddy-' + mode + '.log')
            print(json.dumps({'mode': mode, 'listeners': sorted(listeners), 'started': True}), flush=True)
            while not stopped and (mode == 'public' or time.monotonic() - started < seconds):
                if any(child.poll() is not None for child in children):
                    raise RuntimeError('owned_edge_child_exited')
                time.sleep(0.2)
        finally:
            stop_children(children)
            for thread in log_threads:
                thread.join(timeout=3)
            for number, previous in old_handlers.items():
                signal.signal(number, previous)
            receipt = {'mode': mode, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'children_stopped': all(child.poll() is not None for child in children),
                       'config_sha256': hashlib.sha256(config.read_bytes()).hexdigest()}
            (ROOT / 'private' / ('edge-' + mode + '-stopped.json')).write_text(json.dumps(receipt) + '\n')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('local', 'public'))
    parser.add_argument('--seconds', type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 900:
        parser.error('--seconds must be 1..900 (local mode only)')
    run(args.mode, args.seconds)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, RuntimeError) else type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
