"""One-shot recovery of accepted, stopped synthetic rehearsal containers only."""
import argparse
import copy
from contextlib import closing
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path.home() / 'mac-hosting/tph-backup-rehearsal-v3'
OBSERVATION = Path.home() / 'dieselbridge-staging/private/observations/20261022T192823Z/soak-baseline.json'
OBSERVATION_SHA = '0002ccdd4d0b797e4a79543c1be310cd7a292d8f23b8ecba786031dec16ed328'
SERVICES = ('mongo', 'railway-simulation', 'mac-backup', 'router')
ORDER = ('mongo', 'railway-simulation', 'router')
D = ['/Applications/Docker.app/Contents/Resources/bin/docker', '--context', 'desktop-linux']


def check(value, reason):
    if not value:
        raise RuntimeError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    check(path.resolve() == path and not path.is_symlink(), 'Unsafe file path')
    return json.loads(path.read_text())


def docker(*args):
    result = subprocess.run([*D, *args], capture_output=True, timeout=35)
    check(result.returncode == 0, 'Docker operation failed; no automatic retry')
    return result.stdout


def load_operator():
    manifest = read_json(ROOT / 'private/approved-manifest.json')
    for name in ('tools/operator.py', 'tools/configure.py'):
        path = ROOT / name
        check(path.resolve() == path and digest(path.read_bytes()) == manifest['files'][name], 'Sealed operator changed')
    sys.path.insert(0, str(ROOT / 'tools'))
    spec = importlib.util.spec_from_file_location('accepted_backup_operator', ROOT / 'tools/operator.py')
    operator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(operator)
    operator.safe()
    return operator


