"""Resume only the verified pre-build Docker-helper PATH failure; retain failed journal/log."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import fcntl
import contextlib
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
    with (op.ROOT/'private/operator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        protected_before=op.protected()
        extension=op.ROOT/'router-revision-candidate'
        archive=op.ROOT/'private/router-revision-1'
        journal=op.load('router-revision-uncertain.json');state=journal['state'];before=journal['before'];db_before=journal['logical_state']
        # The prior build stopped before changing compose, images, identity or running containers.
        for name in ('compose.json','private/images.json','private/config-sha256.txt','private/approved-manifest.json','private/rehearsal-identity.json'):
            if digest((op.ROOT/name).read_bytes())!=before[name]:raise RuntimeError('Unexpected partially changed configuration')
        manifest=json.loads((archive/'private/approved-manifest.json').read_text())
        for name,sha in manifest['files'].items():
            expected=extension/Path(name).name if name in ('tools/operator.py','tools/relay.py') else op.ROOT/name
            if name in ('tools/operator.py','tools/relay.py'):
                if (op.ROOT/name).read_bytes()!=expected.read_bytes():raise RuntimeError('Unexpected candidate file drift')
            elif digest(expected.read_bytes())!=sha:raise RuntimeError('Unexpected sealed file drift')
        for name in ('operator.py','relay.py'):
            if (op.ROOT/'tools'/name).read_bytes()!=(extension/name).read_bytes():raise RuntimeError('Reviewed candidate drift')
        if (op.ROOT/'build/router.py').read_bytes()!=(extension/'router.py').read_bytes():raise RuntimeError('Unexpected candidate router source')
        if op.control({'command':'status'})!=state or {name:logical(name) for name in db_before}!=db_before:raise RuntimeError('Durable state drift before resume')
        identities=op.load('rehearsal-identity.json')
        for site in identities:op.inspect(site)
        names=list(before)
        path=op.ROOT/'tools/relay.py'
        tag='macapps-tph-backup-rehearsal:router-root-assets-v2'
        with (archive/'build-resume-path.log').open('xb') as log:
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
        op.compare(protected_before)
        print(json.dumps({'router_only_revision':'accepted','image':image['Id'],'durable_state_unchanged':True}))
if __name__=='__main__':
    try:main()
    except BaseException:
        marker=op.ROOT/'private/router-revision-uncertain.json'
        archived=op.ROOT/'private/router-revision-1/revision-started.json'
        if archived.exists() and not marker.exists():marker.write_bytes(archived.read_bytes())
        raise

