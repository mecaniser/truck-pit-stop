"""Canonical-Origin TLS fixture acceptance, not public browser acceptance.

Runs on the dedicated Mac. Credentials remain in memory and private files.
Never enqueues workers or performs business mutations.
"""
import datetime
import http.client
from http.cookies import SimpleCookie
import json
from pathlib import Path
import re
import socket
import ssl
from urllib.parse import urlencode

ROOT = Path.home() / 'mac-hosting/test-public'
HOSTS = ('dieselbridge-test.elisprotech.com', 'tph-test.elisprotech.com')


class Connection(http.client.HTTPSConnection):
    def connect(self):
        self.sock = self._context.wrap_socket(socket.create_connection(('127.0.0.1', 18444), timeout=15),
                                              server_hostname=self.host)


class Client:
    def __init__(self, host, context):
        self.host, self.context, self.cookies = host, context, {}

    def request(self, path, method='GET', data=None, headers=None):
        headers = dict(headers or {})
        if self.cookies:
            headers.setdefault('Cookie', '; '.join(k + '=' + v for k, v in self.cookies.items()))
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        connection = Connection(self.host, context=self.context, timeout=15)
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        body, status, fields = response.read(), response.status, response.getheaders()
        for key, value in fields:
            if key.lower() == 'set-cookie':
                jar = SimpleCookie(); jar.load(value)
                for name, item in jar.items():
                    if item['max-age'] == '0': self.cookies.pop(name, None)
                    else: self.cookies[name] = item.value
        connection.close()
        return status, body, fields

    def gate_login(self, password):
        status, body, _ = self.request('/_test-access')
        assert status == 200, ('gate_form', status)
        csrf = re.search(rb'name="csrf" value="([^"]+)"', body).group(1).decode()
        form = urlencode({'csrf': csrf, 'password': password}).encode()
        status, _, fields = self.request('/_test-access', 'POST', form, {
            'Origin': 'https://' + self.host, 'Content-Type': 'application/x-www-form-urlencoded'})
        assert status == 303, ('gate_login', status)
        access = next(v for k, v in fields if k.lower() == 'set-cookie' and v.startswith('__Host-test-access='))
        assert all(flag in access for flag in ('Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/'))
        assert 'Domain=' not in access


def main(public=False):
    global Connection
    ca = ROOT / 'private/local-caddy/pki/authorities/local/root.crt'
    if public:
        # Standard DNS, port443 and system trust. No custom resolver or CA bypass.
        Connection = http.client.HTTPSConnection
        context = ssl.create_default_context()
    else:
        context = ssl.create_default_context(cafile=str(ca))
    password = json.loads((ROOT / 'private/operator-access.json').read_text())['password']
    credentials = json.loads((Path.home() / 'mac-hosting/test-stacks/private/credentials.json').read_text())
    clients = {host: Client(host, context) for host in HOSTS}
    for host, client in clients.items():
        assert client.request('/', headers={'Accept': 'text/html'})[0] == 303
        assert client.request('/api/private', headers={'Accept': 'text/html'})[0] == 403
        assert client.request('/api/private?id=LOCALTEST-001', headers={'Accept': 'text/html'})[0] == 403
        assert client.request('/api/private', 'POST', b'', {'Accept': 'text/html'})[0] == 403
        assert client.request('/verify')[0] == 404
        client.gate_login(password)
        status, body, _ = client.request('/')
        assert status == 200 and b'LOCAL TEST - Synthetic data' in body, ('native_page', host, status)
        assert client.request('/health/ready')[0] == 404
        assert client.request('/local-test/ready')[0] == 404
        assert client.request('/', headers={'Host': 'unknown.invalid'})[0] == 404
    db, tph = (clients[host] for host in HOSTS)
    saved = tph.cookies.copy()
    tph.cookies = db.cookies.copy()
    assert tph.request('/api/addresses')[0] == 403
    tph.cookies = saved
    ids, tokens = {}, {}
    for name in ('alpha', 'beta'):
        status, body, fields = db.request('/api/v1/auth/login', 'POST', {
            'email': 'staging-' + name + '@example.com', 'password': credentials[name]})
        assert status == 200, ('native_db_login', name, status)
        tokens[name] = json.loads(body)['access_token']
        cookies = [v for k, v in fields if k.lower() == 'set-cookie']
        assert cookies and all('Secure' in value for value in cookies)
        status, body, _ = db.request('/api/v1/customers', headers={'Authorization': 'Bearer ' + tokens[name]})
        rows = json.loads(body)
        assert status == 200 and len(rows) == 1, ('native_bearer', status)
        ids[name] = rows[0]['id']
    for name, other in (('alpha', 'beta'), ('beta', 'alpha')):
        assert db.request('/api/v1/customers/' + ids[other], headers={'Authorization': 'Bearer ' + tokens[name]})[0] in (403, 404)
    status, body, _ = tph.request('/api/pin/verify-client', 'POST', {'pin': credentials['manager_pin']},
        {'Origin': 'https://' + HOSTS[1]})
    assert status == 200 and json.loads(body)['success'] is True
    assert json.loads(body)['managerToken']
    status, body, _ = tph.request('/api/addresses?id=LOCALTEST-001')
    result = json.loads(body)
    assert status == 200 and result['total'] == 1 and result['addresses'][0]['id'] == 'LOCALTEST-001'
    for bad_origin in ('http://' + HOSTS[1], 'https://' + HOSTS[1] + '.invalid'):
        assert tph.request('/api/addresses?id=LOCALTEST-001', headers={'Origin': bad_origin})[0] == 403
    assert tph.request('/api/pin/verify-client', 'POST', {'pin': '000000'})[0] == 403
    assert tph.request('/api/admin/hiring')[0] in (401, 403)
    assert tph.request('/api/addresses/LOCALTEST-HIDDEN')[0] == 404
    for client in clients.values():
        status, body, _ = client.request('/_test-access')
        csrf = re.search(rb'name="csrf" value="([^"]+)"', body).group(1).decode()
        form = urlencode({'csrf': csrf}).encode()
        assert client.request('/_test-access/logout', 'POST', form, {
            'Origin': 'https://' + client.host, 'Content-Type': 'application/x-www-form-urlencoded'})[0] == 303
        assert client.request('/api/addresses')[0] == 403
    receipt = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'tls_chain_and_hostnames': True, 'gate_native_auth_and_negatives': True,
        'native_bearer_preserved': True, 'db_secure_cookies': True, 'tenant_denials_both_directions': True,
        'cross_host_gate_denied': True, 'logout_denied_afterwards': True,
        'public_readiness_and_unknown_hosts_denied': True, 'synthetic_business_mutations': False,
        'authenticated_query_api_preserved': True,
        'native_tph_exact_https_origin_and_lookalike_denial': True,
        'canonical_origin_fixture_only': not public, 'public_tls_verified': public,
        'public_browser_acceptance': False}
    name = 'public-tls-http-receipt.json' if public else 'local-tls-receipt.json'
    (ROOT / 'private' / name).write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    try:
        import argparse
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--public', action='store_true')
        main(parser.parse_args().public)
    except Exception as error:
        # HTTP responses and exception text can contain credentials; keep them private.
        raise SystemExit('Local TLS fixture acceptance failed: ' + type(error).__name__) from None
