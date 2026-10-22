#!/usr/bin/env python3
"""Fixed private test-app operations; no Railway, production data or live providers."""
import argparse
import contextlib
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path.home() / 'mac-hosting/test-stacks'
DOCKER = '/Applications/Docker.app/Contents/Resources/bin/docker'
PROJECTS = {'dieselbridge': ('db-local-test', {'postgres','redis','web','worker','gateway'}),
            'tph': ('tph-local-test', {'mongo','web','worker','identity','gateway'})}


def docker(args, *, stdin=None, timeout=180, log='operation'):
    result = subprocess.run([DOCKER, '--context', 'desktop-linux', *args], input=stdin,
                            capture_output=True, timeout=timeout)
    if result.returncode:
        (ROOT / 'private' / (log + '.log')).write_bytes(result.stdout + result.stderr)
        raise RuntimeError(log + '_failed_private_log_retained')
    return result.stdout


def compose(app, *args, stdin=None, timeout=180, log='operation'):
    project, _ = PROJECTS[app]
    return docker(['compose','--env-file',str(ROOT/'private/local.env'),'-p',project,
                   '-f',str(ROOT/project/'compose.json'),*args], stdin=stdin, timeout=timeout, log=log)


def inspect(app):
    project, services = PROJECTS[app]
    ids = docker(['ps','-aq','--filter','label=com.docker.compose.project='+project]).decode().split()
    if not ids: return []
    items = json.loads(docker(['inspect',*ids]))
    found = set()
    for item in items:
        labels = item['Config'].get('Labels',{})
        service = labels.get('com.docker.compose.service')
        if (service not in services or service in found or labels.get('io.macapps.test-stack') != 'v1'
                or item['Name'] != '/'+project+'-'+service+'-1'):
            raise RuntimeError('unexpected_container_ownership_'+project)
        found.add(service)
    return items


@contextlib.contextmanager
def lock():
    os.umask(0o077)
    if ROOT.is_symlink() or ROOT.resolve() != ROOT or (ROOT/'.owner').read_text() != 'macapps-test-stacks-v1\n':
        raise RuntimeError('unrecognized_test_stack_root')
    if any(p.is_symlink() for p in ROOT.rglob('*')):
        raise RuntimeError('symlink_in_test_stack_root')
    with (ROOT/'.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        for app in PROJECTS: inspect(app)
        yield


def mark(phase, state):
    path = ROOT/'private/phases.jsonl'
    with path.open('a') as out:
        out.write(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                              'phase':phase,'state':state})+'\n')


def bootstrap():
    # Never seed twice or turn an uncertain partial setup into a silent retry.
    marker = ROOT/'private/bootstrap-started'
    if marker.exists(): raise RuntimeError('bootstrap_already_started_inspect_phases_before_resuming')
    marker.write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
    credentials = json.loads((ROOT/'private/credentials.json').read_text())
    stages = [
        ('db_storage',lambda:compose('dieselbridge','up','-d','--wait','--wait-timeout','90','postgres','redis',log='db-storage')),
        ('db_migrations',lambda:compose('dieselbridge','run','--rm','--no-deps','-T','web','alembic','upgrade','head',log='db-migrate')),
        ('db_seed',lambda:compose('dieselbridge','run','--rm','--no-deps','-T','web','python','db_seed.py',stdin=json.dumps({k:credentials[k] for k in ('alpha','beta')}).encode(),log='db-seed')),
        ('db_receipt_table',lambda:compose('dieselbridge','exec','-T','postgres','psql','-U','localtest','-d','dieselbridge_local_test','-v','ON_ERROR_STOP=1','-c','CREATE TABLE local_test_receipts (job_key text PRIMARY KEY, execution_count integer NOT NULL CHECK(execution_count=1))',log='db-receipt-table')),
        ('db_apps',lambda:compose('dieselbridge','up','-d','--wait','--wait-timeout','120','web','worker','gateway',log='db-apps')),
        ('tph_storage',lambda:compose('tph','up','-d','--wait','--wait-timeout','120','mongo',log='tph-storage')),
        ('tph_seed',lambda:compose('tph','run','--rm','--no-deps','-T','web','node','tph-seed.cjs',stdin=json.dumps({'manager_pin':credentials['manager_pin']}).encode(),log='tph-seed')),
        ('tph_apps',lambda:compose('tph','up','-d','--wait','--wait-timeout','120','web','worker','identity','gateway',log='tph-apps')),
    ]
    for name, action in stages:
        mark(name,'started'); action(); mark(name,'passed'); print(name+' passed',flush=True)
    (ROOT/'private/bootstrap-completed').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())


def probe():
    db = json.loads(compose('dieselbridge','exec','-T','worker','python','db_probe.py',log='db-probe').decode().strip().splitlines()[-1])
    credentials = json.loads((ROOT/'private/credentials.json').read_text())
    raw = compose('tph','exec','-T','web','node','-e',(ROOT/'tools/tph-probe.cjs').read_text(),stdin=json.dumps({'manager_pin':credentials['manager_pin']}).encode(),log='tph-probe')
    tph = json.loads(raw.decode().strip().splitlines()[-1])
    report = {'dieselbridge': db,'tph': tph}
    (ROOT/'private/worker-acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


def status():
    report = {}
    for app in PROJECTS:
        report[app] = [{'service':i['Config']['Labels']['com.docker.compose.service'],
                        'id':i['Id'],'image':i['Image'],'running':i['State']['Running'],
                        'started':i['State']['StartedAt'],'health':i['State'].get('Health',{}).get('Status'),
                        'oom':i['State']['OOMKilled']} for i in inspect(app)]
    for app, port, route in [('dieselbridge',18200,'/health/ready'),('tph',18201,'/local-test/ready')]:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{route}',timeout=5) as response:
            report[app+'_readiness'] = json.load(response)
    print(json.dumps(report,indent=2))


def recover():
    if not (ROOT/'private/bootstrap-completed').exists(): raise RuntimeError('bootstrap_incomplete_no_automatic_recovery')
    for app in PROJECTS:
        compose(app,'up','-d','--wait','--wait-timeout','120','gateway','worker',*(['identity'] if app=='tph' else []),log='recover-'+app)
        compose(app,'restart','gateway',log='recover-gateway-'+app)
    print('Test app stacks recovered; no migrations, seeds or scheduled jobs executed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['bootstrap','status','probe','recover'])
    args=p.parse_args()
    with lock(): globals()[args.command]()


if __name__=='__main__':
    try: main()
    except Exception as error:
        # Never echo application log bodies, credentials, arguments or env values.
        print(str(error) if type(error) is RuntimeError else type(error).__name__,file=sys.stderr)
        raise SystemExit(1)
