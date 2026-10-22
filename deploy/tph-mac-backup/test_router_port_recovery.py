import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

spec=importlib.util.spec_from_file_location('router_port',Path(__file__).with_name('router_port_recovery.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
oldspec=importlib.util.spec_from_file_location('router_port_old',Path(__file__).with_name('recover_existing.py'))
old=importlib.util.module_from_spec(oldspec);oldspec.loader.exec_module(old)


class PortRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();(self.root/'private').mkdir()
        p=patch.object(r,'ROOT',self.root);p.start();self.addCleanup(p.stop)

    def context(self):
        current={s:{'id':s,'running':s in ('mongo','railway-simulation'),'started':'original','health':'healthy'} for s in old.SERVICES}
        approved={'ready':True,'partial_runtime':current,'relay':{'pid':67282,'started':'old'},'start_only':'router','state':{'epoch':5,'watermark':8}}
        diagnostic=Mock();diagnostic.immediate_state.return_value={'running':True,'started':'new-router','health':'healthy'}
        resume=Mock();resume.state_snapshot.return_value=current;resume.authority_probe.return_value={'ok':True}
        original=Mock();original.write_once.side_effect=old.write_once
        return approved,diagnostic,resume,original

    def test_stop_revalidates_exact_identity_and_sends_only_single_term(self):
        identity={'pid':67282,'started':'same'}
        with patch.object(r,'relay_identity',return_value=identity),patch.object(r.os,'kill') as kill,patch.object(r.subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'',b'')),patch.object(r,'ports',return_value=[]):
            r.stop_exact_relay(Mock(),identity)
        kill.assert_called_once_with(67282,signal.SIGTERM)
        with patch.object(r,'relay_identity',return_value={'pid':100}),patch.object(r.os,'kill') as kill:
            with self.assertRaisesRegex(RuntimeError,'before TERM'):r.stop_exact_relay(Mock(),identity)
            kill.assert_not_called()

    def test_pid_reuse_or_unexpected_port_after_exit_refuses_without_second_signal(self):
        identity={'pid':67282,'started':'same'}
        for response,listeners in [(subprocess.CompletedProcess([],0,b'different start',b''),[]),(subprocess.CompletedProcess([],1,b'',b''),[{'pid':999,'listener':'127.0.0.1:18310'}])]:
            with patch.object(r,'relay_identity',return_value=identity),patch.object(r.os,'kill') as kill,patch.object(r.subprocess,'run',return_value=response),patch.object(r,'ports',return_value=listeners):
                with self.assertRaises(RuntimeError):r.stop_exact_relay(Mock(),identity)
                kill.assert_called_once_with(67282,signal.SIGTERM)

    def run_recovery(self,port_values,result=None,restore_error=None):
        approved,diagnostic,resume,original=self.context();newrelay={'pid':123,'started':'new'}
        result=result or {'exit':0,'uncertain':False}
        with patch.object(r,'inspect',return_value=approved),patch.object(r,'evidence'),patch.object(r,'stop_exact_relay') as stop,patch.object(r,'ports',side_effect=port_values),patch.object(r,'capture_router_start',return_value=result) as capture,patch.object(r,'restore_relay',side_effect=restore_error,return_value=newrelay) as restore,patch.object(r,'relay_identity',return_value=newrelay),patch.object(r,'status_get',return_value={'httpStatus':200}):
            try:reply=r.recover(diagnostic,resume,original,Mock(),approved);error=None
            except RuntimeError as e:reply=None;error=e
        return reply,error,stop,capture,restore,original

    def test_only_router_start_and_same_reviewed_relay_restore_positive(self):
        reply,error,stop,capture,restore,original=self.run_recovery([[],[]])
        self.assertIsNone(error);self.assertTrue(reply['reviewed_relay_restored'])
        stop.assert_called_once();capture.assert_called_once();self.assertEqual(capture.call_args.args[-1],'router');restore.assert_called_once();original.docker.assert_not_called()
        self.assertTrue((self.root/'private/router-port-completed.json').exists())

    def test_unexpected_docker_port_owner_blocks_relay_restore_without_kill(self):
        reply,error,stop,capture,restore,original=self.run_recovery([[],[{'pid':999,'listener':'127.0.0.1:18310'}]])
        self.assertIsNotNone(error);capture.assert_called_once();restore.assert_not_called();original.docker.assert_not_called()
        self.assertTrue((self.root/'private/router-port-failed.json').exists())

    def test_router_nonzero_or_uncertain_never_retries_or_restores(self):
        for result,marker in [({'exit':1,'uncertain':False},'failed'),({'exit':-15,'uncertain':True},'uncertain')]:
            for path in (self.root/'private').iterdir():path.unlink()
            reply,error,stop,capture,restore,original=self.run_recovery([[]],result=result)
            self.assertIsNotNone(error);capture.assert_called_once();restore.assert_not_called()
            self.assertTrue((self.root/('private/router-port-'+marker+'.json')).exists())

    def test_failed_relay_restoration_keeps_failure_without_retry_or_compensation(self):
        reply,error,stop,capture,restore,original=self.run_recovery([[],[]],restore_error=RuntimeError('restore failed'))
        self.assertIsNotNone(error);restore.assert_called_once();original.docker.assert_not_called()
        self.assertTrue((self.root/'private/router-port-failed.json').exists())

    def test_prior_port_attempt_or_changed_plan_refuses_all_mutation(self):
        for marker in ('started','failed','uncertain','completed'):
            path=self.root/('private/router-port-'+marker+'.json');path.write_text('keep')
            with self.assertRaisesRegex(RuntimeError,'already attempted'):r.no_attempt()
            self.assertEqual(path.read_text(),'keep');path.unlink()
        approved,diagnostic,resume,original=self.context()
        with patch.object(r,'inspect',return_value={}),patch.object(r,'stop_exact_relay') as stop,patch.object(r,'capture_router_start') as capture:
            with self.assertRaisesRegex(RuntimeError,'plan changed'):r.recover(diagnostic,resume,original,Mock(),approved)
            stop.assert_not_called();capture.assert_not_called()

    def test_occupied_port_blocks_restore_before_spawning_anything(self):
        with patch.object(r,'ports',return_value=[{'pid':999,'listener':'127.0.0.1:18310'}]),patch.object(r.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError,'occupied'):r.restore_relay(Mock(),Mock())
            spawn.assert_not_called()

    def test_unique_new_bounded_command_logs_do_not_overwrite_diagnostic_logs(self):
        original=Mock();original.D=[sys.executable,'-c',"import sys;sys.stderr.write('captured bind: address already in use');sys.exit(1)"]
        diagnostic=Mock()
        def terminate(client):
            if client.poll() is None:client.terminate();client.wait(timeout=3)
        diagnostic.terminate_client.side_effect=terminate
        oldlog=self.root/'private/router-diagnostic-stderr.log';oldlog.write_text('immutable prior evidence')
        result=r.capture_router_start(diagnostic,original,'router')
        self.assertEqual(result['exit'],1);self.assertTrue(result['known_bind_error'])
        self.assertEqual(oldlog.read_text(),'immutable prior evidence')
        self.assertEqual((self.root/'private/router-port-stderr.log').stat().st_mode & 0o777,0o600)
        with self.assertRaises(FileExistsError):r.capture_router_start(diagnostic,original,'router')

    def test_changed_container_state_blocks_relay_term_before_any_start(self):
        approved,diagnostic,resume,original=self.context();resume.state_snapshot.side_effect=RuntimeError('changed first-two/inactive boundary')
        with patch.object(r,'inspect',return_value=approved),patch.object(r,'evidence'),patch.object(r,'stop_exact_relay') as stop,patch.object(r,'capture_router_start') as capture:
            with self.assertRaisesRegex(RuntimeError,'boundary'):r.recover(diagnostic,resume,original,Mock(),approved)
            stop.assert_not_called();capture.assert_not_called()

    def test_captured_bind_evidence_hash_and_literal_error_are_required(self):
        diagnostic=Mock();diagnostic.prior_attempts.return_value={'original':True}
        files={'private/router-diagnostic-command.json':json.dumps({'result':{'exit':1,'known_bind_error':True,'uncertain':False}}).encode(),'private/router-diagnostic-stderr.log':b'bind: address already in use'}
        hashes={name:r.sha(data) for name,data in files.items()}
        for name,data in files.items():(self.root/name).write_bytes(data)
        with patch.object(r,'RECORDS',hashes):
            self.assertEqual(r.evidence(diagnostic,Mock()),{'original':True})
            (self.root/'private/router-diagnostic-stderr.log').write_text('changed')
            with self.assertRaisesRegex(RuntimeError,'evidence changed'):r.evidence(diagnostic,Mock())

    def test_restore_uses_exact_reviewed_argv_cwd_and_loopback_pid(self):
        (self.root/'tools').mkdir();source=self.root/'tools/relay.py';source.write_text('reviewedrelay')
        diagnostic=Mock();diagnostic.PYTHON='exact-approved-python';diagnostic.RELAY_SHA=r.sha(source.read_bytes())
        original=Mock();original.write_once.side_effect=old.write_once
        child=Mock();child.pid=123;child.poll.return_value=None
        identity={'pid':123,'listener':'127.0.0.1:18310'}
        with patch.object(r,'ports',side_effect=[[],[identity]]),patch.object(r.subprocess,'Popen',return_value=child) as spawn,patch.object(r,'relay_identity',return_value=identity):
            self.assertEqual(r.restore_relay(diagnostic,original),identity)
        self.assertEqual(spawn.call_args.args[0],['exact-approved-python',str(source)])
        self.assertEqual(spawn.call_args.kwargs['cwd'],Path.home())
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        self.assertTrue((self.root/'private/router-port-relay-launched.json').exists())


if __name__=='__main__':unittest.main()
