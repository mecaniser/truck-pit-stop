"""Local transactional simulations; no Docker, SSH, providers or real databases."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import remote

DB_IMAGE = 'sha256:' + 'a' * 64
TPH_IMAGE = 'sha256:' + 'b' * 64
NEW_IMAGE = 'sha256:' + 'c' * 64
NEXT_IMAGE = 'sha256:' + 'd' * 64
DB_SOURCE = 'a' * 40
TPH_SOURCE = 'b' * 40
NEW_SOURCE = 'c' * 40
NEXT_SOURCE = 'd' * 40
GRAPH = {'files': {'187.py': 'f' * 64}, 'revisions': ['187'], 'heads': ['187']}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class Operator:
    def __init__(self):
        self.containers = {}
        self.up_calls = []
        self.fail_next_up = False
        self.change_worker = False
        self.generation = 0
        self.app = 'tph'
        self.graphs = {image: copy.deepcopy(GRAPH) for image in (DB_IMAGE, NEW_IMAGE, NEXT_IMAGE)}
        for app, project in remote.PROJECTS.items():
            for service in self.spec(app)['services']:
                self.containers[project + '-' + service + '-1'] = self.item(
                    project + '-' + service + '-1', self.spec(app)['services'][service]['image'])
        for service in ('web', 'postgres', 'redis', 'gateway'):
            name = 'dieselbridge-staging-' + service + '-1'
            self.containers[name] = self.item(name, DB_IMAGE)

    def spec(self, app):
        return json.loads((remote.STACKS / remote.PROJECTS[app] / 'compose.json').read_text())

    def item(self, name, image):
        return {'Name': '/' + name, 'Id': name + '-id-' + str(self.generation), 'Image': image,
                'State': {'StartedAt': 'start-' + str(self.generation), 'Running': True,
                          'OOMKilled': False, 'Health': {'Status': 'healthy'}},
                'Config': {'Labels': {'owned': True}}, 'NetworkSettings': {'Networks': {'internal': {}}}}

    def inspect(self, app):
        project = remote.PROJECTS[app]
        return [copy.deepcopy(value) for key, value in self.containers.items() if key.startswith(project + '-')]

    def docker(self, args, **kwargs):
        if args[:2] == ['image', 'inspect']:
            image = args[2]
            source = {DB_IMAGE: DB_SOURCE, TPH_IMAGE: TPH_SOURCE, NEW_IMAGE: NEW_SOURCE, NEXT_IMAGE: NEXT_SOURCE}[image]
            value = {'Id': image, 'Architecture': 'arm64', 'Os': 'linux', 'Config': {'Labels': {
                'io.macapps.owner': remote.OWNER, 'io.macapps.app': self.app,
                'io.macapps.source': source, 'io.macapps.adapters': 'v1'}}}
            return json.dumps([value]).encode()
        if args[0] == 'run':
            return json.dumps(self.graphs[args[args.index('--entrypoint') + 2]]).encode()
        if args[0] == 'inspect':
            return json.dumps([self.containers[name] for name in args[1:]]).encode()
        if args[0] == 'ps':
            return b''
        raise AssertionError('Unexpected Docker operation')

    def compose(self, app, *args, **kwargs):
        if args[0] == 'up':
            self.up_calls.append((app, args))
            assert '--no-deps' in args and args[-1] in ('web', 'gateway')
            self.generation += 1
            service = args[-1]
            name = remote.PROJECTS[app] + '-' + service + '-1'
            self.containers[name] = self.item(name, self.spec(app)['services'][service]['image'])
            if self.change_worker:
                self.containers['tph-local-test-worker-1']['Id'] = 'unexpected-worker'
            if self.fail_next_up:
                self.fail_next_up = False
                raise RuntimeError('SIMULATED_SECRET_IN_ERROR')
            return b''
        if args[:3] == ('exec', '-T', 'postgres'):
            return b'187\n'
        if args[:3] == ('exec', '-T', 'web'):
            env = self.spec(app)['services']['web']['environment']
            return json.dumps({'ready': True, 'source': env.get('LOCAL_SOURCE_SHA')
                or env.get('RAILWAY_GIT_COMMIT_SHA') or (DB_SOURCE if app == 'dieselbridge' else TPH_SOURCE)}).encode()
        raise AssertionError('Unexpected Compose operation')


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.old_umask = os.umask(0o077)
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve()
        self.patches = [patch.object(remote, 'ROOT', root / 'deploy'), patch.object(remote, 'STACKS', root / 'stacks'),
                        patch.object(remote, 'BASELINE', root / 'baseline.json')]
        for item in self.patches:
            item.start()
        remote.ROOT.mkdir(mode=0o700)
        (remote.ROOT / '.owner').write_text(remote.OWNER + '\n')
        remote.prepare_root()
        remote.BASELINE.write_text('{}')
        base = Path(__file__).resolve().parents[1]
        specs_module = module('test_stack_templates', base / 'mac-test-apps/configure.py')
        public_module = module('public_templates', base / 'mac-test-public/configure.py')
        images = {key: DB_IMAGE for key in ('dieselbridge', 'tph', 'postgres', 'redis', 'mongo', 'nginx')}
        specs = specs_module.specifications(images)
        original = {app: specs[project] for app, project in remote.PROJECTS.items()}
        planned = public_module.plan(original, TPH_IMAGE)
        for app, project in remote.PROJECTS.items():
            directory = remote.STACKS / project
            directory.mkdir(parents=True, mode=0o700)
            env = planned[app]['services']['web']['environment']
            if app == 'tph':
                env['LOCAL_SOURCE_SHA'] = TPH_SOURCE
            (directory / 'compose.json').write_text(json.dumps(planned[app], indent=2) + '\n')
            (directory / 'nginx.conf').write_text('fixed approved private/public profile')
        self.operator = Operator()
        self.remote = remote.Remote(self.operator)
        self.remote.initialize()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()
        os.umask(self.old_umask)

    def deploy_tph(self, image=NEW_IMAGE, source=NEW_SOURCE):
        self.operator.app = 'tph'
        return self.remote.deploy('tph', image, source)

    def manifest(self):
        state = self.remote.load()
        token = 'e' * 32
        directory = remote.ROOT / 'private/database-releases'
        directory.mkdir(mode=0o700)
        value = {'version': 1, 'app': 'dieselbridge', 'token': token, 'image': NEW_IMAGE, 'source': NEW_SOURCE,
                 'original_database': 'dieselbridge_local_test', 'original_database_revision': '187',
                 'original_database_sha256': 'a' * 64,
                 'original_migrations_sha256': remote.digest(remote.canonical(state['database']['graph'])),
                 'security_approved': True, 'qa_approved': True, 'redis_url': 'redis://redis:6379/14',
                 'database_url': 'postgresql+asyncpg://dbtest_1234567890abcdef:synthetic@postgres:5432/dbtest_1234567890abcdef',
                 'database_revision': '187', 'checks': {key: True for key in ('native_login', 'read_write',
                 'restricted_db_role', 'original_db_access_denied', 'no_automatic_migrations', 'worker_queues_blocked',
                 'schema_compatibility', 'tenant_isolation', 'feature_activity')}}
        path = directory / (token + '.json')
        path.write_text(json.dumps(value))
        return token, path, value

    def test_repeatable_deploy_and_legacy_rollback(self):
        first = self.deploy_tph()
        self.assertEqual(first['protected_containers_preserved'], 12)
        self.deploy_tph(NEXT_IMAGE, NEXT_SOURCE)
        self.remote.deploy('tph', rollback=True)
        self.assertEqual(self.remote.load()['apps']['tph']['current']['source'], NEW_SOURCE)
        self.assertTrue(all(app == 'tph' and args[-1] in ('web', 'gateway') for app, args in self.operator.up_calls))
        self.assertFalse(self.remote.active_path.exists())

    def test_original_legacy_image_can_be_restored(self):
        self.deploy_tph()
        self.remote.deploy('tph', rollback=True)
        self.assertEqual(self.remote.load()['apps']['tph']['current']['image'], TPH_IMAGE)

    def test_failed_deploy_retains_full_rollback_history(self):
        self.deploy_tph()
        previous_state = self.remote.load()['apps']['tph']
        self.operator.fail_next_up = True
        with self.assertRaisesRegex(remote.Refused, '^deployment_failed_previous_release_restored$'):
            self.deploy_tph(NEXT_IMAGE, NEXT_SOURCE)
        self.assertEqual(self.remote.load()['apps']['tph'], previous_state)
        self.remote.deploy('tph', rollback=True)
        self.assertEqual(self.remote.load()['apps']['tph']['current']['image'], TPH_IMAGE)

    def test_uncertain_protected_runtime_drift_blocks_more_work(self):
        self.operator.change_worker = True
        with self.assertRaisesRegex(remote.Refused, 'rollback_uncertain'):
            self.deploy_tph()
        self.assertTrue(self.remote.active_path.exists())
        with self.assertRaisesRegex(remote.Refused, 'uncertain_operation'):
            self.deploy_tph()

    def test_existing_configuration_drift_refused_before_mutation(self):
        path = remote.STACKS / 'tph-local-test/compose.json'
        path.write_text(path.read_text() + ' ')
        with self.assertRaisesRegex(remote.Refused, 'configuration_drift'):
            self.deploy_tph()
        self.assertFalse(self.operator.up_calls)

    def test_selected_container_identity_drift_refused(self):
        self.operator.containers['tph-local-test-web-1']['Config']['Labels']['unapproved'] = 'value'
        with self.assertRaisesRegex(remote.Refused, 'accepted_container_identity_drift'):
            self.deploy_tph()

    def test_image_labels_and_architecture_required(self):
        with self.assertRaisesRegex(remote.Refused, 'image_labels'):
            remote.inspect_image(self.operator, NEW_IMAGE, 'dieselbridge', NEW_SOURCE)
        with self.assertRaisesRegex(remote.Refused, 'immutable_image'):
            self.remote.deploy('tph', 'mutable:latest', NEW_SOURCE)
        item = json.loads(self.operator.docker(['image', 'inspect', NEW_IMAGE]))[0]
        item['Architecture'] = 'amd64'
        with patch.object(self.operator, 'docker', return_value=json.dumps([item]).encode()):
            with self.assertRaisesRegex(remote.Refused, 'arm64_linux_image'):
                remote.inspect_image(self.operator, NEW_IMAGE, 'tph', NEW_SOURCE)

    def test_migration_probe_is_resource_and_network_bounded(self):
        with patch.object(self.operator, 'docker', wraps=self.operator.docker) as command:
            remote.migration_graph(self.operator, DB_IMAGE)
        args = next(call.args[0] for call in command.call_args_list if call.args[0][0] == 'run')
        self.assertEqual(args[args.index('--network') + 1], 'none')
        self.assertEqual(args[args.index('--memory') + 1], '384m')
        self.assertEqual(args[args.index('--cpus') + 1], '0.5')
        self.assertEqual(args[args.index('--pids-limit') + 1], '128')
        self.assertIn('size=64m', args[args.index('--tmpfs') + 1])
        self.assertIn('--read-only', args)

    def test_migration_timeout_cleans_only_owned_exact_cid(self):
        for write_cid in (True, False):
            with self.subTest(cid_file_written=write_cid):
                captured, removed = {}, []
                cid = 'f' * 64

                def command(args, **kwargs):
                    if args[0] == 'run':
                        captured['name'] = args[args.index('--name') + 1]
                        captured['token'] = next(value.split('=', 1)[1] for value in args
                                                 if value.startswith('io.macapps.migration-probe='))
                        if write_cid:
                            Path(args[args.index('--cidfile') + 1]).write_text(cid)
                        raise TimeoutError('synthetic CLI timeout')
                    if args[0] == 'ps':
                        self.assertIn('--no-trunc', args)
                        if write_cid:
                            self.assertIn('id=' + cid, args)
                        else:
                            self.assertIn('name=^/' + captured['name'] + '$', args)
                            self.assertIn('label=io.macapps.migration-probe=' + captured['token'], args)
                        return (cid + '\n').encode()
                    if args[0] == 'inspect':
                        self.assertEqual(args[1:], [cid])
                        return json.dumps([{'Id': cid, 'Name': '/' + captured['name'], 'Image': DB_IMAGE,
                          'Config': {'Labels': {'io.macapps.owner': remote.OWNER,
                          'io.macapps.migration-probe': captured['token']}}, 'State': {'Running': True}}]).encode()
                    if args[0] == 'rm':
                        removed.append(args)
                        return b''
                    raise AssertionError('unexpected cleanup operation')

                with patch.object(self.operator, 'docker', side_effect=command):
                    with self.assertRaises(TimeoutError):
                        remote.migration_graph(self.operator, DB_IMAGE)
                self.assertEqual(removed, [['rm', '-f', cid]])

    def test_migration_cleanup_refuses_unowned_container(self):
        cid = 'e' * 64
        path = remote.ROOT / 'private/probe.cid'
        path.write_text(cid)
        calls = []

        def command(args, **kwargs):
            calls.append(args)
            if args[0] == 'ps':
                return cid.encode()
            if args[0] == 'inspect':
                return json.dumps([{'Id': cid, 'Name': '/expected', 'Image': DB_IMAGE,
                                   'Config': {'Labels': {}}, 'State': {'Running': True}}]).encode()
            raise AssertionError('must not remove an unowned container')

        with patch.object(self.operator, 'docker', side_effect=command):
            with self.assertRaisesRegex(remote.Refused, 'cleanup_ownership_refused'):
                remote.cleanup_migration_probe(self.operator, path, 'expected', DB_IMAGE, 'token')
        self.assertFalse(any(args[0] == 'rm' for args in calls))

    def test_migration_cleanup_leaves_exited_probe_to_autoremove(self):
        cid = 'e' * 64
        path = remote.ROOT / 'private/probe.cid'
        path.write_text(cid)
        result = [{'Id': cid, 'Name': '/expected', 'Image': DB_IMAGE, 'Config': {'Labels': {
            'io.macapps.owner': remote.OWNER, 'io.macapps.migration-probe': 'token'}}, 'State': {'Running': False}}]
        with patch.object(self.operator, 'docker', side_effect=[cid.encode(), json.dumps(result).encode()]) as command:
            remote.cleanup_migration_probe(self.operator, path, 'expected', DB_IMAGE, 'token')
        self.assertEqual(command.call_count, 2)

    def test_old_migration_graph_refused_without_database_release(self):
        self.operator.app = 'dieselbridge'
        self.operator.graphs[NEW_IMAGE] = {'files': {'156.py': 'c'}, 'revisions': ['156'], 'heads': ['156']}
        with self.assertRaisesRegex(remote.Refused, 'isolated_database_release'):
            self.remote.deploy('dieselbridge', NEW_IMAGE, NEW_SOURCE)
        self.assertFalse(self.operator.up_calls)
        self.assertFalse(self.remote.active_path.exists())

    def test_isolated_release_switches_only_web_and_rollback_restores_original_database(self):
        self.operator.app = 'dieselbridge'
        token, _, value = self.manifest()
        self.operator.graphs[NEW_IMAGE] = {'files': {'156.py': 'c'}, 'revisions': ['156'], 'heads': ['156']}
        before = self.operator.spec('dieselbridge')
        self.remote.deploy('dieselbridge', NEW_IMAGE, NEW_SOURCE, database_token=token)
        after = self.operator.spec('dieselbridge')
        self.assertEqual(after['services']['worker'], before['services']['worker'])
        self.assertEqual(after['services']['web']['environment']['DATABASE_URL'], value['database_url'])
        self.assertEqual(after['services']['web']['environment']['REDIS_URL'], 'redis://redis:6379/14')
        self.assertEqual((remote.STACKS / 'db-local-test/compose.json').stat().st_mode & 0o777, 0o600)
        self.remote.deploy('dieselbridge', rollback=True)
        self.assertEqual(self.operator.spec('dieselbridge'), before)

    def test_isolated_release_rejects_original_database_and_missing_approval(self):
        self.operator.app = 'dieselbridge'
        token, path, value = self.manifest()
        value['database_url'] = 'postgresql+asyncpg://localtest:synthetic@postgres:5432/dieselbridge_local_test'
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(remote.Refused, 'isolated_database_target'):
            self.remote.deploy('dieselbridge', NEW_IMAGE, NEW_SOURCE, database_token=token)
        self.assertFalse(self.operator.up_calls)
        value['security_approved'] = False
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(remote.Refused, 'binding_refused'):
            self.remote.deploy('dieselbridge', NEW_IMAGE, NEW_SOURCE, database_token=token)

    def test_isolated_release_requires_all_new_security_gates(self):
        self.operator.app = 'dieselbridge'
        token, path, value = self.manifest()
        for flag in ('schema_compatibility', 'tenant_isolation', 'feature_activity'):
            with self.subTest(flag=flag):
                changed = copy.deepcopy(value)
                changed['checks'][flag] = False
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(remote.Refused, 'gates_incomplete'):
                    self.remote.deploy('dieselbridge', NEW_IMAGE, NEW_SOURCE, database_token=token)
                self.assertFalse(self.operator.up_calls)
                self.assertFalse(self.remote.active_path.exists())


if __name__ == '__main__':
    unittest.main()
