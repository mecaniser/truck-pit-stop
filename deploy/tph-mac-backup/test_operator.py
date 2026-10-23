import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import configure

spec=importlib.util.spec_from_file_location('backup_operator',Path(__file__).with_name('operator.py'));operator=importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)

class OperatorBoundary(unittest.TestCase):
    def test_immutable_image_mismatch_refused(self):
        row={'Id':'a'*64,'Image':'sha256:'+'b'*64,'Config':{'Labels':{'io.macapps.backup-rehearsal':configure.OWNER,'com.docker.compose.project':configure.PROJECT}}}
        with patch.object(operator,'docker',return_value=json.dumps([row]).encode()),patch.object(operator,'load',return_value={'app':'sha256:'+'c'*64,'router':'sha256:'+'d'*64}):
            with self.assertRaisesRegex(RuntimeError,'immutable image'):operator.inspect('mac-backup')
    def test_pending_work_refused_before_stop(self):
        state={'site':'railway-simulation','epoch':1,'phase':'active','pending':{'blocked':False}}
        with patch.object(operator,'control',side_effect=[state,{**state,'phase':'draining','pending':{'blocked':True}}]),patch.object(operator,'docker') as docker:
            with self.assertRaisesRegex(RuntimeError,'Drain blocked'):operator.switch('mac-backup')
            docker.assert_not_called()
    def test_config_tampering_refused(self):
        with tempfile.TemporaryDirectory() as path:
            root=Path(path).resolve();root.chmod(0o700);(root/'private').mkdir(mode=0o700);(root/'.owner').write_text(configure.OWNER+'\n');(root/'compose.json').write_text('{"changed":true}');(root/'private/config-sha256.txt').write_text('a'*64)
            with patch.object(operator,'ROOT',root):
                with self.assertRaisesRegex(RuntimeError,'configuration drift'):operator.safe()
    def test_replaced_target_refused_before_promotion(self):
        state={'site':'railway-simulation','epoch':1,'phase':'active','instance_id':'old','pending':{'blocked':False}}
        old={'Id':'old','State':{'Running':True}}
        stopped={'Id':'old','State':{'Running':False}}
        target={'Id':'target','State':{'Running':True}}
        with patch.object(operator,'control',side_effect=[state,state]) as control,patch.object(operator,'inspect',side_effect=[old,target,old,stopped]),patch.object(operator,'ready',side_effect=[target,{'Id':'replacement'}]),patch.object(operator,'docker'),patch.object(operator,'save'):
            with self.assertRaisesRegex(RuntimeError,'Target changed'):operator.switch('mac-backup')
            self.assertEqual(control.call_count,2)

    def test_uri_constructor_preserves_fixed_spec_bytes(self):
        expected='mongodb'+'://rehearsal:'+ '${MONGO_PASSWORD:?required}'+'@mongo:27017/tph_backup_restored?authSource=admin'
        images={'app':'sha256:'+'a'*64,'router':'sha256:'+'b'*64}
        self.assertEqual(configure.specification(images,501,20)['services']['mac-backup']['environment']['MONGO_URI_DEV'],expected)
