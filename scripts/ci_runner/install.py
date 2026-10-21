#!/usr/bin/env python3
"""Install the reviewed supervisor as a per-login macOS launch agent.

Never stop a running service here. Drain and unload it before upgrading.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

from supervisor import owned, validate_capacity


def assert_idle(domain):
    active = subprocess.run(['launchctl', 'print', domain], capture_output=True)
    if active.returncode == 0:
        raise RuntimeError('Drain and unload the existing launch agent before installation')
    runners = json.loads(subprocess.run(
        ['gh', 'api', 'repos/mecaniser/truck-pit-stop/actions/runners'],
        check=True, capture_output=True, text=True).stdout)['runners']
    if any(owned(item['name']) and item['busy'] for item in runners):
        raise RuntimeError('An owned runner is still busy; no installed files changed')
    instances = subprocess.run(['limactl', 'list', '--json'], check=True,
                               capture_output=True, text=True).stdout
    if any(owned(item['name']) and item['status'] != 'Stopped'
           for item in map(json.loads, instances.splitlines())):
        raise RuntimeError('Owned worker VMs must be stopped before installation')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slots', type=int, default=2)
    parser.add_argument('--cpus', type=int, default=4)
    parser.add_argument('--memory', type=int, default=8)
    args = parser.parse_args()
    validate_capacity(args.slots, args.cpus, args.memory)
    home = Path.home()
    root = home / 'Library/Application Support/DieselBridge CI'
    domain = f'gui/{os.getuid()}/com.dieselbridge.ci'
    assert_idle(domain)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (root / 'state').mkdir(exist_ok=True, mode=0o700)
    shutil.copy2(Path(__file__).with_name('supervisor.py'), root / 'supervisor.py')
    (root / 'supervisor.py').chmod(0o700)
    plist = home / 'Library/LaunchAgents/com.dieselbridge.ci.plist'
    plist.parent.mkdir(exist_ok=True)
    settings = {
        'Label': 'com.dieselbridge.ci',
        'ProgramArguments': ['/usr/bin/caffeinate', '-s', '/usr/bin/python3',
                             str(root / 'supervisor.py'), '--state-dir', str(root / 'state'),
                             '--slots', str(args.slots), '--cpus', str(args.cpus),
                             '--memory', str(args.memory)],
        'EnvironmentVariables': {'PATH': str(Path(shutil.which('gh')).parent) + ':/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
        'WorkingDirectory': str(root),
        'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 30,
        'ExitTimeOut': 120, 'ProcessType': 'Standard',
        'StandardOutPath': str(root / 'supervisor.log'),
        'StandardErrorPath': str(root / 'supervisor.log'),
    }
    plist.write_bytes(plistlib.dumps(settings))
    plist.chmod(0o600)
    subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(plist)], check=True)
    print(f'Installed {plist}')


if __name__ == '__main__':
    main()
