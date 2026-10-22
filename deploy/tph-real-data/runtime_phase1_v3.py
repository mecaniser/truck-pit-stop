"""One-shot, exact-plan Mongo-only clone restore. No application/role/gateway start."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path.home() / 'mac-hosting/tph-real-data-v3'
PLAN_SHA = 'b5b98d067f01e178f7ba85fcc8387ed804924e1aead3c17075d9d7af16d431d1'
ARCHIVE = Path.home() / 'mac-hosting/real-data/private/captures/20261022T214813Z/ParkRightDB.archive.gz'
ARCHIVE_SHA = 'caf0a0fcdcbf70d9bcf7b237610327938687a0f8081907290f4eb025c5267fba'
DOCKER = '/Applications/Docker.app/Contents/Resources/bin/docker'
BASELINES = {'soak-baseline.json': '1e7618809a071feb45cadb84667827c97c483c63f7e3fbf645b92628b4544d1e',
 'observations/20261022T192823Z/soak-baseline.json': '0002ccdd4d0b797e4a79543c1be310cd7a292d8f23b8ecba786031dec16ed328'}


def check(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    os.umask(0o077)
    check(len(sys.argv) == 2 and sys.argv[1] == PLAN_SHA, 'explicit_reviewed_plan_required')
    check(ROOT.resolve() == ROOT and not ROOT.is_symlink(), 'root_refused')
    check((ROOT / '.owner').read_text() == 'macapps-tph-real-data-v1\n', 'owner_refused')
    check(digest(ROOT / 'plan.json') == PLAN_SHA, 'plan_drift')
    plan = json.loads((ROOT / 'plan.json').read_text())
    check(plan['project'] == 'macapps-tph-real-data-2c0eb4a11903', 'project_refused')
    for name, sha in plan['artifacts_sha256'].items():
        p = ROOT / name
        check(not p.is_symlink() and digest(p) == sha, 'artifact_drift')
    check(ARCHIVE.stat().st_size == 17398592 and digest(ARCHIVE) == ARCHIVE_SHA, 'archive_refused')
    check((ROOT / 'private').stat().st_mode & 0o077 == 0, 'private_permissions')
    remote = load('real_data_phase1_remote', Path.home() / 'mac-hosting/test-deploy/remote.py')
    operator = remote.load_module('real_data_phase1_operator', Path.home() / 'mac-hosting/test-stacks/tools/stackctl.py')
    private = ROOT / 'private'
    base = [DOCKER, '--context', 'desktop-linux']
    compose = base + ['compose', '--env-file', str(private / 'clone.env'), '-p', plan['project'], '-f', str(ROOT / 'compose.json')]

    def run(args, label, source=None, timeout=300):
        with (private / (label + '.stdout.private')).open('xb') as out, (private / (label + '.stderr.private')).open('xb') as err:
            result = subprocess.run(args, stdin=source, stdout=out, stderr=err, timeout=timeout)
        check(result.returncode == 0, 'phase1_command_failed_' + label)
        return (private / (label + '.stdout.private')).read_bytes()

    def rehearsal_protect():
        receipt = Path.home() / 'mac-hosting/tph-backup-rehearsal-v3/private/router-port-completed.json'
        check(digest(receipt) == '4df056156893ea1c0a2086e14d1a9e8a238992c9a9c72f84ecdf933e36629a30', 'rehearsal_receipt_drift')
        expected = json.loads(receipt.read_text())['containers']
        check(set(expected) == {'mongo', 'railway-simulation', 'mac-backup', 'router'}, 'rehearsal_scope_changed')
        actual = {}
        for service, old in expected.items():
            item = json.loads(subprocess.check_output(base + ['inspect', old['id']]))[0]
            mounts = sorted(item['Mounts'], key=lambda m: (m['Destination'], m['Type']))
            check(len({m['Destination'] for m in mounts}) == len(mounts), 'rehearsal_duplicate_mount')
            check(not item['State'].get('OOMKilled'), 'rehearsal_oom')
            row = {'id': item['Id'], 'image': item['Image'],
                   'config_sha256': hashlib.sha256(json.dumps(item['Config'], sort_keys=True).encode()).hexdigest(),
                   'host_sha256': hashlib.sha256(canonical(item['HostConfig'])).hexdigest(),
                   'mounts_sha256': hashlib.sha256(canonical(mounts)).hexdigest(),
                   'running': item['State']['Running'], 'started': item['State']['StartedAt'],
                   'health': item['State'].get('Health', {}).get('Status')}
            check(row == old, 'rehearsal_identity_or_configuration_drift')
            network_name = item['Config']['Labels']['com.docker.compose.project'] + '_isolated'
            check(set(item['NetworkSettings']['Networks']) == {network_name}, 'rehearsal_network_drift')
            network = json.loads(subprocess.check_output(base + ['network', 'inspect', network_name]))[0]
            check(network['Internal'] and set(network.get('Containers', {})) <= {r['id'] for r in expected.values()}, 'rehearsal_network_boundary_drift')
            actual[service] = row
        return {'receipt_sha256': digest(receipt), 'containers': actual}

    def protect(controller):
        status = controller.status()
        check(all(status[k] for k in ('identity_matches', 'configuration_matches', 'baseline_matches')), 'protected_drift')
        check(not status['uncertain_operation'] and not status['uncertain_recovery'], 'protected_uncertainty')
        for rel, sha in BASELINES.items():
            check(digest(Path.home() / 'dieselbridge-staging/private' / rel) == sha, 'baseline_drift')
        return status

    with operator.lock():
        controller = remote.Remote(operator)
        before = protect(controller)
        rehearsal_before = rehearsal_protect()
        check(before['snapshot'] == json.loads((private / 'protected-before.json').read_text())['snapshot'], 'protected_snapshot_changed')
        for kind, args in [('containers', ['ps', '-aq']), ('networks', ['network', 'ls', '-q']), ('volumes', ['volume', 'ls', '-q'])]:
            data = subprocess.check_output(base + args + ['--filter', 'label=com.docker.compose.project=' + plan['project']])
            check(not data.strip(), 'existing_project_' + kind)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 18221))
        for image in plan['manifest']['images'].values():
            rows = json.loads(subprocess.check_output(base + ['image', 'inspect', image]))
            check(len(rows) == 1 and rows[0]['Id'] == image and rows[0]['Os'] == 'linux' and rows[0]['Architecture'] == 'arm64', 'image_refused')
        with (private / 'phase1-started.json').open('x') as out:
            json.dump({'plan_sha256': PLAN_SHA, 'archive_sha256': ARCHIVE_SHA, 'stage': 'mongo_only_restore'}, out)
        run(compose + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '120', 'mongo'], 'mongo-up', timeout=180)
        cid = run(compose + ['ps', '-q', 'mongo'], 'mongo-cid').decode().strip()
        check(len(cid) == 64, 'mongo_identity_missing')
        info = json.loads(subprocess.check_output(base + ['inspect', cid]))[0]
        check(info['Name'] == '/' + plan['project'] + '-mongo-1' and info['Image'] == plan['manifest']['images']['mongo'], 'mongo_identity_refused')
        check(info['State']['Running'] and info['State']['Health']['Status'] == 'healthy' and not info['State']['OOMKilled'], 'mongo_unhealthy')
        check(not info['HostConfig']['PortBindings'], 'mongo_ports_refused')
        check(set(info['NetworkSettings']['Networks']) == {plan['project'] + '_isolated'}, 'mongo_network_refused')
        network = json.loads(subprocess.check_output(base + ['network', 'inspect', plan['project'] + '_isolated']))[0]
        check(network['Internal'] and network['IPAM']['Config'][0]['Subnet'] == '10.240.64.0/24', 'mongo_network_drift')
        volumes = sorted(m['Name'] for m in info['Mounts'] if m['Type'] == 'volume')
        check(set(volumes) == {plan['project'] + '_mongo', plan['project'] + '_mongo_config'}, 'fresh_volume_binding_refused')
        for mount in (m for m in info['Mounts'] if m['Type'] == 'volume'):
            volume = json.loads(subprocess.check_output(base + ['volume', 'inspect', mount['Name']]))[0]
            check(volume['Labels'].get('com.docker.compose.project') == plan['project'] and volume['Mountpoint'] == mount['Source'], 'fresh_volume_ownership_refused')
            check(volume['Labels'].get('com.docker.compose.volume') in ('mongo', 'mongo_config'), 'fresh_volume_label_refused')
        (private / 'phase1-mongo-identity.json').write_text(json.dumps({'cid': cid, 'volumes': volumes, 'started': info['State']['StartedAt']}, indent=2))
        ttl_js = "if(!db.getSiblingDB('admin').auth(process.env.MONGO_INITDB_ROOT_USERNAME,process.env.MONGO_INITDB_ROOT_PASSWORD))throw Error('local_auth_failed');if(db.getSiblingDB('admin').runCommand({getParameter:1,ttlMonitorEnabled:1}).ttlMonitorEnabled!==false)throw Error('ttl_enabled');print('TTL_DISABLED');"
        check(run(base + ['exec', cid, 'mongosh', '--quiet', '--eval', ttl_js], 'ttl-before-restore').decode().strip() == 'TTL_DISABLED', 'ttl_before_restore_refused')
        js = "if(!db.getSiblingDB('admin').auth(process.env.MONGO_INITDB_ROOT_USERNAME,process.env.MONGO_INITDB_ROOT_PASSWORD))throw Error('local_auth_failed');const t=db.getSiblingDB('tph_local_test');print(JSON.stringify({collections:t.getCollectionNames().length}));"
        raw = run(base + ['exec', cid, 'mongosh', '--quiet', '--eval', js], 'empty-target')
        check(json.loads(raw.decode().strip().splitlines()[-1])['collections'] == 0, 'populated_target_refused')
        check(subprocess.check_output(compose + ['ps', '-q', 'mongo']).decode().strip() == cid, 'mongo_identity_changed')
        check(digest(ARCHIVE) == ARCHIVE_SHA, 'archive_changed')
        with ARCHIVE.open('rb') as archive:
            run(base + ['exec', '-i', cid, 'mongorestore', '--config', '/run/clone/restore-config.yml', '--username', 'clone_restore_admin', '--authenticationDatabase', 'admin', '--archive', '--gzip', '--stopOnError', '--nsInclude=ParkRightDB.*', '--nsFrom=ParkRightDB.*', '--nsTo=tph_local_test.*'], 'full-restore', source=archive)
        check(run(base + ['exec', cid, 'mongosh', '--quiet', '--eval', ttl_js], 'ttl-after-restore').decode().strip() == 'TTL_DISABLED', 'ttl_after_restore_refused')
        after = protect(controller)
        check(rehearsal_protect() == rehearsal_before, 'rehearsal_post_restore_drift')
        check(before['snapshot'] == after['snapshot'], 'protected_post_restore_drift')
        record = {'restored': True, 'plan_sha256': PLAN_SHA, 'cid': cid, 'volumes': volumes, 'archive_sha256': ARCHIVE_SHA,
                  'protected_unchanged': True, 'web_started': False, 'role_created': False, 'public_cutover': False,
                  'ttl_monitor_enabled': False, 'full_document_index_comparison': 'pending; not claimed', 'stage': 'STOP_after_restore_before_application'}
        with (private / 'phase1-restored.json').open('x') as out:
            json.dump(record, out, indent=2)
        print(json.dumps(record))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('phase1_refused_or_failed_preserve_private_evidence_no_retry', file=sys.stderr)
        raise SystemExit(1)
