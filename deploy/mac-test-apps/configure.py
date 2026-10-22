"""Generate two fixed isolated application test stacks; no production management."""
import json
import os
from pathlib import Path
import re

ROOT = Path.home() / 'mac-hosting/test-stacks'
DB_SHA = '65afe9b8fa52a946ca86f645abbf4ebe70aa3604'
TPH_SHA = 'b369e9f5e28584ba99f1cbe35d8f65080a51aeda'
DIGEST = re.compile(r'sha256:[a-f0-9]{64}\Z')


def specifications(images):
    if set(images) != {'dieselbridge', 'tph', 'postgres', 'redis', 'mongo', 'nginx'}:
        raise ValueError('Exact image set required')
    if any(not DIGEST.fullmatch(value) for value in images.values()):
        raise ValueError('Immutable full image IDs required')
    common = {'restart': 'unless-stopped', 'networks': ['isolated'], 'cpus': 0.75,
              'security_opt': ['no-new-privileges:true'], 'pids_limit': 192,
              'logging': {'driver': 'json-file', 'options': {'max-size': '5m', 'max-file': '2'}},
              'labels': {'io.macapps.test-stack': 'v1'}}
    db_env = {
        'ENVIRONMENT': 'staging', 'LOCAL_TEST_ONLY': 'true',
        'DATABASE_URL': 'postgresql+asyncpg://localtest:${DB_PASSWORD:?required}@postgres:5432/dieselbridge_local_test',
        'REDIS_URL': 'redis://redis:6379/13', 'SECRET_KEY': '${DB_SECRET:?required}',
        'FRONTEND_URL': 'http://localhost:18200', 'CORS_ORIGINS_STR': 'http://localhost:18200',
        'COOKIE_DOMAIN': '', 'COOKIE_SECURE': 'false',
        'WORKOS_AUTH_ENABLED': 'false', 'MOTIVE_ENABLED': 'false', 'TELEMATICS_PROVIDER': 'manual',
        'SMS_TENANT_ROUTING_ENABLED': 'false', 'SMS_AUTOMATION_OUTBOX_ENABLED': 'false',
        'SMS_RECOVERY_ENABLED': 'false', 'PROVIDER_OUTBOX_ENABLED': 'false',
        'ETS_COMPLETED_OUTCOMES_ENABLED': 'false', 'SHOP_HISTORY_CAPTURE_ENABLED': 'false',
        'STRIPE_CONNECT_INVOICE_PAYMENTS_APPROVED': 'false', 'QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED': 'false',
        'DATABASE_POOL_SIZE': '2', 'DATABASE_MAX_OVERFLOW': '1',
    }
    def gateway(port):
        return {**common, 'image': images['nginx'], 'networks': ['isolated', 'ingress'],
                'ports': [f'127.0.0.1:{port}:8080'], 'volumes': ['./nginx.conf:/etc/nginx/nginx.conf:ro'],
                'read_only': True, 'tmpfs': ['/var/cache/nginx:size=16m', '/var/run:size=1m'],
                'mem_limit': '32m', 'depends_on': {'web': {'condition': 'service_healthy'}}}
    db_app = {**common, 'read_only': True, 'cap_drop': ['ALL'], 'tmpfs': ['/tmp:size=64m,mode=1777'], 'image': images['dieselbridge'], 'environment': db_env, 'mem_limit': '768m',
              'volumes': ['uploads:/app/uploads'],
              'depends_on': {'postgres': {'condition': 'service_healthy'}, 'redis': {'condition': 'service_healthy'}}}
    db_worker = {**db_app, 'command': ['celery', '-A', 'db_worker', 'worker', '-Q', 'db-local-test',
                 '--pool=solo', '--concurrency=1', '--without-gossip', '--without-mingle', '--without-heartbeat',
                 '--loglevel=warning', '-n', 'db-local-test@%h'],
                 'volumes': [], 'mem_limit': '512m',
                 'healthcheck': {'test': ['CMD-SHELL', 'celery -A db_worker inspect ping --timeout=3 >/dev/null'],
                                  'interval': '20s', 'timeout': '8s', 'retries': 5, 'start_period': '40s'}}
    db = {'name': 'db-local-test', 'services': {
        'postgres': {**common, 'image': images['postgres'], 'mem_limit': '512m',
                     'environment': {'POSTGRES_DB': 'dieselbridge_local_test', 'POSTGRES_USER': 'localtest', 'POSTGRES_PASSWORD': '${DB_PASSWORD:?required}'},
                     'volumes': ['postgres:/var/lib/postgresql/data'],
                     'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U localtest -d dieselbridge_local_test'], 'interval': '5s', 'timeout': '3s', 'retries': 20}},
        'redis': {**common, 'image': images['redis'], 'mem_limit': '128m', 'volumes': ['redis:/data'],
                  'command': ['redis-server', '--appendonly', 'yes', '--maxmemory', '64mb', '--maxmemory-policy', 'noeviction'],
                  'healthcheck': {'test': ['CMD', 'redis-cli', 'ping'], 'interval': '5s', 'timeout': '3s', 'retries': 20}},
        'web': {**db_app, 'healthcheck': {'test': ['CMD', 'curl', '--fail', '--silent', 'http://127.0.0.1:8000/health/ready'], 'interval': '10s', 'timeout': '5s', 'retries': 15}},
        'worker': db_worker, 'gateway': gateway(18200)},
          'networks': {'isolated': {'internal': True}, 'ingress': {}}, 'volumes': {'postgres': {}, 'redis': {}, 'uploads': {}}}
    tph_env = {
        'NODE_ENV': 'production', 'LOCAL_TEST_ONLY': 'true', 'LOCAL_SOURCE_SHA': TPH_SHA, 'SQUARE_ENVIRONMENT': 'sandbox',
        'MONGO_URI_DEV': 'mongodb://localtest:${MONGO_PASSWORD:?required}@mongo:27017/tph_local_test?authSource=admin',
        'DISABLE_SCHEDULER': 'true', 'BLOG_STUDIO_ENABLED': 'false', 'BLOG_STUDIO_RUN_IN_WEB': 'false',
        'WORKOS_TENANT_ENABLED': 'false', 'MONTHLY_SUBSCRIPTIONS_ENABLED': 'false',
        'MONTHLY_CUSTOM_AUTOPAY_ENABLED': 'false', 'HIRING_CANDIDATE_SMS_ENABLED': 'false',
        'ADMIN_SMS_ENABLED': 'false', 'ADMIN_PAYMENT_SMS_ENABLED': 'false', 'ERROR_ALERTS_ENABLED': 'false',
        'ERROR_ALERTS_SMS_ENABLED': 'false', 'PERF_SLO_ALERTS_ENABLED': 'false',
        'SQUARE_ACCESS_TOKEN': 'LOCAL_TEST_INVALID_NOT_A_PROVIDER_CREDENTIAL',
        'AUTH0_DOMAIN': 'auth.tph.invalid', 'AUTH0_AUDIENCE': 'https://tph.invalid',
        'MANAGER_JWT_SECRET': '${TPH_MANAGER_SECRET:?required}', 'JWT_SECRET': '${TPH_JWT_SECRET:?required}',
        'ADMIN_API_KEY': '${TPH_API_SECRET:?required}', 'LOG_LEVEL': 'error',
    }
    tph_app = {**common, 'image': images['tph'], 'environment': tph_env, 'mem_limit': '512m',
               'user': 'node', 'read_only': True, 'tmpfs': ['/tmp:size=32m,mode=1777', '/usr/src/app/backend/logs:rw,noexec,nosuid,size=16777216,uid=1000,gid=1000,mode=0700'],
               'cap_drop': ['ALL'], 'depends_on': {'mongo': {'condition': 'service_healthy'}}}
    tph = {'name': 'tph-local-test', 'services': {
        'mongo': {**common, 'image': images['mongo'], 'mem_limit': '512m',
                  'command': ['mongod', '--wiredTigerCacheSizeGB', '0.25', '--bind_ip_all'],
                  'environment': {'MONGO_INITDB_ROOT_USERNAME': 'localtest', 'MONGO_INITDB_ROOT_PASSWORD': '${MONGO_PASSWORD:?required}'},
                  'volumes': ['mongo:/data/db', 'mongo_config:/data/configdb'],
                  'healthcheck': {'test': ['CMD', 'mongosh', '--quiet', '--eval', 'quit(db.adminCommand({ping:1}).ok ? 0 : 1)'], 'interval': '10s', 'timeout': '5s', 'retries': 20}},
        'web': {**tph_app, 'healthcheck': {'test': ['CMD', 'node', '-e', "fetch('http://127.0.0.1:5051/local-test/ready').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"], 'interval': '10s', 'timeout': '5s', 'retries': 20}},
        'worker': {**tph_app, 'command': ['node', 'tph-worker.cjs'], 'healthcheck': {'test': ['CMD', 'node', '-e', "const s=JSON.parse(require('fs').readFileSync('/tmp/local-worker-health.json'));process.exit(Date.now()-s.at<20000?0:1)"], 'interval': '10s', 'timeout': '5s', 'retries': 10}},
        'identity': {**tph_app, 'command': ['node', 'backend/workers/workosIdentityEventsWorker.js'],
                     'mem_limit': '192m', 'healthcheck': {'test': ['CMD', 'node', '-e', "process.kill(1,0)"], 'interval': '15s', 'timeout': '3s', 'retries': 10}},
        'gateway': gateway(18201)},
        'networks': {'isolated': {'internal': True}, 'ingress': {}}, 'volumes': {'mongo': {}, 'mongo_config': {}}}
    return {'db-local-test': db, 'tph-local-test': tph}



