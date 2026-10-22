"""Recovery controller tests: transactional files and realistic Docker metadata, no Docker/SSH."""
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import remote
import recovery
import test_remote


def hexid(value):
    return hashlib.sha256(value.encode()).hexdigest()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        test_remote.DeploymentTests.setUp(self)
        tools = remote.STACKS / 'tools'
        tools.mkdir(mode=0o700)
        (tools / 'stackctl.py').write_text('# fixed accepted operator\n')
        self.networks = {}
        for index, (project, services) in enumerate(recovery.SERVICES.items()):
            for kind in ('isolated', 'ingress'):
                number = 20 + index * 2 + (kind == 'ingress')
                name = project + '_' + kind
                self.networks[name] = {'Name': name, 'Id': hexid(name), 'Created': 'fixed-created',
                    'Driver': 'bridge', 'Scope': 'local', 'Internal': kind == 'isolated', 'EnableIPv6': False,
                    'Attachable': False, 'Ingress': False, 'ConfigOnly': False,
                    'Options': {'com.docker.network.enable_ipv4': 'true', 'com.docker.network.enable_ipv6': 'false'},
                    'Labels': {'com.docker.compose.project': project, 'com.docker.compose.network': kind,
                               'com.docker.compose.version': '5.0.2', 'com.docker.compose.config-hash': hexid('compose-' + name)},
                    'IPAM': {'Driver': 'default', 'Options': None,
                             'Config': [{'Subnet': f'172.{number}.0.0/16', 'Gateway': f'172.{number}.0.1'}]},
                    'Containers': {}}
            app = next((a for a, p in remote.PROJECTS.items() if p == project), None)
            for offset, service in enumerate(services, 2):
                name = project + '-' + service + '-1'
                item = self.operator.containers[name]
                item['Id'] = hexid(name)
                item['State']['StartedAt'] = 'restarted-at'
                spec = self.operator.spec(app)['services'][service] if app else {}
                env = {k: re.sub(r'\$\{[^}]+\}', 'synthetic-secret', v)
                       for k, v in spec.get('environment', {}).items()}
                if not app and service == 'web':
                    env = {'ENVIRONMENT': 'staging', 'REDIS_URL': 'redis://redis:6379/0',
                           'DATABASE_URL': 'postgresql+asyncpg://staging:synthetic@postgres:5432/dieselbridge_staging',
                           **{k: 'false' for k in ('WORKOS_AUTH_ENABLED', 'MOTIVE_ENABLED', 'SMS_TENANT_ROUTING_ENABLED',
                           'SMS_AUTOMATION_OUTBOX_ENABLED', 'SMS_RECOVERY_ENABLED', 'PROVIDER_OUTBOX_ENABLED')}}
                item['Config']['Env'] = [k + '=' + v for k, v in env.items()]
                if 'command' in spec:
                    item['Config']['Cmd'] = spec['command']
                if 'user' in spec:
                    item['Config']['User'] = spec['user']
                item['HostConfig'] = {'NetworkMode': project + ('_ingress' if service == 'gateway' else '_isolated'),
                    'PortBindings': {port: [{'HostIp': '127.0.0.1', 'HostPort': target}]
                                     for port, target in recovery.PORTS[project].items()} if service == 'gateway' else {},
                    'Privileged': False, 'CapAdd': None, 'Devices': [], 'DeviceRequests': None,
                    'PidMode': '', 'IpcMode': 'private', 'UTSMode': '', 'UsernsMode': '',
                    'ReadonlyRootfs': spec.get('read_only', False), 'CapDrop': spec.get('cap_drop', []),
                    'SecurityOpt': spec.get('security_opt', []), 'PidsLimit': spec.get('pids_limit', 0),
                    'NanoCpus': int(spec.get('cpus', 0) * 1_000_000_000),
                    'Tmpfs': {v.split(':', 1)[0]: v.partition(':')[2] for v in spec.get('tmpfs', [])},
                    'Memory': int(spec.get('mem_limit', '0m')[:-1]) * 1024 ** 2,
                    'RestartPolicy': {'Name': 'unless-stopped', 'MaximumRetryCount': 0},
                    'LogConfig': {'Type': 'json-file', 'Config': spec.get('logging', {}).get('options', {})}}
                if not app and service == 'gateway':
                    item['HostConfig'].update(ReadonlyRootfs=True, Tmpfs={'/var/cache/nginx': '', '/var/run': ''})
                mounts = spec.get('volumes', []) if app else {'postgres': ['postgres:/var/lib/postgresql/data'],
                    'redis': ['redis:/data'], 'gateway': ['./nginx.conf:/etc/nginx/nginx.conf:ro']}.get(service, [])
                item['Mounts'] = []
                for mount in mounts:
                    parts = mount.split(':')
                    value = {'Destination': parts[1], 'RW': len(parts) < 3 or parts[2] != 'ro'}
                    if parts[0].startswith('./'):
                        root = remote.STACKS / project if app else Path.home() / 'dieselbridge-staging/source/deploy/mac-staging'
                        value.update(Type='bind', Source=str(root / parts[0][2:]))
                    else:
                        value.update(Type='volume', Name=project + '_' + parts[0], Source='/var/lib/docker/volumes/' + project + '_' + parts[0] + '/_data')
                    item['Mounts'].append(value)
                item['NetworkSettings']['Ports'] = copy.deepcopy(item['HostConfig']['PortBindings'])
                item['NetworkSettings']['Networks'] = {}
                for kind in ('isolated', 'ingress') if service == 'gateway' else ('isolated',):
                    network = self.networks[project + '_' + kind]
                    number = network['IPAM']['Config'][0]['Subnet'].split('.')[1]
                    ip = f'172.{number}.0.{offset}'
                    endpoint = {'NetworkID': network['Id'], 'EndpointID': hexid(name + kind), 'IPAddress': ip,
                        'IPPrefixLen': 16, 'Gateway': '' if kind == 'isolated' else f'172.{number}.0.1',
                        'MacAddress': f'02:42:ac:{int(number):02x}:00:{offset:02x}', 'GlobalIPv6Address': '',
                        'GlobalIPv6PrefixLen': 0, 'IPv6Gateway': '', 'IPAMConfig': None, 'Links': None,
                        'DriverOpts': None, 'GwPriority': 0, 'Aliases': [name, service],
                        'DNSNames': [name, service, item['Id'][:12]]}
                    item['NetworkSettings']['Networks'][network['Name']] = endpoint
                    network['Containers'][item['Id']] = {'Name': name, 'EndpointID': endpoint['EndpointID'],
                         'MacAddress': endpoint['MacAddress'], 'IPv4Address': ip + '/16', 'IPv6Address': ''}
        original_docker = self.operator.docker
        original_compose = self.operator.compose
        def docker(args, **kw):
            if args[:2] == ['network', 'inspect']:
                return json.dumps([self.networks[n] for n in args[2:]]).encode()
            return original_docker(args, **kw)
        def compose(app, *args, **kw):
            if args[:3] in (('exec', '-T', 'redis'), ('exec', '-T', 'worker')):
                return b'0\n'
            return original_compose(app, *args, **kw)
        self.operator.docker, self.operator.compose = docker, compose
        state = self.remote.load()
        state['snapshot'] = remote.snapshot(self.operator)
        for item in state['snapshot']['containers'].values():
            item['started'], item['networks_sha256'] = 'before-docker-restart', '0' * 64
        # A real nested previous release must remain byte-equivalent after acceptance.
        state['apps']['tph']['previous'] = copy.deepcopy(state['apps']['tph']['current'])
        remote.atomic_json(self.remote.state_path, state)
        self.old_raw = self.remote.state_path.read_bytes()
        self.core = recovery.Recovery(remote, self.remote)

    def tearDown(self):
        test_remote.DeploymentTests.tearDown(self)

    def propose(self):
        return self.core.propose('20261022T192823Z')

    def approve(self, result, change=None, mode=0o400):
        path = remote.ROOT / 'private/recovery-proposals' / (result['proposal'] + '.json')
        raw = path.read_bytes()
        proposal = json.loads(raw)
        approval = {'version': 1, 'decision': 'approve_new_acceptance', 'proposal_sha256': remote.digest(raw),
            'observation': proposal['observation'], 'old_state_sha256': proposal['evidence']['old_state_sha256'],
            'snapshot_sha256': proposal['snapshot_sha256'], 'topology_sha256': proposal['topology_sha256'],
            'helpers_sha256': proposal['evidence']['helpers_sha256'], 'files_sha256': proposal['evidence']['files_sha256'],
            'container_ids': {n: v['id'] for n, v in proposal['evidence']['snapshot']['containers'].items()},
            'qa': {'reviewer': 'independent-qa', 'reference': 'review-qa-1', 'decision': 'GO'},
            'security': {'reviewer': 'independent-security', 'reference': 'review-security-1', 'decision': 'GO'},
            'checks': {key: True for key in recovery.REVIEW_CHECKS},
            'expires_at': (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()}
        if change:
            change(approval)
        path = self.core.directory('recovery-approvals') / (result['proposal'] + '.json')
        self.core.write_once(path, self.core.encoded(approval))
        path.chmod(mode)
        return remote.digest(path.read_bytes())

    def test_round_trip_archives_original_and_only_updates_snapshot(self):
        self.assertFalse(self.remote.status()['identity_matches'])
        result = self.propose()
        sha = self.approve(result)
        self.assertEqual(self.remote.state_path.read_bytes(), self.old_raw)
        done = self.core.commit(result['proposal'], sha)
        self.assertTrue(done['recovered'])
        after, before = self.remote.load(), json.loads(self.old_raw)
        self.assertEqual({k: v for k, v in before.items() if k != 'snapshot'},
                         {k: v for k, v in after.items() if k != 'snapshot'})
        directory = remote.ROOT / 'private/recoveries' / result['proposal']
        self.assertEqual((directory / 'state.before.json').read_bytes(), self.old_raw)
        self.assertTrue(self.remote.status()['identity_matches'])
        self.assertFalse(self.remote.status()['uncertain_recovery'])
        self.assertEqual(self.operator.up_calls, [])
        self.assertFalse(done['historical_normalized_topology_verified'])
        with self.assertRaisesRegex(remote.Refused, 'already_journaled'):
            self.core.commit(result['proposal'], sha)

    def test_staging_gateway_exact_source_project_mount_only(self):
        item = self.operator.containers['dieselbridge-staging-gateway-1']
        mount = item['Mounts'][0]
        expected = Path.home() / 'dieselbridge-staging/source/deploy/mac-staging/nginx.conf'
        self.assertEqual(mount['Source'], str(expected))
        # Exact native staging source layout is accepted without changing any runtime state.
        self.propose()
        for wrong in (Path.home() / 'dieselbridge-staging/nginx.conf',
                      expected.parent / 'other-nginx.conf', Path('/tmp/nginx.conf')):
            with self.subTest(path=str(wrong)):
                mount['Source'] = str(wrong)
                with self.assertRaisesRegex(remote.Refused, 'host_mount_refused'):
                    self.propose()
        mount['Source'] = str(expected)
        self.assertEqual(self.remote.state_path.read_bytes(), self.old_raw)
        self.assertEqual(self.operator.up_calls, [])

    def test_native_mongo_mount_order_is_canonical_without_losing_metadata(self):
        item = self.operator.containers['tph-local-test-mongo-1']
        # Preserve extra Docker mount metadata, including fields irrelevant to sorting.
        for mount in item['Mounts']:
            mount.update(Driver='local', Mode='rw', Propagation='', ArbitraryFutureMetadata={'retained': True})
        original = copy.deepcopy(item['Mounts'])
        first = self.core.observe()
        item['Mounts'].reverse()
        second = self.core.observe()
        self.assertEqual(first, second)
        output = first['topology']['runtime_profiles']['tph-local-test-mongo-1']['mounts']
        self.assertEqual(output, sorted(original, key=lambda v: (v['Destination'], v['Type'], remote.canonical(v))))
        self.assertEqual({remote.canonical(v) for v in output}, {remote.canonical(v) for v in original})
        # A proposal remains usable if Docker only changes the mounts array order.
        result = self.propose()
        sha = self.approve(result)
        item['Mounts'].reverse()
        self.assertTrue(self.core.commit(result['proposal'], sha)['recovered'])

    def test_native_mongo_mount_changes_and_duplicate_destinations_refused(self):
        item = self.operator.containers['tph-local-test-mongo-1']
        original = copy.deepcopy(item['Mounts'])
        changes = [lambda: item['Mounts'][0].update(Source='/foreign/data'),
                   lambda: item['Mounts'][0].update(RW=False),
                   lambda: item['Mounts'].append(copy.deepcopy(item['Mounts'][0])),
                   lambda: item['Mounts'].__setitem__(1, copy.deepcopy(item['Mounts'][0])),
                   lambda: item['Mounts'].__setitem__(1, {**item['Mounts'][0], 'Type': 'bind'})]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                item['Mounts'] = copy.deepcopy(original)
                change()
                with self.assertRaises(remote.Refused):
                    self.propose()
        item['Mounts'] = original
        self.assertEqual(self.remote.state_path.read_bytes(), self.old_raw)

    def test_identity_drift_refused(self):
        for field, value in [('id', '9' * 64), ('image', 'sha256:' + '9' * 64), ('config_sha256', '9' * 64), ('running', False)]:
            with self.subTest(field=field):
                state = json.loads(self.old_raw)
                state['snapshot']['containers']['tph-local-test-web-1'][field] = value
                remote.atomic_json(self.remote.state_path, state)
                with self.assertRaises(remote.Refused):
                    self.propose()
        self.assertEqual(self.operator.up_calls, [])

    def test_topology_and_runtime_negative_contracts(self):
        changes = [
            lambda: self.networks['tph-local-test_isolated'].update(Internal=False),
            lambda: self.networks['tph-local-test_isolated']['Containers'].update({'f' * 64: {}}),
            lambda: self.networks['tph-local-test_isolated']['Labels'].update({'foreign': 'true'}),
            lambda: self.operator.containers['tph-local-test-web-1']['NetworkSettings']['Networks']['tph-local-test_isolated']['Aliases'].append('production'),
            lambda: self.operator.containers['tph-local-test-web-1']['HostConfig'].update(Privileged=True),
            lambda: self.operator.containers['tph-local-test-web-1']['HostConfig'].update(PortBindings={'5050/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '5050'}]}),
            lambda: self.operator.containers['tph-local-test-web-1']['Mounts'].append({'Type': 'bind', 'Source': '/var/run/docker.sock', 'Destination': '/socket', 'RW': True}),
            lambda: self.operator.containers['tph-local-test-worker-1']['Config']['Env'].append('DISABLE_SCHEDULER=false'),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                old_containers, old_networks = copy.deepcopy(self.operator.containers), copy.deepcopy(self.networks)
                change()
                with self.assertRaises(remote.Refused):
                    self.propose()
                self.operator.containers, self.networks = old_containers, old_networks
        self.assertEqual(self.remote.state_path.read_bytes(), self.old_raw)

    def test_stale_proposal_started_or_hostconfig_refused(self):
        result = self.propose()
        sha = self.approve(result)
        self.operator.containers['tph-local-test-worker-1']['State']['StartedAt'] = 'another-restart'
        with self.assertRaisesRegex(remote.Refused, 'stale_proposal'):
            self.core.commit(result['proposal'], sha)
        self.assertEqual(self.remote.state_path.read_bytes(), self.old_raw)

    def test_helper_drift_refused(self):
        result = self.propose()
        sha = self.approve(result)
        (remote.STACKS / 'tools/stackctl.py').write_text('# changed\n')
        with self.assertRaisesRegex(remote.Refused, 'stale_proposal'):
            self.core.commit(result['proposal'], sha)

    def test_approval_binding_review_and_expiry_negatives(self):
        changes = [lambda a: a.update(snapshot_sha256='0' * 64), lambda a: a.update(old_state_sha256='0' * 64),
            lambda a: a['qa'].update(reviewer='hosting_contract'),
            lambda a: a['security'].update(reviewer='independent-qa'),
            lambda a: a['checks'].update(historical_topology_continuity_not_claimed=False),
            lambda a: a.update(expires_at='2020-01-01T00:00:00+00:00')]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                result = self.propose()
                sha = self.approve(result, change)
                with self.assertRaises(remote.Refused):
                    self.core.commit(result['proposal'], sha)
        result = self.propose()
        sha = self.approve(result, mode=0o600)
        with self.assertRaisesRegex(remote.Refused, 'immutable_artifact'):
            self.core.commit(result['proposal'], sha)

    def test_interrupted_before_state_write_keeps_journal_and_blocks_deploy(self):
        result = self.propose()
        sha = self.approve(result)
        with patch.object(remote, 'atomic_json', side_effect=OSError('private IO error')):
            with self.assertRaises(OSError):
                self.core.commit(result['proposal'], sha)
        self.assertEqual(self.remote.state_path.read_bytes(), self.old_raw)
        self.assertTrue(self.core.active.exists())
        with self.assertRaisesRegex(remote.Refused, 'uncertain_recovery'):
            self.remote.preflight(self.remote.load(), 'tph')
        with self.assertRaisesRegex(remote.Refused, 'already_journaled'):
            self.core.commit(result['proposal'], sha)

    def test_final_recheck_catches_race_without_accepting_snapshot(self):
        result = self.propose()
        sha = self.approve(result)
        original = self.core.observe
        calls = []
        def observe(**kw):
            calls.append(1)
            if len(calls) == 2:
                self.operator.containers['db-local-test-web-1']['State']['StartedAt'] = 'race'
            return original(**kw)
        with patch.object(self.core, 'observe', side_effect=observe):
            with self.assertRaisesRegex(remote.Refused, 'final_recheck_failed'):
                self.core.commit(result['proposal'], sha)
        self.assertTrue(self.core.active.exists())
        self.assertEqual(self.remote.state_path.read_bytes(), self.old_raw)

    def test_interrupted_after_state_write_keeps_archive_and_blocks_mutations(self):
        result = self.propose()
        sha = self.approve(result)
        original = self.core.write_once
        def write(path, raw):
            if path.name == 'state.after.json':
                raise OSError('simulated disk error')
            return original(path, raw)
        with patch.object(self.core, 'write_once', side_effect=write):
            with self.assertRaises(OSError):
                self.core.commit(result['proposal'], sha)
        self.assertTrue(self.core.active.exists())
        self.assertEqual((remote.ROOT / 'private/recoveries' / result['proposal'] / 'state.before.json').read_bytes(), self.old_raw)
        with self.assertRaisesRegex(remote.Refused, 'uncertain_recovery'):
            self.remote.preflight(self.remote.load(), 'tph')

    def test_pending_deployment_and_early_archive_failure_fail_closed(self):
        self.remote.active_path.write_text('{}')
        with self.assertRaisesRegex(remote.Refused, 'uncertain_operation'):
            self.propose()
        self.remote.active_path.unlink()
        result = self.propose()
        sha = self.approve(result)
        original = self.core.write_once
        def write(path, raw):
            if path.name == 'state.before.json':
                raise OSError('archive failed')
            return original(path, raw)
        with patch.object(self.core, 'write_once', side_effect=write), self.assertRaises(OSError):
            self.core.commit(result['proposal'], sha)
        self.assertTrue(self.core.active.exists())
        self.assertEqual(self.remote.state_path.read_bytes(), self.old_raw)
        with self.assertRaisesRegex(remote.Refused, 'uncertain_recovery'):
            self.remote.preflight(self.remote.load(), 'tph')

    def test_state_history_and_configuration_drift_invalidate_proposal(self):
        result = self.propose()
        sha = self.approve(result)
        state = self.remote.load()
        state['apps']['tph']['previous']['source'] = 'f' * 40
        remote.atomic_json(self.remote.state_path, state)
        with self.assertRaisesRegex(remote.Refused, 'stale_proposal'):
            self.core.commit(result['proposal'], sha)
        self.remote.state_path.write_bytes(self.old_raw)
        path = remote.STACKS / 'tph-local-test/nginx.conf'
        path.write_text('changed')
        with self.assertRaisesRegex(remote.Refused, 'configuration_drift'):
            self.core.commit(result['proposal'], sha)

    def test_approval_hash_and_hardlink_refused(self):
        result = self.propose()
        sha = self.approve(result)
        with self.assertRaisesRegex(remote.Refused, 'approval_hash_mismatch'):
            self.core.commit(result['proposal'], '0' * 64)
        path = remote.ROOT / 'private/recovery-approvals' / (result['proposal'] + '.json')
        os.link(path, path.with_suffix('.linked'))
        with self.assertRaisesRegex(remote.Refused, 'immutable_artifact'):
            self.core.commit(result['proposal'], sha)

    def test_runtime_provider_database_and_namespace_contract_even_with_accepted_config_hash(self):
        for key, value in [('DISABLE_SCHEDULER', 'false'), ('MONGO_URI_DEV', 'mongodb://secret@production.invalid/live')]:
            with self.subTest(key=key):
                item = self.operator.containers['tph-local-test-worker-1']
                old = copy.deepcopy(item['Config'])
                item['Config']['Env'] = [v for v in old['Env'] if not v.startswith(key + '=')] + [key + '=' + value]
                # Prove current contract is validated, not merely the historical opaque Config hash.
                state = self.remote.load()
                state['snapshot']['containers']['tph-local-test-worker-1']['config_sha256'] = remote.digest(remote.canonical(item['Config']))
                remote.atomic_json(self.remote.state_path, state)
                with self.assertRaisesRegex(remote.Refused, 'runtime_(environment|database)'):
                    self.propose()
                item['Config'] = old
                self.remote.state_path.write_bytes(self.old_raw)
        item = self.operator.containers['db-local-test-worker-1']
        item['HostConfig']['CgroupnsMode'] = 'host'
        with self.assertRaisesRegex(remote.Refused, 'runtime_privilege'):
            self.propose()

    def test_queue_schema_source_and_baseline_drift(self):
        for method in ('queue', 'schema', 'source', 'baseline'):
            with self.subTest(method=method):
                if method == 'queue':
                    original = self.operator.compose
                    def compose(app, *args, **kw):
                        if args[:3] == ('exec', '-T', 'redis'):
                            return b'1\n'
                        return original(app, *args, **kw)
                    target = patch.object(self.operator, 'compose', side_effect=compose)
                elif method == 'schema':
                    target = patch.object(remote, 'database_revision', return_value='188')
                elif method == 'source':
                    target = patch.object(remote, 'runtime', return_value={'ready': True, 'source': 'e' * 40})
                else:
                    target = patch.object(remote, 'BASELINE', remote.BASELINE.with_name('different.json'))
                    remote.BASELINE.with_name('different.json').write_text('changed')
                with target, self.assertRaises((remote.Refused, json.JSONDecodeError)):
                    self.propose()


if __name__ == '__main__':
    unittest.main()
