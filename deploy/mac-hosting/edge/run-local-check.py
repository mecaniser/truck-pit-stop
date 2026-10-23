"""Bounded isolated HTTPS acceptance on the Mac; never starts public ingress."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

root = Path.home() / 'mac-hosting'
edge = root / 'edge'
private = edge / 'private'
private.mkdir(mode=0o700, exist_ok=True)
os.umask(0o077)
# Fail rather than replace any existing listener, even another owned test.
with socket.socket() as probe:
    probe.settimeout(0.5)
    assert probe.connect_ex(('127.0.0.1', 18443)) != 0, 'existing_tls_listener'
env = {**os.environ, 'XDG_CONFIG_HOME': str(private / 'config'),
       'XDG_DATA_HOME': str(private / 'data')}
command = [str(root / 'bin/caddy')]
local = str(edge / 'Caddyfile.local-test')
adapted = subprocess.run([*command, 'adapt', '--adapter', 'caddyfile', '--config', local],
                         capture_output=True, text=True, env=env, check=True, timeout=15)
config = json.loads(adapted.stdout)
listeners = [listener for server in config['apps']['http']['servers'].values() for listener in server['listen']]
assert listeners and set(listeners) == {'127.0.0.1:18443'}
assert config['admin']['disabled'] is True
assert config['apps']['pki']['certificate_authorities']['local']['install_trust'] is False
with (edge / 'local-check.log').open('w') as log:
    subprocess.run([*command, 'validate', '--adapter', 'caddyfile', '--config', local],
                   stdout=log, stderr=log, env=env, check=True, timeout=15)
    process = subprocess.Popen([*command, 'run', '--adapter', 'caddyfile', '--config', local],
                               stdout=log, stderr=log, env=env)
    try:
        last = None
        for _ in range(20):
            if process.poll() is not None:
                raise RuntimeError('isolated_caddy_exited')
            result = subprocess.run([sys.executable, str(edge / 'test_tls.py')],
                                    capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                last = json.loads(result.stdout)
                break
            time.sleep(0.5)
        if last is None:
            raise RuntimeError('local_tls_checks_failed_inspect_private_log')
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
assert process.poll() is not None
with socket.socket() as probe:
    probe.settimeout(0.5)
    assert probe.connect_ex(('127.0.0.1', 18443)) != 0, 'existing_tls_listener'
# Public template is parsed only, never provisioned, loaded or started.
public = subprocess.run([*command, 'adapt', '--adapter', 'caddyfile', '--config',
                         str(edge / 'Caddyfile.public.DISABLED')],
                        capture_output=True, text=True, timeout=15,
                        env={**env, 'CADDY_LAN_ADDRESS': '192.168.4.239'}, check=True)
json.loads(public.stdout)
receipt = {**last, 'listeners': listeners, 'admin_disabled': True,
           'machine_trust_installation_disabled': True, 'test_process_stopped': True,
           'public_template_adapted_only': True}
(edge / 'local-tls-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
