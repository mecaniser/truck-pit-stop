"""Prepare a new immutable Mac-only Auth0/read-only app profile; never starts services."""
import copy
import hashlib
import json
import os
from pathlib import Path

ROOT = Path.home() / 'mac-hosting/tph-real-data-v3'
PLAN_SHA = 'b5b98d067f01e178f7ba85fcc8387ed804924e1aead3c17075d9d7af16d431d1'
DOMAIN = 'dev-wp1mdcmju5ix3zgt.us.auth0.com'
CLIENT = 'vdyn414odhKwyDvsiNCSssA0In0Lc1i2'
AUDIENCE = 'https://trucksparkinghub.com/api'
READ_COLLECTIONS = ['pins', 'parkingspaces', 'parkingbays', 'Bookings', 'parkingspotchangelogs',
                    'sitesettings', 'blogposts', 'landlords', 'spotadditionrequests', 'locationadditionrequests', 'paymentfeeplans']


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def nginx():
    return '''events { worker_connections 128; }
http {
map "$request_method:$uri" $clone_allowed {
 default 0;
 ~*^(GET|HEAD):/api/spot-changes(?:/(?:daily-spots|locations|monthly-markings|spots/[a-zA-Z0-9_-]+|spot/[a-zA-Z0-9_-]+))?$ 1;
 ~*^(GET|HEAD):/api/addresses(?:/[a-zA-Z0-9_-]+)?$ 1;
 ~*^(GET|HEAD):/local-test/ready$ 1;
 ~*^(GET|HEAD):/(?!api(?:/|$)) 1;
 "POST:/api/pin/verify-client" 1;
 "POST:/api/pin/verify-staff" 1;
 "POST:/api/pin/verify-admin" 1;
}
server {
listen 8080;
client_max_body_size 8k;
if ($clone_allowed = 0) { return 403; }
add_header Cache-Control "no-store" always;
add_header X-Local-Test "real-data-copy-read-only-no-business-effects" always;
add_header Content-Security-Policy "default-src 'self'; connect-src 'self' https://AUTH0; form-action 'self' https://AUTH0; frame-src https://AUTH0; object-src 'none'; script-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; base-uri 'self'; worker-src 'none'; frame-ancestors 'none'" always;
location = /local-test/ready { proxy_pass http://web:5051/local-test/ready; }
location / {
proxy_pass http://web:5050;
proxy_set_header Host $http_host;
proxy_set_header X-Forwarded-Proto https;
proxy_set_header Accept-Encoding "";
proxy_buffer_size 32k;
proxy_buffers 4 32k;
proxy_busy_buffers_size 64k;
proxy_hide_header Content-Security-Policy;
proxy_hide_header Cache-Control;
sub_filter_types application/javascript text/javascript application/json;
sub_filter 'auth.tph.invalid' 'AUTH0';
sub_filter 'local-test-client' 'CLIENT';
sub_filter 'https://tph.invalid' 'AUDIENCE';
sub_filter '<body>' '<body><div style="background:#ffe58f;color:#111;padding:8px;text-align:center;font:14px sans-serif;position:relative;z-index:2147483647">MAC COPY - Real data captured October 22 - Read only - Payments, messages and jobs blocked</div>';
sub_filter_once off;
}
}
}
'''.replace('AUTH0', DOMAIN).replace('CLIENT', CLIENT).replace('AUDIENCE', AUDIENCE)