def nginx_configuration(is_db):
    port = 8000 if is_db else 5050
    readiness = '' if is_db else 'location = /local-test/ready { proxy_pass http://web:5051/local-test/ready; }'
    # Browser requests are constrained too: server isolation does not protect a
    # client from hardcoded live-provider URLs in an application's bundle.
    return f"""events {{ worker_connections 128; }}
http {{ server {{ listen 8080;
add_header Content-Security-Policy "default-src 'self'; connect-src 'self'; form-action 'self'; frame-src 'none'; object-src 'none'; script-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; base-uri 'self'; worker-src 'none'; frame-ancestors 'none'" always;
add_header X-Local-Test "synthetic-only" always;
{readiness}
location / {{
proxy_pass http://web:{port};
proxy_set_header Host $http_host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Accept-Encoding "";
proxy_buffer_size 32k;
proxy_buffers 4 32k;
proxy_busy_buffers_size 64k;
sub_filter '<body>' '<body><div style="background:#ffe58f;color:#111;padding:8px;text-align:center;font:14px sans-serif;position:relative;z-index:2147483647">LOCAL TEST - Synthetic data - Messages and schedules disabled</div>';
sub_filter_once on;
}} }} }}
"""


def main():
    os.umask(0o077)
    if ROOT.is_symlink() or ROOT.resolve() != ROOT or (ROOT / '.owner').read_text() != 'macapps-test-stacks-v1\n':
        raise RuntimeError('Unrecognized isolated stack root')
    images = json.loads((ROOT / 'private/images.json').read_text())
    for name, spec in specifications(images).items():
        directory = ROOT / name
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / 'compose.json'
        if path.exists():
            raise RuntimeError('Existing test stack configuration; inspect before replacement')
        path.write_text(json.dumps(spec, indent=2) + '\n')
        (directory / 'nginx.conf').write_text(nginx_configuration(name == 'db-local-test'))
    print('Two isolated fixed test-stack configurations generated')


if __name__ == '__main__':
    main()
