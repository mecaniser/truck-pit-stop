"""Mac-only image deployments. No migrations, seeds, workers or production management."""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid
from urllib.parse import urlsplit

ROOT = Path.home() / 'mac-hosting/test-deploy'
STACKS = Path.home() / 'mac-hosting/test-stacks'
BASELINE = Path.home() / 'dieselbridge-staging/private/soak-baseline.json'
PROJECTS = {'dieselbridge': 'db-local-test', 'tph': 'tph-local-test'}
HOSTS = {'dieselbridge': 'dieselbridge-test.elisprotech.com', 'tph': 'tph-test.elisprotech.com'}
OWNER = 'macapps-test-deploy-v1'
IMAGE = re.compile(r'sha256:[0-9a-f]{64}\Z')
SOURCE = re.compile(r'[0-9a-f]{40}\Z')


class Refused(RuntimeError):
    """Only fixed, non-sensitive error identifiers belong in this exception."""


def check(condition, code):
    if not condition:
        raise Refused(code)


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def load_module(name, path):
    check(not path.is_symlink() and path.resolve() == path, 'module_path_refused')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_path(path):
    check(not path.is_symlink() and path.resolve() == path, 'control_path_refused')
    if path.exists():
        info = path.stat()
        check(info.st_uid == os.getuid() and not (stat.S_IMODE(info.st_mode) & 0o077), 'control_permissions_refused')


def prepare_root():
    check(ROOT.resolve() == ROOT and not ROOT.is_symlink(), 'unknown_deployment_root')
    check((ROOT / '.owner').read_text() == OWNER + '\n', 'unknown_deployment_owner')
    for path in (ROOT / 'private', ROOT / 'releases'):
        safe_path(path)
        path.mkdir(mode=0o700, exist_ok=True)
    for name in ('state.json', 'active.json', 'recovery-active.json', 'schema-compatibility-approval.json'):
        safe_path(ROOT / 'private' / name)


def atomic_json(path, value):
    safe_path(path)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('xb') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(json.dumps(value, sort_keys=True, indent=2).encode() + b'\n')
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def current_files():
    result = {}
    for project in PROJECTS.values():
        for name in ('compose.json', 'nginx.conf'):
            path = STACKS / project / name
            check(path.resolve() == path and not path.is_symlink(), 'stack_configuration_path_refused')
            result[project + '/' + name] = path.read_bytes()
    return result


def file_hashes(files):
    return {key: digest(value) for key, value in files.items()}


def install_compose(app, data):
    path = STACKS / PROJECTS[app] / 'compose.json'
    check(path.resolve() == path and not path.is_symlink(), 'stack_configuration_path_refused')
    temporary = path.with_name('compose.json.deploy.tmp')
    with temporary.open('xb') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def inspect_image(operator, image, app=None, source=None, *, legacy=False):
    check(bool(IMAGE.fullmatch(image)), 'immutable_image_required')
    values = json.loads(operator.docker(['image', 'inspect', image], log='deploy-image-inspection'))
    check(len(values) == 1, 'single_local_image_required')
    item = values[0]
    check(item['Id'] == image and item['Architecture'] == 'arm64' and item['Os'] == 'linux', 'arm64_linux_image_required')
    if not legacy:
        labels = item['Config'].get('Labels') or {}
        expected = {'io.macapps.owner': OWNER, 'io.macapps.app': app,
                    'io.macapps.source': source, 'io.macapps.adapters': 'v1'}
        check(all(labels.get(key) == value for key, value in expected.items()), 'candidate_image_labels_refused')
    return item


