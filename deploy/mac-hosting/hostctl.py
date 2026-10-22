#!/usr/bin/env python3
"""Private, stateless Mac application hosting. Never manages staging or production."""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path.home() / 'mac-hosting'
DOCKER = '/Applications/Docker.app/Contents/Resources/bin/docker'
MARKER = 'mac-hosting-v1-private-stateless\n'
GATEWAY_IMAGE = 'sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5'
RESERVED = {'dieselbridge', 'staging', 'production', 'prod', 'railway'}
SLUG = re.compile(r'[a-z][a-z0-9-]{0,30}[a-z0-9]\Z')
IMAGE = re.compile(r'sha256:[a-f0-9]{64}\Z')


class Refused(RuntimeError):
    pass


def slug(value):
    if not SLUG.fullmatch(value) or any(x in value for x in RESERVED):
        raise Refused('invalid_or_reserved_app_name')
    return value


def run(args, timeout=90):
    # Tool output can contain application secrets. Keep it private; expose only exit code.
    try:
        p = subprocess.run([DOCKER, '--context', 'desktop-linux', *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Refused('docker_command_timeout') from None
    if p.returncode:
        raise Refused('docker_command_failed_' + str(p.returncode))
    return p.stdout


def save(path, data):
    temp = path.with_suffix('.tmp')
    with temp.open('w') as out:
        os.chmod(temp, 0o600)
        json.dump(data, out, sort_keys=True, indent=2)
        out.write('\n')
    temp.replace(path)


def check_root(root):
    if root.is_symlink() or not root.is_dir() or root.resolve() != root:
        raise Refused('unsafe_hosting_root')
    if (root / '.owner').read_text() != MARKER:
        raise Refused('unrecognized_hosting_root')
    # Same-account operator controls this tree. Reject symlinks before reading state.
    if any(p.is_symlink() for p in root.rglob('*')):
        raise Refused('symlink_in_hosting_root')


@contextlib.contextmanager
def locked(root=ROOT):
    check_root(root)
    with (root / '.lock').open('a') as lock:
        os.chmod(root / '.lock', 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def initialize(root=ROOT):
    if root.exists():
        check_root(root)
        return
    root.mkdir(mode=0o700)
    (root / '.owner').write_text(MARKER)
    (root / '.owner').chmod(0o600)
    (root / 'apps').mkdir(mode=0o700)
    (root / 'backups').mkdir(mode=0o700)


def state_path(root, app):
    return root / 'apps' / slug(app) / 'state.json'


def all_states(root):
    return [json.loads(p.read_text()) for p in sorted((root / 'apps').glob('*/state.json'))]


def image_id(value):
    if not IMAGE.fullmatch(value):
        raise Refused('immutable_full_image_id_required')
    info = json.loads(run(['image', 'inspect', value]))[0]
    if info['Id'] != value or info.get('Os') != 'linux' or info.get('Architecture') != 'arm64':
        raise Refused('linux_arm64_image_required')
    if info.get('Config', {}).get('Volumes'):
        raise Refused('image_declared_volumes_not_supported')
    return value


def validate_spec(spec):
    slug(spec['app'])
    if not IMAGE.fullmatch(spec['image']) or not IMAGE.fullmatch(spec['gateway_image']):
        raise Refused('immutable_full_image_id_required')
    if spec['gateway_image'] != GATEWAY_IMAGE:
        raise Refused('unreviewed_gateway_image')
    if not 18100 <= spec['port'] <= 18199 or not 1024 <= spec['container_port'] <= 65535:
        raise Refused('port_out_of_range')
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', spec['revision']):
        raise Refused('invalid_source_revision')
    if not re.fullmatch(r'/[A-Za-z0-9/_-]{0,100}', spec['health']):
        raise Refused('invalid_health_path')


def containers(app):
    project = 'macapps-' + slug(app)
    ids = run(['ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project]).split()
    if not ids:
        return []
    return json.loads(run(['inspect', *ids]))


def owned(app, known):
    items = containers(app)
    if items and not known:
        raise Refused('unowned_existing_project')
    seen = set()
    for item in items:
        labels = item['Config'].get('Labels', {})
        service = labels.get('com.docker.compose.service')
        if (labels.get('io.mac-hosting.owner') != 'v1' or
                service not in {'app', 'gateway'} or service in seen or
                item['Name'] != '/macapps-' + app + '-' + service + '-1'):
            raise Refused('unowned_or_unexpected_container')
        seen.add(service)
    return items


def managed(root, app):
    path = state_path(root, app).parent / 'managed.json'
    return path.exists() and json.loads(path.read_text()) == {'app': app, 'owner': 'v1'}


def available_port(root, spec, current):
    for other in all_states(root):
        if other['app'] != spec['app'] and other['current']['port'] == spec['port']:
            raise Refused('port_reserved_by_other_app')
    if current and current['current']['port'] != spec['port']:
        raise Refused('app_port_is_immutable')
    # Existing own gateway legitimately occupies its reserved port.
    has_gateway = any(i['Config']['Labels'].get('com.docker.compose.service') == 'gateway'
                      and i['State']['Running'] for i in owned(spec['app'], bool(current) or managed(root, spec['app'])))
    if not has_gateway:
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', spec['port']))
            except OSError:
                raise Refused('host_port_occupied') from None


def compose_spec(spec, config_path):
    validate_spec(spec)
    common = {'restart': 'unless-stopped', 'read_only': True, 'cap_drop': ['ALL'],
              'security_opt': ['no-new-privileges:true'], 'pids_limit': 128,
              'logging': {'driver': 'json-file', 'options': {'max-size': '5m', 'max-file': '2'}},
              'labels': {'io.mac-hosting.owner': 'v1'}}
    return {'name': 'macapps-' + spec['app'], 'services': {
        'app': {**common, 'image': spec['image'], 'user': '65532:65532',
                'networks': ['isolated'], 'tmpfs': ['/tmp:size=32m,mode=1777'],
                'mem_limit': '256m', 'cpus': 0.5},
        'gateway': {**common, 'image': spec['gateway_image'], 'user': '101:101',
                    'networks': ['isolated', 'ingress'],
                    'ports': ['127.0.0.1:' + str(spec['port']) + ':8080'],
                    'volumes': [str(config_path) + ':/etc/nginx/nginx.conf:ro'],
                    'tmpfs': ['/tmp:size=16m,mode=1777'],
                    'mem_limit': '32m', 'cpus': 0.25}},
            'networks': {'isolated': {'internal': True}, 'ingress': {}}}


def compose(root, app, *args):
    directory = root / 'apps' / slug(app)
    return run(['compose', '-p', 'macapps-' + app, '-f', str(directory / 'compose.json'), *args])


def apply(root, spec):
    directory = root / 'apps' / spec['app']
    nginx = directory / 'nginx.conf'
    nginx.write_text('worker_processes 1; pid /tmp/nginx.pid; error_log /dev/stderr;\nevents { worker_connections 128; }\nhttp {\n'
                     'access_log off; server_tokens off; client_body_temp_path /tmp/client; proxy_temp_path /tmp/proxy;\n'
                     'fastcgi_temp_path /tmp/fastcgi; uwsgi_temp_path /tmp/uwsgi; scgi_temp_path /tmp/scgi;\nserver { listen 8080;\n'
                     'location / { proxy_pass http://app:' + str(spec['container_port']) + ';\n'
                     'proxy_set_header Host $http_host; proxy_set_header X-Forwarded-Proto $scheme;\n'
                     'proxy_connect_timeout 2s; proxy_read_timeout 15s; } } }\n')
    nginx.chmod(0o644)
    save(directory / 'compose.json', compose_spec(spec, nginx))
    compose(root, spec['app'], 'up', '-d', '--pull', 'never', '--no-build', 'app')
    compose(root, spec['app'], 'up', '-d', '--pull', 'never', '--no-build', 'gateway')
    # Resolve the recreated app's new IP without touching any other project.
    compose(root, spec['app'], 'restart', 'gateway')


def healthy(spec, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen('http://127.0.0.1:' + str(spec['port']) + spec['health'], timeout=2) as response:
                if response.status == 200:
                    items = owned(spec['app'], True)
                    if len(items) == 2 and all(i['State']['Running'] and not i['State']['OOMKilled'] for i in items):
                        app = next(i for i in items if i['Config']['Labels']['com.docker.compose.service'] == 'app')
                        if app['Image'] == spec['image'] and not app.get('Mounts'):
                            return True
        except (OSError, ValueError, Refused):
            pass
        time.sleep(0.5)
    return False


def event(directory, kind, **fields):
    path = directory / 'events.jsonl'
    with path.open('a') as out:
        os.chmod(path, 0o600)
        out.write(json.dumps({'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'event': kind, **fields}) + '\n')


def deploy(root, spec, rollback=False):
    validate_spec(spec)
    path = state_path(root, spec['app'])
    previous = json.loads(path.read_text()) if path.exists() else None
    directory = path.parent
    if (directory / 'pending.json').exists():
        raise Refused('unresolved_pending_deployment_requires_inspection')
    owned(spec['app'], bool(previous) or managed(root, spec['app']))
    image_id(spec['image'])
    image_id(spec['gateway_image'])
    available_port(root, spec, previous)
    if shutil.disk_usage(root).free < 25 * 1024 ** 3:
        raise Refused('less_than_25GiB_free')
    if not previous and len(all_states(root)) >= 4:
        raise Refused('four_app_capacity_limit')
    directory.mkdir(mode=0o700, exist_ok=True)
    save(directory / 'managed.json', {'app': spec['app'], 'owner': 'v1'})
    save(directory / 'pending.json', spec)
    event(directory, 'deploy_started', revision=spec['revision'], image=spec['image'])
    try:
        apply(root, spec)
        if not healthy(spec):
            raise Refused('release_health_failed')
    except (Refused, OSError):
        event(directory, 'deploy_failed', revision=spec['revision'])
        if previous:
            try:
                owned(spec['app'], True)
                apply(root, previous['current'])
                if not healthy(previous['current']):
                    raise Refused('rollback_health_failed')
            except (Refused, OSError):
                event(directory, 'automatic_rollback_failed')
                raise Refused('deploy_and_rollback_failed_pending_preserved') from None
            event(directory, 'automatic_rollback_passed', revision=previous['current']['revision'])
        else:
            # Only containers just created in this marked project. Preserve all evidence.
            owned(spec['app'], True)
            compose(root, spec['app'], 'stop')
            event(directory, 'first_release_stopped')
        (directory / 'pending.json').unlink()
        raise Refused('release_failed_previous_restored' if previous else 'release_failed_app_stopped') from None
    accepted = {'app': spec['app'], 'current': spec,
                'previous': previous['current'] if previous else None,
                'accepted_at': dt.datetime.now(dt.timezone.utc).isoformat()}
    save(path, accepted)
    (directory / 'releases').mkdir(mode=0o700, exist_ok=True)
    save(directory / 'releases' / (uuid.uuid4().hex + '.json'), accepted)
    event(directory, 'rollback_accepted' if rollback else 'deploy_accepted', revision=spec['revision'])
    (directory / 'pending.json').unlink()
    return accepted


def status(root):
    result = []
    for state in all_states(root):
        spec = state['current']
        items = owned(spec['app'], True)
        result.append({'app': spec['app'], 'revision': spec['revision'], 'image': spec['image'],
                       'url': 'http://localhost:' + str(spec['port']),
                       'previous_revision': (state.get('previous') or {}).get('revision'),
                       'pending': (state_path(root, spec['app']).parent / 'pending.json').exists(),
                       'healthy': healthy(spec, timeout=2),
                       'containers': [{'id': i['Id'], 'started': i['State']['StartedAt'],
                                       'running': i['State']['Running'], 'oom': i['State']['OOMKilled']}
                                      for i in items]})
    accepted_apps = {item['app'] for item in result}
    for directory in sorted((root / 'apps').iterdir()):
        if directory.is_dir() and directory.name not in accepted_apps:
            result.append({'app': directory.name, 'healthy': False, 'accepted': False,
                           'pending': (directory / 'pending.json').exists(),
                           'status': 'no_accepted_release_inspect_events'})
    return result


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('init', 'status', 'backup', 'recover'):
        sub.add_parser(command)
    p = sub.add_parser('deploy')
    p.add_argument('app', type=slug)
    p.add_argument('--image', required=True)
    p.add_argument('--gateway-image', required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--container-port', type=int, default=8080)
    p.add_argument('--health', default='/health')
    p = sub.add_parser('rollback')
    p.add_argument('app', type=slug)
    p = sub.add_parser('access')
    p.add_argument('app', type=slug)
    args = parser.parse_args()
    if args.command == 'init':
        initialize()
        print('Private stateless hosting initialized')
        return
    with locked():
        if args.command == 'deploy':
            spec = {key: getattr(args, key) for key in ('app', 'image', 'gateway_image', 'revision', 'port', 'container_port', 'health')}
            print(json.dumps(deploy(ROOT, spec)))
        elif args.command == 'rollback':
            state = json.loads(state_path(ROOT, args.app).read_text())
            if not state.get('previous'):
                raise Refused('no_previous_accepted_release')
            print(json.dumps(deploy(ROOT, state['previous'], rollback=True)))
        elif args.command == 'status':
            print(json.dumps(status(ROOT), indent=2))
        elif args.command == 'access':
            spec = json.loads(state_path(ROOT, args.app).read_text())['current']
            print('ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:{0}:127.0.0.1:{0} sergio@192.168.4.239'.format(spec['port']))
            print('http://localhost:' + str(spec['port']))
        elif args.command == 'backup':
            # Configuration/release history only: this stateless contract has no app volumes.
            name = ROOT / 'backups' / ('registry-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])
            shutil.make_archive(str(name), 'gztar', ROOT, 'apps')
            print(str(name) + '.tar.gz')
        elif args.command == 'recover':
            for state in all_states(ROOT):
                app = state['app']
                if (state_path(ROOT, app).parent / 'pending.json').exists():
                    raise Refused('pending_deployment_requires_inspection_' + app)
                owned(app, True)
                apply(ROOT, state['current'])
                if not healthy(state['current']):
                    raise Refused('recovery_health_failed_' + app)
            print('Accepted hosted apps recovered')


if __name__ == '__main__':
    try:
        main()
    except (Refused, OSError, ValueError, KeyError) as error:
        # Never echo exception bodies, configuration or environment values.
        print(str(error) if isinstance(error, Refused) else type(error).__name__, file=sys.stderr)
        sys.exit(1)
