import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import relay

class RelayBoundary(unittest.TestCase):
    def test_fixed_owned_cid_and_structured_stdin(self):
        response={'status':403,'body':'e30=','headers':[['Content-Type','application/json']]}
        with patch.object(relay.op,'safe') as safe,patch.object(relay.op,'inspect',return_value={'Id':'a'*64}) as inspect,patch.object(relay.op,'docker',return_value=json.dumps(response).encode()) as docker:
            self.assertEqual(relay.exchange('POST','/api/payments',b'{}',{'Origin':'null'})[0],403)
            safe.assert_called_once();inspect.assert_called_once_with('router')
            args=docker.call_args.args[0];self.assertEqual(args[:3],['exec','-i','a'*64]);self.assertNotIn('/api/payments',args)
            payload=json.loads(docker.call_args.kwargs['stdin']);self.assertEqual(payload['headers']['Host'],'localhost:18310')
    def test_identity_failure_prevents_exec(self):
        with patch.object(relay.op,'safe'),patch.object(relay.op,'inspect',side_effect=RuntimeError('identity drift')),patch.object(relay.op,'docker') as docker:
            with self.assertRaises(RuntimeError):relay.exchange('GET','/')
            docker.assert_not_called()
