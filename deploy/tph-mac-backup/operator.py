"""Operate only the isolated TPH backup rehearsal; live activation is forbidden."""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid
from urllib.parse import urlunsplit
from configure import ROOT,PROJECT,SOURCE,BASE,MONGO,OWNER,specification

D=['/Applications/Docker.app/Contents/Resources/bin/docker','--context','desktop-linux']


def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(name,value):
    with (ROOT/'private'/name).open('x') as f:json.dump(value,f,indent=2)
def load(name):return json.loads((ROOT/'private'/name).read_text())
def safe():
    if (ROOT/'private/router-revision-uncertain.json').exists():raise RuntimeError('Router revision uncertain; inspect retained evidence')
    if ROOT.is_symlink() or ROOT.resolve()!=ROOT or (ROOT/'.owner').read_text()!=OWNER+'\n':raise RuntimeError('Unknown rehearsal root')
    if (ROOT/'private/config-sha256.txt').read_text().strip()!=hashlib.sha256((ROOT/'compose.json').read_bytes()).hexdigest():raise RuntimeError('Rehearsal configuration drift')
    manifest=load('approved-manifest.json')
    for name,digest in manifest['files'].items():
        file=ROOT/name
        if file.resolve()!=file or file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest()!=digest:raise RuntimeError('Approved rehearsal files changed')
    if json.loads((ROOT/'compose.json').read_text())!=specification(manifest['images'],manifest['uid'],manifest['gid']):raise RuntimeError('Fixed rehearsal contract changed')
    if ROOT.stat().st_mode&0o077 or (ROOT/'private').stat().st_mode&0o077:raise RuntimeError('Private rehearsal permissions required')
def docker(args,*,stdin=None,timeout=120,log=None,env=None):
    result=subprocess.run([*D,*args],input=stdin,capture_output=True,timeout=timeout,env=env)
    if result.returncode:
        if log:(ROOT/'private'/(log+'-'+uuid.uuid4().hex+'.log')).write_bytes(result.stdout+result.stderr)
        raise RuntimeError('Rehearsal operation failed; private evidence retained')
    return result.stdout

def compose(*args,**kw):return docker(['compose','--env-file',str(ROOT/'private/rehearsal.env'),'-p',PROJECT,'-f',str(ROOT/'compose.json'),*args],**kw)
def inspect(site):
    if site not in ('mongo','railway-simulation','mac-backup','router'):raise RuntimeError('Unknown rehearsal service')
    value=json.loads(docker(['inspect',PROJECT+'-'+site+'-1']))[0]
    if value['Config'].get('Labels',{}).get('io.macapps.backup-rehearsal')!=OWNER or value['Config']['Labels'].get('com.docker.compose.project')!=PROJECT:raise RuntimeError('Rehearsal ownership mismatch')
    images=load('images.json');expected_image=MONGO if site=='mongo' else images['router' if site=='router' else 'app']
    if value['Image']!=expected_image:raise RuntimeError('Rehearsal immutable image mismatch')
    identity=ROOT/'private/rehearsal-identity.json'
    if identity.exists():
        expected=json.loads(identity.read_text())[site]
        if value['Id']!=expected['id'] or value['Image']!=expected['image'] or hashlib.sha256(json.dumps(value['Config'],sort_keys=True).encode()).hexdigest()!=expected['config_sha256']:
            raise RuntimeError('Rehearsal runtime identity drift')
    return value

def control(value):
    raw=compose('exec','-T','router','python','control_cli.py',stdin=json.dumps(value).encode(),timeout=30,log='control')
    return json.loads(raw)

def protected():
    path=Path.home()/'mac-hosting/test-deploy/remote.py'
    raw=subprocess.check_output(['/opt/homebrew/bin/python3',str(path),'status'],timeout=30)
    value=json.loads(raw)
    if not value['configuration_matches'] or not value['baseline_matches'] or value['uncertain_operation']:raise RuntimeError('Existing infrastructure drift')
    return value['snapshot']

