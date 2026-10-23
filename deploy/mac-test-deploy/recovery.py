"""Explicit new acceptance after Docker restart; never changes Docker or app data.

Historical NetworkSettings are opaque hashes. This tool makes no historical
normalized-topology claim. Independently reviewed current topology becomes a new
acceptance boundary. Approval is an external artifact, never generated here.
"""
import copy
import datetime
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import uuid
from urllib.parse import urlsplit

HEX = re.compile(r'[0-9a-f]{64}\Z')
TOKEN = re.compile(r'[0-9a-f]{32}\Z')
SERVICES = {'db-local-test': ('gateway', 'postgres', 'redis', 'web', 'worker'),
            'tph-local-test': ('gateway', 'identity', 'mongo', 'web', 'worker'),
            'dieselbridge-staging': ('gateway', 'postgres', 'redis', 'web')}
PORTS = {'db-local-test': {'8080/tcp': '18200', '8081/tcp': '18210'},
         'tph-local-test': {'8080/tcp': '18201', '8081/tcp': '18211'},
         'dieselbridge-staging': {'8080/tcp': '18080'}}
REVIEW_CHECKS = ('current_topology_against_frozen_contract', 'runtime_security_and_mounts',
                 'providers_schedulers_and_database_bindings', 'read_only_schema_queues_and_health',
                 'rollback_images_available', 'historical_topology_continuity_not_claimed',
                 'new_observation_baseline_untouched')


