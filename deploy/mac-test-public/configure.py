"""Prepare exact-host HTTPS ingress without starting it or touching workers."""
import copy
import hashlib
import json
from pathlib import Path
import re

HOSTS = {'dieselbridge': 'dieselbridge-test.elisprotech.com',
         'tph': 'tph-test.elisprotech.com'}
PROJECTS = {'dieselbridge': 'db-local-test', 'tph': 'tph-local-test'}
ROOT = Path.home() / 'mac-hosting/test-public'
STACKS = Path.home() / 'mac-hosting/test-stacks'


def plan(original, image):
    if set(original) != set(PROJECTS) or not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
        raise ValueError('Exact apps and immutable public TPH image required')
    result = copy.deepcopy(original)
    for app, spec in result.items():
        if spec['name'] != PROJECTS[app] or not spec['networks']['isolated']['internal']:
            raise ValueError('Unrecognized test stack')
        web = spec['services']['web']
        # The private generator intentionally shares environment objects; detach
        # this web-only override even when preparing directly from that generator.
        web['environment'] = copy.deepcopy(web['environment'])
        if app == 'dieselbridge':
            web['environment'].update(FRONTEND_URL='https://' + HOSTS[app],
                CORS_ORIGINS_STR='https://' + HOSTS[app], COOKIE_SECURE='true', COOKIE_DOMAIN='')
        else:
            web['image'] = image
        spec['services']['gateway']['ports'].append(
            '127.0.0.1:' + ('18210' if app == 'dieselbridge' else '18211') + ':8081')
        for name, service in original[app]['services'].items():
            if name not in ('web', 'gateway') and spec['services'][name] != service:
                raise ValueError('Worker or storage configuration changed')
    return result


def nginx(original, app):
    start = 'events { worker_connections 128; }\nhttp { server { listen 8080;\n'
    if not original.startswith(start) or not original.rstrip().endswith('} } }'):
        raise ValueError('Unexpected private nginx profile')
    body = original[len(start):original.rfind('} } }')] + '}\n'
    body = body.replace('proxy_set_header X-Forwarded-Proto $scheme;',
                        'proxy_set_header X-Forwarded-Proto https;')
    body = body.replace('location = /local-test/ready { proxy_pass http://web:5051/local-test/ready; }', '')
    deny = 'location ~ ^/(health|local-test|metrics)(/|$) { return 404; }\n'
    # Retain the existing private server byte-for-byte; append inside its http block.
    return original.rstrip()[:-1] + '\nserver { listen 8081; server_name ' + HOSTS[app] + ';\n' + deny + body + '}\n}\n'


def caddy(*, local):
    global_options = ('auto_https disable_redirects\n    skip_install_trust' if local
                      else 'auto_https disable_redirects\n    http_port 8088\n    https_port 8443')
    result = '{\n    admin off\n    ' + global_options + '\n    storage file_system ' + str(ROOT / 'private' / ('local-caddy' if local else 'public-caddy')) + '\n}\n'
    for app, host in HOSTS.items():
        address = 'https://' + host + (':18444' if local else '')
        bind = '127.0.0.1' if local else '192.168.4.239'
        headers = '\n'.join('            header_up ' + key + ' ' + value for key, value in {
            'Host': '{http.request.host}', 'X-Test-Host': '{http.request.host}',
            'X-Test-Method': '{http.request.method}', 'X-Test-Uri': '{http.request.uri}',
            'X-Test-Client-IP': '{http.request.remote.host}'}.items())
        result += address + ' {\n    bind ' + bind + '\n'
        if local: result += '    tls internal\n'
        result += '''    header {
        X-Robots-Tag "noindex, nofollow, noarchive"
        Cache-Control "no-store"
        -Server
    }
    route {
        @access path /_test-access /_test-access/logout
        handle @access {
            reverse_proxy 127.0.0.1:18680 {
''' + headers + '''
            }
        }
        @private path /verify /_test-access/* /_test-*
        handle @private {
            respond "Not found" 404
        }
        handle {
            forward_auth 127.0.0.1:18680 {
                uri /verify
''' + headers + '''
            }
            reverse_proxy 127.0.0.1:''' + ('18210' if app == 'dieselbridge' else '18211') + ''' {
                header_up -X-Test-*
                header_up Cookie "(^|; *)__Host-test-(access|csrf)=[^;]*" ""
            }
        }
    }
}
'''
        if not local:
            result += 'http://' + host + ' {\n    bind ' + bind + '\n    redir https://' + host + '{uri} 308\n}\n'
    # A mismatched Host on a valid SNI must never reach either app.
    result += ('https://:18444 {\n    bind 127.0.0.1\n    tls internal\n' if local else
               'https://:8443 {\n    bind 192.168.4.239\n') + '    respond "Unknown test application" 404\n}\n'
    if not local:
        result += 'http://:8088 {\n    bind 192.168.4.239\n    respond "Unknown test application" 404\n}\n'
    return result


def main():
    import os
    import sys
    os.umask(0o077)
    if (STACKS / '.owner').read_text() != 'macapps-test-stacks-v1\n' or STACKS.is_symlink():
        raise RuntimeError('Unknown test stack owner')
    ROOT.mkdir(mode=0o700, exist_ok=False)
    (ROOT / 'private').mkdir(mode=0o700)
    (ROOT / '.owner').write_text('macapps-test-public-v1\n')
    original = {app: json.loads((STACKS / project / 'compose.json').read_text()) for app, project in PROJECTS.items()}
    planned = plan(original, sys.argv[1])
    snapshot = {}
    for app, project in PROJECTS.items():
        for filename in ('compose.json', 'nginx.conf'):
            data = (STACKS / project / filename).read_bytes()
            (ROOT / 'private' / (project + '.' + filename + '.before')).write_bytes(data)
            snapshot[project + '/' + filename] = hashlib.sha256(data).hexdigest()
        (ROOT / (project + '.compose.pending.json')).write_text(json.dumps(planned[app], indent=2) + '\n')
        (ROOT / (project + '.nginx.pending.conf')).write_text(nginx((STACKS / project / 'nginx.conf').read_text(), app))
    (ROOT / 'private/source-hashes.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    (ROOT / 'Caddyfile.local').write_text(caddy(local=True))
    (ROOT / 'Caddyfile.public.DISABLED').write_text(caddy(local=False))
    print('Prepared only: no service, network or DNS changes')


if __name__ == '__main__':
    main()