MIGRATIONS = r'''
import ast,hashlib,json,pathlib
root=pathlib.Path('/app/alembic/versions')
files={}; revisions=[]; parents=[]
for p in sorted(root.glob('*.py')):
    if p.name=='__init__.py': continue
    raw=p.read_bytes(); values={}
    for n in ast.parse(raw).body:
        if isinstance(n,ast.Assign):
            names=[t.id for t in n.targets if isinstance(t,ast.Name)]
        elif isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name): names=[n.target.id]
        else: continue
        for name in names:
            if name in ('revision','down_revision'): values[name]=ast.literal_eval(n.value)
    revision=values['revision']; parent=values.get('down_revision')
    assert isinstance(revision,str) and revision not in revisions
    revisions.append(revision)
    parents.extend([parent] if isinstance(parent,str) else (parent or []))
    files[p.name]=hashlib.sha256(raw).hexdigest()
assert files and set(parents)<=set(revisions)
print(json.dumps({'files':files,'revisions':sorted(revisions),'heads':sorted(set(revisions)-set(parents))}))
'''


def cleanup_migration_probe(operator, cid_path, name, image, token):
    """Remove only a still-running probe whose exact CID and ownership match."""
    cid = None
    if cid_path.exists():
        check(not cid_path.is_symlink() and cid_path.resolve() == cid_path, 'migration_probe_cid_path_refused')
        info = cid_path.stat()
        check(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_size <= 128,
              'migration_probe_cid_file_refused')
        cid_path.chmod(0o600)
        cid = cid_path.read_text().strip()
        check(re.fullmatch(r'[0-9a-f]{64}', cid) is not None, 'migration_probe_cid_refused')
        filters = ['--filter', 'id=' + cid]
    else:
        # The CLI can die after Docker creates the container but before it
        # writes the CID file. Resolve only our UUID name AND ownership labels.
        filters = ['--filter', 'name=^/' + name + '$', '--filter', 'label=io.macapps.owner=' + OWNER,
                   '--filter', 'label=io.macapps.migration-probe=' + token]
    found = operator.docker(['ps', '-aq', '--no-trunc', *filters], timeout=15,
                            log='deploy-migration-cleanup-discovery').decode().split()
    if not found:
        return
    check(len(found) == 1 and re.fullmatch(r'[0-9a-f]{64}', found[0]) is not None
          and (cid is None or found[0] == cid), 'migration_probe_cleanup_identity_refused')
    cid = found[0]
    items = json.loads(operator.docker(['inspect', cid], timeout=15, log='deploy-migration-cleanup-inspection'))
    check(len(items) == 1, 'migration_probe_cleanup_identity_refused')
    item = items[0]
    labels = item.get('Config', {}).get('Labels') or {}
    check(item.get('Id') == cid and item.get('Name') == '/' + name and item.get('Image') == image
          and labels.get('io.macapps.owner') == OWNER and labels.get('io.macapps.migration-probe') == token,
          'migration_probe_cleanup_ownership_refused')
    if item.get('State', {}).get('Running') is True:
        operator.docker(['rm', '-f', cid], timeout=20, log='deploy-migration-owned-probe-cleanup')


def migration_graph(operator, image):
    directory = ROOT / 'private/migration-probes'
    safe_path(directory)
    directory.mkdir(mode=0o700, exist_ok=True)
    token = uuid.uuid4().hex
    name = 'macapps-migration-' + token
    cid_path = directory / (token + '.cid')
    atomic_json(directory / (token + '.json'), {'name': name, 'image': image, 'token': token, 'started': stamp()})
    try:
        raw = operator.docker(['run', '--rm', '--name', name, '--cidfile', str(cid_path),
                               '--label', 'io.macapps.owner=' + OWNER,
                               '--label', 'io.macapps.migration-probe=' + token,
                               '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                               '--security-opt', 'no-new-privileges:true', '--memory', '384m', '--cpus', '0.5',
                               '--pids-limit', '128', '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m,mode=1777',
                               '--entrypoint', 'python', image,
                               '-c', MIGRATIONS], timeout=60, log='deploy-migration-inspection')
    finally:
        cleanup_migration_probe(operator, cid_path, name, image, token)
    graph = json.loads(raw)
    check(isinstance(graph.get('files'), dict) and graph['files'] and isinstance(graph.get('heads'), list),
          'migration_graph_unavailable')
    return graph