def role_source():
    names = json.dumps(READ_COLLECTIONS)
    return '''const fs=require('fs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
if(Object.keys(input).sort().join(',')!=='password'||!/^[-_a-zA-Z0-9]{43}$/.test(input.password))throw Error('role_input_refused');
const authorized=db.getSiblingDB('admin').auth(process.env.MONGO_INITDB_ROOT_USERNAME,process.env.MONGO_INITDB_ROOT_PASSWORD);
if(!(authorized===1||authorized?.ok===1))throw Error('local_admin_auth_refused');
const target=db.getSiblingDB('tph_local_test');
if(target.getCollectionNames().length!==78||target.getRole('clone_reader_role')||target.getUser('clone_reader'))throw Error('target_not_approved_fresh_restored_copy');
target.createRole({role:'clone_reader_role',privileges:[
...COLLECTIONS.map(collection=>({resource:{db:'tph_local_test',collection},actions:['find','listIndexes']})),
{resource:{db:'tph_local_test',collection:''},actions:['listCollections']},
{resource:{db:'tph_local_test',collection:'pins'},actions:['update']}
],roles:[]});
target.createUser({user:'clone_reader',pwd:input.password,roles:[{role:'clone_reader_role',db:'tph_local_test'}]});
print(JSON.stringify({rolePrepared:true,operationalWritesAllowed:false}));
'''.replace('COLLECTIONS', names)


def prepare(root=ROOT, source=None):
    source = source or Path(__file__).parent
    assert root.resolve() == root and digest((root / 'plan.json').read_bytes()) == PLAN_SHA
    plan = json.loads((root / 'plan.json').read_text())
    before = json.loads((root / 'compose.json').read_text())
    assert digest((root / 'compose.json').read_bytes()) == plan['artifacts_sha256']['compose.json']
    profile = root / 'phase2-auth0'
    assert not profile.exists()
    spec = copy.deepcopy(before)
    web = spec['services']['web']
    web['environment']['AUTH0_DOMAIN'] = DOMAIN
    web['environment']['AUTH0_AUDIENCE'] = AUDIENCE
    web['volumes'] = [str(profile / 'clone-web-auth0.cjs') + ':/usr/src/app/tph-web.cjs:ro',
                      str(profile / 'auth0_cached_jwks.cjs') + ':/run/clone/auth0_cached_jwks.cjs:ro',
                      str(profile / 'auth0-jwks.json') + ':/run/clone/auth0-jwks.json:ro']
    spec['services']['gateway']['volumes'] = [str(profile / 'nginx.conf') + ':/etc/nginx/nginx.conf:ro']
    assert spec['services']['mongo'] == before['services']['mongo']
    assert spec['networks'] == before['networks'] and spec['volumes'] == before['volumes']
    artifacts = {'compose.json': json.dumps(spec, sort_keys=True, indent=2).encode() + b'\n',
                 'nginx.conf': nginx().encode(), 'create-reader-role.js': role_source().encode()}
    for name in ('clone-web-auth0.cjs', 'auth0_cached_jwks.cjs', 'auth0-jwks.json'):
        artifacts[name] = (source / name).read_bytes()
    approval = {'version': 1, 'base_plan_sha256': PLAN_SHA, 'artifacts_sha256': {k:digest(v) for k,v in artifacts.items()},
                'project': plan['project'], 'application_source': plan['manifest']['source'],
                'auth0': {'domain': DOMAIN, 'client_id': CLIENT, 'audience': AUDIENCE,
                          'callback': 'https://tph-test.elisprotech.com/callback', 'keys': 'official-public-JWKS-cache-only'},
                'role_read_collections': READ_COLLECTIONS, 'role_update_collection': 'pins',
                'runtime_started': False, 'public_cutover': False, 'production_changed': False,
                'activation': 'BLOCKED pending full data equality, independent role/source/runtime plan and private acceptance'}
    profile.mkdir(mode=0o700)
    for name, raw in artifacts.items():
        with (profile / name).open('xb') as out:
            os.fchmod(out.fileno(),0o644 if name.endswith('.cjs') or name == 'auth0-jwks.json' else 0o600)
            out.write(raw)
    raw = json.dumps(approval, sort_keys=True, indent=2).encode() + b'\n'
    with (profile / 'plan.json').open('xb') as out:
        os.fchmod(out.fileno(),0o600);out.write(raw)
    return {'prepared': True, 'phase2_plan_sha256': digest(raw), 'runtime_started': False, 'public_cutover': False}


if __name__ == '__main__':
    os.umask(0o077)
    try:print(json.dumps(prepare()))
    except Exception:raise SystemExit('phase2_prepare_refused_no_runtime_action') from None
