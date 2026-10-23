import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('mac_test_build',Path(__file__).with_name('build.py'))
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)

class CleanupTests(unittest.TestCase):
    def exercise(self, *, missing=False, owned=True, running=True):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'probe.cid';cid='a'*64;release='b'*32;name='macapps-build-probe-'+release;image='sha256:'+'c'*64
            if not missing:path.write_text(cid)
            item={'Id':cid,'Name':'/'+name,'Image':image if owned else 'sha256:'+'d'*64,'Config':{'Labels':{'io.macapps.owner':'macapps-test-deploy-v1','io.macapps.probe':release}},'State':{'Running':running}}
            with patch.object(build.subprocess,'check_output',side_effect=[cid,json.dumps([item]).encode()]) as output,patch.object(build.subprocess,'run') as run:
                if not owned:
                    with self.assertRaisesRegex(RuntimeError,'ownership'):build.cleanup_artifact_probe(path,name,image,release)
                    run.assert_not_called()
                else:
                    build.cleanup_artifact_probe(path,name,image,release)
                    self.assertEqual(run.call_count,int(running))
                    if running:self.assertEqual(run.call_args.args[0][-3:],['rm','-f',cid])
                    if missing:self.assertIn('name=^/'+name+'$',output.call_args_list[0].args[0])
    def test_exact_cid_cleanup(self):self.exercise()
    def test_timeout_before_cid_uses_owned_name(self):self.exercise(missing=True)
    def test_wrong_image_never_removed(self):self.exercise(missing=True,owned=False)
    def test_exited_probe_never_removed(self):self.exercise(running=False)

if __name__=='__main__':unittest.main()
