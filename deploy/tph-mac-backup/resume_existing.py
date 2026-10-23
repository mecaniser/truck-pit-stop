"""Reviewed one-shot continuation: start only the preserved rehearsal router."""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path.home() / 'mac-hosting/tph-backup-rehearsal-v3'
ORIGINAL = ROOT / 'recover_existing.py'
PROVENANCE = {
    'recover_existing.py': '270960841fd8af20b24a420c978cf9b88bc42f2b7c1fef7a9c52d6c7b74c58ab',
    'private/existing-recovery-reviewed-plan-v2.json': '8868ac83858a1370d256cac26dc5766b637f33b9a9448580dc8b814a048975f7',
    'private/existing-recovery-started.json': '2cb78edf5d945f68a2e3dd9097b72c114ec4d002e5be9c1a8d0ad5aee2b602eb',
    'private/existing-recovery-failed.json': 'f0afbb7032a5b8074c43bcf62db4ba3eed7b27641bab9c92826479477c30c340',
}
STARTS = {'mongo': '2026-10-22T20:03:53.486818263Z', 'railway-simulation': '2026-10-22T20:04:00.591453794Z'}
AUTHORITY_SHA = '9ba7b0f38dcf28dd4326a7ff057d93add977d46da403ebb4b1a0c2f4c49c7483'
SOURCE = 'b369e9f5e28584ba99f1cbe35d8f65080a51aeda'


def check(value, reason):
    if not value:
        raise RuntimeError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def provenance():
    check(ROOT.resolve() == ROOT and not ROOT.is_symlink(), 'Unsafe root')
    for name, expected in PROVENANCE.items():
        path = ROOT / name
        check(path.resolve() == path and not path.is_symlink() and sha(path.read_bytes()) == expected, 'Original recovery provenance changed')
    check(not (ROOT / 'private/existing-recovery-completed.json').exists(), 'Original recovery already completed')
    plan = json.loads((ROOT / 'private/existing-recovery-reviewed-plan-v2.json').read_text())
    started = json.loads((ROOT / 'private/existing-recovery-started.json').read_text())
    check(started['approved_plan_sha256'] == sha(canonical(plan)) and started['starts'] == ['mongo', 'railway-simulation', 'router'], 'Original attempt/plan binding changed')
    return plan


