import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

spec=importlib.util.spec_from_file_location('diagnostic_router',Path(__file__).with_name('diagnostic_router_start.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
oldspec=importlib.util.spec_from_file_location('recovery_for_diagnostic_tests',Path(__file__).with_name('recover_existing.py'))
old=importlib.util.module_from_spec(oldspec);oldspec.loader.exec_module(old)


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();(self.root/'private').mkdir()
        p=patch.object(r,'ROOT',self.root);p.start();self.addCleanup(p.stop)

    def context(self):
        containers={s:dict(id=s,image='image',config_sha256='config',host_sha256='host',mounts_sha256='mounts',running=s in ('mongo','railway-simulation'),started='same',health='healthy') for s in old.SERVICES}
        approved={'ready':True,'partial_runtime':containers,'state':{'epoch':5},'protected':{'fixed':True},'relay':{'pid':67282},'start_only':'router'}
        original=Mock();original.write_once.side_effect=old.write_once;original.database_snapshot.return_value=approved['state'];original.protected_snapshot.return_value=approved['protected'];original.container_snapshot.return_value=containers;original.assert_runtime=Mock(side_effect=old.assert_runtime)
        resume=Mock();resume.state_snapshot.return_value=containers;resume.authority_probe.return_value={'ok':True}
        return approved,original,resume

    def test_prior_attempt_marker_refuses_all_repetition(self):
        for kind in ('started','failed','uncertain','completed'):
            path=self.root/('private/router-diagnostic-'+kind+'.json');path.write_text('retained')
            with self.assertRaisesRegex(RuntimeError,'already attempted'):r.no_attempt()
            self.assertEqual(path.read_text(),'retained');path.unlink()

    def test_nonzero_preserves_capture_and_never_retries_or_stops_relay(self):
        approved,original,resume=self.context();result={'exit':1,'uncertain':False,'known_bind_error':True}
        oldmarker=self.root/'private/existing-resume-failed.json';oldmarker.write_text('original retained')
        with patch.object(r,'inspect',return_value=approved),patch.object(r,'prior_attempts'),patch.object(r,'relay_snapshot',return_value=approved['relay']),patch.object(r,'capture_start',return_value=result) as capture,patch.object(r,'immediate_state',return_value={'running':False,'started':'same'}):
            reply=r.diagnose(resume,original,Mock(),approved)
        capture.assert_called_once_with(original,'router');self.assertTrue(reply['failed']);original.docker.assert_not_called()
        self.assertEqual(oldmarker.read_text(),'original retained')
        failed=json.loads((self.root/'private/router-diagnostic-failed.json').read_text());self.assertEqual(failed['result']['exit'],1)
        self.assertTrue((self.root/'private/router-diagnostic-command.json').exists())

    def test_timeout_remains_uncertain_without_retry(self):
        approved,original,resume=self.context()
        with patch.object(r,'inspect',return_value=approved),patch.object(r,'prior_attempts'),patch.object(r,'relay_snapshot',return_value=approved['relay']),patch.object(r,'capture_start',return_value={'exit':-15,'uncertain':True,'timeout':True}) as capture,patch.object(r,'immediate_state',return_value={'running':False,'started':'same'}):
            self.assertTrue(r.diagnose(resume,original,Mock(),approved)['uncertain'])
        capture.assert_called_once();self.assertTrue((self.root/'private/router-diagnostic-uncertain.json').exists())
        self.assertFalse((self.root/'private/router-diagnostic-completed.json').exists())

    def test_changed_plan_or_relay_refuses_before_start(self):
        for which in ('plan','relay'):
            for path in (self.root/'private').iterdir():path.unlink()
            approved,original,resume=self.context()
            with patch.object(r,'inspect',return_value={} if which=='plan' else approved),patch.object(r,'prior_attempts'),patch.object(r,'relay_snapshot',return_value={}),patch.object(r,'capture_start') as capture:
                with self.assertRaises(RuntimeError):r.diagnose(resume,original,Mock(),approved)
                capture.assert_not_called()

    def test_zero_exit_requires_single_healthy_new_start_and_proof(self):
        approved,original,resume=self.context();state={'running':True,'started':'authorized-new','health':'healthy'}
        with patch.object(r,'inspect',return_value=approved),patch.object(r,'prior_attempts'),patch.object(r,'relay_snapshot',return_value=approved['relay']),patch.object(r,'capture_start',return_value={'exit':0,'uncertain':False}) as capture,patch.object(r,'immediate_state',return_value=state):
            self.assertTrue(r.diagnose(resume,original,Mock(),approved)['completed'])
        capture.assert_called_once();self.assertTrue((self.root/'private/router-diagnostic-completed.json').exists())
        original.docker.assert_not_called()

    def test_relay_identity_requires_exact_pid_start_command_cwd_listener_and_source(self):
        (self.root/'tools').mkdir();source=self.root/'tools/relay.py';source.write_text('reviewedrelay')
        correct=[r.RELAY_START,r.PYTHON+' '+str(source),'p67282\nfcwd\nn'+str(Path.home()),'p67282\ncPython\nf3\nn127.0.0.1:18310']
        with patch.object(r,'RELAY_SHA',r.sha(source.read_bytes())),patch.object(r,'run_readonly',side_effect=correct):
            self.assertEqual(r.relay_snapshot()['pid'],67282)
        for at in range(4):
            changed=list(correct);changed[at]='unexpected'
            with patch.object(r,'RELAY_SHA',r.sha(source.read_bytes())),patch.object(r,'run_readonly',side_effect=changed):
                with self.assertRaises(RuntimeError):r.relay_snapshot()

    def capture(self,code):
        original=Mock();original.D=[sys.executable,'-c',code]
        return r.capture_start(original,'exact-router-id')

    def test_actual_child_capture_retains_private_stderr_and_known_error_only(self):
        result=self.capture("import sys;sys.stderr.write('bind: address already in use');sys.exit(1)")
        self.assertEqual(result['exit'],1);self.assertTrue(result['known_bind_error'])
        self.assertEqual((self.root/'private/router-diagnostic-stderr.log').read_text(),'bind: address already in use')
        self.assertNotIn('address already',json.dumps(result));self.assertFalse(result['uncertain'])

    def test_actual_child_output_limit_is_bounded_and_uncertain(self):
        with patch.object(r,'CAPTURE_LIMIT',64):result=self.capture("import sys;sys.stdout.write('x'*10000)")
        self.assertTrue(result['uncertain']);self.assertTrue(result['output_limit'])
        self.assertLessEqual(sum(x['bytes'] for x in result['capture'].values()),64)


if __name__=='__main__':unittest.main()
