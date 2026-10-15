#!/usr/bin/env python3
"""Install the reviewed supervisor as a per-login macOS launch agent."""
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

home = Path.home()
root = home / 'Library/Application Support/DieselBridge CI'
root.mkdir(parents=True, exist_ok=True, mode=0o700)
(root / 'state').mkdir(exist_ok=True, mode=0o700)
shutil.copy2(Path(__file__).with_name('supervisor.py'), root / 'supervisor.py')
(root / 'supervisor.py').chmod(0o700)
plist = home / 'Library/LaunchAgents/com.dieselbridge.ci.plist'
plist.parent.mkdir(exist_ok=True)
settings = {
    'Label': 'com.dieselbridge.ci',
    'ProgramArguments': ['/usr/bin/caffeinate', '-s', '/usr/bin/python3',
                         str(root / 'supervisor.py'), '--state-dir', str(root / 'state')],
    'EnvironmentVariables': {'PATH': str(Path(shutil.which('gh')).parent) + ':/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
    'WorkingDirectory': str(root),
    'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 30,
    'ExitTimeOut': 120, 'ProcessType': 'Background',
    'StandardOutPath': str(root / 'supervisor.log'),
    'StandardErrorPath': str(root / 'supervisor.log'),
}
plist.write_bytes(plistlib.dumps(settings))
plist.chmod(0o600)
subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(plist)], check=True)
print(f'Installed {plist}')
