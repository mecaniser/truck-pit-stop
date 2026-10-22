import base64
import copy
import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import public_keys as k

N=base64.urlsafe_b64encode(bytes([255])*256).decode().rstrip('=')
KEY={'kty':'RSA','use':'sig','alg':'RS256','kid':'first','n':N,'e':'AQAB'}
class PublicKeysTests(unittest.TestCase):
 def test_valid_public_shape(self):self.assertEqual(k.validate_jwks({'keys':[KEY]}),{'keys':[KEY]})
 def test_private_duplicate_wrong_algorithm_weak(self):
  variants=[{**KEY,'d':'private'},{**KEY,'alg':'HS256'},{**KEY,'n':'AQAB'},{**KEY,'use':'enc'}]
  for value in variants:
   with self.subTest(value=list(value)):
    with self.assertRaises(ValueError):k.validate_jwks({'keys':[value]})
  with self.assertRaises(ValueError):k.validate_jwks({'keys':[KEY,KEY]})
 def test_fetch_exact_endpoint_and_deadline(self):
  response=unittest.mock.MagicMock();response.status=200;response.url=k.URL;response.read.return_value=json.dumps({'keys':[KEY]}).encode()
  context=unittest.mock.MagicMock();context.__enter__.return_value=response
  opener=unittest.mock.Mock();opener.open.return_value=context
  with patch.object(k.urllib.request,'build_opener',return_value=opener):
   value=k.fetch(datetime.datetime(2030,1,1,tzinfo=datetime.timezone.utc))
  request=opener.open.call_args.args[0];self.assertEqual(request.full_url,k.URL)
  self.assertEqual(opener.open.call_args.kwargs['timeout'],5)
  self.assertEqual(value['valid_until'],'2030-01-02T00:00:00+00:00')
 def test_redirect_refused(self):
  with self.assertRaises(ValueError):k.NoRedirect().redirect_request(None,None,302,'',{},k.URL)
 def test_failed_fetch_preserves_old_snapshot_expiry(self):
  with tempfile.TemporaryDirectory() as directory:
   cache=Path(directory).resolve();os.chmod(cache,0o755);path=cache/'current.json';path.write_bytes(b'old-expired-snapshot');os.chmod(path,0o644)
   with patch.object(k,'CACHE',cache),patch.object(k,'fetch',side_effect=TimeoutError()):
    with self.assertRaises(TimeoutError):k.refresh(cache)
   self.assertEqual(path.read_bytes(),b'old-expired-snapshot')
 def test_atomic_refresh_public_material_only(self):
  with tempfile.TemporaryDirectory() as directory:
   cache=Path(directory).resolve();os.chmod(cache,0o755)
   value={'version':1,'jwks':{'keys':[KEY]}}
   with patch.object(k,'CACHE',cache),patch.object(k,'fetch',return_value={**value,'valid_until':'2030-01-01'}):k.refresh(cache)
   self.assertEqual((cache/'current.json').stat().st_mode&0o777,0o644)
   self.assertEqual(len(list(cache.iterdir())),1)

if __name__=='__main__':unittest.main()
