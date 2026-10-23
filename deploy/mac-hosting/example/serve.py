"""Small credential-free hosting acceptance app; no external calls or app data."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json

REVISION = Path('/srv/revision').read_text().strip()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        code = 503 if REVISION == 'unhealthy' and self.path == '/health' else 200
        if self.path in ('/health', '/version'):
            body = json.dumps({'app': 'hosting-demo', 'revision': REVISION, 'status': 'ready' if code == 200 else 'failed'}).encode()
            kind = 'application/json'
        else:
            body = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                    '<title>Mac app hosting</title><style>body{font:18px system-ui;background:#101923;color:#edf5ff;max-width:700px;margin:12vh auto;padding:24px}'
                    'h1{font-size:48px}span{color:#74e6b1}code{background:#243345;padding:6px 10px;border-radius:8px}</style>'
                    '<span>Private Mac server · Running</span><h1>App hosting is ready.</h1>'
                    '<p>This app runs in its own isolated container, reached through SSH.</p>'
                    '<p>Release <code>' + REVISION + '</code></p>'
                    '<p>Deploy · Check health · Roll back</p></html>').encode()
            kind = 'text/html; charset=utf-8'
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
