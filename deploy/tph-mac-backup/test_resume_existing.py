import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

spec=importlib.util.spec_from_file_location('resume_existing',Path(__file__).with_name('resume_existing.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
oldspec=importlib.util.spec_from_file_location('recover_existing_for_tests',Path(__file__).with_name('recover_existing.py'))
old=importlib.util.module_from_spec(oldspec);oldspec.loader.exec_module(old)


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'private').mkdir()
        self.p=patch.object(r,'ROOT',self.root);self.p.start();self.addCleanup(self.p.stop)

    def plan(self):
        containers={name:dict(id=name,image='image',config_sha256='config',host_sha256='host',mounts_sha256='mount',running=False,started='original-'+name,health='unhealthy') for name in old.SERVICES}
        base={'containers':containers,'state':{'authority_sha256':r.AUTHORITY_SHA,'epoch':5,'watermark':8},'protected':{'same':True}}
        return base

    def original(self,base):
        original=Mock();original.database_snapshot.return_value=base['state'];original.protected_snapshot.return_value=base['protected']
        original.assert_runtime=Mock(side_effect=old.assert_runtime);original.write_once.side_effect=old.write_once
        return original

    def test_partial_state_restarted_first_two_or_inactive_changed_or_router_running_refuse(self):
        base=self.plan();expected=r.expected_partial(base)
        changes=[('mongo',{'started':'restarted'}),('railway-simulation',{'started':'restarted'}),('mongo',{'running':False}),('mac-backup',{'started':'restart-then-stop'}),('mac-backup',{'running':True}),('router',{'running':True}),('router',{'started':'changed-original'})]
        for name,change in changes:
            with self.subTest(name=name,change=change):
                actual=copy.deepcopy(expected);actual[name].update(change)
                original=self.original(base);original.container_snapshot.return_value=actual
                with patch.object(r,'provenance',return_value=base):
                    with self.assertRaises(RuntimeError):r.state_snapshot(original,Mock(),expected)
                original.docker.assert_not_called()

    def test_uncertain_state_or_protected_drift_refuses(self):
        base=self.plan();expected=r.expected_partial(base)
        for kind in ['state','protected']:
            original=self.original(base)
            if kind=='state':original.database_snapshot.return_value={'epoch':6}
            else:original.protected_snapshot.return_value={}
            with patch.object(r,'provenance',return_value=base):
                with self.assertRaises(RuntimeError):r.state_snapshot(original,Mock(),expected)
            original.docker.assert_not_called()

    def test_duplicate_resume_markers_never_cleared(self):
        for kind in ['started','failed','completed']:
            path=self.root/('private/existing-resume-'+kind+'.json');path.write_text('retained')
            with self.assertRaisesRegex(RuntimeError,'already attempted'):r.require_no_resume()
            self.assertEqual(path.read_text(),'retained');path.unlink()

    def test_single_router_start_preserves_original_failure(self):
        base=self.plan();actual=r.expected_partial(base);operator=Mock();original=self.original(base)
        proof={'ok':True};approved={'ready':True,'authority_probe':{'ok':True},'partial_runtime':copy.deepcopy(actual),'state':base['state'],'protected':base['protected'],'start_only':'router'}
        oldfailure=self.root/'private/existing-recovery-failed.json';oldfailure.write_text('original retained failure')
        def start(*args):
            self.assertEqual(args,('start','router'));actual['router'].update(running=True,started='new-router',health='healthy')
        original.docker.side_effect=start
        operator.inspect.side_effect=lambda name:{'State':{'Running':actual[name]['running'],'StartedAt':actual[name]['started'],'Health':{'Status':actual[name]['health']}}}
        def snapshot(_o,_p,expected):old.assert_runtime(actual,expected);return copy.deepcopy(actual)
        with patch.object(r,'inspect_resume',return_value=approved),patch.object(r,'state_snapshot',side_effect=snapshot),patch.object(r,'authority_probe',return_value=proof):
            result=r.resume(original,operator,approved)
        original.docker.assert_called_once_with('start','router');self.assertTrue(result['router_started_only'])
        self.assertEqual(oldfailure.read_text(),'original retained failure')
        self.assertTrue((self.root/'private/existing-resume-completed.json').exists())

    def test_failed_get_summary_retained_and_router_not_started(self):
        base=self.plan();original=self.original(base);partial=r.expected_partial(base)
        approved={'ready':True,'authority_probe':{'ok':True},'partial_runtime':partial,'state':base['state'],'protected':base['protected'],'start_only':'router'}
        diagnostic={'ok':False,'dockerExit':1,'timeout':False,'stderrBytes':99,'stderrSha256':'hash'}
        with patch.object(r,'inspect_resume',return_value=approved),patch.object(r,'state_snapshot',return_value=partial),patch.object(r,'authority_probe',return_value=diagnostic):
            with self.assertRaisesRegex(RuntimeError,'before router'):r.resume(original,Mock(),approved)
        original.docker.assert_not_called()
        failed=json.loads((self.root/'private/existing-resume-failed.json').read_text())
        self.assertEqual(failed['authority_diagnostics'],[diagnostic]);self.assertNotIn('stderr',failed)

    def test_probe_sanitizes_provider_body_and_stderr_and_timeout(self):
        original=Mock();original.D=['docker','--context','desktop-linux']
        result=subprocess.CompletedProcess([],1,b'private raw body',b'private raw error')
        with patch.object(r.subprocess,'run',return_value=result):diagnostic=r.authority_probe(original,{'id':'a'*64})
        self.assertFalse(diagnostic['ok']);self.assertEqual(diagnostic['stderrBytes'],17)
        self.assertNotIn('private',json.dumps(diagnostic))
        with patch.object(r.subprocess,'run',side_effect=subprocess.TimeoutExpired('command',15)):
            self.assertTrue(r.authority_probe(original,{'id':'a'*64})['timeout'])

    def test_inspection_failed_get_returns_not_ready_with_bounded_summary(self):
        base=self.plan();original=self.original(base);partial=r.expected_partial(base)
        with patch.object(r,'provenance',return_value=base),patch.object(r,'state_snapshot',return_value=partial),patch.object(r,'authority_probe',return_value={'ok':False,'httpStatus':503}):
            result=r.inspect_resume(original,Mock())
        self.assertFalse(result['ready']);self.assertEqual(result['authority_probe']['httpStatus'],503)
        with self.assertRaisesRegex(RuntimeError,'no successful authority'):r.resume(original,Mock(),result)
        original.docker.assert_not_called()

    def test_probe_http_parse_proof_and_success_stages(self):
        original=Mock();original.D=['docker']
        fields={k:True for k in ['database','source','watermark','pinUsage','authority','prefix']}
        cases=[({'httpStatus':503,'bodyJson':True},'http',False),({'httpStatus':200,'bodyJson':False},'parse',False),({'httpStatus':200,'bodyJson':True,'fields':{**fields,'authority':False}},'proof',False),({'httpStatus':200,'bodyJson':True,'fields':fields},'accepted',True)]
        for body,stage,ok in cases:
            with self.subTest(stage=stage),patch.object(r.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(body).encode(),b'')) as run:
                diagnostic=r.authority_probe(original,{'id':'a'*64})
                self.assertEqual((diagnostic['stage'],diagnostic['ok']),(stage,ok))
                self.assertIn('5051/authority',run.call_args.args[0][-2])
                self.assertNotIn('/checkpoint',run.call_args.args[0][-2])
        with patch.object(r.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'not json',b'')):
            self.assertEqual(r.authority_probe(original,{'id':'a'*64})['stage'],'parse')

    def test_provenance_binds_prior_failure_and_canonical_started_plan(self):
        plan={'containers':{},'state':{}};rawplan=json.dumps(plan,indent=2).encode()
        started={'approved_plan_sha256':r.sha(r.canonical(plan)),'starts':['mongo','railway-simulation','router']}
        files={'recover_existing.py':b'reviewed dependency','private/existing-recovery-reviewed-plan-v2.json':rawplan,'private/existing-recovery-started.json':json.dumps(started).encode(),'private/existing-recovery-failed.json':b'original failed evidence'}
        hashes={name:r.sha(data) for name,data in files.items()}
        for name,data in files.items():(self.root/name).write_bytes(data)
        with patch.object(r,'PROVENANCE',hashes):
            self.assertEqual(r.provenance(),plan)
            (self.root/'private/existing-recovery-failed.json').write_text('changed')
            with self.assertRaisesRegex(RuntimeError,'provenance'):r.provenance()


if __name__=='__main__':unittest.main()