def identity(value):
    return {name: {k: v for k, v in item.items() if k != 'health'}
            for name, item in value['containers'].items()}


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Recovery:
    def __init__(self, api, controller):
        self.api, self.controller = api, controller
        self.private = api.ROOT / 'private'
        self.active = self.private / 'recovery-active.json'

    def require(self, condition, code):
        self.api.check(condition, 'recovery_' + code)

    def immutable_read(self, path):
        self.api.safe_path(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            self.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                         and stat.S_IMODE(info.st_mode) == 0o400 and info.st_size <= 2_000_000,
                         'immutable_artifact_required')
            raw = b''
            while True:
                block = os.read(fd, 65536)
                if not block:
                    break
                raw += block
            after = os.fstat(fd)
            self.require(all(getattr(info, key) == getattr(after, key) for key in
                             ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid', 'st_nlink')),
                         'artifact_changed_during_read')
            return raw
        finally:
            os.close(fd)

    def directory(self, name):
        path = self.private / name
        self.api.safe_path(path)
        path.mkdir(mode=0o700, exist_ok=True)
        return path

    def write_once(self, path, raw):
        self.api.safe_path(path)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, 'wb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        fsync_directory(path.parent)

    def encoded(self, value):
        return self.api.canonical(value) + b'\n'

    def helpers(self):
        paths = [Path(__file__).resolve(), Path(self.api.__file__).resolve(),
                 self.api.STACKS / 'tools/stackctl.py']
        return {path.name: self.api.digest(path.read_bytes()) for path in paths}

    def containers(self):
        names = [project + '-' + service + '-1' for project, services in SERVICES.items() for service in services]
        items = json.loads(self.controller.operator.docker(['inspect', *names], timeout=30,
                           log='recovery-fixed-container-inspection'))
        result = {item['Name'].lstrip('/'): item for item in items}
        self.require(len(items) == 14 and set(result) == set(names), 'exact_membership_required')
        self.require(len({v['Id'] for v in items}) == 14
                     and all(HEX.fullmatch(v['Id']) for v in items), 'immutable_container_ids_required')
        return result

    def topology(self, items, specs):
        names = [project + '_' + kind for project in SERVICES for kind in ('isolated', 'ingress')]
        networks = json.loads(self.controller.operator.docker(['network', 'inspect', *names], timeout=30,
                              log='recovery-network-topology-inspection'))
        self.require(len(networks) == 6 and {n['Name'] for n in networks} == set(names), 'six_networks_required')
        result = {}
        for network in networks:
            name = network['Name']
            project, kind = name.rsplit('_', 1)
            expected = {items[project + '-' + service + '-1']['Id'] for service in SERVICES[project]
                        if kind == 'isolated' or service == 'gateway'}
            labels = network.get('Labels') or {}
            self.require(set(labels) == {'com.docker.compose.project', 'com.docker.compose.network',
                                         'com.docker.compose.version', 'com.docker.compose.config-hash'}
                         and labels['com.docker.compose.project'] == project
                         and labels['com.docker.compose.network'] == kind
                         and bool(HEX.fullmatch(labels['com.docker.compose.config-hash']))
                         and bool(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', labels['com.docker.compose.version'])),
                         'network_labels_refused')
            self.require(bool(HEX.fullmatch(network['Id'])), 'network_id_refused')
            self.require(network['Driver'] == 'bridge' and network['Scope'] == 'local'
                         and network['Internal'] is (kind == 'isolated')
                         and not network['EnableIPv6'] and not network['Attachable'] and not network['Ingress']
                         and network.get('ConfigOnly', False) is False
                         and network.get('Options') == {'com.docker.network.enable_ipv4': 'true',
                                                      'com.docker.network.enable_ipv6': 'false'}
                         and set(network['Containers']) == expected, 'network_boundary_refused')
            ipam = network['IPAM']
            self.require(ipam['Driver'] == 'default' and not ipam.get('Options') and len(ipam['Config']) == 1,
                         'network_ipam_refused')
            config = ipam['Config'][0]
            subnet = ipaddress.ip_network(config['Subnet'])
            self.require(subnet.version == 4 and subnet.is_private and subnet.prefixlen == 16
                         and set(config) == {'Subnet', 'Gateway'}
                         and ipaddress.ip_address(config['Gateway']) in subnet, 'network_subnet_refused')
            for container_id, member in network['Containers'].items():
                item = next(v for v in items.values() if v['Id'] == container_id)
                container_name = item['Name'].lstrip('/')
                service = container_name[len(project) + 1:-2]
                endpoint = item['NetworkSettings']['Networks'][name]
                self.require(member['Name'] == container_name and member['EndpointID'] == endpoint['EndpointID']
                             and bool(HEX.fullmatch(endpoint['EndpointID'])) and endpoint['NetworkID'] == network['Id']
                             and member['MacAddress'] == endpoint['MacAddress']
                             and member['IPv4Address'] == endpoint['IPAddress'] + '/16'
                             and ipaddress.ip_address(endpoint['IPAddress']) in subnet
                             and member['IPv6Address'] == '' and endpoint['IPPrefixLen'] == 16
                             and endpoint['Gateway'] == ('' if kind == 'isolated' else config['Gateway'])
                             and endpoint['GlobalIPv6Address'] == '' and endpoint['IPv6Gateway'] == ''
                             and endpoint['GlobalIPv6PrefixLen'] == 0
                             and not endpoint.get('IPAMConfig') and not endpoint.get('Links')
                             and not endpoint.get('DriverOpts') and endpoint.get('GwPriority', 0) == 0
                             and set(endpoint['Aliases']) == {container_name, service}
                             and len(endpoint['Aliases']) == 2
                             and set(endpoint['DNSNames']) == {container_name, service, container_id[:12]}
                             and len(endpoint['DNSNames']) == 3, 'endpoint_contract_refused')
            result[name] = network
        subnets = [ipaddress.ip_network(n['IPAM']['Config'][0]['Subnet']) for n in networks]
        self.require(all(not a.overlaps(b) for i, a in enumerate(subnets) for b in subnets[i + 1:]),
                     'overlapping_networks_refused')
        profiles = {}
        for project, services in SERVICES.items():
            for service in services:
                name = project + '-' + service + '-1'
                item = items[name]
                host = item['HostConfig']
                attached = {project + '_isolated'} | ({project + '_ingress'} if service == 'gateway' else set())
                self.require(set(item['NetworkSettings']['Networks']) == attached, 'extra_attachment_refused')
                expected_ports = {port: [{'HostIp': '127.0.0.1', 'HostPort': target}]
                                  for port, target in PORTS[project].items()} if service == 'gateway' else {}
                self.require((host.get('PortBindings') or {}) == expected_ports
                             and host['NetworkMode'] == project + ('_ingress' if service == 'gateway' else '_isolated')
                             and not host.get('PublishAllPorts')
                             and {p: value for p, value in (item['NetworkSettings'].get('Ports') or {}).items()
                                  if value is not None} == expected_ports, 'runtime_ports_refused')
                self.require(not host.get('Privileged') and not host.get('CapAdd') and not host.get('Devices')
                             and not host.get('DeviceRequests') and not host.get('VolumesFrom')
                             and not host.get('Links') and not host.get('ExtraHosts') and not host.get('Sysctls')
                             and not host.get('Dns') and not host.get('DnsSearch') and not host.get('DnsOptions')
                             and not host.get('PidMode') and host.get('IpcMode') in ('', 'private')
                             and not host.get('UTSMode') and not host.get('UsernsMode')
                             and host.get('CgroupnsMode', 'private') == 'private', 'runtime_privilege_refused')
                if project != 'dieselbridge-staging':
                    spec = specs[project]['services'][service]
                    self.require(host.get('ReadonlyRootfs') is spec.get('read_only', False)
                                 and sorted(host.get('CapDrop') or []) == sorted(spec.get('cap_drop', []))
                                 and sorted(host.get('SecurityOpt') or []) == sorted(spec.get('security_opt', []))
                                 and host.get('PidsLimit') == spec['pids_limit']
                                 and host.get('NanoCpus') == int(spec['cpus'] * 1_000_000_000),
                                 'runtime_security_profile_refused')
                    expected_tmpfs = {v.split(':', 1)[0] for v in spec.get('tmpfs', [])}
                    self.require(set(host.get('Tmpfs') or {}) == expected_tmpfs, 'tmpfs_targets_refused')
                    limit = re.fullmatch(r'([0-9]+)([mg])', spec['mem_limit'])
                    expected_memory = int(limit[1]) * (1024 ** (2 if limit[2] == 'm' else 3))
                    self.require(host.get('Memory') == expected_memory
                                 and host.get('RestartPolicy') == {'Name': 'unless-stopped', 'MaximumRetryCount': 0}
                                 and host.get('LogConfig') == {'Type': spec['logging']['driver'], 'Config': spec['logging']['options']},
                                 'runtime_resource_contract_refused')
                    expected_mounts = spec.get('volumes', [])
                else:
                    expected_mounts = ({'postgres': ['postgres:/var/lib/postgresql/data'], 'redis': ['redis:/data'],
                                        'gateway': ['./nginx.conf:/etc/nginx/nginx.conf:ro']}).get(service, [])
                env = dict(part.split('=', 1) for part in item['Config'].get('Env', []))
                if project != 'dieselbridge-staging':
                    for key, expected_value in spec.get('environment', {}).items():
                        actual_value = env.get(key)
                        self.require(isinstance(actual_value, str), 'runtime_environment_missing')
                        if '${' not in expected_value:
                            self.require(actual_value == expected_value, 'runtime_environment_binding_refused')
                        elif key in ('DATABASE_URL', 'MONGO_URI_DEV'):
                            expected_url = urlsplit(re.sub(r'\$\{[^}]+\}', 'placeholder', expected_value))
                            actual_url = urlsplit(actual_value)
                            self.require((actual_url.scheme, actual_url.hostname, actual_url.port, actual_url.path, actual_url.query)
                                         == (expected_url.scheme, expected_url.hostname, expected_url.port, expected_url.path, expected_url.query),
                                         'runtime_database_binding_refused')
                    if 'command' in spec:
                        self.require(item['Config'].get('Cmd') == spec['command'], 'runtime_command_refused')
                    if 'user' in spec:
                        self.require(item['Config'].get('User') == spec['user'], 'runtime_user_refused')
                elif service == 'web':
                    flags = ('WORKOS_AUTH_ENABLED', 'MOTIVE_ENABLED', 'SMS_TENANT_ROUTING_ENABLED',
                             'SMS_AUTOMATION_OUTBOX_ENABLED', 'SMS_RECOVERY_ENABLED', 'PROVIDER_OUTBOX_ENABLED')
                    target = urlsplit(env.get('DATABASE_URL', ''))
                    self.require(env.get('ENVIRONMENT') == 'staging' and all(env.get(k) == 'false' for k in flags)
                                 and env.get('REDIS_URL') == 'redis://redis:6379/0'
                                 and target.hostname == 'postgres' and target.path == '/dieselbridge_staging',
                                 'original_staging_profile_refused')
                if project == 'dieselbridge-staging':
                    self.require(set(host.get('Tmpfs') or {}) == ({'/var/cache/nginx', '/var/run'} if service == 'gateway' else set())
                                 and host.get('ReadonlyRootfs') is (service == 'gateway'), 'original_rootfs_contract_refused')
                mounts = item.get('Mounts', [])
                self.require(len(mounts) == len(expected_mounts), 'unexpected_mount_refused')
                # Mount order is not identity; duplicate destinations are ambiguous even
                # when their types differ. Validate before canonicalizing all metadata.
                self.require(len({mount['Destination'] for mount in mounts}) == len(mounts),
                             'duplicate_mount_destination_refused')
                for mount in mounts:
                    matches = [v for v in expected_mounts if v.split(':')[1] == mount['Destination']]
                    self.require(len(matches) == 1, 'unexpected_mount_target_refused')
                    parts = matches[0].split(':')
                    self.require(mount['RW'] is (len(parts) < 3 or parts[2] != 'ro'), 'mount_mode_refused')
                    if parts[0].startswith('./'):
                        # Original staging runs its frozen Compose source project here;
                        # do not infer a mount root from arbitrary Docker labels.
                        root = (self.api.STACKS / project if project != 'dieselbridge-staging'
                                else Path.home() / 'dieselbridge-staging/source/deploy/mac-staging')
                        self.require(mount['Type'] == 'bind' and mount['Source'] == str(root / parts[0][2:]),
                                     'host_mount_refused')
                    else:
                        self.require(mount['Type'] == 'volume' and mount['Name'] == project + '_' + parts[0]
                                     and mount['Source'] == '/var/lib/docker/volumes/' + project + '_' + parts[0] + '/_data',
                                     'volume_mount_refused')
                # Full host settings and mount metadata are review-bound. No env values are exported.
                profiles[name] = {'host_config_sha256': self.api.digest(self.api.canonical(host)),
                                  'mounts': sorted(mounts, key=lambda mount: (mount['Destination'], mount['Type'], self.api.canonical(mount))),
                                  'ports': item['NetworkSettings'].get('Ports') or {}}
        return {'networks': result, 'runtime_profiles': profiles}

    def observe(self, owned_marker=None):
        self.require(not self.controller.active_path.exists(), 'uncertain_operation')
        if owned_marker is None:
            self.require(not self.active.exists(), 'uncertain_operation')
        else:
            self.require(json.loads(self.immutable_read(self.active)) == {'id': owned_marker, 'phase': 'prepared'},
                         'journal_changed')
        raw = self.controller.state_path.read_bytes()
        state = json.loads(raw)
        self.require(state.get('version') == 1 and state.get('owner') == self.api.OWNER, 'unknown_state')
        files = self.api.current_files()
        self.require(self.api.file_hashes(files) == state['files_sha256'], 'configuration_drift')
        self.api.initial_safety(files)
        specs = {}
        for app, project in self.api.PROJECTS.items():
            spec = json.loads(files[project + '/compose.json'])
            self.require(self.api.normalize(spec, app) == state['approved_specs'][app], 'approved_contract_drift')
            specs[project] = spec
        observed = self.api.snapshot(self.controller.operator)
        self.api.healthy(observed)
        old = state['snapshot']
        self.require(old['baseline_sha256'] == observed['baseline_sha256'], 'baseline_drift')
        self.require(set(old['containers']) == set(observed['containers']), 'accepted_membership_drift')
        for name, accepted in old['containers'].items():
            self.require({k: v for k, v in accepted.items() if k not in ('health', 'started', 'networks_sha256')}
                         == {k: v for k, v in observed['containers'][name].items()
                             if k not in ('health', 'started', 'networks_sha256')}, 'unapproved_identity_drift')
        items = self.containers()
        # Cross-bind the separately inspected runtime/endpoint data to this snapshot.
        for name, item in items.items():
            snap = observed['containers'][name]
            self.require(item['Id'] == snap['id'] and item['Image'] == snap['image']
                         and item['State']['StartedAt'] == snap['started']
                         and self.api.digest(self.api.canonical(item['Config'])) == snap['config_sha256']
                         and self.api.digest(self.api.canonical(item['NetworkSettings']['Networks'])) == snap['networks_sha256'],
                         'inspection_race')
        topology = self.topology(items, specs)
        live = {}
        for app in self.api.PROJECTS:
            live[app] = self.api.runtime(self.controller.operator, app)
            self.require(live[app]['source'] == state['apps'][app]['current']['source'], 'source_drift')
        revision = self.api.database_revision(self.controller.operator)
        self.require(revision == state['database']['revision'], 'schema_drift')
        images = sorted({entry['image'] for app in state['apps'].values()
                         for entry in (app['current'], app.get('previous')) if entry})
        for image in images:
            self.api.inspect_image(self.controller.operator, image, legacy=True)
        # Queue observations are counts only, never drain/claim/execute an operation.
        queues = {}
        for db in ('13', '14'):
            value = self.controller.operator.compose('dieselbridge', 'exec', '-T', 'redis', 'redis-cli', '-n', db,
                    'LLEN', 'db-local-test', timeout=15, log='recovery-read-only-queue-count').decode().strip()
            self.require(value.isdigit() and int(value) == 0, 'nonempty_worker_queue')
            queues['redis' + db] = int(value)
        mongo_script = "const m=require('mongoose');m.connect(process.env.MONGO_URI_DEV).then(async()=>{const n=await m.connection.db.collection('blogresearchjobs').countDocuments({status:{$in:['queued','running']}});console.log(n);await m.disconnect()}).catch(()=>process.exit(1))"
        value = self.controller.operator.compose('tph', 'exec', '-T', 'worker', 'node', '-e', mongo_script,
                    timeout=20, log='recovery-read-only-mongo-queue-count').decode().strip()
        self.require(value.isdigit() and int(value) == 0, 'nonempty_mongo_worker_queue')
        queues['mongo_blog_pending'] = int(value)
        self.require(self.controller.state_path.read_bytes() == raw
                     and self.api.file_hashes(self.api.current_files()) == state['files_sha256']
                     and self.api.snapshot(self.controller.operator) == observed, 'late_inspection_race')
        self.require(self.topology(self.containers(), specs) == topology, 'late_topology_race')
        return {'old_state_sha256': self.api.digest(raw), 'files_sha256': self.api.file_hashes(files),
                'helpers_sha256': self.helpers(), 'snapshot': observed, 'topology': topology,
                'runtime': live, 'database_revision': revision, 'queues': queues, 'rollback_images': images}

    def propose(self, observation):
        self.require(bool(re.fullmatch(r'[0-9]{8}T[0-9]{6}Z', observation or '')), 'observation_required')
        value = {'version': 1, 'kind': 'explicit_new_acceptance', 'id': uuid.uuid4().hex,
                 'at': self.api.stamp(), 'observation': observation,
                 'historical_normalized_topology_verified': False, 'evidence': self.observe()}
        value['snapshot_sha256'] = self.api.digest(self.api.canonical(value['evidence']['snapshot']))
        value['topology_sha256'] = self.api.digest(self.api.canonical(value['evidence']['topology']))
        path = self.directory('recovery-proposals') / (value['id'] + '.json')
        raw = self.encoded(value)
        self.write_once(path, raw)
        return {'proposal': value['id'], 'proposal_sha256': self.api.digest(raw),
                'snapshot_sha256': value['snapshot_sha256'], 'topology_sha256': value['topology_sha256'],
                'historical_normalized_topology_verified': False, 'applied': False}

    def commit(self, token, approval_sha):
        self.require(bool(TOKEN.fullmatch(token or '')) and bool(HEX.fullmatch(approval_sha or '')), 'approval_identity_required')
        proposal_raw = self.immutable_read(self.directory('recovery-proposals') / (token + '.json'))
        proposal = json.loads(proposal_raw)
        approval_raw = self.immutable_read(self.directory('recovery-approvals') / (token + '.json'))
        approval = json.loads(approval_raw)
        self.require(proposal.get('version') == 1 and proposal.get('id') == token
                     and proposal.get('kind') == 'explicit_new_acceptance'
                     and proposal.get('historical_normalized_topology_verified') is False
                     and proposal['snapshot_sha256'] == self.api.digest(self.api.canonical(proposal['evidence']['snapshot']))
                     and proposal['topology_sha256'] == self.api.digest(self.api.canonical(proposal['evidence']['topology'])),
                     'proposal_contract_refused')
        self.require(self.api.digest(approval_raw) == approval_sha, 'approval_hash_mismatch')
        self.require(approval.get('version') == 1 and approval.get('decision') == 'approve_new_acceptance'
                     and approval.get('proposal_sha256') == self.api.digest(proposal_raw)
                     and approval.get('observation') == proposal['observation']
                     and approval.get('old_state_sha256') == proposal['evidence']['old_state_sha256']
                     and approval.get('snapshot_sha256') == proposal['snapshot_sha256']
                     and approval.get('topology_sha256') == proposal['topology_sha256']
                     and approval.get('helpers_sha256') == proposal['evidence']['helpers_sha256']
                     and approval.get('files_sha256') == proposal['evidence']['files_sha256']
                     and approval.get('container_ids') == {n: v['id'] for n, v in proposal['evidence']['snapshot']['containers'].items()},
                     'independent_approval_binding_required')
        reviewers = [approval.get(role, {}) for role in ('qa', 'security')]
        self.require(all(isinstance(r.get('reviewer'), str) and r['reviewer'].strip()
                         and r['reviewer'] != 'hosting_contract' and r.get('reference')
                         and r.get('decision') == 'GO' for r in reviewers)
                     and reviewers[0]['reviewer'] != reviewers[1]['reviewer']
                     and approval.get('checks') == {key: True for key in REVIEW_CHECKS}, 'independent_reviews_required')
        expires = datetime.datetime.fromisoformat(approval['expires_at'])
        now = datetime.datetime.now(datetime.timezone.utc)
        self.require(expires.tzinfo is not None and now < expires <= now + datetime.timedelta(hours=24), 'approval_expired')
        directory = self.directory('recoveries') / token
        self.require(not directory.exists(), 'already_journaled_inspect_receipt')
        self.require(self.observe() == proposal['evidence'], 'stale_proposal')
        old_raw = self.controller.state_path.read_bytes()
        old = json.loads(old_raw)
        new = copy.deepcopy(old)
        new['snapshot'] = proposal['evidence']['snapshot']
        self.require({k: v for k, v in new.items() if k != 'snapshot'}
                     == {k: v for k, v in old.items() if k != 'snapshot'}, 'non_snapshot_state_changed')
        # Marker precedes directory/archive writes: even an early I/O interruption blocks deployment.
        self.write_once(self.active, self.encoded({'id': token, 'phase': 'prepared'}))
        directory.mkdir(mode=0o700)
        fsync_directory(directory.parent)
        self.write_once(directory / 'state.before.json', old_raw)
        self.write_once(directory / 'proposal.json', proposal_raw)
        self.write_once(directory / 'approval.json', approval_raw)
        planned_raw = json.dumps(new, sort_keys=True, indent=2).encode() + b'\n'
        self.write_once(directory / 'state.after.planned.json', planned_raw)
        receipt = {'version': 1, 'id': token, 'at': self.api.stamp(), 'approval_sha256': approval_sha,
                   'before_sha256': self.api.digest(old_raw), 'planned_after_sha256': self.api.digest(planned_raw),
                   'non_snapshot_sha256': self.api.digest(self.api.canonical({k: v for k, v in old.items() if k != 'snapshot'})),
                   'snapshot_sha256': proposal['snapshot_sha256'],
                   'observation': proposal['observation'], 'historical_normalized_topology_verified': False}
        self.write_once(directory / 'prepared.json', self.encoded(receipt))
        # Leave the durable marker in place throughout the final read-only recheck.
        fresh = self.observe(owned_marker=token)
        self.require(fresh == proposal['evidence'] and self.immutable_read(directory / 'approval.json') == approval_raw
                     and self.immutable_read(self.directory('recovery-approvals') / (token + '.json')) == approval_raw,
                     'final_recheck_failed')
        self.api.atomic_json(self.controller.state_path, new)
        fsync_directory(self.private)
        self.require(self.controller.state_path.read_bytes() == planned_raw, 'state_write_uncertain')
        self.write_once(directory / 'state.after.json', self.controller.state_path.read_bytes())
        self.write_once(directory / 'completed.json', self.encoded({**receipt, 'after_sha256': self.api.digest(self.controller.state_path.read_bytes())}))
        self.active.rename(directory / 'closed-active.json')
        fsync_directory(self.private)
        fsync_directory(directory)
        return {'recovered': True, 'recovery': token, 'historical_normalized_topology_verified': False,
                'containers_restarted': 0, 'state_fields_updated': ['snapshot']}

