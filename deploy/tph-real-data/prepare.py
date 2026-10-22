"""Prepare an isolated real-data reader plan. Never runs Docker, exports, restores or deploys."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

OWNER = 'macapps-tph-real-data-v1'
SOURCE = 'b369e9f5e28584ba99f1cbe35d8f65080a51aeda'
ROOT = Path.home() / 'mac-hosting/tph-real-data-v3'
# Only these explicit candidate subnets are allowed. Parent must independently
# verify Docker + host/LAN/VPN route non-overlap before Phase1 approval.
SUBNETS = {'isolated': '10.240.64.0/24', 'ingress': '10.240.65.0/24'}
IMAGE = re.compile(r'sha256:[0-9a-f]{64}\Z')
FLAGS_FALSE = ('BLOG_STUDIO_ENABLED', 'BLOG_STUDIO_RUN_IN_WEB', 'WORKOS_TENANT_ENABLED',
               'MONTHLY_SUBSCRIPTIONS_ENABLED', 'MONTHLY_CUSTOM_AUTOPAY_ENABLED',
               'HIRING_CANDIDATE_SMS_ENABLED', 'ADMIN_SMS_ENABLED', 'ADMIN_PAYMENT_SMS_ENABLED',
               'ERROR_ALERTS_ENABLED', 'ERROR_ALERTS_SMS_ENABLED', 'PERF_SLO_ALERTS_ENABLED')


def require(value):
    if not value:
        raise ValueError('isolated_clone_plan_refused')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def specification(manifest, root):
    require(set(manifest) == {'images', 'source', 'token'} and manifest['source'] == SOURCE
            and re.fullmatch(r'[0-9a-f]{32}', manifest['token'])
            and set(manifest['images']) == {'web', 'mongo', 'gateway'}
            and all(IMAGE.fullmatch(value) for value in manifest['images'].values()))
    require(root.is_absolute() and root.resolve() == root)
    project = 'macapps-tph-real-data-' + manifest['token'][:12]
    env = {**{key: 'false' for key in FLAGS_FALSE}, 'NODE_ENV': 'production', 'LOCAL_TEST_ONLY': 'true',
           'REAL_DATA_CLONE': 'true', 'DISABLE_SCHEDULER': 'true', 'SQUARE_ENVIRONMENT': 'sandbox',
           'LOCAL_SOURCE_SHA': SOURCE, 'MONGO_URI_DEV': 'mongodb://clone_reader:${CLONE_READER_PASSWORD:?required}@mongo:27017/tph_local_test?authSource=tph_local_test',
           'MANAGER_JWT_SECRET': '${CLONE_MANAGER_SECRET:?required}', 'JWT_SECRET': '${CLONE_JWT_SECRET:?required}',
           'ADMIN_API_KEY': '${CLONE_API_SECRET:?required}', 'AUTH0_DOMAIN': 'auth.tph.invalid',
           'AUTH0_AUDIENCE': 'https://tph.invalid', 'SQUARE_ACCESS_TOKEN': 'LOCAL_TEST_INVALID_NOT_A_PROVIDER_CREDENTIAL',
           'LOG_LEVEL': 'error'}
    common = {'restart': 'no', 'networks': ['isolated'], 'security_opt': ['no-new-privileges:true'],
              'pids_limit': 160, 'cpus': 0.5, 'labels': {'io.macapps.real-data-clone': OWNER},
              'logging': {'driver': 'json-file', 'options': {'max-size': '2m', 'max-file': '2'}}}
    spec = {'name': project, 'services': {
        'mongo': {**common, 'image': manifest['images']['mongo'], 'mem_limit': '512m',
                  'command': ['mongod', '--wiredTigerCacheSizeGB', '0.25', '--bind_ip_all',
                              '--setParameter', 'ttlMonitorEnabled=false'],
                  'environment': {'MONGO_INITDB_ROOT_USERNAME': 'clone_restore_admin',
                                  'MONGO_INITDB_ROOT_PASSWORD': '${CLONE_RESTORE_PASSWORD:?required}'},
                  'volumes': ['mongo:/data/db', 'mongo_config:/data/configdb',
                              str(root / 'create-reader-role.js') + ':/run/clone/create-reader-role.js:ro',
                              str(root / 'private/restore-config.yml') + ':/run/clone/restore-config.yml:ro'],
                  'healthcheck': {'test': ['CMD', 'mongosh', '--quiet', '--eval', 'quit(db.adminCommand({ping:1}).ok?0:1)'],
                                  'interval': '5s', 'timeout': '4s', 'retries': 30}},
        'web': {**common, 'image': manifest['images']['web'], 'mem_limit': '512m', 'read_only': True,
                'user': 'node', 'cap_drop': ['ALL'], 'command': ['node', 'tph-web.cjs'],
                'environment': env, 'tmpfs': ['/tmp:size=32m,mode=1777',
                  '/usr/src/app/backend/logs:rw,noexec,nosuid,size=16777216,uid=1000,gid=1000,mode=0700'],
                'volumes': [str(root / 'clone-web.cjs') + ':/usr/src/app/tph-web.cjs:ro'],
                'healthcheck': {'test': ['CMD', 'node', '-e', "fetch('http://127.0.0.1:5051/local-test/ready').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"],
                                'interval': '10s', 'timeout': '5s', 'retries': 20}},
        'gateway': {**common, 'image': manifest['images']['gateway'], 'networks': ['isolated', 'ingress'],
                    'mem_limit': '48m', 'read_only': True, 'tmpfs': ['/var/cache/nginx:size=16m', '/var/run:size=1m'],
                    'ports': ['127.0.0.1:18221:8080'],
                    'volumes': [str(root / 'nginx.conf') + ':/etc/nginx/nginx.conf:ro']}},
        'networks': {'isolated': {'internal': True, 'ipam': {'driver': 'default', 'config': [{'subnet': SUBNETS['isolated']}]}},
                     'ingress': {'ipam': {'driver': 'default', 'config': [{'subnet': SUBNETS['ingress']}]}}},
        'volumes': {'mongo': {}, 'mongo_config': {}}}
    return spec


def nginx(origin='http://127.0.0.1:18221'):
    # Public cutover requires a separately reviewed config; arbitrary URLs are refused.
    require(origin in ('http://127.0.0.1:18221', 'https://tph-test.elisprotech.com'))
    return '''events { worker_connections 128; }
http {
map "$request_method:$uri" $clone_allowed {
  default 0;
  ~^(GET|HEAD):/api/spot-changes(?:/(?:daily-spots|locations|monthly-markings|spots/[a-zA-Z0-9_-]+|spot/[a-zA-Z0-9_-]+))?$ 1;
  ~^(GET|HEAD):/api/addresses(?:/[a-zA-Z0-9_-]+)?$ 1;
  ~^(GET|HEAD):/local-test/ready$ 1;
  ~^(GET|HEAD):/(?!api(?:/|$)) 1;
  "POST:/api/pin/verify-client" 1;
  "POST:/api/pin/verify-staff" 1;
  "POST:/api/pin/verify-admin" 1;
}
server {
listen 8080;
client_max_body_size 8k;
add_header Content-Security-Policy "default-src 'self'; connect-src 'self'; form-action 'self'; frame-src 'none'; object-src 'none'; script-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; base-uri 'self'; worker-src 'none'; frame-ancestors 'none'" always;
add_header Cache-Control "no-store" always;
add_header X-Local-Test "REAL DATA COPY - providers and edits blocked" always;
if ($clone_allowed = 0) { return 403; }
# Copied capabilities, provider callbacks and operational endpoints are never activated.
location ~* ^/api/(webhooks|booking-auth|auth|customer|payments|stripe|square|jobs|cron|internal)(/|$) { return 403; }
location = /local-test/ready { proxy_pass http://web:5051/local-test/ready; }
location / {
proxy_pass http://web:5050;
proxy_set_header Host $http_host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Accept-Encoding "";
proxy_hide_header Content-Security-Policy;
proxy_hide_header Cache-Control;
sub_filter_types application/javascript text/javascript application/json;
sub_filter 'https://tph-test.elisprotech.com' 'ORIGIN';
sub_filter_once off;
}
}
}
'''.replace('ORIGIN', origin)


def role_script():
    # Manual post-restore step, not a server startup/init hook. Secret arrives on stdin
    # to its explicit runner, never from a production provider environment.
    return '''const fs=require('fs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
if(Object.keys(input).sort().join(',')!=='password'||!/^[-_a-zA-Z0-9]{43}$/.test(input.password))throw Error('clone_role_input_refused');
const authorized=db.getSiblingDB('admin').auth(process.env.MONGO_INITDB_ROOT_USERNAME,process.env.MONGO_INITDB_ROOT_PASSWORD);
if(!(authorized===1||authorized?.ok===1))throw Error('clone_local_admin_auth_refused');
const target=db.getSiblingDB('tph_local_test');
if(target.getCollectionNames().length===0||target.getRole('clone_reader_role')||target.getUser('clone_reader'))throw Error('clone_role_existing_or_empty_refused');
target.createRole({role:'clone_reader_role',privileges:[
...['pins','parkingspaces','parkingbays','bookings','parkingspotchangelogs','sitesettings','blogposts','landlords']
.map(collection=>({resource:{db:'tph_local_test',collection},actions:['find','listIndexes']})),
{resource:{db:'tph_local_test',collection:''},actions:['listCollections']},
{resource:{db:'tph_local_test',collection:'pins'},actions:['update']}
],roles:[]});
target.createUser({user:'clone_reader',pwd:input.password,roles:[{role:'clone_reader_role',db:'tph_local_test'}]});
print(JSON.stringify({rolePrepared:true,jobWritesAllowed:false,providerActionsAllowed:false}));
'''


def prepare(manifest, root=ROOT):
    # Planning writes only a NEW owner directory; no Docker calls and no overwrite.
    require(not root.exists() and root.parent.exists() and root.resolve() == root)
    spec = specification(manifest, root)
    adapter = Path(__file__).with_name('clone-web.cjs').read_bytes()
    artifacts = {'compose.json': json.dumps(spec, sort_keys=True, indent=2).encode() + b'\n',
                 'nginx.conf': nginx().encode(), 'nginx.public.DISABLED.conf': nginx('https://tph-test.elisprotech.com').encode(),
                 'clone-web.cjs': adapter, 'create-reader-role.js': role_script().encode()}
    plan = {'version': 3, 'owner': OWNER, 'project': spec['name'], 'manifest': manifest,
            'artifacts_sha256': {name: sha(value) for name, value in artifacts.items()},
            'public_cutover': False, 'production_mutations': False, 'workers': 0,
            'ttl_monitor_enabled': False,
            'network_contract': {'subnets': SUBNETS, 'overlap_verification': 'REQUIRED before runtime approval'},
            'activation': 'BLOCKED until independent exact-plan approval, full empty-target restore verification and auth acceptance',
            'auth0_password_login': 'unavailable; no identity-provider change or bypass'}
    root.mkdir(mode=0o700)
    private = root / 'private'
    private.mkdir(mode=0o700)
    secret_names = ('CLONE_RESTORE_PASSWORD', 'CLONE_READER_PASSWORD', 'CLONE_MANAGER_SECRET', 'CLONE_JWT_SECRET', 'CLONE_API_SECRET')
    local_secrets = {name: secrets.token_urlsafe(32) for name in secret_names}
    artifacts['private/clone.env'] = ''.join(name + '=' + value + '\n' for name, value in local_secrets.items()).encode()
    artifacts['private/restore-config.yml'] = ('password: ' + local_secrets['CLONE_RESTORE_PASSWORD'] + '\n').encode()
    artifacts['.owner'] = (OWNER + '\n').encode()
    artifacts['plan.json'] = json.dumps(plan, sort_keys=True, indent=2).encode() + b'\n'
    for name, raw in artifacts.items():
        with (root / name).open('xb') as output:
            os.fchmod(output.fileno(), 0o644 if name == 'clone-web.cjs' else 0o600)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    return {'prepared': True, 'project': spec['name'], 'plan_sha256': sha(artifacts['plan.json']),
            'runtime_started': False, 'public_cutover': False}


if __name__ == '__main__':
    os.umask(0o077)
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(prepare(json.load(__import__('sys').stdin))))
    except Exception:
        raise SystemExit('clone_prepare_refused_no_runtime_action') from None