def load_original():
    provenance()
    spec = importlib.util.spec_from_file_location('reviewed_original_recovery', ORIGINAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_no_resume():
    check(not any((ROOT / ('private/existing-resume-' + suffix + '.json')).exists() for suffix in ('started', 'completed', 'failed')), 'Resume already attempted; preserve and investigate')


# The child emits only status and proof booleans, never the response body/authority.
PROBE = r"""const crypto=require('node:crypto');const expected=JSON.parse(process.argv[1]);
(async()=>{let status=null,json=false;try{const r=await fetch('http://127.0.0.1:5051/authority',{signal:AbortSignal.timeout(5000)});status=r.status;let data='',n=0;for await(const chunk of r.body){n+=chunk.length;if(n>8192)throw Error('limit');data+=Buffer.from(chunk).toString('utf8');}const p=JSON.parse(data);json=true;const fields={database:p.database==='tph_backup_restored',source:p.source===expected.source,watermark:p.watermark===8,pinUsage:p.pin_usage===3,authority:typeof p.authority_id==='string'&&crypto.createHash('sha256').update(p.authority_id).digest('hex')===expected.authority,prefix:p.instance_prefix===expected.prefix};process.stdout.write(JSON.stringify({httpStatus:status,bodyJson:json,fields}));}catch(_){process.stdout.write(JSON.stringify({httpStatus:status,bodyJson:json,probeFailed:true}));}})();"""


def authority_probe(original, owner):
    expected = json.dumps({'source': SOURCE, 'authority': AUTHORITY_SHA, 'prefix': owner['id'][:12]})
    diagnostic = {'dockerExit': None, 'timeout': False, 'stage': 'docker'}
    try:
        result = subprocess.run([*original.D, 'exec', owner['id'], 'node', '-e', PROBE, expected], capture_output=True, timeout=15)
        diagnostic['dockerExit'] = result.returncode
        diagnostic['stderrBytes'] = len(result.stderr)
        # Hash permits correlation without retaining raw potentially sensitive data.
        diagnostic['stderrSha256'] = sha(result.stderr)
        if result.returncode == 0 and len(result.stdout) <= 2048:
            try:
                raw = json.loads(result.stdout)
                check(isinstance(raw, dict), 'Invalid probe diagnostic')
                status = raw.get('httpStatus')
                diagnostic['httpStatus'] = status if type(status) is int and 100 <= status <= 599 else None
                diagnostic['bodyJson'] = raw.get('bodyJson') is True
                fields = raw.get('fields', {})
                if not isinstance(fields, dict): fields = {}
                diagnostic['stage'] = 'http' if diagnostic['httpStatus'] != 200 else 'parse' if not diagnostic['bodyJson'] else 'proof'
                diagnostic['fields'] = {key: fields.get(key) is True for key in ('database', 'source', 'watermark', 'pinUsage', 'authority', 'prefix')}
            except (ValueError, TypeError, RuntimeError):
                diagnostic['invalidDiagnostic'] = True
                diagnostic['stage'] = 'parse'
    except subprocess.TimeoutExpired:
        diagnostic['timeout'] = True
        diagnostic['stage'] = 'timeout'
    diagnostic['ok'] = diagnostic['dockerExit'] == 0 and diagnostic.get('httpStatus') == 200 and diagnostic.get('bodyJson') is True and all(diagnostic.get('fields', {}).values()) and len(diagnostic.get('fields', {})) == 6
    if diagnostic['ok']: diagnostic['stage'] = 'accepted'
    return diagnostic


def state_snapshot(original, operator, expected_runtime):
    operator.safe()
    old = provenance()
    check(original.database_snapshot() == old['state'] and old['state']['authority_sha256'] == AUTHORITY_SHA, 'Control/provider state changed or uncertain')
    check(original.protected_snapshot() == old['protected'], 'Protected fourteen/new observation changed')
    current = original.container_snapshot(operator)
    original.assert_runtime(current, expected_runtime)
    return current


def expected_partial(old):
    expected = copy.deepcopy(old['containers'])
    for service, started in STARTS.items():
        expected[service].update(started=started, running=True, health='healthy')
    return expected


def inspect_resume(original, operator):
    require_no_resume()
    old = provenance()
    partial = expected_partial(old)
    current = state_snapshot(original, operator, partial)
    diagnostic = authority_probe(original, current['railway-simulation'])
    return {'schema': 1, 'root': str(ROOT), 'helper_sha256': sha(Path(__file__).read_bytes()), 'provenance': PROVENANCE,
            'partial_runtime': partial, 'state': old['state'], 'protected': old['protected'], 'authority_probe': diagnostic,
            'start_only': current['router']['id'], 'ready': diagnostic['ok'], 'live_activation': 'forbidden'}


def resume(original, operator, approved):
    check(approved.get('ready') is True, 'Resume plan has no successful authority proof')
    observed = inspect_resume(original, operator)
    check(observed['ready'], 'Read-only authority probe failed: ' + json.dumps(observed['authority_probe']))
    check(observed == approved, 'Reviewed resume plan no longer matches')
    private = ROOT / 'private'
    original.write_once(private / 'existing-resume-started.json', {'approved_plan_sha256': sha(canonical(approved)), 'start_only': approved['start_only'], 'prior_failure_preserved': True})
    diagnostics = []
    try:
        current = state_snapshot(original, operator, approved['partial_runtime'])
        diagnostic = authority_probe(original, current['railway-simulation']); diagnostics.append(diagnostic)
        check(diagnostic['ok'], 'Read-only authority probe failed before router start')
        # The proof GET cannot authorize a changed container/state between checks.
        current = state_snapshot(original, operator, approved['partial_runtime'])
        original.docker('start', approved['start_only'])
        first = operator.inspect('router')['State']
        check(first['Running'] and first['StartedAt'] != current['router']['started'], 'Router authorized start not observed')
        started = first['StartedAt']
        expected = copy.deepcopy(approved['partial_runtime'])
        expected['router'].update(started=started, running=True, health='healthy')
        for _ in range(45):
            item = operator.inspect('router')['State']
            check(item['Running'] and item['StartedAt'] == started, 'Router exited/restarted during readiness')
            if item.get('Health', {}).get('Status') == 'healthy':
                break
            time.sleep(1)
        else:
            raise RuntimeError('Router not healthy; no automatic retry')
        final = state_snapshot(original, operator, expected)
        diagnostic = authority_probe(original, final['railway-simulation']); diagnostics.append(diagnostic)
        check(diagnostic['ok'], 'Read-only authority probe failed after router start')
        final = state_snapshot(original, operator, expected)
        original.write_once(private / 'existing-resume-completed.json', {'simulation_only': True, 'state': approved['state'], 'containers': final, 'provenance': PROVENANCE, 'authority_diagnostics': diagnostics, 'start_only': approved['start_only'], 'protected_unchanged': True, 'prior_failure_preserved': True, 'provider_or_business_actions': False})
        return {'simulation_only': True, 'router_started_only': True, 'epoch': 5, 'watermark': 8}
    except BaseException as error:
        original.write_once(private / 'existing-resume-failed.json', {'error_type': type(error).__name__, 'authority_diagnostics': diagnostics, 'automatic_retry_forbidden': True})
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inspect', 'resume'))
    parser.add_argument('--approved-plan', type=Path)
    parser.add_argument('--sha256')
    args = parser.parse_args()
    original = load_original(); operator = original.load_operator()
    with (ROOT / 'private/operator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'inspect':
            result = inspect_resume(original, operator)
        else:
            check(args.approved_plan and args.sha256, 'Private reviewed resume plan required')
            check(args.approved_plan.resolve() == args.approved_plan and not args.approved_plan.stat().st_mode & 0o077 and sha(args.approved_plan.read_bytes()) == args.sha256, 'Private resume plan path/hash mismatch')
            result = resume(original, operator, json.loads(args.approved_plan.read_text()))
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Resume refused: ' + (str(error) if isinstance(error, RuntimeError) else type(error).__name__)) from None
