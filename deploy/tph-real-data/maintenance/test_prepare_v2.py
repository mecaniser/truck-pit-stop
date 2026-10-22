import importlib.util
from pathlib import Path
import unittest
import prepare_v2 as p

class PrepareTests(unittest.TestCase):
 def old(self):
  root=Path('/Users/sergio/mac-hosting/tph-real-data-v3')
  return root,{'services':{'mongo':{'image':'fixed'},'web':{'environment':{'unchanged':'yes'},'volumes':[str(root/'phase2-auth0/clone-web-auth0.cjs')+':/usr/src/app/tph-web.cjs:ro',str(root/'phase2-auth0/auth0-jwks.json')+':/run/clone/auth0-jwks.json:ro','fixed-base:/run/clone/auth0_cached_jwks.cjs:ro']},'gateway':{'volumes':[str(root/'ui-fix-html-v1/nginx.conf')+':/etc/nginx/nginx.conf:ro']}},'networks':{'isolated':{'internal':True}}}
 def test_spec_only_mounts_change(self):
  root,old=self.old();new=p.spec_for(old,root)
  self.assertEqual(new['services']['mongo'],old['services']['mongo']);self.assertEqual(new['networks'],old['networks'])
  self.assertEqual(new['services']['web']['environment'],old['services']['web']['environment'])
  self.assertIn(str(root/'auth0-public-keys')+':/run/clone/auth0-public-keys:ro',new['services']['web']['volumes'])
 def test_exact_routes_only(self):
  raw=b"http {\n default 0;\nsub_filter '<body>' $clone_html_body;\n}"
  fixed=p.nginx(raw).decode()
  self.assertEqual(fixed.count('map_hash_bucket_size 128;'),1)
  self.assertTrue(fixed.startswith('http {\nmap_hash_bucket_size 128;\n'))
  for route in p.ROUTES:
   self.assertIn('"GET:'+route+'" 1;',fixed);self.assertIn('"HEAD:'+route+'" 1;',fixed)
  for denied in ('/api/profile','/api/admin/operations/summary','/api/admin/hiring','POST:/api/admin/pins'):self.assertNotIn(denied,fixed)
 def test_duplicate_bucket_directive_refused(self):
  with self.assertRaises(RuntimeError):p.nginx(b"http {\nmap_hash_bucket_size 64;\n default 0;\nsub_filter '<body>' $clone_html_body;\n}")
 def test_hourly_schedule_and_only_public_fetcher(self):
  row=p.launchagent(Path('/Users/sergio/mac-hosting/tph-real-data-v3'))
  self.assertEqual(row['StartInterval'],900);self.assertTrue(row['RunAtLoad']);self.assertEqual(row['Label'],p.LABEL)
  self.assertEqual(row['ProgramArguments'][0],'/opt/homebrew/bin/python3');self.assertNotIn('EnvironmentVariables',row)

if __name__=='__main__':unittest.main()