def database_snapshot():
    """No Control/FakeProvider constructors: neither schema nor state is written."""
    snapshots = {}
    for name in ('control', 'provider'):
        path = ROOT / 'private/state' / (name + '.sqlite3')
        check(path.is_file() and path.resolve() == path and path.stat().st_nlink == 1, 'Unsafe state file')
        with closing(sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA query_only=ON')
            check(connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'SQLite integrity failed')
            tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            snapshots[name] = {table: sorted([dict(r) for r in connection.execute('SELECT * FROM "' + table.replace('"', '""') + '"')], key=lambda r: canonical(r)) for table in tables}
    control, provider = snapshots['control'], snapshots['provider']
    check(set(control) == {'authority', 'admissions', 'operations', 'transitions'} and set(provider) == {'effects'}, 'Unexpected state schema')
    check(len(control['authority']) == 1, 'Authority missing')
    state = control['authority'][0]
    check(state['site'] == 'railway-simulation' and state['epoch'] == 5 and state['phase'] == 'active' and state['watermark'] == 8, 'Owner/epoch/watermark changed')
    outcomes = lambda rows: {value: sum(r['outcome'] == value for r in rows) for value in {r['outcome'] for r in rows}}
    check(outcomes(control['admissions']) == {'accepted': 3, 'rejected': 1}, 'Admission state changed or unsettled')
    check(outcomes(control['operations']) == {'accepted': 5} and len(provider['effects']) == 5, 'Effects changed or unsettled')
    operations = {r['operation_id']: r for r in control['operations']}
    for effect in provider['effects']:
        operation = operations.get(effect['operation_id'])
        check(operation and all(effect[k] == operation[k] for k in ('scope', 'kind', 'business_id', 'payload_sha256')) and effect['receipt'] == operation['provider_receipt'], 'Fake provider receipt mismatch')
    return {'logical_sha256': digest(canonical(snapshots)), 'site': state['site'], 'epoch': state['epoch'], 'watermark': state['watermark'], 'instance_id': state['instance_id'], 'authority_sha256': digest(state['authority_id'].encode()), 'accepted_admissions': 3, 'rejected_admissions': 1, 'accepted_fake_effects': 5}


def protected_snapshot():
    check(digest(OBSERVATION.read_bytes()) == OBSERVATION_SHA, 'Observation baseline changed')
    baseline = read_json(OBSERVATION)
    raw = subprocess.check_output(['/opt/homebrew/bin/python3', str(Path.home() / 'mac-hosting/test-deploy/remote.py'), 'status'], timeout=40)
    status = json.loads(raw)
    # Consume the existing controller gate, including its reviewed recovery gate.
    check(status['configuration_matches'] and status['baseline_matches'] and status.get('identity_matches') is True and status.get('uncertain_recovery') is False and not status['uncertain_operation'], 'Controller recovery not accepted or protected infrastructure drift')
    containers = status['snapshot']['containers']
    check(len(containers) == 14, 'Expected fourteen protected containers')
    names = list(baseline['container_started'])
    check(len(names) == 4, 'Observation scope changed')
    for name in names:
        check(containers[name]['running'] and containers[name]['started'] == baseline['container_started'][name], 'New observation container changed')
    check(all(c['running'] and not c['oom'] and c['health'] in (None, 'healthy') for c in containers.values()), 'Protected container unhealthy')
    return status['snapshot']


def canonical_mounts(mounts):
    check(isinstance(mounts, list) and all(isinstance(m, dict) and
          isinstance(m.get('Destination'), str) and m['Destination'].startswith('/') and
          m.get('Type') in ('volume', 'bind', 'tmpfs') for m in mounts), 'Malformed mount metadata')
    check(len({m['Destination'] for m in mounts}) == len(mounts), 'Duplicate mount destination')
    # Retain every metadata field, including Source, RW, Driver and Propagation.
    # Only Docker's semantically unordered list ordering is canonicalized.
    return sorted(mounts, key=lambda m: (m['Destination'], m['Type']))


def container_snapshot(operator):
    result = {}
    network_name = operator.PROJECT + '_isolated'
    network = json.loads(docker('network', 'inspect', network_name))[0]
    check(network['Internal'] is True and network.get('Labels', {}).get('com.docker.compose.project') == operator.PROJECT, 'Network isolation changed')
    for service in SERVICES:
        item = operator.inspect(service)  # accepted full CID/image/Config hash
        host = item['HostConfig']
        check(set(item['NetworkSettings']['Networks']) == {network_name} and host['NetworkMode'] == network_name, 'Unexpected network attachment')
        check(not host['Privileged'] and not host.get('PublishAllPorts') and host['CapDrop'] == ['ALL'] and 'no-new-privileges:true' in host['SecurityOpt'], 'Sandbox controls changed')
        check(host['RestartPolicy']['Name'] == 'no' and host['PidsLimit'] == 128 and host['NanoCpus'] == 500000000, 'Resource/restart policy changed')
        check(host['Memory'] == (192 if service == 'router' else 512) * 1024 * 1024, 'Memory limit changed')
        check(host['ReadonlyRootfs'] == (service != 'mongo'), 'Filesystem boundary changed')
        bindings = host.get('PortBindings') or {}
        check(bindings == ({'18310/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '18310'}]} if service == 'router' else {}), 'Unexpected published port')
        mounts = canonical_mounts(item['Mounts'])
        expected_mounts = {'/data/db', '/data/configdb'} if service == 'mongo' else {'/state'} if service == 'router' else set()
        check({m['Destination'] for m in mounts if m['Type'] != 'tmpfs'} == expected_mounts, 'Unexpected persistent mount')
        for mount in mounts:
            if mount['Type'] == 'tmpfs':
                continue
            if service == 'mongo':
                check(mount['Type'] == 'volume' and mount['Name'] == operator.PROJECT + ('_mongo' if mount['Destination'] == '/data/db' else '_mongo_config'), 'Mongo volume replaced')
            else:
                check(mount['Type'] == 'bind' and mount['Source'] == str(ROOT / 'private/state'), 'Control mount replaced')
        check(not item['State'].get('OOMKilled'), 'Container previously OOM killed')
        result[service] = {'id': item['Id'], 'image': item['Image'], 'config_sha256': digest(json.dumps(item['Config'], sort_keys=True).encode()), 'host_sha256': digest(canonical(host)), 'mounts_sha256': digest(canonical(mounts)), 'running': item['State']['Running'], 'started': item['State']['StartedAt'], 'health': item['State'].get('Health', {}).get('Status')}
    check(set(network.get('Containers', {})) <= {r['id'] for r in result.values()}, 'Foreign network member')
    return result


def inventory(operator):
    operator.safe()
    state = database_snapshot()
    containers = container_snapshot(operator)
    check(state['instance_id'] == containers[state['site']]['id'], 'Recorded owner CID mismatch')
    check(all(not value['running'] for value in containers.values()), 'Recovery requires all four accepted containers stopped')
    return {'schema': 1, 'root': str(ROOT), 'helper_sha256': digest(Path(__file__).read_bytes()), 'manifest_sha256': digest((ROOT / 'private/approved-manifest.json').read_bytes()), 'state': state, 'containers': containers, 'protected': protected_snapshot(), 'observation_sha256': OBSERVATION_SHA, 'start_order': list(ORDER), 'live_activation': 'forbidden'}


def prove_native_authority(owner, state):
    # Fixed local GET only: never call checkpoint/PIN/control/provider endpoints.
    script = "fetch('http://127.0.0.1:5051/authority').then(async r=>{if(!r.ok)throw Error('unavailable');process.stdout.write(await r.text())}).catch(()=>process.exit(1))"
    proof = json.loads(docker('exec', owner['id'], 'node', '-e', script))
    check(proof['database'] == 'tph_backup_restored' and proof['source'] == 'b369e9f5e28584ba99f1cbe35d8f65080a51aeda'
          and proof['watermark'] == 8 and proof['pin_usage'] == 3
          and digest(proof['authority_id'].encode()) == state['authority_sha256']
          and proof['instance_prefix'] == owner['id'][:12], 'Native restored authority/PIN checkpoint changed')


def write_once(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def assert_runtime(current, expected):
    check(set(current) == set(expected), 'Rehearsal service membership changed')
    for service, accepted in expected.items():
        check(all(current[service][key] == accepted[key] for key in
                  ('id', 'image', 'config_sha256', 'host_sha256', 'mounts_sha256', 'started', 'running')),
              'Accepted container identity/start/running state changed')
        if accepted['running']:
            check(current[service]['health'] == 'healthy', 'Recovered container no longer healthy')


def recover(operator, approved):
    check(inventory(operator) == approved, 'Reviewed recovery plan no longer matches')
    private = ROOT / 'private'
    check(not any((private / ('existing-recovery-' + suffix + '.json')).exists() for suffix in ('started', 'failed', 'completed')), 'One-shot recovery already attempted; investigate retained receipts')
    write_once(private / 'existing-recovery-started.json', {'approved_plan_sha256': digest(canonical(approved)), 'starts': list(ORDER)})
    expected_runtime = copy.deepcopy(approved['containers'])
    try:
        for service in ORDER:
            operator.safe()
            check(protected_snapshot() == approved['protected'], 'Protected identity/network/start changed')
            check(database_snapshot() == approved['state'], 'Rehearsal state changed')
            current = container_snapshot(operator)
            assert_runtime(current, expected_runtime)
            check(not current['mac-backup']['running'] and not current[service]['running'], 'Unexpected running service')
            docker('start', current[service]['id'])
            first = operator.inspect(service)['State']
            check(first['Running'], 'Recovered container exited')
            started = first['StartedAt']
            check(started and started != expected_runtime[service]['started'], 'Authorized start timestamp not observed')
            expected_runtime[service]['running'] = True
            expected_runtime[service]['started'] = started
            for _ in range(45):
                item = operator.inspect(service)
                check(item['State']['Running'], 'Recovered container exited')
                check(item['State']['StartedAt'] == started, 'Recovered container restarted during readiness')
                if item['State'].get('Health', {}).get('Status') == 'healthy':
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Recovered container not healthy; no automatic restart')
            assert_runtime(container_snapshot(operator), expected_runtime)
            if service == 'railway-simulation':
                prove_native_authority(current[service], approved['state'])
        check(database_snapshot() == approved['state'], 'State changed during recovery')
        check(protected_snapshot() == approved['protected'], 'Protected infrastructure changed')
        final = container_snapshot(operator)
        assert_runtime(final, expected_runtime)
        check(all(final[s]['running'] == (s in ORDER) for s in SERVICES), 'Unexpected final running set')
        write_once(private / 'existing-recovery-completed.json', {'simulation_only': True, 'state': approved['state'], 'containers': final, 'protected_unchanged': True, 'provider_or_business_actions': False, 'volumes_replaced': False})
        return {'simulation_only': True, 'recovered': list(ORDER), 'inactive_still_stopped': True, 'epoch': 5, 'watermark': 8}
    except BaseException as error:
        write_once(private / 'existing-recovery-failed.json', {'error_type': type(error).__name__, 'automatic_retry_forbidden': True})
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inspect', 'recover'))
    parser.add_argument('--approved-plan', type=Path)
    parser.add_argument('--sha256')
    args = parser.parse_args()
    check(ROOT.resolve() == ROOT and not ROOT.is_symlink(), 'Unsafe rehearsal root')
    operator = load_operator()
    with (ROOT / 'private/operator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'inspect':
            result = inventory(operator)
        else:
            check(args.approved_plan and args.sha256, 'Reviewed private plan and SHA256 required')
            check(not args.approved_plan.stat().st_mode & 0o077, 'Plan must be private')
            check(digest(args.approved_plan.read_bytes()) == args.sha256, 'Approved plan digest mismatch')
            result = recover(operator, read_json(args.approved_plan))
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Recovery refused: ' + (str(error) if isinstance(error, RuntimeError) else type(error).__name__)) from None
