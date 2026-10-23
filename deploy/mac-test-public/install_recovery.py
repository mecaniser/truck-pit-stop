"""Install recovery for only the approved public test ingress after acceptance."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess

ROOT = Path.home() / 'mac-hosting/test-public'
LABEL = 'com.macapps.testpublic.edge'


def main():
    os.umask(0o077)
    import run_edge
    run_edge.validate_root()
    run_edge.public_authorized(ROOT / 'Caddyfile.public.DISABLED')
    acceptance = json.loads((ROOT / 'private/public-acceptance.json').read_text())
    if (acceptance.get('public_tls_verified') is not True or acceptance.get('browser_verified') is not True
            or acceptance.get('approved_config_sha256') != hashlib.sha256((ROOT / 'Caddyfile.public.DISABLED').read_bytes()).hexdigest()):
        raise RuntimeError('Public acceptance required before login recovery installation')
    destination = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    if destination.exists() or destination.is_symlink():
        raise RuntimeError('Existing recovery job; inspect before replacing')
    value = {'Label': LABEL, 'ProgramArguments': ['/opt/homebrew/bin/python3', str(ROOT / 'run_edge.py'), 'public'],
        'WorkingDirectory': str(ROOT), 'RunAtLoad': True, 'KeepAlive': {'SuccessfulExit': False},
        'ThrottleInterval': 30, 'Umask': 0o077,
        'StandardOutPath': str(ROOT / 'private/supervisor.log'),
        'StandardErrorPath': str(ROOT / 'private/supervisor-error.log')}
    with destination.open('xb') as output:
        plistlib.dump(value, output)
    subprocess.run(['/bin/launchctl', 'bootstrap', 'gui/' + str(os.getuid()), str(destination)], check=True)
    print('Installed independent public test ingress login recovery')


if __name__ == '__main__':
    main()
