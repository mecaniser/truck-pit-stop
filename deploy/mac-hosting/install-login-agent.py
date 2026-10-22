"""Install independent hosted-app login recovery; never changes staging jobs."""
import os
from pathlib import Path
import plistlib
import subprocess

root = Path.home() / 'mac-hosting'
script = root / 'bin' / 'hostctl.py'
if not script.is_file() or script.is_symlink():
    raise SystemExit('Install hosting controller first')
label = 'com.macapps.hosting.recover'
path = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
config = {
    'Label': label,
    'ProgramArguments': ['/opt/homebrew/bin/python3', str(script), 'recover'],
    'RunAtLoad': True,
    'StandardOutPath': str(root / 'recovery.log'),
    'StandardErrorPath': str(root / 'recovery-error.log'),
}
# Docker restart policies recover existing containers. This job additionally recreates
# accepted hosting projects at login, retrying only when Docker was not ready yet.
config.update(KeepAlive={'SuccessfulExit': False}, ThrottleInterval=60)
if path.exists() and plistlib.loads(path.read_bytes()) != config:
    raise SystemExit('Conflicting hosting login job; refusing replacement')
path.parent.mkdir(exist_ok=True)
path.write_bytes(plistlib.dumps(config))
path.chmod(0o600)
target = 'gui/' + str(os.getuid())
loaded = subprocess.run(['launchctl', 'print', target + '/' + label], capture_output=True)
if loaded.returncode:
    subprocess.run(['launchctl', 'bootstrap', target, str(path)], check=True)
print('Hosted-app recovery installed; FileVault still requires local unlock/login')
