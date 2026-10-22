import copy
from pathlib import Path
import unittest
import prepare_phase2
import prepare_ui_fix as p

class PreparationTests(unittest.TestCase):
    def raw(self):
        return prepare_phase2.NGINX.encode() if hasattr(prepare_phase2,'NGINX') else prepare_phase2.nginx().encode()
    def test_public_source_644_and_private_600_accepted(self):
        import tempfile,os
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory).resolve()/'source.cjs';path.write_bytes(b'public-source')
            for mode in (0o644,0o600):
                os.chmod(path,mode);self.assertEqual(p.artifact_read(path),b'public-source')
    def test_writable_public_source_refused(self):
        import tempfile,os
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory).resolve()/'source.cjs';path.write_bytes(b'public-source');os.chmod(path,0o664)
            with self.assertRaises(RuntimeError):p.artifact_read(path)
    def test_symlink_source_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory).resolve()/'source.cjs';path.write_bytes(b'public-source')
            link=Path(directory).resolve()/'link.cjs';link.symlink_to(path)
            with self.assertRaises(RuntimeError):p.artifact_read(link)
    def test_unowned_source_refused(self):
        import tempfile,os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory).resolve()/'source.cjs';path.write_bytes(b'public-source');os.chmod(path,0o644)
            with patch.object(p.os,'getuid',return_value=os.getuid()+1):
                with self.assertRaises(RuntimeError):p.artifact_read(path)
    def test_real_config_only_banner_rule_changes(self):
        raw=self.raw();fixed=p.corrected_nginx(raw)
        self.assertIn(b'"~*^text/html(?:;|$)"',fixed)
        self.assertIn(b"default '<body>';",fixed)
        self.assertIn(b"sub_filter '<body>' $clone_html_body;",fixed)
        for line in raw.splitlines():
            if b"sub_filter '<body>'" not in line:self.assertIn(line,fixed)
        self.assertEqual(fixed.count(b'MAC COPY - Real data captured'),1)
    def test_duplicate_banner_refused(self):
        raw=self.raw();line=next(x for x in raw.splitlines() if b"sub_filter '<body>'" in x)
        with self.assertRaises(RuntimeError):p.corrected_nginx(raw+b'\n'+line)
    def test_no_banner_refused(self):
        with self.assertRaises(RuntimeError):p.corrected_nginx(b'http {\n}\n')
    def test_already_fixed_refused(self):
        with self.assertRaises(RuntimeError):p.corrected_nginx(p.corrected_nginx(self.raw()))
    def test_only_gateway_mount_changes(self):
        spec={'services':{'web':{'image':'pinned'},'mongo':{'command':['ttl=false']},'gateway':{'volumes':['/old/nginx.conf:/etc/nginx/nginx.conf:ro'],'ports':['127.0.0.1:18221:8080']}},'networks':{'isolated':{'internal':True}}}
        original=copy.deepcopy(spec);fixed=p.corrected_spec(spec,Path('/old'),Path('/new'))
        self.assertEqual(spec,original);fixed['services']['gateway']['volumes']=spec['services']['gateway']['volumes']
        self.assertEqual(fixed,spec)
    def test_additional_mount_refused(self):
        with self.assertRaises(RuntimeError):p.corrected_spec({'services':{'gateway':{'volumes':['unexpected']}}},Path('/old'),Path('/new'))

if __name__=='__main__':unittest.main()
