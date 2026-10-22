import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cfg', Path(__file__).with_name('configure.py'))
cfg = importlib.util.module_from_spec(spec); spec.loader.exec_module(cfg)
control_spec = importlib.util.spec_from_file_location('control', Path(__file__).with_name('stackctl.py'))
control = importlib.util.module_from_spec(control_spec); control_spec.loader.exec_module(control)


class StackContract(unittest.TestCase):
    def setUp(self):
        self.images = {key: 'sha256:'+'a'*64 for key in ('dieselbridge','tph','postgres','redis','mongo','nginx')}
        self.stacks = cfg.specifications(self.images)

    def test_missing_private_mongo_password_refused_before_docker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root/'.owner').write_text('macapps-test-stacks-v1\n')
            (root/'private').mkdir()
            required = ('DB_PASSWORD','DB_SECRET','MONGO_PASSWORD','TPH_MANAGER_SECRET','TPH_JWT_SECRET','TPH_API_SECRET')
            for bad_value in (None, 'short'):
                values = {key: 'x'*64 for key in required}
                if bad_value is None: values.pop('MONGO_PASSWORD')
                else: values['MONGO_PASSWORD'] = bad_value
                (root/'private/local.env').write_text(''.join(key+'='+value+'\n' for key,value in values.items()))
                with patch.object(control, 'ROOT', root), patch.object(control, 'inspect') as inspect:
                    with self.assertRaisesRegex(RuntimeError, 'missing_or_short'):
                        with control.lock(): pass
                    inspect.assert_not_called()

    def test_immutable_exact_images(self):
        with self.assertRaises(ValueError): cfg.specifications({**self.images, 'tph': 'latest'})
        with self.assertRaises(ValueError): cfg.specifications({**self.images, 'other': 'sha256:'+'a'*64})

    def test_network_ports_storage_separate(self):
        for project, stack in self.stacks.items():
            self.assertEqual(stack['name'], project)
            self.assertTrue(stack['networks']['isolated']['internal'])
            for service, item in stack['services'].items():
                if service != 'gateway':
                    self.assertEqual(item['networks'], ['isolated'])
                    self.assertNotIn('ports', item)
                else:
                    self.assertTrue(item['ports'][0].startswith('127.0.0.1:1820'))
            for volume in stack['volumes'].values(): self.assertNotIn('external', volume)
        self.assertNotEqual(self.stacks['db-local-test']['services']['gateway']['ports'], self.stacks['tph-local-test']['services']['gateway']['ports'])

    def test_worker_no_production_schedule(self):
        db = self.stacks['db-local-test']['services']['worker']
        self.assertNotIn('--beat', db['command'])
        self.assertEqual(db['command'][db['command'].index('-Q')+1], 'db-local-test')
        tph = self.stacks['tph-local-test']['services']
        self.assertEqual(tph['worker']['command'], ['node','tph-worker.cjs'])
        for name in ('web','worker','identity'):
            env = tph[name]['environment']
            self.assertEqual(env['DISABLE_SCHEDULER'], 'true')
            self.assertEqual(env['WORKOS_TENANT_ENABLED'], 'false')
            self.assertEqual(env['BLOG_STUDIO_ENABLED'], 'false')
            self.assertEqual(env['LOCAL_TEST_ONLY'], 'true')
            self.assertNotIn('MONGO_URI', env)
            for key in ('TWILIO_AUTH_TOKEN','POSTMARK_API_TOKEN','STRIPE_SECRET_KEY','WORKOS_API_KEY','OPENAI_API_KEY','META_ACCESS_TOKEN'):
                self.assertNotIn(key, env)

    def test_no_host_socket_or_production_paths(self):
        for stack in self.stacks.values():
            for service in stack['services'].values():
                self.assertNotIn('privileged', service)
                for mount in service.get('volumes', []):
                    self.assertNotIn('docker.sock', mount)
                    self.assertNotIn('dieselbridge-staging', mount)
                    self.assertFalse(mount.startswith('/'))

    def test_browser_cannot_connect_to_live_apis(self):
        for is_db in (True, False):
            source = cfg.nginx_configuration(is_db)
            self.assertIn("connect-src 'self'", source)
            self.assertIn("form-action 'self'", source)
            self.assertIn("frame-src 'none'", source)
            self.assertIn('LOCAL TEST - Synthetic data', source)

    def test_tph_web_cannot_direct_start_scheduler(self):
        source = Path(__file__).with_name('tph-web.cjs').read_text()
        self.assertIn("require('./backend/server')", source)
        self.assertNotIn('initializeScheduler', source)
        self.assertNotIn('cron.', source)
        self.assertEqual(self.stacks['tph-local-test']['services']['web']['image'], self.images['tph'])


if __name__ == '__main__': unittest.main()
