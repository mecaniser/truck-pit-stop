"""Create only a new owned rehearsal root and build its two immutable images."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
from configure import ROOT,BASE,OWNER,specification

D=['/Applications/Docker.app/Contents/Resources/bin/docker','--context','desktop-linux']

def main():
    os.umask(0o077)
    os.environ['PATH']='/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'
    if ROOT.resolve()!=ROOT or ROOT.is_symlink() or (ROOT/'.owner').read_text()!=OWNER+'\n':raise RuntimeError('Unknown rehearsal root')
    if (ROOT/'private/setup-started.json').exists():raise RuntimeError('Setup already started; inspect evidence before retry')
    (ROOT/'private/setup-started.json').write_text(json.dumps({'exclusive':True}))
    build=ROOT/'build';images={}
    base=json.loads(subprocess.check_output([*D,'image','inspect',BASE]))[0]
    if base['Id']!=BASE or base['Architecture']!='arm64':raise RuntimeError('Accepted native TPH base unavailable')
    alias='macapps-tph-backup-base:'+BASE.split(':')[1]
    old=subprocess.run([*D,'image','inspect',alias],capture_output=True)
    if old.returncode==0 and json.loads(old.stdout)[0]['Id']!=BASE:raise RuntimeError('Base alias belongs to another image')
    subprocess.run([*D,'tag',BASE,alias],check=True)
    for kind in ('app','router'):
        tag='macapps-tph-backup-rehearsal:'+kind
        with (ROOT/'private'/('build-'+kind+'.log')).open('xb') as log:
            subprocess.run([*D,'build','--pull=false','--memory=1g','--build-arg','BASE_IMAGE='+alias,'--label','io.macapps.backup-rehearsal='+OWNER,'-f','Dockerfile.'+kind,'-t',tag,'.'],cwd=build,stdout=log,stderr=log,check=True,timeout=300)
        value=json.loads(subprocess.check_output([*D,'image','inspect',tag]))[0]
        if value['Architecture']!='arm64':raise RuntimeError('Rehearsal image architecture mismatch')
        images[kind]=value['Id']
    if json.loads(subprocess.check_output([*D,'image','inspect',alias]))[0]['Id']!=BASE:raise RuntimeError('Native base alias changed')
    values={'mongo_password':secrets.token_hex(32),'pin':str(secrets.randbelow(899999)+100000),'manager_secret':secrets.token_hex(32),'jwt_secret':secrets.token_hex(32),'admin_secret':secrets.token_hex(32),'control_token':secrets.token_hex(32),'authority':secrets.token_hex(32)}
    (ROOT/'private/credentials.json').write_text(json.dumps(values))
    env=''.join(k.upper()+'='+v+'\n' for k,v in values.items() if k!='pin')
    # Specification uses explicit credential names; no live configuration is copied.
    (ROOT/'private/rehearsal.env').write_text(env)
    (ROOT/'private/images.json').write_text(json.dumps(images))
    spec=specification(images,os.getuid(),os.getgid());raw=(json.dumps(spec,indent=2)+'\n').encode();(ROOT/'compose.json').write_bytes(raw)
    (ROOT/'private/config-sha256.txt').write_text(hashlib.sha256(raw).hexdigest())
    receipt={'images':images,'base':BASE,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in build.iterdir() if p.is_file()},'production_credentials_copied':False,'live_activation':'forbidden'}
    paths=['compose.json','private/rehearsal.env','private/credentials.json','private/images.json','private/config-sha256.txt']
    paths += [str(p.relative_to(ROOT)) for p in (ROOT/'tools').iterdir() if p.is_file()]
    manifest={'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(paths)},'images':images,'uid':os.getuid(),'gid':os.getgid()}
    with (ROOT/'private/approved-manifest.json').open('x') as f:json.dump(manifest,f,indent=2)
    (ROOT/'private/setup-completed.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))

if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Rehearsal setup failed: '+type(e).__name__+'; private log retained') from None