def database_revision(operator):
    raw = operator.compose('dieselbridge', 'exec', '-T', 'postgres', 'psql', '-U', 'localtest',
                           '-d', 'dieselbridge_local_test', '-At', '-c', 'SELECT version_num FROM alembic_version',
                           timeout=20, log='deploy-read-only-database-revision')
    revisions = raw.decode().split()
    check(len(revisions) == 1 and re.fullmatch(r'[A-Za-z0-9_]+', revisions[0]) is not None,
          'single_known_database_revision_required')
    return revisions[0]


def database_release(operator, state, token, image, source):
    check(re.fullmatch(r'[0-9a-f]{32}', token or '') is not None, 'database_release_token_refused')
    path = ROOT / 'private/database-releases' / (token + '.json')
    safe_path(path.parent)
    safe_path(path)
    report = json.loads(path.read_text())
    expected = {'version': 1, 'app': 'dieselbridge', 'token': token, 'image': image, 'source': source,
                'original_database': 'dieselbridge_local_test',
                'original_database_revision': state['database']['revision'],
                'original_migrations_sha256': digest(canonical(state['database']['graph'])),
                'security_approved': True, 'qa_approved': True, 'redis_url': 'redis://redis:6379/14'}
    check(all(report.get(key) == value for key, value in expected.items()), 'database_release_binding_refused')
    check(re.fullmatch(r'[0-9a-f]{64}', report.get('original_database_sha256', '')) is not None,
          'original_database_archive_fingerprint_required')
    check(all(report.get('checks', {}).get(key) is True for key in
              ('native_login', 'read_write', 'restricted_db_role', 'original_db_access_denied',
               'no_automatic_migrations', 'worker_queues_blocked', 'schema_compatibility',
               'tenant_isolation', 'feature_activity')), 'database_release_gates_incomplete')
    url = urlsplit(report.get('database_url', ''))
    check(url.scheme == 'postgresql+asyncpg' and url.hostname == 'postgres' and url.port == 5432
          and re.fullmatch(r'dbtest_[0-9a-f]{16}', url.username or '') is not None
          and url.path == '/' + url.username and bool(url.password) and not url.query and not url.fragment,
          'isolated_database_target_refused')
    check(database_revision(operator) == state['database']['revision'], 'original_database_revision_drift')
    raw = operator.compose('dieselbridge', 'exec', '-T', 'postgres', 'psql', '-U', 'localtest',
                           '-d', url.username, '-At', '-c', 'SELECT version_num FROM alembic_version',
                           timeout=20, log='deploy-read-only-isolated-database-revision')
    revisions = raw.decode().split()
    check(len(revisions) == 1 and revisions[0] == report.get('database_revision')
          and re.fullmatch(r'[A-Za-z0-9_]+', revisions[0]) is not None,
          'isolated_database_revision_unverified')
    return {'mode': 'reviewed_isolated_database', 'token': token,
            'manifest_sha256': digest(path.read_bytes()), 'database_revision': revisions[0]}, {
                'DATABASE_URL': report['database_url'], 'REDIS_URL': report['redis_url']}


def schema_gate(operator, state, image, source):
    accepted = state['database']
    revision = database_revision(operator)
    check(revision == accepted['revision'], 'database_revision_drift_no_migrations_allowed')
    candidate = migration_graph(operator, image)
    if candidate == accepted['graph'] and candidate['heads'] == [revision]:
        return {'mode': 'exact_migrations', 'database_revision': revision,
                'candidate_migrations_sha256': digest(canonical(candidate))}
    raise Refused('migration_difference_requires_isolated_database_release')


