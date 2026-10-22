import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('public_builder', Path(__file__).with_name('build_tph_cors.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BuildIdentity(unittest.TestCase):
    def test_base_mismatch_refused_before_tag_or_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / '.owner').write_text('macapps-test-public-v1\n')
            (root / 'private').mkdir(mode=0o700)
            with patch.object(builder, 'ROOT', root), patch.object(builder, 'image_id', return_value='wrong'), patch.object(builder.subprocess, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'base image identity'):
                    builder.main()
                run.assert_not_called()

    def test_foreign_alias_refused_before_tag_or_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / '.owner').write_text('macapps-test-public-v1\n')
            (root / 'private').mkdir(mode=0o700)
            foreign = subprocess.CompletedProcess([], 0, stdout='sha256:' + 'a' * 64)
            with patch.object(builder, 'ROOT', root), patch.object(builder, 'image_id', return_value=builder.EXPECTED), patch.object(builder.subprocess, 'run', return_value=foreign) as run:
                with self.assertRaisesRegex(RuntimeError, 'different image'):
                    builder.main()
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][len(builder.DOCKER):len(builder.DOCKER)+2], ['image', 'inspect'])


if __name__ == '__main__':
    unittest.main()
