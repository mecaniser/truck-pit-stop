import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import runtime_v2 as r

class RuntimeTests(unittest.TestCase):
 def contract(self):
  contract=r.approval_contract('a'*64,'b'*64,'c'*64)
  return contract,{**contract,'qa':{'reviewer':'freshQA','reference':'review','decision':'GO'},'security':{'reviewer':'freshSecurity','reference':'security','decision':'GO'},'expires_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat()}
 def test_independent_exact_approval(self):
  contract,value=self.contract();r.validate_approval(value,contract)
 def test_changed_binding_selfreview_and_expired_refused(self):
  for kind in ('binding','self','expiry','same'):
   contract,value=self.contract()
   if kind=='binding':value['old_web_cid']='different'
   elif kind=='self':value['qa']['reviewer']='hosting_contract'
   elif kind=='same':value['security']['reviewer']=value['qa']['reviewer']
   else:value['expires_at']='2020-01-01T00:00:00+00:00'
   with self.subTest(kind=kind):
    with self.assertRaises(RuntimeError):r.validate_approval(value,contract)
 def test_existing_journal_refuses_without_docker(self):
  with tempfile.TemporaryDirectory() as directory:
   runner=r.Runner(Path(directory).resolve());runner.directory.mkdir(parents=True)
   with patch.object(runner.r,'command',side_effect=AssertionError('docker forbidden')):
    with self.assertRaisesRegex(RuntimeError,'uncertain_or_already_started'):runner.execute('a'*64,'b'*64)
 def test_other_services_never_recreated(self):
  runner=r.Runner()
  for service in ('mongo','worker','identity-worker'):
   with self.assertRaisesRegex(RuntimeError,'service_refused'):runner.compose(service,{})
 def test_failed_attempt_boundary_refuses_if_original_started(self):
  with tempfile.TemporaryDirectory() as directory:
   runner=r.Runner(Path(directory).resolve());runner.private.mkdir();(runner.private/'maintenance-started.json').write_bytes(b'{}')
   with self.assertRaisesRegex(RuntimeError,'old_attempt_passed_preactivation_boundary'):runner.failed_attempt()
 def test_failed_receipt_contract_binds_known_source_and_failure(self):
  value=r.approval_contract('a'*64,'b'*64,'c'*64)
  self.assertEqual(value['previous_runner_sha256'],'3ab6a63ad88008857f76c4d0c315b5a7c7744e473936a39c66111576783436f6')
  self.assertEqual(value['failed_stderr_sha256'],r.FAILED_STDERR_SHA)
 def test_fixed_phase2_helper_hash_still_matches(self):
  self.assertEqual(r.p.load_helper().PLAN_SHA,'695f276e35f16a54ee8ac6759f63e4196b09d0f99743b0ed53f8ccb53aa95dcf')

if __name__=='__main__':unittest.main()
