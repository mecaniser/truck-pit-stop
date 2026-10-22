"""Loopback-only operator relay over Docker exec; containers retain zero internet routes."""
import base64
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading

spec=importlib.util.spec_from_file_location('backup_operator',Path(__file__).with_name('operator.py'));op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)
CLIENT="""import sys,json,http.client,base64
v=json.load(sys.stdin);c=http.client.HTTPConnection('127.0.0.1',18310,timeout=15)
c.request(v['method'],v['path'],body=base64.b64decode(v['body']) if v['body'] else None,headers=v['headers'])
r=c.getresponse();b=r.read(12582913)
if len(b)>12582912:raise RuntimeError('response_limit')
print(json.dumps({'status':r.status,'headers':r.getheaders(),'body':base64.b64encode(b).decode()}));c.close()
"""
def exchange(method,path,body=b'',headers=None):
    if (op.ROOT/'private/router-revision-uncertain.json').exists():raise RuntimeError('Router revision uncertain')
    op.safe();identity=op.inspect('router')
    value={'method':method,'path':path,'body':base64.b64encode(body).decode(),'headers':{'Host':'localhost:18310',**(headers or {})}}
    raw=op.docker(['exec','-i',identity['Id'],'python','-c',CLIENT],stdin=json.dumps(value).encode(),timeout=25,log='relay-exchange')
    result=json.loads(raw);return result['status'],base64.b64decode(result['body']),result['headers']

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def setup(self):super().setup();self.connection.settimeout(20)
    def handle_request(self):
        try:
            if self.headers.get_all('Host') not in (['localhost:18310'],['127.0.0.1:18310']) or self.headers.get('Transfer-Encoding') or self.headers.get('Upgrade'):raise ValueError('framing')
            lengths=self.headers.get_all('Content-Length',[])
            if len(lengths)>1:raise ValueError('length')
            length=int(lengths[0]) if lengths else 0
            if not 0<=length<=1024:raise ValueError('length')
            body=self.rfile.read(length)
            headers={name:self.headers[name] for name in ('Origin','Content-Type','Cookie','Authorization') if self.headers.get(name)}
            if len(self.headers.get_all('Origin',[]))>1:raise ValueError('origin')
            status,data,response_headers=exchange(self.command,self.path,body,headers)
            if any(k.lower()=='content-type' and 'text/html' in v for k,v in response_headers):
                data=data.replace(b'background:#ffe58f;color:#111;padding:10px;text-align:center;font:14px sans-serif',b'position:fixed;bottom:0;left:0;right:0;z-index:2147483647;background:#ffe58f;color:#111;padding:10px;text-align:center;font:14px sans-serif',1)
            self.send_response(status)
            for k,v in response_headers:
                if k.lower() not in ('connection','transfer-encoding','content-length','server','date'):self.send_header(k,v)
            self.send_header('Content-Length',str(len(data)));self.end_headers()
            if self.command!='HEAD':self.wfile.write(data)
        except Exception:
            self.send_response(503);self.send_header('Content-Length','0');self.end_headers()
    do_GET=do_POST=do_HEAD=do_OPTIONS=do_PUT=do_PATCH=do_DELETE=handle_request
class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args):self.slots=threading.BoundedSemaphore(16);super().__init__(*args)
    def process_request(self,*args):
        self.slots.acquire()
        try:super().process_request(*args)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,*args):
        try:super().process_request_thread(*args)
        finally:self.slots.release()
if __name__=='__main__':
    op.safe();op.inspect('router');Server(('127.0.0.1',18310),Handler).serve_forever()