def compare(before):
    after=protected()
    # Health must stay healthy; transient reporting fields are not identities.
    if before!=after:raise RuntimeError('Protected fourteen containers or baseline changed')
    return after

@contextlib.contextmanager
def lock():
    safe()
    with (ROOT/'private/operator.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=protected()
        try:yield
        finally:compare(before)

def credentials():return load('credentials.json')
def mongosh(javascript,log='mongo-read'):
    prefix="const u=new URL('mongodb://127.0.0.1:27017/?authSource=admin');u.username='rehearsal';u.password=process.env.MONGO_INITDB_ROOT_PASSWORD;const conn=new Mongo(u.toString());"
    raw=compose('exec','-T','mongo','mongosh','--quiet','--eval',prefix+javascript,log=log)
    return raw.decode().strip().splitlines()[-1]

LOGICAL=r'''function stable(v){if(Array.isArray(v))return v.map(stable);if(v&&typeof v==='object'){const o={};for(const k of Object.keys(v).sort())o[k]=stable(v[k]);return o;}return v;}
function snapshot(name){const d=conn.getDB(name);const result={};for(const item of d.getCollectionInfos().sort((a,b)=>a.name.localeCompare(b.name))){const c=d.getCollection(item.name);result[item.name]={rows:c.find().sort({_id:1}).toArray().map(x=>stable(EJSON.serialize(x,{relaxed:false}))),indexes:c.getIndexes().map(x=>{delete x.ns;return stable(x)}).sort((a,b)=>a.name.localeCompare(b.name))};}return result;}
'''

def initialize():
    if (ROOT/'private/init-started.json').exists():raise RuntimeError('Rehearsal init already started; inspect retained state')
    save('init-started.json',{'at':now()})
    compose('up','-d','--no-deps','--wait','--wait-timeout','120','mongo',timeout=150,log='mongo-start')
    # Only a new empty synthetic database can be seeded.
    compose('run','--rm','--no-deps','-T','-e','MONGO_URI_DEV','railway-simulation','node','backup-seed.cjs',stdin=json.dumps({'pin':credentials()['pin']}).encode(),timeout=90,log='seed',env={**os.environ,'MONGO_URI_DEV':urlunsplit(('mongodb','rehearsal:'+credentials()['mongo_password']+'@mongo:27017','/tph_backup_source','authSource=admin',''))})
    cfg="umask 077; cat > /tmp/backup-rehearsal-mongo-config.json"
    uri=urlunsplit(('mongodb','rehearsal:'+credentials()['mongo_password']+'@127.0.0.1:27017','/','authSource=admin',''))
    compose('exec','-T','mongo','sh','-c',cfg,stdin=json.dumps({'uri':uri}).encode(),log='backup-private-config')
    try:
        archive=compose('exec','-T','mongo','mongodump','--config','/tmp/backup-rehearsal-mongo-config.json','--archive','--db','tph_backup_source',timeout=120,log='backup')
        (ROOT/'private/synthetic-source.archive').write_bytes(archive)
        compose('exec','-T','mongo','mongorestore','--config','/tmp/backup-rehearsal-mongo-config.json','--archive','--nsFrom','tph_backup_source.*','--nsTo','tph_backup_restored.*',stdin=archive,timeout=120,log='restore')
    finally:compose('exec','-T','mongo','rm','-f','/tmp/backup-rehearsal-mongo-config.json',log='backup-config-cleanup')
    raw=json.loads(mongosh(LOGICAL+"print(JSON.stringify({source:snapshot('tph_backup_source'),restored:snapshot('tph_backup_restored')}));"))
    if raw['source']!=raw['restored']:raise RuntimeError('Restored synthetic rows/indexes differ')
    digest=hashlib.sha256(json.dumps(raw['source'],sort_keys=True).encode()).hexdigest()
    save('backup-restore.json',{'at':now(),'synthetic_only':True,'source':'tph_backup_source','restored':'tph_backup_restored','collections':{k:len(v['rows']) for k,v in raw['source'].items()},'content_and_index_sha256':digest,'archive_sha256':hashlib.sha256(archive).hexdigest(),'rows_and_indexes_equal':True})
    authority=credentials()['authority']
    mongosh("conn.getDB('tph_backup_restored').backup_rehearsal_authority.insertOne({_id:'shared',authority_id:"+json.dumps(authority)+",watermark:0});print('authority_created');",'authority-create')
    for site in ('railway-simulation','mac-backup'):
        compose('up','-d','--no-deps','--wait','--wait-timeout','120',site,timeout=150,log='start-'+site)
    compose('up','-d','--no-deps','router',log='router-start')
    state=control({'command':'init','site':'railway-simulation','instance_id':inspect('railway-simulation')['Id'],'authority_id':authority})
    identities={}
    for site in ('mongo','railway-simulation','mac-backup','router'):
        item=inspect(site);identities[site]={'id':item['Id'],'image':item['Image'],'config_sha256':hashlib.sha256(json.dumps(item['Config'],sort_keys=True).encode()).hexdigest()}
    save('rehearsal-identity.json',identities)
    save('init-completed.json',{'at':now(),'state':state,'images':load('images.json'),'source':SOURCE,'production_activation':'forbidden'})
    return state

def ready(site):
    for _ in range(30):
        value=inspect(site)
        if value['State']['Running'] and value['State'].get('Health',{}).get('Status')=='healthy':return value
        time.sleep(1)
    raise RuntimeError('Rehearsal target not ready; no promotion')

def switch(target):
    if target not in ('railway-simulation','mac-backup'):raise RuntimeError('Invalid rehearsal target')
    state=control({'command':'status'})
    if state['site']==target and state['phase']=='active':return {'already_active':target,'simulation':True}
    if state['phase']=='frozen' and state['pending']['blocked']:raise RuntimeError('Unknown/inflight outcome blocks switching')
    state=control({'command':'drain'})
    if state['pending']['blocked']:raise RuntimeError('Drain blocked by admitted or unknown work; no container stopped')
    old=inspect(state['site'])
    if old['Id']!=state['instance_id']:raise RuntimeError('Old rehearsal container identity drift')
    other=inspect(target)
    if not other['State']['Running']:docker(['start',other['Id']],log='target-start')
    target_value=ready(target)
    # Inspect immediately before touching the exact owned source.
    old=inspect(state['site'])
    if old['Id']!=state['instance_id']:raise RuntimeError('Old identity changed before stop')
    if old['State']['Running']:docker(['stop','--time','15',old['Id']],timeout=25,log='source-stop')
    observed=inspect(state['site'])
    if observed['Id']!=old['Id'] or observed['State']['Running']:raise RuntimeError('Old rehearsal site not demonstrably stopped')
    fresh_target=ready(target)
    if fresh_target['Id']!=target_value['Id']:raise RuntimeError('Target changed immediately before promotion')
    value=control({'command':'promote','target':target,'target_instance_id':target_value['Id'],'stopped':{'id':old['Id'],'running':False,'observation_id':uuid.uuid4().hex}})
    save('switch-'+str(value['epoch'])+'.json',{'at':now(),'simulation':True,'old_site':state['site'],'old_id':old['Id'],'old_stopped':True,'target_site':target,'new_state':value,'rpo_zero_shared_data':True})
    return value

def status():
    value=control({'command':'status'});return {'simulation':True,'control':value,'services':{s:{'id':(v:=inspect(s))['Id'],'running':v['State']['Running'],'image':v['Image']} for s in ('mongo','railway-simulation','mac-backup','router')},'live_activation':'forbidden'}

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('init','status','switch','activate-live'));p.add_argument('target',nargs='?');a=p.parse_args()
    if a.command=='activate-live':raise RuntimeError('LIVE ACTIVATION FORBIDDEN: Railway primary is unchanged; current-data/fencing/provider/domain release is not approved')
    with lock():
        result=initialize() if a.command=='init' else status() if a.command=='status' else switch(a.target)
        print(json.dumps(result))

if __name__=='__main__':
    try:main()
    except Exception as error:raise SystemExit(str(error) if isinstance(error,RuntimeError) else 'Rehearsal refused: '+type(error).__name__) from None