def runtime(operator, app):
    if app == 'dieselbridge':
        script = "import json,urllib.request; h=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=5)); b=json.load(urllib.request.urlopen('http://127.0.0.1:8000/build-version',timeout=5)); print(json.dumps({'ready':h.get('status')=='ready' and h.get('environment')=='staging','source':b.get('sha')}))"
        raw = operator.compose(app, 'exec', '-T', 'web', 'python', '-c', script, timeout=20, log='deploy-runtime-identity')
    else:
        script = "fetch('http://127.0.0.1:5051/local-test/ready').then(async r=>{const h=await r.json();console.log(JSON.stringify({ready:r.ok&&h.status==='ready'&&h.environment==='local-test'&&h.scheduler==='disabled',source:h.source}))}).catch(()=>process.exit(1))"
        raw = operator.compose(app, 'exec', '-T', 'web', 'node', '-e', script, timeout=20, log='deploy-runtime-identity')
    value = json.loads(raw.decode().strip().splitlines()[-1])
    check(value.get('ready') is True and isinstance(value.get('source'), str)
          and SOURCE.fullmatch(value['source']) is not None, 'runtime_readiness_or_source_unverified')
    return value


def snapshot(operator):
    items = []
    for app in PROJECTS:
        owned = operator.inspect(app)
        check(len(owned) == 5, 'expected_five_services_per_test_stack')
        items.extend(owned)
    names = ['dieselbridge-staging-' + part + '-1' for part in ('web', 'postgres', 'redis', 'gateway')]
    items.extend(json.loads(operator.docker(['inspect', *names], log='deploy-protected-staging-inspection')))
    result = {}
    for item in items:
        state = item['State']
        result[item['Name'].lstrip('/')] = {'id': item['Id'], 'started': state['StartedAt'], 'image': item['Image'],
            'running': state['Running'], 'oom': state['OOMKilled'], 'health': state.get('Health', {}).get('Status'),
            'config_sha256': digest(canonical(item['Config'])),
            'networks_sha256': digest(canonical(item['NetworkSettings']['Networks']))}
    check(len(result) == 14, 'exact_fourteen_containers_required')
    return {'containers': result, 'baseline_sha256': digest(BASELINE.read_bytes())}


def identity_matches(accepted, observed):
    def identities(value):
        return {name: {key: field for key, field in item.items() if key != 'health'}
                for name, item in value['containers'].items()}
    return identities(accepted) == identities(observed)


def protected(value, app):
    excluded = {PROJECTS[app] + '-' + service + '-1' for service in ('web', 'gateway')}
    return {name: {key: field for key, field in item.items() if key != 'health'}
            for name, item in value['containers'].items() if name not in excluded}


def preserved(before, after, app):
    check(before['baseline_sha256'] == after['baseline_sha256']
          and protected(before, app) == protected(after, app), 'protected_runtime_drift_stop_and_inspect')


def healthy(value):
    check(all(item['running'] and not item['oom'] and item['health'] in (None, 'healthy')
              for item in value['containers'].values()), 'unhealthy_existing_runtime')


def normalize(spec, app):
    value = copy.deepcopy(spec)
    web = value['services']['web']
    web['image'] = '<allowed-image>'
    for key in ('LOCAL_SOURCE_SHA', 'RAILWAY_GIT_COMMIT_SHA'):
        if key == 'LOCAL_SOURCE_SHA' or app == 'dieselbridge':
            web['environment'].pop(key, None)
    if app == 'dieselbridge':
        for key in ('DATABASE_URL', 'REDIS_URL'):
            web['environment'][key] = '<bound-database-release>'
    return value


