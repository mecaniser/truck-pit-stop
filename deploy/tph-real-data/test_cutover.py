"""Prove that edge transformation refuses ambiguous or wrong-host upstreams."""
import unittest
from unittest.mock import patch
import datetime
import json
from pathlib import Path
import tempfile
import cutover


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.prefix = b'https://dieselbridge-test.elisprotech.com { reverse_proxy 127.0.0.1:18210 { } }\n'
        self.target = b'https://tph-test.elisprotech.com { forward_auth 127.0.0.1:18680 { uri /verify } reverse_proxy 127.0.0.1:18211 { header_up -X-Test-* } }\n'
        self.suffix = b'http://tph-test.elisprotech.com { redir https://tph-test.elisprotech.com{uri} 308 }\n'

    def test_only_target_upstream_changes(self):
        original = self.prefix + self.target + self.suffix
        result = cutover.new_configuration(original)
        self.assertEqual(result, original.replace(b'reverse_proxy 127.0.0.1:18211 {',b'reverse_proxy 127.0.0.1:18221 {'))
        self.assertTrue(result.startswith(self.prefix))
        self.assertTrue(result.endswith(self.suffix))
        self.assertIn(b'forward_auth 127.0.0.1:18680 { uri /verify }',result)
        self.assertIn(b'header_up -X-Test-*',result)

    def test_wrong_host_refused(self):
        with self.assertRaises(RuntimeError):
            cutover.new_configuration(self.prefix.replace(b'18210',b'18211') + self.target.replace(b'18211',b'18212') + self.suffix)

    def test_duplicate_upstream_refused(self):
        with self.assertRaises(RuntimeError):
            cutover.new_configuration(self.prefix.replace(b'18210',b'18211') + self.target + self.suffix)

    def test_already_cutover_refused(self):
        with self.assertRaises(RuntimeError):
            cutover.new_configuration((self.prefix+self.target+self.suffix).replace(b'18211',b'18221'))

    def test_upstream_outside_https_target_refused(self):
        with self.assertRaises(RuntimeError):
            cutover.new_configuration(self.prefix + self.target.replace(b'18211',b'18212') + self.suffix + b'reverse_proxy 127.0.0.1:18211 {')

    def test_gate_cookie_scope_preserves_csrf_and_other_host(self):
        source = b'''ACCESS='access'
CSRF='csrf'
def cookie(name, value, ttl):
    return f"{name}={value}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age={ttl}"
def login(host,token):
    return cookie(ACCESS, token, ACCESS_TTL)
def logout(host):
    return cookie(ACCESS, "", 0)
def form(host):
    return f'<p>Synthetic data. Test access only.</p>'
'''
        with patch.object(cutover,'OLD_GATE_SHA',cutover.sha(source)):
            result=cutover.new_gate(source)
        namespace={};exec(compile(result,'gate-test','exec'),namespace)
        cookie=namespace['cookie']
        self.assertIn('SameSite=Lax',cookie('access','signed',28800,'tph-test.elisprotech.com'))
        for name,host in [('csrf','tph-test.elisprotech.com'),('access','dieselbridge-test.elisprotech.com'),('access',None)]:
            self.assertIn('SameSite=Strict',cookie(name,'signed',28800,host))
        self.assertIn('Path=/; Secure; HttpOnly;',cookie('access','signed',28800,'tph-test.elisprotech.com'))
        self.assertIn('Max-Age=28800',cookie('access','signed',28800,'tph-test.elisprotech.com'))
        with self.assertRaisesRegex(RuntimeError,'original_gate_source_drift'):
            cutover.new_gate(source+b'\n')


