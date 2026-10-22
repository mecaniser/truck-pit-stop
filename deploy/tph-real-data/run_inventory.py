"""One isolated, read-only raw BSON diagnostic; private output, no application imports."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

ROOT = Path.home() / 'mac-hosting/tph-real-data-v3'
TOOLS = Path.home() / 'mac-hosting/tph-real-data-tools-v3'
PLAN_SHA = 'b5b98d067f01e178f7ba85fcc8387ed804924e1aead3c17075d9d7af16d431d1'
TARGET_SHA = '9e1418f5d955554f40722b0e2ff25e8251eb888fa7569c8bbe465c8d8611f312'
MONGO = 'c73ebffa80e5c221d54929ed71c71425bcc726646a172b18e48e23f95ea11a9c'
IMAGE = 'sha256:95df264063f3224f9a2519fd68a99e537f7a8da26d17ff78b5e6a87267a798b0'
PROJECT = 'macapps-tph-real-data-2c0eb4a11903'
D = ['/Applications/Docker.app/Contents/Resources/bin/docker', '--context', 'desktop-linux']


def require(ok):
    if not ok:
        raise RuntimeError('inventory_preflight_or_command_refused')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(ok, reason):
    require(ok)


def main():
    os.umask(0o077)
    require(hashlib.sha256((ROOT / 'plan.json').read_bytes()).hexdigest() == PLAN_SHA)
    require(hashlib.sha256((TOOLS / 'target_inventory.cjs').read_bytes()).hexdigest() == TARGET_SHA)
    receipt = json.loads((ROOT / 'private/phase1-restored.json').read_text())
    require(receipt['cid'] == MONGO and receipt['ttl_monitor_enabled'] is False and receipt['web_started'] is False)
    spec = importlib.util.spec_from_file_location('inventory_operator_remote', Path.home() / 'mac-hosting/test-deploy/remote.py')
    module = importlib.util.module_from_spec(spec);sys.modules[spec.name] = module;spec.loader.exec_module(module)
    operator = module.load_module('inventory_shared_operator', Path.home() / 'mac-hosting/test-stacks/tools/stackctl.py')
    private = ROOT / 'private'
    def rehearsal_protect():
        receipt = Path.home() / 'mac-hosting/tph-backup-rehearsal-v3/private/router-port-completed.json'
        check(digest(receipt) == '4df056156893ea1c0a2086e14d1a9e8a238992c9a9c72f84ecdf933e36629a30', 'rehearsal_receipt_drift')
        expected = json.loads(receipt.read_text())['containers']
        check(set(expected) == {'mongo', 'railway-simulation', 'mac-backup', 'router'}, 'rehearsal_scope_changed')
        actual = {}
        for service, old in expected.items():
            item = json.loads(subprocess.check_output(D + ['inspect', old['id']]))[0]
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
            network = json.loads(subprocess.check_output(D + ['network', 'inspect', network_name]))[0]
            check(network['Internal'] and set(network.get('Containers', {})) <= {r['id'] for r in expected.values()}, 'rehearsal_network_boundary_drift')
            actual[service] = row
        return {'receipt_sha256': digest(receipt), 'containers': actual}


    with operator.lock():
        remote = module.Remote(operator);before = remote.status()
        rehearsal_before = rehearsal_protect()
        from_root = Path.home() / 'dieselbridge-staging/private'
        baseline_hashes = {str(path): digest(path) for path in (from_root/'soak-baseline.json', from_root/'observations/20261022T192823Z/soak-baseline.json')}
        require(set(baseline_hashes.values()) == {'1e7618809a071feb45cadb84667827c97c483c63f7e3fbf645b92628b4544d1e','0002ccdd4d0b797e4a79543c1be310cd7a292d8f23b8ecba786031dec16ed328'})
        require(all(before[k] for k in ('identity_matches', 'configuration_matches', 'baseline_matches')))
        require(not before['uncertain_operation'] and not before['uncertain_recovery'])
        mongo = json.loads(subprocess.check_output(D + ['inspect', MONGO]))[0]
        require(mongo['Name'] == '/' + PROJECT + '-mongo-1' and mongo['State']['Running'] and mongo['State']['Health']['Status'] == 'healthy')
        require(not mongo['State']['OOMKilled'] and not mongo['HostConfig']['PortBindings'])
        net = json.loads(subprocess.check_output(D + ['network', 'inspect', PROJECT + '_isolated']))[0]
        require(net['Internal'] and set(net.get('Containers', {})) == {MONGO} and net['IPAM']['Config'][0]['Subnet'] == '10.240.64.0/24')
        name = PROJECT + '-inventory'
        require(not subprocess.check_output(D + ['ps', '-aq', '--filter', 'name=^/' + name + '$']).strip())
        with (private / 'inventory-started.json').open('x') as out:
            json.dump({'plan_sha256': PLAN_SHA, 'source_sha256': TARGET_SHA, 'mongo_cid': MONGO}, out)
        args = D + ['create', '--interactive', '--name', name, '--network', PROJECT + '_isolated', '--entrypoint', 'node',
                    '--read-only', '--user', 'node', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                    '--pids-limit', '64', '--memory', '512m', '--cpus', '0.5', '--restart', 'no', '--log-driver', 'none',
                    '--label', 'io.macapps.readonly-inventory=DB-INFRA-006', '--mount',
                    'type=bind,source=' + str(TOOLS / 'target_inventory.cjs') + ',target=/usr/src/app/target_inventory.cjs,readonly',
                    IMAGE, '/usr/src/app/target_inventory.cjs']
        cid = subprocess.check_output(args, stderr=subprocess.DEVNULL).decode().strip()
        require(len(cid) == 64)
        item = json.loads(subprocess.check_output(D + ['inspect', cid]))[0]
        require(item['Image'] == IMAGE and item['Config']['Entrypoint'] == ['node'] and item['Config']['Cmd'] == ['/usr/src/app/target_inventory.cjs'])
        require(item['Config']['OpenStdin'] is True and item['Config']['Tty'] is False)
        require(len(item['Mounts']) == 1 and item['Mounts'][0]['Type'] == 'bind' and item['Mounts'][0]['Source'] == str(TOOLS / 'target_inventory.cjs') and item['Mounts'][0]['Destination'] == '/usr/src/app/target_inventory.cjs' and item['Mounts'][0]['RW'] is False)
        require(item['Config']['User'] == 'node' and set(item['NetworkSettings']['Networks']) == {PROJECT + '_isolated'})
        require(item['HostConfig']['ReadonlyRootfs'] and not item['HostConfig']['Privileged'] and item['HostConfig']['CapDrop'] == ['ALL'])
        require(not item['HostConfig']['PortBindings'] and item['HostConfig']['RestartPolicy']['Name'] == 'no' and item['HostConfig']['LogConfig']['Type'] == 'none')
        (private / 'inventory-cid.json').write_text(json.dumps({'cid': cid, 'source_sha256': TARGET_SHA, 'image': IMAGE}))
        env = dict(line.split('=', 1) for line in (private / 'clone.env').read_text().splitlines())
        value = {'mongoUri': 'mongodb://clone_restore_admin:' + quote(env['CLONE_RESTORE_PASSWORD'], safe='') + '@mongo:27017/tph_local_test?authSource=admin'}
        with (private / 'target-inventory.json').open('xb') as out, (private / 'target-inventory.stderr.private').open('xb') as err:
            result = subprocess.run(D + ['start', '-ai', cid], input=json.dumps(value).encode(), stdout=out, stderr=err, timeout=300)
        require(result.returncode == 0)
        target = json.loads((private / 'target-inventory.json').read_text())
        require(target['database'] == 'tph_local_test' and target['namespace_count'] == 78)
        final = json.loads(subprocess.check_output(D + ['inspect', cid]))[0]
        require(not final['State']['Running'] and final['State']['ExitCode'] == 0 and not final['State']['OOMKilled'])
        after = remote.status();require(before['snapshot'] == after['snapshot'])
        require(rehearsal_protect() == rehearsal_before)
        require(all(digest(Path(path)) == sha for path, sha in baseline_hashes.items()))
        record = {'diagnostic_cid': cid, 'mongo_cid': MONGO, 'source_sha256': TARGET_SHA,
                  'namespaces': target['namespace_count'], 'documents': target['document_count'],
                  'target_receipt_sha256': hashlib.sha256((private / 'target-inventory.json').read_bytes()).hexdigest(),
                  'protected_unchanged': True, 'app_started': False, 'data_equality': 'pending comparison'}
        with (private / 'inventory-completed.json').open('x') as out:json.dump(record, out, indent=2)
        print(json.dumps(record))


if __name__ == '__main__':
    try:main()
    except Exception:
        print('inventory_failed_private_evidence_preserved_no_application_start', file=sys.stderr)
        raise SystemExit(1)
