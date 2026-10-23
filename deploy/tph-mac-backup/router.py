"""Fail-closed ingress for an isolated synthetic TPH switch rehearsal."""
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import threading
from urllib.parse import parse_qs, urlsplit
import uuid
from control import Control, Refused

STATE='/state/control.sqlite3'
ORIGIN='http://localhost:18310'
TOKEN=os.environ['REHEARSAL_CONTROL_TOKEN']
MAX_RESPONSE=12*1024*1024
MUTATION=threading.Lock()


def auxiliary(site,path,body=None):
    if site not in ('railway-simulation','mac-backup'):raise Refused('unknown_site')
    c=http.client.HTTPConnection(site,5051,timeout=5)
    try:
        c.request('POST' if body is not None else 'GET',path,body=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-Rehearsal-Control':TOKEN})
        r=c.getresponse();data=r.read(8192)
        if r.status!=200:raise Refused('shared_data_unavailable')
        return json.loads(data)
    finally:c.close()


def checkpoint(control,site):
    state=control.state()
    try:auxiliary(site,'/checkpoint',{'authority_id':state['authority_id'],'watermark':state['watermark']})
    except Exception:
        control.freeze('shared_data_checkpoint_uncertain')
        raise Refused('shared_data_checkpoint_uncertain') from None


def allowed(method,raw):
    value=urlsplit(raw)
    if value.scheme or value.netloc or value.fragment or len(raw)>500 or '%' in value.path or '..' in value.path or '//' in value.path:return False
    path=value.path
    if method=='POST':return path=='/api/pin/verify-client' and not value.query
    if method!='GET':return False
    query=parse_qs(value.query,keep_blank_values=True,strict_parsing=True) if value.query else {}
    if any(len(v)!=1 for v in query.values()):return False
    if path=='/api/addresses':
        if not set(query)<={'id','limit','skip'}:return False
        return all(re.fullmatch(r'[A-Za-z0-9_-]{1,64}',v[0]) for v in query.values())
    if path in ('/','/spot-changes','/api/site-settings','/api/spot-changes/daily-spots'):return not query
    if query:return False
    if re.fullmatch(r'/(?:runtime-main|vendor-[A-Za-z0-9_-]+|main-[a-f0-9]+|[0-9]+)\.[a-f0-9]{16,64}\.(?:js|css)',path):return True
    return bool(re.fullmatch(r'/static/(js|css|media)/[A-Za-z0-9_.-]+',path) and not path.endswith('.map')) or bool(re.fullmatch(r'/[A-Za-z0-9_-]+\.(ico|png|svg|webp|jpg|json|avif)',path))


def backend_connection(site):
    if site not in ('railway-simulation','mac-backup'):raise Refused('unknown_site')
    return http.client.HTTPConnection(site,5050,timeout=10)


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def setup(self):super().setup();self.connection.settimeout(15)
    def reply(self,status,body,kind='application/json',headers=None):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Backup-Rehearsal','synthetic-only');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Robots-Tag','noindex, nofollow');self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'self'; connect-src 'self'; form-action 'self'; frame-src 'none'; object-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; frame-ancestors 'none'; base-uri 'self'")
        for k,v in (headers or []):self.send_header(k,v)
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(body)
    def denied(self,status=403,reason='rehearsal_route_denied'):
        self.close_connection=True;self.reply(status,json.dumps({'error':reason,'live_activation':'blocked'}).encode())
    def do_GET(self):self.handle_request()
    def do_POST(self):self.handle_request()
    def do_HEAD(self):self.denied()
    def do_OPTIONS(self):self.denied()
    def do_PUT(self):self.denied()
    def do_PATCH(self):self.denied()
    def do_DELETE(self):self.denied()
    def handle_request(self):
        admission=None;control=None;state=None
        try:
            if self.headers.get_all('Host',[]) not in (['localhost:18310'],['127.0.0.1:18310']):return self.denied()
            if self.headers.get('Upgrade') or self.headers.get('Transfer-Encoding'):return self.denied()
            if self.command=='GET' and (self.headers.get('Content-Length') not in (None,'0')):return self.denied()
            control=Control(STATE);state=control.state()
            if self.command=='GET' and self.path=='/__backup/status':
                return self.reply(200,json.dumps({'simulation':True,'primary':'Railway simulation (on this Mac)','active_site':state['site'],'epoch':state['epoch'],'phase':state['phase'],'watermark':state['watermark'],'live_activation':'blocked','rpo':'zero; stale/uncertain data blocks switching'}).encode())
            if state['phase']!='active':return self.denied(503,'rehearsal_frozen_or_draining')
            if not allowed(self.command,self.path):return self.denied()
            body=None
            lock=MUTATION if self.command=='POST' else threading.Lock()
            with lock:
                if self.command=='POST':
                    if self.headers.get('Origin')!=ORIGIN or self.headers.get('Content-Type')!='application/json' or len(self.headers.get_all('Content-Length',[]))!=1:return self.denied()
                    length=self.headers.get('Content-Length','')
                    if not length.isdigit() or not 1<=int(length)<=1024:return self.denied()
                    body=self.rfile.read(int(length));value=json.loads(body)
                    if set(value)!={'pin'} or not isinstance(value['pin'],str) or not re.fullmatch('[0-9]{6}',value['pin']):return self.denied()
                    admission=control.admit(state['site'],state['epoch'],uuid.uuid4().hex,{'path':self.path,'method':'POST'})
                c=backend_connection(state['site'])
                try:
                    headers={'Host':'localhost:18310','Accept-Encoding':'identity'}
                    for name in ('Authorization','Cookie','Content-Type','Origin'):
                        if self.headers.get(name):headers[name]=self.headers[name]
                    c.request(self.command,self.path,body=body,headers=headers);r=c.getresponse();data=r.read(MAX_RESPONSE+1)
                    if len(data)>MAX_RESPONSE:raise Refused('rehearsal_response_limit')
                    if admission:
                        if r.status==200 and json.loads(data).get('success') is True:
                            control.complete(admission['admission_id'],'accepted');checkpoint(control,state['site'])
                        elif 400<=r.status<500:control.complete(admission['admission_id'],'rejected')
                        else:control.complete(admission['admission_id'],'unknown');return self.denied(503,'native_pin_outcome_unknown')
                    kind=r.getheader('Content-Type','application/octet-stream')
                    if 'text/html' in kind:
                        label='Railway simulation (both hosts run on this Mac)' if state['site']=='railway-simulation' else 'Mac backup (synthetic rehearsal)'
                        banner=('<div style="background:#ffe58f;color:#111;padding:10px;text-align:center;font:14px sans-serif">FAILOVER REHEARSAL — '+label+' — Fake data. Bookings, payments and messages blocked.</div>').encode()
                        data=data.replace(b'<body>',b'<body>'+banner,1)
                    forwarded=[(k,v) for k,v in r.getheaders() if k.lower() in ('set-cookie',)]
                    forwarded.append(('X-Rehearsal-Active-Site',state['site']))
                    self.reply(r.status,data,kind,forwarded)
                finally:c.close()
        except Exception:
            if admission and control:
                try:control.complete(admission['admission_id'],'unknown')
                except Exception:control.freeze('native_pin_outcome_uncertain')
            try:self.denied(503,'rehearsal_unavailable')
            except Exception:pass


class BoundedServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(32)
        super().__init__(*args,**kwargs)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            try:request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally:self.shutdown_request(request)
            return
        try:super().process_request(request,address)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,*args):
        try:super().process_request_thread(*args)
        finally:self.slots.release()


if __name__=='__main__':
    os.umask(0o077)
    BoundedServer(('0.0.0.0',18310),Handler).serve_forever()
