#!/usr/bin/env python3
"""Permanent host supervisor; every GitHub job gets a discarded Linux VM.

Install a reviewed copy outside any checkout. GitHub admin token remains in the
host keychain. Never execute repository-provided host commands or reuse a guest.
"""
import argparse
import concurrent.futures
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time

REPO = 'mecaniser/truck-pit-stop'
BASE = 'db-ci-base'
PREFIX = 'db-ci-worker-'
LABEL = 'dieselbridge-local'
STOP = threading.Event()
LOG = logging.getLogger('db-ci')


def command(args, *, data=None, timeout=120, check=True):
    result = subprocess.run(args, input=data, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    if check and result.returncode:
        # Never echo stdin or GitHub API response bodies; they can contain tokens.
        raise RuntimeError(f'{args[0]} {args[1]} exited {result.returncode}: {result.stderr[-800:]}')
    return result


def api(path, method='GET'):
    return json.loads(command(['gh', 'api', path, '--method', method]).stdout or '{}')


def guest(name, *args, data=None, check=True, timeout=120):
    return command(['limactl', 'shell', name, *args], data=data, check=check, timeout=timeout)


def owned(name):
    return re.fullmatch(r'db-ci-worker-[12]', name) is not None


def destroy(name):
    if not owned(name):
        raise ValueError('Refusing to remove an unmanaged VM')
    instances = [json.loads(line) for line in command(['limactl', 'list', '--json']).stdout.splitlines()]
    if any(item['name'] == name for item in instances):
        command(['limactl', 'stop', '--force', name], check=False)
        command(['limactl', 'delete', '--force', name])
    for runner in api(f'repos/{REPO}/actions/runners')['runners']:
        if runner['name'] == name:
            api(f'repos/{REPO}/actions/runners/{runner["id"]}', 'DELETE')


def cycle(name):
    destroy(name)
    command(['limactl', 'clone', BASE, name, '--mount-none', '--ssh-port=0', '-y'], timeout=180)
    command(['limactl', 'start', '-y', name], timeout=180)
    # No job can start unless the root-owned firewall is active and identity is safe.
    guest(name, 'sudo', 'nft', 'list', 'table', 'inet', 'ci_isolation')
    guest(name, 'sudo', 'bash', '-c', 'test "$(id -Gn runner)" = runner && ! sudo -l -U runner 2>/dev/null | grep -q NOPASSWD')
    token = api(f'repos/{REPO}/actions/runners/registration-token', 'POST')['token']
    configure = '''set -eu
cd /opt/actions-runner
export ACTIONS_RUNNER_INPUT_TOKEN="$(cat)"
./config.sh --unattended --ephemeral --url https://github.com/''' + REPO + ''' --name ''' + name + ''' --labels ''' + LABEL + ''' --work _work
'''
    # Token sent only over SSH stdin, not command-line args, files, or logs.
    guest(name, 'sudo', '-u', 'runner', 'env', 'HOME=/home/runner',
          'bash', '-c', configure, data=token, timeout=120)
    guest(name, 'sudo', 'systemctl', 'start', 'db-ci-runner')
    LOG.info('%s listening in a fresh VM', name)
    started = time.monotonic()
    while not STOP.wait(15):
        state = guest(name, 'systemctl', 'is-active', 'db-ci-runner', check=False).stdout.strip()
        if state != 'active':
            LOG.info('%s finished (%s); discarding VM', name, state)
            return
        if time.monotonic() - started > 7200:
            LOG.error('%s exceeded two-hour worker lifetime; discarding VM', name)
            return


def worker(name):
    while not STOP.is_set():
        try:
            cycle(name)
        except Exception as error:
            LOG.error('%s: %s', name, error)
        finally:
            try:
                destroy(name)
            except Exception as error:
                LOG.error('%s cleanup failed: %s', name, error)
                # Never register another worker on a potentially contaminated VM.
        STOP.wait(15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slots', type=int, choices=(1, 2), default=2)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.state_dir / 'supervisor.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        signal.signal(signal.SIGTERM, lambda *_: STOP.set())
        signal.signal(signal.SIGINT, lambda *_: STOP.set())
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.slots) as pool:
            for slot in range(1, args.slots + 1):
                pool.submit(worker, PREFIX + str(slot))


if __name__ == '__main__':
    main()
