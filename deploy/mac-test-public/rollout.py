"""One-shot, web/gateway-only public-test rollout. Never seeds or starts workers."""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path.home() / 'mac-hosting/test-public'
STACKS = Path.home() / 'mac-hosting/test-stacks'
PROJECTS = {'dieselbridge': 'db-local-test', 'tph': 'tph-local-test'}
HOSTS = {'dieselbridge': 'dieselbridge-test.elisprotech.com', 'tph': 'tph-test.elisprotech.com'}
BASELINE = Path.home() / 'dieselbridge-staging/private/soak-baseline.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def safe_root():
    if ROOT.is_symlink() or ROOT.resolve() != ROOT or (ROOT / '.owner').read_text() != 'macapps-test-public-v1\n':
        raise RuntimeError('unrecognized_public_test_root')
    if any(path.is_symlink() for path in ROOT.rglob('*')):
        raise RuntimeError('symlink_in_public_test_root')
    if (ROOT / 'private').stat().st_mode & 0o077:
        raise RuntimeError('public_private_directory_permissions')


def load_operator():
    path = STACKS / 'tools/stackctl.py'
    if path.is_symlink() or path.resolve() != path:
        raise RuntimeError('unrecognized_stack_operator')
    spec = importlib.util.spec_from_file_location('test_stack_operator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files(*, planned):
    result = {}
    for project in PROJECTS.values():
        for filename, suffix in [('compose.json', 'compose.pending.json'), ('nginx.conf', 'nginx.pending.conf')]:
            key = project + '/' + filename
            source = ROOT / (project + '.' + suffix) if planned else ROOT / 'private' / (project + '.' + filename + '.before')
            result[key] = source.read_bytes()
    return result


def validate_plan(before, planned):
    for app, project in PROJECTS.items():
        original = json.loads(before[project + '/compose.json'])
        proposed = json.loads(planned[project + '/compose.json'])
        expected = copy.deepcopy(original)
        if original['name'] != project or original['networks']['isolated'].get('internal') is not True:
            raise RuntimeError('unrecognized_stack_configuration')
        if app == 'dieselbridge':
            expected['services']['web']['environment'].update(
                FRONTEND_URL='https://' + HOSTS[app], CORS_ORIGINS_STR='https://' + HOSTS[app],
                COOKIE_SECURE='true', COOKIE_DOMAIN='')
        else:
            image = proposed['services']['web']['image']
            if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
                raise RuntimeError('immutable_tph_image_required')
            expected['services']['web']['image'] = image
        expected['services']['gateway']['ports'].append(
            '127.0.0.1:' + ('18210' if app == 'dieselbridge' else '18211') + ':8081')
        if proposed != expected:
            raise RuntimeError('rollout_exceeds_web_gateway_contract')
        # Reuse the independently reviewed generator for the exact two-server nginx profile.
        spec = importlib.util.spec_from_file_location('public_test_configure', Path(__file__).with_name('configure.py'))
        configure = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(configure)
        expected_nginx = configure.nginx(before[project + '/nginx.conf'].decode(), app).encode()
        if planned[project + '/nginx.conf'] != expected_nginx:
            raise RuntimeError('nginx_plan_not_exact_reviewed_profile')


def hashes(data):
    return {key: digest(value) for key, value in data.items()}


def current_hashes():
    return {project + '/' + name: digest((STACKS / project / name).read_bytes())
            for project in PROJECTS.values() for name in ('compose.json', 'nginx.conf')}


def snapshot(operator):
    result = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'baseline_sha256': digest(BASELINE.read_bytes()), 'containers': {}, 'configuration_sha256': current_hashes()}
    all_items = []
    for app in PROJECTS:
        items = operator.inspect(app)
        if len(items) != 5:
            raise RuntimeError('expected_five_test_services')
        all_items.extend(items)
    names = ['dieselbridge-staging-' + service + '-1' for service in ('web', 'postgres', 'redis', 'gateway')]
    all_items.extend(json.loads(operator.docker(['inspect', *names], log='public-baseline-inspection')))
    for item in all_items:
        state = item['State']
        result['containers'][item['Name'].lstrip('/')] = {
            'id': item['Id'], 'started': state['StartedAt'], 'image': item['Image'],
            'running': state['Running'], 'oom': state['OOMKilled'],
            'health': state.get('Health', {}).get('Status'),
            'config_sha256': digest(encoded(item['Config'])),
            'networks_sha256': digest(encoded(item['NetworkSettings']['Networks'])),
        }
    return result


