"""Reuse the existing hostile-request suite against the exact proposed gate."""
import importlib.util
from pathlib import Path
import types
import unittest

import cutover

directory=Path(__file__).resolve().parents[1]/'mac-test-public'
spec=importlib.util.spec_from_file_location('original_gate_tests',directory/'test_access_gate.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
modified=types.ModuleType('mac_auth0_gate')
exec(compile(cutover.new_gate((directory/'access_gate.py').read_bytes()),'mac_auth0_gate.py','exec'),modified.__dict__)
original.gate_module=modified


class TphAuth0Tests(original.GateTests):
    def test_tph_login_sets_lax_access_and_strict_csrf(self):
        host='tph-test.elisprotech.com'
        status,headers,_=self.request('/_test-access',host=host)
        self.assertEqual(status,200)
        self.assertTrue(all('SameSite=Strict' in value for name,value in headers if name=='Set-Cookie'))
        status,headers,_=self.login(host=host)
        self.assertEqual(status,303)
        access=next(value for name,value in headers if name=='Set-Cookie' and value.startswith(modified.ACCESS+'='))
        self.assertIn('SameSite=Lax',access)
        for value in ('Path=/','Secure','HttpOnly','Max-Age=28800'):
            self.assertIn(value,access)
        self.assertNotIn('Domain=',access)
        token=access.split(';',1)[0]
        self.assertEqual(self.request(host=host,original_uri='/callback?code=fixture&state=fixture',extra={'Cookie':token})[0],204)
        self.assertEqual(self.request(host='dieselbridge-test.elisprotech.com',extra={'Cookie':token})[0],303)
        self.assertEqual(self.login(host=host,origin='https://unapproved.invalid')[0],403)
        self.assertEqual(self.login(host=host,csrf_host='dieselbridge-test.elisprotech.com')[0],403)


if __name__=='__main__':unittest.main()