def initial_safety(files):
    for app, project in PROJECTS.items():
        spec = json.loads(files[project + '/compose.json'])
        check(spec['name'] == project and spec['networks']['isolated'].get('internal') is True,
              'isolated_fixed_project_required')
        expected_ports = ['127.0.0.1:' + ('18200' if app == 'dieselbridge' else '18201') + ':8080',
                          '127.0.0.1:' + ('18210' if app == 'dieselbridge' else '18211') + ':8081']
        check(spec['services']['gateway']['ports'] == expected_ports, 'fixed_loopback_gateway_ports_required')
        for name, service in spec['services'].items():
            check(not service.get('privileged') and service.get('network_mode') != 'host'
                  and service.get('networks') == (['isolated', 'ingress'] if name == 'gateway' else ['isolated']),
                  'service_network_boundary_refused')
            if name != 'gateway':
                check(not service.get('ports'), 'private_service_port_refused')
        env = spec['services']['web']['environment']
        if app == 'dieselbridge':
            check(env.get('ENVIRONMENT') == 'staging' and env.get('LOCAL_TEST_ONLY') == 'true'
                  and env.get('FRONTEND_URL') == 'https://' + HOSTS[app]
                  and env.get('CORS_ORIGINS_STR') == 'https://' + HOSTS[app]
                  and env.get('COOKIE_SECURE') == 'true', 'dieselbridge_public_test_profile_required')
            flags = ('WORKOS_AUTH_ENABLED', 'MOTIVE_ENABLED', 'SMS_TENANT_ROUTING_ENABLED',
                     'SMS_AUTOMATION_OUTBOX_ENABLED', 'SMS_RECOVERY_ENABLED', 'PROVIDER_OUTBOX_ENABLED')
            check(all(env.get(key) == 'false' for key in flags), 'dieselbridge_provider_flags_refused')
        else:
            check(env.get('LOCAL_TEST_ONLY') == 'true' and env.get('SQUARE_ENVIRONMENT') == 'sandbox'
                  and env.get('DISABLE_SCHEDULER') == 'true', 'tph_sandbox_profile_required')
            flags = ('BLOG_STUDIO_ENABLED', 'BLOG_STUDIO_RUN_IN_WEB', 'WORKOS_TENANT_ENABLED',
                     'MONTHLY_SUBSCRIPTIONS_ENABLED', 'MONTHLY_CUSTOM_AUTOPAY_ENABLED',
                     'HIRING_CANDIDATE_SMS_ENABLED', 'ADMIN_SMS_ENABLED', 'ADMIN_PAYMENT_SMS_ENABLED',
                     'ERROR_ALERTS_ENABLED', 'ERROR_ALERTS_SMS_ENABLED')
            check(all(env.get(key) == 'false' for key in flags), 'tph_delivery_flags_refused')