def protected(snapshot_value, *, tph_only=False):
    projects = ['tph-local-test'] if tph_only else PROJECTS.values()
    names = {project + '-' + service + '-1' for project in projects for service in ('web', 'gateway')}
    return {key: {field: value for field, value in item.items() if field != 'health'}
            for key, item in snapshot_value['containers'].items() if key not in names}


def require_preserved(before, after, *, tph_only=False):
    if (before['baseline_sha256'] != after['baseline_sha256']
            or protected(before, tph_only=tph_only) != protected(after, tph_only=tph_only)):
        raise RuntimeError('protected_container_or_baseline_changed_preserve_evidence')


def save(name, data):
    path = ROOT / 'private' / name
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('x') as output:
        output.write(json.dumps(data, sort_keys=True, indent=2) + '\n')
    temporary.replace(path)


def journal(operation, phase, state):
    with (ROOT / 'private/rollout-journal.jsonl').open('a') as output:
        output.write(json.dumps({'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                 'operation': operation, 'phase': phase, 'state': state}) + '\n')


def install(data):
    for key, content in data.items():
        destination = STACKS / key
        temporary = destination.with_name(destination.name + '.public-rollout.tmp')
        with temporary.open('xb') as output:
            output.write(content)
        temporary.replace(destination)


def repaired_current_hashes(applied, planned_files):
    """Accept only the completed, proof-linked, single-image repair for rollback."""
    started_path = ROOT / 'private/tph-image-repair-started.json'
    completed_path = ROOT / 'private/tph-image-repair-completed.json'
    if not started_path.exists() and not completed_path.exists():
        return applied['planned_sha256']
    if not started_path.exists() or not completed_path.exists():
        raise RuntimeError('partial_tph_image_repair_inspect_before_rollback')
    started = json.loads(started_path.read_text())
    completed = json.loads(completed_path.read_text())
    planned_hashes = hashes(planned_files)
    image = started.get('new_image', '')
    if (started.get('before_configuration_sha256') != planned_hashes
            or started.get('planned_sha256') != applied['planned_sha256']
            or completed.get('before_configuration_sha256') != planned_hashes
            or completed.get('new_image') != image
            or completed.get('protected_preserved') is not True
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', image)):
        raise RuntimeError('tph_image_repair_receipt_mismatch')
    key = 'tph-local-test/compose.json'
    expected = json.loads(planned_files[key])
    expected['services']['web']['image'] = image
    expected_files = {**planned_files, key: (json.dumps(expected, indent=2) + '\n').encode()}
    expected_hashes = hashes(expected_files)
    if completed.get('after_configuration_sha256') != expected_hashes:
        raise RuntimeError('tph_image_repair_exceeds_single_image_contract')
    return expected_hashes


def repair_tph(image, operator):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
        raise RuntimeError('immutable_tph_image_required')
    started_path = ROOT / 'private/tph-image-repair-started.json'
    if started_path.exists() or (ROOT / 'private/tph-image-repair-completed.json').exists():
        raise RuntimeError('tph_image_repair_already_started_inspect_journal_no_automatic_retry')
    if (ROOT / 'private/rollback-started.json').exists():
        raise RuntimeError('rollback_started_no_tph_image_repair')
    before_files, planned_files = files(planned=False), files(planned=True)
    source_hashes = json.loads((ROOT / 'private/source-hashes.json').read_text())
    if hashes(before_files) != source_hashes:
        raise RuntimeError('original_configuration_receipt_mismatch')
    validate_plan(before_files, planned_files)
    applied = json.loads((ROOT / 'private/apply-started.json').read_text())
    completed_apply = json.loads((ROOT / 'private/apply-completed.json').read_text())
    expected_current = hashes(planned_files)
    if (applied.get('planned_sha256') != expected_current or applied.get('before_sha256') != source_hashes
            or completed_apply.get('configuration_sha256') != expected_current
            or completed_apply.get('protected_preserved') is not True
            or current_hashes() != expected_current):
        raise RuntimeError('unexpected_current_configuration_no_tph_image_repair')
    key = 'tph-local-test/compose.json'
    replacement = json.loads(planned_files[key])
    if replacement['services']['web']['image'] == image:
        raise RuntimeError('tph_image_repair_requires_different_image')
    replacement['services']['web']['image'] = image
    desired = {key: (json.dumps(replacement, indent=2) + '\n').encode()}
    initial = snapshot(operator)
    save('tph-image-repair-before.json', initial)
    receipt = {'before_configuration_sha256': expected_current,
               'planned_sha256': applied['planned_sha256'], 'new_image': image}
    with started_path.open('x') as output:
        json.dump(receipt, output)
    journal('repair-tph', 'configuration', 'started')
    try:
        install(desired)
        journal('repair-tph', 'configuration', 'passed')
        for service in ('web', 'gateway'):
            journal('repair-tph', service, 'started')
            # nginx caches its upstream address; explicitly recreate the gateway
            # even though its configuration is unchanged by this repair.
            extra = ('--force-recreate',) if service == 'gateway' else ()
            operator.compose('tph', 'up', '-d', '--no-deps', *extra, '--wait', '--wait-timeout', '120', service,
                             timeout=150, log='public-repair-tph-' + service)
            journal('repair-tph', service, 'passed')
    finally:
        final = snapshot(operator)
        save('tph-image-repair-after.json', final)
        require_preserved(initial, final, tph_only=True)
    expected_after = hashes({**planned_files, **desired})
    if current_hashes() != expected_after:
        raise RuntimeError('configuration_drift_during_tph_image_repair')
    save('tph-image-repair-completed.json', {**receipt, 'after_configuration_sha256': expected_after,
                                          'protected_preserved': True})
    print(json.dumps({'operation': 'repair-tph', 'new_image': image, 'protected_preserved': True,
                      'receipt': 'tph-image-repair-after.json'}))


def change(operation, operator):
    before_files, planned_files = files(planned=False), files(planned=True)
    expected_before = json.loads((ROOT / 'private/source-hashes.json').read_text())
    if hashes(before_files) != expected_before:
        raise RuntimeError('original_configuration_receipt_mismatch')
    validate_plan(before_files, planned_files)
    marker = ROOT / 'private' / (operation + '-started.json')
    if marker.exists():
        raise RuntimeError(operation + '_already_started_inspect_journal_no_automatic_retry')
    if operation == 'apply':
        expected_current, desired = expected_before, planned_files
    else:
        applied = json.loads((ROOT / 'private/apply-started.json').read_text())
        if applied['planned_sha256'] != hashes(planned_files):
            raise RuntimeError('planned_configuration_changed_since_apply')
        expected_current, desired = repaired_current_hashes(applied, planned_files), before_files
    if current_hashes() != expected_current:
        raise RuntimeError('live_configuration_drift_no_mutation')
    initial = snapshot(operator)
    save(operation + '-before.json', initial)
    with marker.open('x') as output:
        json.dump({'planned_sha256': hashes(planned_files), 'before_sha256': expected_before}, output)
    journal(operation, 'configuration', 'started')
    try:
        install(desired)
        journal(operation, 'configuration', 'passed')
        for app in PROJECTS:
            for service in ('web', 'gateway'):
                phase = app + '-' + service
                journal(operation, phase, 'started')
                operator.compose(app, 'up', '-d', '--no-deps', '--wait', '--wait-timeout', '120', service,
                                 timeout=150, log='public-' + operation + '-' + phase)
                journal(operation, phase, 'passed')
    finally:
        final = snapshot(operator)
        save(operation + '-after.json', final)
        require_preserved(initial, final)
    save(operation + '-completed.json', {'configuration_sha256': current_hashes(), 'protected_preserved': True})
    print(json.dumps({'operation': operation, 'protected_preserved': True, 'receipt': operation + '-after.json'}))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('snapshot', 'apply', 'rollback', 'repair-tph'))
    parser.add_argument('image', nargs='?')
    args = parser.parse_args()
    if args.command == 'repair-tph':
        if args.image is None or not re.fullmatch(r'sha256:[a-f0-9]{64}', args.image):
            parser.error('repair-tph requires a full immutable sha256 image ID')
    elif args.image is not None:
        parser.error('only repair-tph accepts an image argument')
    safe_root()
    operator = load_operator()
    with operator.lock():
        if args.command == 'snapshot':
            report = snapshot(operator)
            save('snapshot.json', report)
            print(json.dumps(report))
        elif args.command == 'repair-tph':
            repair_tph(args.image, operator)
        else:
            change(args.command, operator)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, RuntimeError) else type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
