"""Clone only the synthetic DieselBridge database for an older app; never downgrade."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sys
from urllib.parse import quote

ROOT = Path.home() / 'mac-hosting/test-deploy'
STACKS = Path.home() / 'mac-hosting/test-stacks'


def operator():
    spec = importlib.util.spec_from_file_location('stackctl', STACKS / 'tools/stackctl.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('image');p.add_argument('source');p.add_argument('token');a=p.parse_args()
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',a.image) or not re.fullmatch('[a-f0-9]{40}',a.source) or not re.fullmatch('[a-f0-9]{32}',a.token): raise RuntimeError('Invalid release identity')
    if ROOT.resolve()!=ROOT or (ROOT/'.owner').read_text()!='macapps-test-deploy-v1\n': raise RuntimeError('Unknown deploy root')
    op=operator()
    with op.lock():
        directory=ROOT/'private/database-releases'/a.token;directory.mkdir(mode=0o700,parents=True)
        # Exclusive marker preserves an uncertain clone instead of silently retrying.
        marker=directory/'started.json'
        with marker.open('x') as f:json.dump({'source':a.source,'image':a.image,'at':datetime.datetime.now(datetime.timezone.utc).isoformat()},f)
        name='dbtest_'+a.token[:16]; password=secrets.token_hex(32)
        url='postgresql+asyncpg://'+name+':'+quote(password,safe='')+'@postgres:5432/'+name
        def sql(query,database='dieselbridge_local_test',log='clone-query'):
            return op.compose('dieselbridge','exec','-T','postgres','psql','-U','localtest','-d',database,'-v','ON_ERROR_STOP=1','-At',stdin=query.encode(),log=log).decode().strip()
        revision=sql('SELECT version_num FROM alembic_version;')
        dump=op.compose('dieselbridge','exec','-T','postgres','pg_dump','-U','localtest','-d','dieselbridge_local_test','-Fc',log='deploy-clone-dump')
        (directory/'original.dump').write_bytes(dump)
        sql('CREATE ROLE '+name+" LOGIN PASSWORD '"+password+"' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;",log='deploy-clone-role')
        op.compose('dieselbridge','exec','-T','postgres','createdb','-U','localtest','-O',name,name,log='deploy-clone-create')
        op.compose('dieselbridge','exec','-T','postgres','pg_restore','-U','localtest','--no-owner','--role',name,'-d',name,stdin=dump,log='deploy-clone-restore')
        # Only this candidate database is changed; original ACLs remain untouched.
        sql('REVOKE ALL ON DATABASE '+name+' FROM PUBLIC;',name)
        env=dict(json.loads(op.docker(['compose','--env-file',str(STACKS/'private/local.env'),'-p','db-local-test','-f',str(STACKS/'db-local-test/compose.json'),'config','--format','json'],log='deploy-resolve-config'))['services']['web']['environment'])
        env.update(DATABASE_URL=url,REDIS_URL='redis://redis:6379/14',LOCAL_SOURCE_SHA=a.source,RAILWAY_GIT_COMMIT_SHA=a.source)
        (directory/'candidate.env').write_text(''.join(k+'='+str(v)+'\n' for k,v in sorted(env.items())))
        value={'version':1,'app':'dieselbridge','token':a.token,'source':a.source,'image':a.image,'database_url':url,'redis_url':'redis://redis:6379/14','original_database':'dieselbridge_local_test','original_database_revision':revision,'original_database_sha256':hashlib.sha256(dump).hexdigest(),'database_revision':sql('SELECT version_num FROM alembic_version;',name),'security_approved':False,'qa_approved':False,'checks':{}}
        (directory/'candidate.json').write_text(json.dumps(value,indent=2))
        (directory/'clone-completed.json').write_text(json.dumps({'source':a.source,'image':a.image,'token':a.token,'database':name,'original_revision':revision,'clone_revision':value['database_revision'],'original_mutated':False,'backup_retained':True},indent=2))
        print(json.dumps({'token':a.token,'database':name,'clone_revision':value['database_revision'],'original_mutated':False,'approved':False}))


if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Synthetic database clone failed: '+type(e).__name__+'; inspect private release log') from None
