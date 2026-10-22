import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
with patch.dict(os.environ,{'REHEARSAL_CONTROL_TOKEN':'a'*64}):
    import router
from provider_sink import FakeProvider
from control import Refused

class RouterPolicy(unittest.TestCase):
    def test_exact_reads_and_pin(self):
        for method,path in [('GET','/'),('GET','/spot-changes'),('GET','/api/addresses?id=BACKUP-REHEARSAL-001'),('GET','/static/js/main.abc.js'),('POST','/api/pin/verify-client')]:self.assertTrue(router.allowed(method,path))
    def test_native_mutation_and_ambiguous_paths_refused(self):
        for method,path in [('POST','/api/payments'),('POST','/api/bookings'),('POST','/api/pin/verify-client?x=1'),('GET','http://evil/'),('GET','//evil/api/addresses'),('GET','/api/%61ddresses'),('GET','/api/../addresses'),('HEAD','/'),('OPTIONS','/'),('GET','/api/addresses?id=a&id=b'),('GET','/api/addresses?name=.*')]:self.assertFalse(router.allowed(method,path),(method,path))
    def test_read_site_settings_requires_seeded_row(self):
        self.assertTrue(router.allowed('GET','/api/site-settings'));self.assertFalse(router.allowed('GET','/api/site-settings/admin'))

class FakeProviderPolicy(unittest.TestCase):
    def test_concurrent_same_business_effect_is_one(self):
        with tempfile.TemporaryDirectory() as root:
            p=FakeProvider(Path(root).resolve()/'fake.sqlite3');row={'scope':'synthetic','kind':'payment','business_id':'booking-1','payload_sha256':'a'*64,'operation_id':'fake-1'}
            with ThreadPoolExecutor(max_workers=10) as pool:receipts=list(pool.map(lambda _:p.accept(row),range(10)))
            self.assertEqual(len(set(receipts)),1);self.assertEqual(p.counts(),{'payment':1})
            with self.assertRaises(Refused):p.accept({**row,'payload_sha256':'b'*64})
            self.assertEqual(p.lookup(row).provider_receipt,receipts[0])

if __name__=='__main__':unittest.main()

import http.client
import json
import socket
import threading
from unittest.mock import Mock

class FakeControl:
    outcome=[]
    def __init__(self,*args):pass
    def state(self):return {'site':'railway-simulation','epoch':1,'phase':'active','watermark':0,'authority_id':'fake'}
    def admit(self,*args):return {'admission_id':'fake-admission'}
    def complete(self,identifier,outcome):self.outcome.append(outcome)
    def freeze(self,reason):self.outcome.append('frozen')

class FakeResponse:
    status=200
    def read(self,*args):return b'{"success":true}'
    def getheader(self,name,default=None):return 'application/json' if name=='Content-Type' else default
    def getheaders(self):return []

class IngressHTTP(unittest.TestCase):
    def setUp(self):
        FakeControl.outcome=[];self.backend=Mock();self.response=FakeResponse();self.backend.getresponse.return_value=self.response
        self.patches=[patch.object(router,'Control',FakeControl),patch.object(router,'checkpoint',return_value=None),patch.object(router,'backend_connection',return_value=self.backend)]
        for p in self.patches:p.start()
        self.server=router.BoundedServer(('127.0.0.1',0),router.Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        for p in reversed(self.patches):p.stop()
    def raw(self,lines,body=b''):
        s=socket.create_connection(self.server.server_address,timeout=3);s.sendall(('\r\n'.join(lines)+'\r\n\r\n').encode()+body);r=http.client.HTTPResponse(s);r.begin();status=r.status;r.read();r.close();s.close();return status
    def test_wrong_duplicate_host_and_upgrade_refused(self):
        for fields in [['Host: evil'],['Host: localhost:18310','Host: localhost:18310'],['Host: localhost:18310','Upgrade: websocket']]:
            self.assertEqual(self.raw(['GET / HTTP/1.1',*fields]),403)
        self.backend.request.assert_not_called()
    def test_pin_origin_and_duplicate_length_and_transfer_encoding_refused(self):
        body=b'{"pin":"123456"}'
        base=['POST /api/pin/verify-client HTTP/1.1','Host: localhost:18310','Content-Type: application/json']
        for fields in [[],['Origin: null'],['Origin: http://evil'],['Origin: http://localhost:18310','Content-Length: 16','Content-Length: 16'],['Origin: http://localhost:18310','Transfer-Encoding: chunked']]:
            self.assertEqual(self.raw(base+fields,body),403)
        self.backend.request.assert_not_called()
    def test_forwarding_headers_not_trusted(self):
        self.assertEqual(self.raw(['GET /api/addresses HTTP/1.1','Host: localhost:18310','X-Forwarded-Host: evil','X-Forwarded-Proto: https','X-API-Key: evil','X-Internal-Auth: true']),200)
        headers=self.backend.request.call_args.kwargs['headers']
        self.assertEqual(headers,{'Host':'localhost:18310','Accept-Encoding':'identity'})
    def test_unknown_native_outcome_freezes_and_denies(self):
        self.response.status=500;body=b'{"pin":"123456"}'
        result=self.raw(['POST /api/pin/verify-client HTTP/1.1','Host: localhost:18310','Origin: http://localhost:18310','Content-Type: application/json','Content-Length: '+str(len(body))],body)
        self.assertEqual(result,503);self.assertIn('unknown',FakeControl.outcome)

class NativeRootAssets(unittest.TestCase):
    def test_exact_webpack_assets_only(self):
        for path in ('/runtime-main.e6ad7d1f704215002408.js','/vendor-auth0.98c0f12278def948a14d.js','/main-4f064d56.ce2d65d23d75f297ec68.css','/6671.2bdab51149bac10c4b71.js','/tph-logo-desktop.avif'):
            self.assertTrue(router.allowed('GET',path),path)
            self.assertFalse(router.allowed('POST',path),path)
            self.assertFalse(router.allowed('GET',path+'?x=1'),path)
        for path in ('/api/jobs','/anything.js','/main-x.123.js','/runtime-main.e6ad7d1f704215002408.js.map','/%2e%2e/main-4f064d56.ce2d65d23d75f297ec68.css'):
            self.assertFalse(router.allowed('GET',path),path)