class FailureTests(unittest.TestCase):
    def test_old_readiness_uses_private_peer_and_old_public_signin(self):
        response=unittest.mock.MagicMock()
        response.__enter__.return_value=response
        response.status=200;response.read.return_value=b'old synthetic app'
        with patch.object(cutover.urllib.request,'urlopen',return_value=response) as get:
            cutover.private_ready(18211)
            self.assertEqual([c.args[0].full_url for c in get.call_args_list],
                ['http://127.0.0.1:18201/local-test/ready','http://127.0.0.1:18211/signin'])

    def approval(self):
        return {name:{'decision':'GO','reviewer':name+'-independent',
                      'reference':'source-review-123',
                      'expires_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat()}
                for name in ('qa','security')}

    def test_truthy_no_go_refused(self):
        for bad in ({'decision':'NO-GO'},'GO',{'decision':'GO','reviewer':'x'}):
            receipt=self.approval();receipt['qa']=bad
            with self.assertRaises(RuntimeError):cutover.reviews(receipt)

    def test_same_reviewer_refused(self):
        receipt=self.approval();receipt['security']['reviewer']=receipt['qa']['reviewer']
        with self.assertRaises(RuntimeError):cutover.reviews(receipt)

    def test_foreign_listener_refused(self):
        children={5:'caddy run --adapter caddyfile',6:str(cutover.ROOT/'access_gate.py')}
        with patch.object(cutover,'command',return_value=b'p999\nn192.168.4.239:8088\n'):
            with self.assertRaisesRegex(RuntimeError,'foreign_or_wrong_bind_listener'):
                cutover.listeners({'children':children})

    def test_existing_gate_non_navigation_denials(self):
        with patch.object(cutover,'command',side_effect=[b'403',b'403',b'200']*2) as request:
            cutover.gate_negative_checks()
            self.assertEqual(request.call_count,6)
            self.assertFalse(any('--insecure' in args.args[0] for args in request.call_args_list))
        with patch.object(cutover,'command',return_value=b'200'):
            with self.assertRaisesRegex(RuntimeError,'unauthenticated_access_not_denied'):
                cutover.gate_negative_checks()

    def test_partial_apply_rollback_ignores_broken_new_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=root/'journal';journal.mkdir()
            old=b'old';new=b'new';activation=cutover.canonical({'approved_config_sha256':cutover.sha(old)})
            (journal/'old.caddy').write_bytes(old);(journal/'old.activation.json').write_bytes(activation)
            config=root/'config';config.write_bytes(new)
            old_gate=b'oldgate';new_gate=b'newgate';(root/'access_gate.py').write_bytes(new_gate)
            (journal/'old.access_gate.py').write_bytes(old_gate)
            (journal/'new.access_gate.py').write_bytes(new_gate)
            active=root/'activation';active.write_bytes(activation) # Crash between the two replacements.
            original={'pid':10,'identity':'oldidentity','children':{11:'oldgate',12:'oldcaddy'}}
            current={'pid':20,'identity':'newidentity','children':{21:'newgate',22:'newcaddy'}}
            plan={'runner_sha256':cutover.digest(Path(cutover.__file__)),'sources':{},'containers':{},
                  'old_config':cutover.sha(old),'new_config':cutover.sha(new),'old_activation':cutover.sha(activation),
                  'old_gate':cutover.sha(old_gate),'new_gate':cutover.sha(new_gate)}
            raw=cutover.canonical(plan);(journal/'plan.json').write_bytes(raw);plan_sha=cutover.sha(raw)
            (journal/'apply-started.json').write_text(json.dumps({'plan':plan_sha}))
            receipt=self.approval();receipt.update(plan_sha256=plan_sha,runner_sha256=plan['runner_sha256'],allow_test_upstream_and_rollback=True)
            raw=cutover.canonical(receipt);(journal/'approval.json').write_bytes(raw)
            def ready(port=18221):
                self.assertEqual(port,18211,'Rollback must not depend on failed new application')
            with patch.multiple(cutover,JOURNAL=journal,CONFIG=config,ACTIVATION=active,ROOT=root), \
                 patch.object(cutover,'sources',return_value={}),patch.object(cutover,'protected_snapshot',return_value={}), \
                 patch.object(cutover,'private_ready',side_effect=ready) as readiness, \
                 patch.object(cutover,'owned_processes',side_effect=[original,current]), \
                 patch.object(cutover,'process',return_value='oldidentity'),patch.object(cutover.os,'kill') as kill, \
                 patch.object(cutover,'command',return_value=b''),patch.object(cutover,'service',return_value='gui/501/test'), \
                 patch.object(cutover.subprocess,'run') as start,patch.object(cutover,'listeners'), \
                 patch.object(cutover,'gate_negative_checks'):
                result=cutover.transition('rollback',plan_sha,cutover.sha(raw))
                self.assertTrue(result['completed']);readiness.assert_called_once_with(18211)
                kill.assert_called_once_with(10,cutover.signal.SIGTERM)
                self.assertEqual(start.call_args.args[0],['/bin/launchctl','kickstart','gui/501/test'])
                self.assertEqual(config.read_bytes(),old);self.assertEqual(active.read_bytes(),activation)
                self.assertTrue((journal/'apply-started.json').exists())
                self.assertTrue((journal/'rollback-completed.json').exists())


if __name__=='__main__':unittest.main()
