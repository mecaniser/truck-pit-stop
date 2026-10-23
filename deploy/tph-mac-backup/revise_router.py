"""One reviewed router-only revision; preserve failures and immutable prior evidence."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
spec=importlib.util.spec_from_file_location('backup_operator',Path(__file__).with_name('operator.py'));op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)

def digest(data):return hashlib.sha256(data).hexdigest()
def logical(name):
    c=sqlite3.connect('file:'+str(op.ROOT/'private/state'/name)+'?mode=ro',uri=True)
    try:return digest('\n'.join(c.iterdump()).encode())
    finally:c.close()
def main():
    os.umask(0o077)
    os.environ['PATH']='/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'
    with op.lock():
        protected_before=op.protected()
        state=op.control({'command':'status'})
        if state['phase']!='active' or state['pending']['blocked']:raise RuntimeError('Router revision requires settled active state')
        identities=op.load('rehearsal-identity.json')
        for site in identities:op.inspect(site)
        extension=op.ROOT/'router-revision-candidate'
        archive=op.ROOT/'private/router-revision-1';archive.mkdir(mode=0o700)
        names=['compose.json','private/images.json','private/config-sha256.txt','private/approved-manifest.json','private/rehearsal-identity.json','tools/operator.py','tools/relay.py','build/router.py']
        before={name:digest((op.ROOT/name).read_bytes()) for name in names}
        for name in names:
            target=archive/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((op.ROOT/name).read_bytes())
        db_before={name:logical(name) for name in ('control.sqlite3','provider.sqlite3')}
        # Stop only the recorded, exact host relay before any mutable revision.
        relay=op.load('relay-banner-revision.json');pid=relay['pid'];path=op.ROOT/'tools/relay.py'
        command=subprocess.check_output(['ps','-p',str(pid),'-o','command=']).decode().strip()
        expected='/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python '+str(path)
        if command!=expected:raise RuntimeError('Exact relay process identity drift')
        op.save('router-revision-uncertain.json',{'at':op.now(),'before':before,'state':state,'logical_state':db_before})
        os.kill(pid,signal.SIGTERM)
        for name in ('operator.py','relay.py'):(op.ROOT/'tools'/name).write_bytes((extension/name).read_bytes())
        (op.ROOT/'build/router.py').write_bytes((extension/'router.py').read_bytes())
        tag='macapps-tph-backup-rehearsal:router-root-assets-v2'
        with (archive/'build.log').open('xb') as log:
            subprocess.run([*op.D,'build','--pull=false','--memory=1g','--label','io.macapps.backup-rehearsal='+op.OWNER,'-f','Dockerfile.router','-t',tag,'.'],cwd=op.ROOT/'build',stdout=log,stderr=log,check=True,timeout=180)
        image=json.loads(op.docker(['image','inspect',tag]))[0]
        if image['Architecture']!='arm64':raise RuntimeError('Wrong router architecture')
        images=op.load('images.json');images['router']=image['Id']
        raw=(json.dumps(op.specification(images,os.getuid(),os.getgid()),indent=2)+'\n').encode()
        (op.ROOT/'compose.json').write_bytes(raw);(op.ROOT/'private/images.json').write_text(json.dumps(images));(op.ROOT/'private/config-sha256.txt').write_text(digest(raw))
        op.compose('up','-d','--no-deps','--wait','--wait-timeout','90','router',timeout=120,log='router-asset-revision')
        value=json.loads(op.docker(['inspect',op.PROJECT+'-router-1']))[0]
        if value['Image']!=image['Id'] or not value['State']['Running'] or value['State'].get('Health',{}).get('Status')!='healthy' or value['Config']['Labels'].get('io.macapps.backup-rehearsal')!=op.OWNER:raise RuntimeError('New router acceptance failed')
        if op.control({'command':'status'})!=state:raise RuntimeError('Control changed during router revision')
        if {name:logical(name) for name in db_before}!=db_before:raise RuntimeError('Durable logical state changed')
        op.compare(protected_before)
        for site in ('mongo','railway-simulation','mac-backup'):op.inspect(site)
        identities['router']={'id':value['Id'],'image':value['Image'],'config_sha256':digest(json.dumps(value['Config'],sort_keys=True).encode())}
        (op.ROOT/'private/rehearsal-identity.json').write_text(json.dumps(identities))
        manifest=op.load('approved-manifest.json');manifest['images']=images
        for file in (op.ROOT/'tools').iterdir():
            if file.is_file():manifest['files'][str(file.relative_to(op.ROOT))]=digest(file.read_bytes())
        for name in manifest['files']:manifest['files'][name]=digest((op.ROOT/name).read_bytes())
        (op.ROOT/'private/approved-manifest.json').write_text(json.dumps(manifest,indent=2))
        # Preserve the uncertain record as the completed revision journal, never erase it.
        (op.ROOT/'private/router-revision-uncertain.json').rename(archive/'revision-started.json')
        fresh_spec=importlib.util.spec_from_file_location('revised_operator',op.ROOT/'tools/operator.py');fresh=importlib.util.module_from_spec(fresh_spec);fresh_spec.loader.exec_module(fresh);fresh.safe();fresh.inspect('router')
        with (op.ROOT/'private/relay-root-assets.log').open('xb') as log:process=subprocess.Popen(['/opt/homebrew/bin/python3',str(path)],stdout=log,stderr=log,start_new_session=True)
        op.save('router-revision-1.json',{'at':op.now(),'before':before,'after':{name:digest((op.ROOT/name).read_bytes()) for name in names},'logical_state_unchanged':db_before,'native_cids_unchanged':True,'new_router':identities['router'],'relay_pid':process.pid,'old_state':state,'live_activation':'forbidden'})
        print(json.dumps({'router_only_revision':'accepted','image':image['Id'],'durable_state_unchanged':True}))
if __name__=='__main__':
    try:main()
    except BaseException:
        marker=op.ROOT/'private/router-revision-uncertain.json'
        archived=op.ROOT/'private/router-revision-1/revision-started.json'
        if archived.exists() and not marker.exists():marker.write_bytes(archived.read_bytes())
        raise

