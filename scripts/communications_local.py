#!/usr/bin/env python3
"""Explicit isolated DB-COMMS-002 sandbox. Never imports into production."""
from __future__ import annotations
import argparse
import os
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / '.env.communications.local'
PG = 'dieselbridge-comms-002-postgres'
REDIS = 'dieselbridge-comms-002-redis'
VOLUME = 'dieselbridge-comms-002-pgdata'

def config():
    if not CONFIG.exists():
        values = {
            'POSTGRES_PASSWORD': secrets.token_hex(24),
            'SECRET_KEY': secrets.token_hex(32),
            'LOCAL_STAFF_PASSWORD': secrets.token_urlsafe(24),
        }
        CONFIG.write_text(''.join(f'{k}={v}\n' for k,v in values.items()))
        CONFIG.chmod(0o600)
    values = dict(line.split('=',1) for line in CONFIG.read_text().splitlines() if '=' in line)
    if 'LOCAL_WEBHOOK_SECRET' not in values:
        values['LOCAL_WEBHOOK_SECRET'] = secrets.token_hex(32)
        CONFIG.write_text(''.join(f'{k}={v}\n' for k,v in values.items()))
    return values

def environment():
    if (ROOT / "backend/.env").exists():
        raise RuntimeError("Remove or relocate backend/.env before using the isolated harness; existing credentials must not load")
    c = config()
    # Do not inherit any provider/application environment from the caller.
    env = {k:v for k,v in os.environ.items() if k in ('PATH','HOME','TMPDIR','LANG','VIRTUAL_ENV')}
    env.update(c)
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH','')
    env.update(DATABASE_URL=f"postgresql+asyncpg://comms_local:{c['POSTGRES_PASSWORD']}@127.0.0.1:55460/communications_local", REDIS_URL='redis://127.0.0.1:6386/0', ENVIRONMENT='development', FRONTEND_URL='http://127.0.0.1:5186', PUBLIC_API_BASE_URL='http://127.0.0.1:8006', CORS_ORIGINS_STR='http://127.0.0.1:5186', PYTHONPATH=str(ROOT/'backend'), COMMUNICATIONS_ISOLATED_LOCAL='1', TWILIO_AUTH_TOKEN=c['LOCAL_WEBHOOK_SECRET'], TWILIO_ACCOUNT_SID='')
    return env

def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def containers():
    existing = subprocess.check_output(['docker','ps','-a','--format','{{.Names}}'],text=True).splitlines()
    for name, port, destination in [(PG, '55460', '/var/lib/postgresql/data'), (REDIS, '6386', None)]:
        if name in existing:
            item = json.loads(subprocess.check_output(['docker','inspect',name]))[0]
            if item['Config'].get('Labels', {}).get('dieselbridge.scope') != 'communications-local':
                raise RuntimeError(f'Refusing unrelated container {name}')
            bindings = [b for group in item['HostConfig']['PortBindings'].values() for b in group]
            if not any(b['HostIp'] == '127.0.0.1' and b['HostPort'] == port for b in bindings):
                raise RuntimeError(f'Unexpected port binding for {name}')
            if destination and not any(m['Destination'] == destination and m.get('Name') == VOLUME for m in item['Mounts']):
                raise RuntimeError(f'Unexpected volume for {name}')
    if PG not in existing:
        run('docker','run','-d','--name',PG,'--label','dieselbridge.scope=communications-local','-p','127.0.0.1:55460:5432','-e','POSTGRES_USER=comms_local','-e','POSTGRES_DB=communications_local','-e','POSTGRES_PASSWORD','-v',VOLUME+':/var/lib/postgresql/data','postgres:16-alpine',env={**os.environ,'POSTGRES_PASSWORD':config()['POSTGRES_PASSWORD']})
    else:
        run('docker','start',PG)
    if REDIS not in existing:
        run('docker','run','-d','--name',REDIS,'--label','dieselbridge.scope=communications-local','-p','127.0.0.1:6386:6379','redis:7-alpine')
    else:
        run('docker','start',REDIS)
    for _ in range(30):
        probe = subprocess.run(['docker','exec',PG,'pg_isready','-U','comms_local','-d','communications_local'],stdout=subprocess.DEVNULL)
        if probe.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError('Dedicated PostgreSQL did not become ready')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['up','migrate','seed','serve','exec','simulate-next'])
    parser.add_argument('args',nargs=argparse.REMAINDER)
    args = parser.parse_args()
    env = environment()
    if args.command == 'simulate-next':
        if len(args.args) != 1 or args.args[0] not in ('accepted','rejected','unknown'):
            parser.error('simulate-next requires accepted, rejected, or unknown')
        with sqlite3.connect(ROOT / '.communications-provider.sqlite') as ledger:
            ledger.execute('CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY CHECK (id = 1), outcome TEXT NOT NULL)')
            ledger.execute('INSERT OR REPLACE INTO control (id,outcome) VALUES (1,?)',(args.args[0],))
        print('Next simulated provider outcome: ' + args.args[0])
    elif args.command == 'up':
        containers()
    elif args.command == 'migrate':
        run(sys.executable,'-m','alembic','upgrade','head',cwd=ROOT/'backend',env=env)
    elif args.command == 'seed':
        run(sys.executable,str(ROOT/'scripts/communications_local_seed.py'),cwd=ROOT/'backend',env=env)
    elif args.command == 'serve':
        env['PYTHONPATH'] = str(ROOT/'scripts') + os.pathsep + env['PYTHONPATH']
        os.chdir(ROOT/'backend')
        os.execve(sys.executable,[sys.executable,'-m','uvicorn','communications_local_app:app','--host','127.0.0.1','--port','8006'],env)
    else:
        run(*args.args,cwd=ROOT/'backend',env=env)

if __name__ == '__main__':
    main()