class Remote:
    def __init__(self, operator):
        self.operator = operator
        self.state_path = ROOT / 'private/state.json'
        self.active_path = ROOT / 'private/active.json'

    def initialize(self):
        check(not self.state_path.exists() and not self.active_path.exists()
              and not (ROOT / 'private/recovery-active.json').exists(), 'deployment_state_already_initialized')
        files = current_files()
        initial_safety(files)
        observed = snapshot(self.operator)
        healthy(observed)
        state = {'version': 1, 'owner': OWNER, 'at': stamp(), 'files_sha256': file_hashes(files),
                 'approved_specs': {}, 'snapshot': observed, 'apps': {}, 'legacy_images': {}}
        for app, project in PROJECTS.items():
            spec = json.loads(files[project + '/compose.json'])
            image = spec['services']['web']['image']
            inspect_image(self.operator, image, legacy=True)
            source = runtime(self.operator, app)['source']
            check(observed['containers'][project + '-web-1']['image'] == image, 'initial_web_image_mismatch')
            state['approved_specs'][app] = normalize(spec, app)
            state['apps'][app] = {'current': {'image': image, 'source': source, 'legacy': True,
                 'config_text': files[project + '/compose.json'].decode()}, 'previous': None}
            state['legacy_images'][app] = {'image': image, 'source': source}
        graph = migration_graph(self.operator, state['apps']['dieselbridge']['current']['image'])
        revision = database_revision(self.operator)
        check(graph['heads'] == [revision] and revision in graph['revisions'], 'initial_database_migrations_unverified')
        env = json.loads(files['db-local-test/compose.json'])['services']['web']['environment']
        state['database'] = {'revision': revision, 'graph': graph,
                             'environment': {key: env[key] for key in ('DATABASE_URL', 'REDIS_URL')}}
        atomic_json(self.state_path, state)
        return {'initialized': True, 'legacy_images_explicitly_recorded': True, 'database_revision': revision}

    def load(self):
        state = json.loads(self.state_path.read_text())
        check(state.get('owner') == OWNER and state.get('version') == 1, 'unknown_deployment_state')
        return state

    def preflight(self, state, app):
        check(not self.active_path.exists(), 'uncertain_operation_inspect_active_receipt')
        check(not (ROOT / 'private/recovery-active.json').exists(), 'uncertain_recovery_inspect_private_receipt')
        files = current_files()
        check(file_hashes(files) == state['files_sha256'], 'configuration_drift_refused')
        for candidate_app, project in PROJECTS.items():
            check(normalize(json.loads(files[project + '/compose.json']), candidate_app)
                  == state['approved_specs'][candidate_app], 'approved_service_contract_drift')
        observed = snapshot(self.operator)
        healthy(observed)
        check(state['snapshot']['baseline_sha256'] == observed['baseline_sha256'], 'accepted_baseline_drift')
        for name, accepted in state['snapshot']['containers'].items():
            check({key: value for key, value in accepted.items() if key != 'health'}
                  == {key: value for key, value in observed['containers'].get(name, {}).items() if key != 'health'},
                  'accepted_container_identity_drift')
        for candidate_app, project in PROJECTS.items():
            check(observed['containers'][project + '-web-1']['image']
                  == state['apps'][candidate_app]['current']['image'], 'accepted_web_image_drift')
        return files, observed

    def journal(self, directory, phase):
        with (directory / 'journal.jsonl').open('a') as output:
            output.write(json.dumps({'at': stamp(), 'phase': phase}) + '\n')
            output.flush()
            os.fsync(output.fileno())

    def recreate(self, app, directory):
        for service in ('web', 'gateway'):
            self.journal(directory, service + '_started')
            force = ('--force-recreate',) if service == 'gateway' else ()
            self.operator.compose(app, 'up', '-d', '--no-deps', *force, '--wait', '--wait-timeout', '120', service,
                                  timeout=150, log='deploy-' + directory.name + '-' + service)
            self.journal(directory, service + '_healthy')

    def verify(self, app, release, before):
        value = runtime(self.operator, app)
        check(value['source'] == release['source'], 'candidate_runtime_source_mismatch')
        after = snapshot(self.operator)
        healthy(after)
        preserved(before, after, app)
        check(after['containers'][PROJECTS[app] + '-web-1']['image'] == release['image'], 'candidate_runtime_image_mismatch')
        return after

    def deploy(self, app, image=None, source=None, *, rollback=False, database_token=None):
        check(app in PROJECTS, 'unknown_application')
        state = self.load()
        old_state = copy.deepcopy(state)
        files, before = self.preflight(state, app)
        previous = state['apps'][app]['current']
        if rollback:
            check(database_token is None, 'rollback_cannot_select_database_release')
            release = copy.deepcopy(state['apps'][app]['previous'])
            check(release is not None, 'no_previous_accepted_release')
            image, source = release['image'], release['source']
            if release.get('legacy') is True:
                check(state['legacy_images'].get(app) == {'image': image, 'source': source},
                      'legacy_image_exemption_not_recorded')
            inspect_image(self.operator, image, app, source, legacy=release.get('legacy') is True)
            proposed = json.loads(release['config_text'])
            check(normalize(proposed, app) == state['approved_specs'][app], 'rollback_configuration_contract_refused')
        else:
            check(bool(SOURCE.fullmatch(source or '')), 'full_source_sha_required')
            inspect_image(self.operator, image, app, source)
            proposed = json.loads(files[PROJECTS[app] + '/compose.json'])
            proposed['services']['web']['image'] = image
            proposed['services']['web']['environment']['LOCAL_SOURCE_SHA'] = source
            if app == 'dieselbridge':
                proposed['services']['web']['environment']['RAILWAY_GIT_COMMIT_SHA'] = source
            release = {'image': image, 'source': source, 'legacy': False,
                       'config_text': json.dumps(proposed, indent=2) + '\n'}
        check(image != previous['image'] or source != previous['source'], 'release_already_current')
        check(proposed['services']['web']['image'] == image, 'release_image_configuration_mismatch')
        check(normalize(proposed, app) == state['approved_specs'][app], 'candidate_configuration_contract_refused')
        if app == 'dieselbridge':
            token = release.get('database_release') if rollback else database_token
            if token:
                schema, environment = database_release(self.operator, state, token, image, source)
                proposed['services']['web']['environment'].update(environment)
                release['database_release'] = token
            else:
                schema = schema_gate(self.operator, state, image, source)
                proposed['services']['web']['environment'].update(state['database']['environment'])
            if rollback:
                check(proposed == json.loads(release['config_text']), 'rollback_database_profile_changed')
            else:
                release['config_text'] = json.dumps(proposed, indent=2) + '\n'
        else:
            check(database_token is None, 'database_release_only_supported_for_dieselbridge')
            schema = {'mode': 'no_migrations_run'}
        directory = ROOT / 'releases' / str(uuid.uuid4())
        directory.mkdir(mode=0o700)
        atomic_json(directory / 'before.json', {'snapshot': before, 'release': previous,
                    'previous_release': old_state['apps'][app]['previous'], 'files_sha256': file_hashes(files)})
        atomic_json(directory / 'candidate.json', {'release': release, 'schema': schema, 'rollback': rollback})
        with self.active_path.open('x') as output:
            json.dump({'operation': directory.name, 'app': app, 'started': stamp()}, output)
            output.flush()
            os.fsync(output.fileno())
        self.journal(directory, 'transaction_started')
        try:
            check(current_files() == files, 'configuration_changed_before_install')
            install_compose(app, release['config_text'].encode())
            self.journal(directory, 'candidate_configuration_installed')
            self.recreate(app, directory)
            after = self.verify(app, release, before)
            state['apps'][app] = {'current': release, 'previous': previous}
            state['snapshot'], state['files_sha256'], state['at'] = after, file_hashes(current_files()), stamp()
            atomic_json(self.state_path, state)
            atomic_json(directory / 'completed.json', {'snapshot': after, 'source': source, 'image': image, 'at': stamp()})
            self.journal(directory, 'accepted')
        except Exception:
            # Restore only our exact candidate; unexpected drift or a failed
            # rollback keeps active.json and blocks every subsequent mutation.
            self.journal(directory, 'candidate_failed')
            try:
                expected_files = {**files, PROJECTS[app] + '/compose.json': release['config_text'].encode()}
                check(current_files() == expected_files, 'rollback_configuration_drift')
                preserved(before, snapshot(self.operator), app)
                install_compose(app, previous['config_text'].encode())
                self.journal(directory, 'automatic_rollback_started')
                self.recreate(app, directory)
                recovered = self.verify(app, previous, before)
                # State may have been updated immediately before a receipt I/O
                # failure; retain the prior release history captured at intake.
                state = old_state
                state['snapshot'], state['files_sha256'], state['at'] = recovered, file_hashes(current_files()), stamp()
                atomic_json(self.state_path, state)
                atomic_json(directory / 'rolled-back.json', {'snapshot': recovered, 'source': previous['source'], 'at': stamp()})
                self.active_path.replace(directory / 'closed-active.json')
            except Exception:
                self.journal(directory, 'automatic_rollback_failed_inspection_required')
                raise Refused('deployment_failed_rollback_uncertain_inspect_active_receipt') from None
            raise Refused('deployment_failed_previous_release_restored') from None
        self.active_path.replace(directory / 'closed-active.json')
        return {'app': app, 'source': source, 'image': image, 'operation': directory.name,
                'rollback': rollback, 'protected_containers_preserved': 12}

    def status(self):
        state = self.load()
        files = current_files()
        observed = snapshot(self.operator)
        live = {}
        for app in PROJECTS:
            try:
                value = runtime(self.operator, app)
                live[app] = {**value, 'matches_accepted_source': value['source'] == state['apps'][app]['current']['source']}
            except Exception:
                live[app] = {'ready': False, 'matches_accepted_source': False}
        return {'apps': {app: {'image': entry['current']['image'], 'source': entry['current']['source'],
                              'previous_source': (entry.get('previous') or {}).get('source')}
                         for app, entry in state['apps'].items()},
                'configuration_matches': file_hashes(files) == state['files_sha256'],
                'baseline_matches': observed['baseline_sha256'] == state['snapshot']['baseline_sha256'],
                'identity_matches': identity_matches(state['snapshot'], observed),
                'live_runtime': live, 'uncertain_operation': self.active_path.exists(),
                'uncertain_recovery': (ROOT / 'private/recovery-active.json').exists(), 'snapshot': observed}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'status', 'deploy', 'rollback', 'recovery-propose', 'recovery-commit'))
    parser.add_argument('app', nargs='?', choices=tuple(PROJECTS))
    parser.add_argument('image', nargs='?')
    parser.add_argument('source', nargs='?')
    parser.add_argument('--database-release', dest='database_token')
    parser.add_argument('--observation')
    parser.add_argument('--proposal')
    parser.add_argument('--approval-sha256')
    args = parser.parse_args()
    if args.command == 'deploy':
        if args.app is None or IMAGE.fullmatch(args.image or '') is None or SOURCE.fullmatch(args.source or '') is None:
            parser.error('deploy requires APP sha256:IMAGE FULL_SOURCE_SHA')
    elif args.command == 'rollback':
        if args.app is None or args.image is not None or args.source is not None:
            parser.error('rollback requires only APP')
    elif any(value is not None for value in (args.app, args.image, args.source)):
        parser.error('init/status accept no additional arguments')
    if args.database_token is not None and (args.command != 'deploy' or args.app != 'dieselbridge'
                                           or re.fullmatch(r'[0-9a-f]{32}', args.database_token) is None):
        parser.error('--database-release requires dieselbridge deploy and a 32-character lowercase hex token')
    if args.command == 'recovery-propose':
        if not args.observation or args.proposal or args.approval_sha256:
            parser.error('recovery-propose requires only --observation')
    elif args.command == 'recovery-commit':
        if not args.proposal or not args.approval_sha256 or args.observation:
            parser.error('recovery-commit requires --proposal and --approval-sha256')
    elif any((args.observation, args.proposal, args.approval_sha256)):
        parser.error('recovery flags require a recovery command')
    prepare_root()
    operator = load_module('accepted_stack_operator', STACKS / 'tools/stackctl.py')
    # Same shared lock as the original stack operator and public rollout.
    # Never acquire the public runner's lifetime lock or stop its processes.
    with operator.lock():
        remote = Remote(operator)
        if args.command == 'init':
            result = remote.initialize()
        elif args.command == 'status':
            result = remote.status()
        elif args.command.startswith('recovery-'):
            module = load_module('accepted_recovery', Path(__file__).resolve().with_name('recovery.py'))
            recovery = module.Recovery(sys.modules[__name__], remote)
            result = recovery.propose(args.observation) if args.command == 'recovery-propose' else recovery.commit(args.proposal, args.approval_sha256)
        else:
            result = remote.deploy(args.app, args.image, args.source, rollback=args.command == 'rollback',
                                   database_token=args.database_token)
        print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Refused as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print('deployment_operation_failed_inspect_private_receipts', file=sys.stderr)
        raise SystemExit(1)
