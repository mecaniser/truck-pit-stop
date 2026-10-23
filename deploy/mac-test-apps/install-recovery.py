"""Install separate user-login recovery for accepted private test stacks only."""
import os
from pathlib import Path
import plistlib
import subprocess
root=Path.home()/'mac-hosting/test-stacks'
if not (root/'private/bootstrap-completed').exists(): raise SystemExit('Accept bootstrap before installing recovery')
label='com.macapps.teststacks.recover'
path=Path.home()/'Library/LaunchAgents'/(label+'.plist')
config={'Label':label,'ProgramArguments':['/opt/homebrew/bin/python3',str(root/'tools/stackctl.py'),'recover'],
        'RunAtLoad':True,'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':60,
        'StandardOutPath':str(root/'private/recovery.log'),'StandardErrorPath':str(root/'private/recovery-error.log')}
if path.exists() and plistlib.loads(path.read_bytes())!=config: raise SystemExit('Conflicting recovery job refused')
path.write_bytes(plistlib.dumps(config));path.chmod(0o600)
target='gui/'+str(os.getuid())
if subprocess.run(['launchctl','print',target+'/'+label],capture_output=True).returncode:
    subprocess.run(['launchctl','bootstrap',target,str(path)],check=True)
print('Private test-stack recovery configured; FileVault local unlock remains required')
