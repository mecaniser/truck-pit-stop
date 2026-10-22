import datetime
import unittest
from unittest.mock import patch
import runtime_ui_fix as r

class RuntimeTests(unittest.TestCase):
    def approval(self):
        base=r.approval_contract('a'*64,'b'*64,'c'*64)
        value={**base,'qa':{'reviewer':'freshQA','reference':'review-1','decision':'GO'},
               'security':{'reviewer':'freshSecurity','reference':'review-2','decision':'GO'},
               'expires_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat()}
        return value,base
    def test_bound_independent_approval(self):
        value,base=self.approval();r.validate_approval(value,base)
    def test_changed_binding(self):
        value,base=self.approval();value['web_cid']='d'*64
        with self.assertRaises(RuntimeError):r.validate_approval(value,base)
    def test_self_review(self):
        value,base=self.approval();value['security']['reviewer']='hosting_contract'
        with self.assertRaises(RuntimeError):r.validate_approval(value,base)
    def test_same_reviewer(self):
        value,base=self.approval();value['security']['reviewer']=value['qa']['reviewer']
        with self.assertRaises(RuntimeError):r.validate_approval(value,base)
    def test_expired_approval(self):
        value,base=self.approval();value['expires_at']='2020-01-01T00:00:00+00:00'
        with self.assertRaises(RuntimeError):r.validate_approval(value,base)
    def test_javascript_identity_preserves_popup_literal(self):
        raw=b"const popup='<body>'; const d='auth.tph.invalid', c='local-test-client', a='https://tph.invalid';"
        served=raw
        for old,new in r.REPLACEMENTS:served=served.replace(old,new)
        self.assertEqual(r.verify_javascript(raw,served),[1,1,1])
    def test_original_corruption_detected(self):
        raw=b"const popup='<body>';"
        with self.assertRaises(RuntimeError):r.verify_javascript(raw,raw.replace(b'<body>',b'<body>'+r.BANNER))
    def test_unrelated_js_change_denied(self):
        with self.assertRaises(RuntimeError):r.verify_javascript(b'let x=1;',b'let x=2;')
    def test_missing_replacement_denied(self):
        with self.assertRaises(RuntimeError):r.verify_javascript(b'auth.tph.invalid',b'auth.tph.invalid')
    def test_existing_journal_refuses_before_commands(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as temp:
            runner=r.Runner(Path(temp));runner.directory.mkdir(parents=True)
            with patch.object(runner.r,'command',side_effect=AssertionError('must not run')):
                with self.assertRaisesRegex(RuntimeError,'already_started'):runner.execute('a'*64,'b'*64)
    def test_invalid_explicit_hashes_refuse(self):
        with self.assertRaisesRegex(RuntimeError,'explicit_hashes'):r.Runner().execute('','')
    def test_actual_build_root_inventory_and_served_root_path(self):
        runner=r.Runner();name='vendor-misc-69904bf9.bfa12a49d8635f04933e.js'
        raw=b"const d='auth.tph.invalid',c='local-test-client',a='https://tph.invalid',popup='<body>';"
        served=raw
        for old,new in r.REPLACEMENTS:served=served.replace(old,new)
        def command(args,label,**kwargs):
            if label=='js-list':
                self.assertIn('/usr/src/app/build',args[-1]);self.assertNotIn('build/static/js',args[-1])
                return __import__('json').dumps([name]).encode()
            if label=='js-original':return raw
            if label=='js-syntax':
                self.assertEqual(args,['exec','-i',r.p.WEB,'node','--check']);self.assertEqual(kwargs['input'],served)
                return b''
            self.fail('unexpected command')
        with patch.object(runner.r,'command',side_effect=command),patch.object(runner.r,'http',return_value=(200,{'Content-Type':'application/javascript'},served)) as http:
            self.assertEqual(runner.javascript()['file_count'],1)
            http.assert_called_once_with('GET','/'+name)

    def test_nginx_validation_uses_only_old_gateway_no_reload(self):
        runner=r.Runner()
        with patch.object(runner.h,'private_read',return_value=b'reviewed config'),patch.object(runner.r,'command',return_value=b'') as command:
            runner.nginx_syntax()
            command.assert_called_once_with(['exec','-i',r.p.GATEWAY,'nginx','-t','-c','/dev/stdin'],
                                            'proposed-nginx-syntax',input=b'reviewed config')
    def test_frozen_helper_loaded(self):
        self.assertEqual(r.helper().PLAN_SHA,r.p.PHASE2_SHA)

if __name__=='__main__':unittest.main()
