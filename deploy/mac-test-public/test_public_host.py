import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node required for native adapter checks')
class PublicOrigin(unittest.TestCase):
    def test_exact_https_origin_needs_both_runtime_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'backend').mkdir()
            source = root / 'backend/server.js'
            source.write_text("const corsOptions = { origin: function(origin, callback) {\n"
                              "    if (!origin) return callback(null, true);\n"
                              "    callback(new Error('Not allowed by CORS'));\n"
                              "}}; module.exports = corsOptions;\n")
            patch = str(Path(__file__).with_name('public-host.cjs'))
            env = {**os.environ, 'SQUARE_ENVIRONMENT': 'sandbox'}
            result = subprocess.run(['node', patch], cwd=root, env=env, capture_output=True)
            self.assertEqual(result.returncode, 0)
            script = """const assert=require('node:assert/strict');const c=require('./backend/server');
function allowed(origin){let yes=false;c.origin(origin,(err,ok)=>yes=!err&&ok===true);return yes}
process.env.LOCAL_TEST_ONLY='true';process.env.SQUARE_ENVIRONMENT='sandbox';
assert.equal(allowed('https://tph-test.elisprotech.com'),true);
for(const x of ['http://tph-test.elisprotech.com','https://tph-test.elisprotech.com.invalid','null','https://tph-test.elisprotech.com:444'])assert.equal(allowed(x),false);
process.env.LOCAL_TEST_ONLY='false';assert.equal(allowed('https://tph-test.elisprotech.com'),false);
process.env.LOCAL_TEST_ONLY='true';process.env.SQUARE_ENVIRONMENT='production';assert.equal(allowed('https://tph-test.elisprotech.com'),false);
"""
            self.assertEqual(subprocess.run(['node', '-e', script], cwd=root, env=env, capture_output=True).returncode, 0)
            before = source.read_bytes()
            self.assertNotEqual(subprocess.run(['node', patch], cwd=root, env=env, capture_output=True).returncode, 0)
            self.assertEqual(source.read_bytes(), before)

    def test_production_build_and_unknown_native_boundary_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'backend').mkdir()
            source = root / 'backend/server.js'
            patch = str(Path(__file__).with_name('public-host.cjs'))
            for text, square in (("    if (!origin) return callback(null, true);", 'production'),
                                 ('unrecognized source', 'sandbox')):
                source.write_text(text)
                env = {**os.environ, 'SQUARE_ENVIRONMENT': square}
                self.assertNotEqual(subprocess.run(['node', patch], cwd=root, env=env, capture_output=True).returncode, 0)
                self.assertEqual(source.read_text(), text)


if __name__ == '__main__':
    unittest.main()
