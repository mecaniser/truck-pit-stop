"""Host-only fetcher for one literal public Auth0 JWKS endpoint. No credentials."""
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import signal
import sys
import urllib.request

URL='https://dev-wp1mdcmju5ix3zgt.us.auth0.com/.well-known/jwks.json'
CACHE=Path.home()/'mac-hosting/tph-real-data-v3/auth0-public-keys'
MAX_BYTES=65536

def check(value,code):
    if not value:raise ValueError(code)

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()

def integer(value):
    check(isinstance(value,str) and re.fullmatch('[A-Za-z0-9_-]+',value),'rsa_encoding')
    raw=base64.urlsafe_b64decode(value+'='*((-len(value))%4))
    check(raw and raw[0]!=0 and base64.urlsafe_b64encode(raw).decode().rstrip('=')==value,'rsa_encoding')
    return int.from_bytes(raw,'big')

def validate_jwks(value):
    check(isinstance(value,dict) and set(value)=={'keys'} and isinstance(value['keys'],list) and 0<len(value['keys'])<=16,'jwks_schema')
    kids=set()
    for key in value['keys']:
        check(isinstance(key,dict) and set(key)<= {'kty','use','alg','kid','n','e','x5c','x5t','x5t#S256'}
              and all(key.get(k)==v for k,v in [('kty','RSA'),('use','sig'),('alg','RS256')]),'public_rs256_only')
        kid=key.get('kid');check(isinstance(kid,str) and re.fullmatch(r'[A-Za-z0-9_+/.=-]{1,256}',kid) and kid not in kids,'unique_kid')
        kids.add(kid);n=integer(key.get('n'));e=integer(key.get('e'))
        check(2048<=n.bit_length()<=8192 and n%2==1 and e>=3 and e<=65537 and e%2==1,'rsa_strength')
    return value

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('redirect_refused')

def fetch(now=None):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def expired(*_):raise TimeoutError('public_fetch_deadline')
    check(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'existing_timer_refused')
    previous=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,5)
    try:
        with opener.open(urllib.request.Request(URL,headers={'Accept':'application/json'}),timeout=5) as response:
            check(response.status==200 and response.url==URL,'exact_response_url')
            raw=response.read(MAX_BYTES+1);check(len(raw)<=MAX_BYTES,'jwks_size')
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    jwks=validate_jwks(json.loads(raw))
    now=now or datetime.datetime.now(datetime.timezone.utc)
    return {'version':1,'url':URL,'fetched_at':now.isoformat(),'valid_until':(now+datetime.timedelta(hours=24)).isoformat(),
            'jwks_sha256':digest(canonical(jwks)),'jwks':jwks}

def refresh(cache=CACHE):
    check(cache==CACHE and cache.resolve()==cache and not cache.is_symlink(),'fixed_cache_directory')
    info=cache.stat();check(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode)==0o755 and info.st_uid==os.getuid(),'cache_directory_mode')
    # Fetch and validate completely BEFORE replacing anything; failure preserves old expiry.
    snapshot=fetch();raw=canonical(snapshot)+b'\n';check(len(raw)<=MAX_BYTES,'snapshot_size')
    path=cache/'current.json';temporary=cache/('refresh-'+os.urandom(16).hex()+'.tmp')
    with temporary.open('xb') as file:
        os.fchmod(file.fileno(),0o644);file.write(raw);file.flush();os.fsync(file.fileno())
    if path.exists():check(not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode) and path.stat().st_uid==os.getuid(),'cache_target_refused')
    os.replace(temporary,path)
    fd=os.open(cache,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'refreshed':True,'snapshot_sha256':digest(raw),'valid_until':snapshot['valid_until']}

if __name__=='__main__':
    try:
        check(len(sys.argv)==1,'no_arguments')
        print(json.dumps(refresh()))
    except Exception:raise SystemExit('public_signing_key_refresh_failed_old_expiry_unchanged')
