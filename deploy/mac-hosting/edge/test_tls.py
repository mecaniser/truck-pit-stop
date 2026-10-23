"""Verify chain, hostname, routing and unknown-host handling; never bypass TLS."""
import json
from pathlib import Path
import socket
import ssl

ca = Path.home() / 'mac-hosting/edge/private/caddy/pki/authorities/local/root.crt'
context = ssl.create_default_context(cafile=str(ca))
results = []
for name, revision in [('alpha.macapps.test', 'v1'), ('beta.macapps.test', 'v2')]:
    with socket.create_connection(('127.0.0.1', 18443), timeout=5) as tcp:
        with context.wrap_socket(tcp, server_hostname=name) as tls:
            tls.sendall(('GET /version HTTP/1.1\r\nHost: ' + name + '\r\nConnection: close\r\n\r\n').encode())
            chunks = []
            while chunk := tls.recv(65536):
                chunks.append(chunk)
            response = b''.join(chunks)
            assert response.startswith(b'HTTP/1.1 200'), response[:100]
            assert json.loads(response.split(b'\r\n\r\n', 1)[1])['revision'] == revision
            results.append({'name': name, 'revision': revision, 'tls': tls.version(), 'verified': True})
# Valid TLS SNI followed by unknown Host must never reach an app.
with socket.create_connection(('127.0.0.1', 18443), timeout=5) as tcp:
    with context.wrap_socket(tcp, server_hostname='alpha.macapps.test') as tls:
        tls.sendall(b'GET /version HTTP/1.1\r\nHost: unknown.macapps.test\r\nConnection: close\r\n\r\n')
        assert tls.recv(1024).startswith(b'HTTP/1.1 404')
# Wrong server name must fail certificate verification; no local trust installed.
try:
    with socket.create_connection(('127.0.0.1', 18443), timeout=5) as tcp:
        with context.wrap_socket(tcp, server_hostname='wrong.macapps.test'):
            raise AssertionError('Wrong hostname accepted')
except (ssl.SSLError, ConnectionError):
    pass
print(json.dumps({'apps': results, 'unknown_host_rejected': True, 'wrong_tls_hostname_rejected': True}))
