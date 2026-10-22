import importlib.util
from pathlib import Path
import unittest


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


cfg = module('public_config', Path(__file__).with_name('configure.py'))
private = module('private_config', Path(__file__).parents[1] / 'mac-test-apps/configure.py')


class PublicContract(unittest.TestCase):
    def setUp(self):
        images = {key: 'sha256:' + 'a' * 64 for key in ('dieselbridge', 'tph', 'postgres', 'redis', 'mongo', 'nginx')}
        stacks = private.specifications(images)
        self.before = {'dieselbridge': stacks['db-local-test'], 'tph': stacks['tph-local-test']}
        self.after = cfg.plan(self.before, 'sha256:' + 'b' * 64)

    def test_workers_storage_and_private_networks_unchanged(self):
        for app in self.before:
            for service in self.before[app]['services']:
                if service not in ('web', 'gateway'):
                    self.assertEqual(self.before[app]['services'][service], self.after[app]['services'][service])
            self.assertEqual(self.before[app]['networks'], self.after[app]['networks'])
            self.assertEqual(self.before[app]['volumes'], self.after[app]['volumes'])

    def test_only_web_public_settings_and_image(self):
        db = self.after['dieselbridge']['services']['web']['environment']
        self.assertEqual(db['COOKIE_SECURE'], 'true')
        self.assertEqual(db['COOKIE_DOMAIN'], '')
        self.assertEqual(db['FRONTEND_URL'], 'https://dieselbridge-test.elisprotech.com')
        self.assertEqual(db['CORS_ORIGINS_STR'], db['FRONTEND_URL'])
        self.assertEqual(self.before['dieselbridge']['services']['web']['environment']['COOKIE_SECURE'], 'false')
        self.assertEqual(self.after['tph']['services']['web']['image'], 'sha256:' + 'b' * 64)
        self.assertNotEqual(self.after['tph']['services']['web']['image'], self.after['tph']['services']['worker']['image'])

    def test_no_new_network_exposure(self):
        for app, port in (('dieselbridge', 18210), ('tph', 18211)):
            gateway = self.after[app]['services']['gateway']
            self.assertEqual(gateway['ports'][:-1], self.before[app]['services']['gateway']['ports'])
            self.assertEqual(gateway['ports'][-1], f'127.0.0.1:{port}:8081')

    def test_bad_image_and_unknown_stacks_refused(self):
        with self.assertRaises(ValueError): cfg.plan(self.before, 'latest')
        with self.assertRaises(ValueError): cfg.plan({'other': {}}, 'sha256:' + 'b' * 64)

    def test_private_nginx_preserved_and_public_scheme_fixed(self):
        for app in self.before:
            before = private.nginx_configuration(app == 'dieselbridge')
            after = cfg.nginx(before, app)
            self.assertTrue(after.startswith(before.rstrip()[:-1]))
            public = after.split('server { listen 8081;', 1)[1]
            self.assertIn('proxy_set_header X-Forwarded-Proto https;', public)
            self.assertNotIn('X-Forwarded-Proto $scheme', public)
            self.assertNotIn('web:5051', public)
            self.assertIn('return 404', public)
            self.assertIn("connect-src 'self'", public)
            self.assertIn('LOCAL TEST - Synthetic data', public)
        with self.assertRaises(ValueError): cfg.nginx('unexpected config', 'tph')

    def test_public_caddy_exact_targets_and_auth_before_proxy(self):
        source = cfg.caddy(local=False)
        for host in cfg.HOSTS.values(): self.assertIn('https://' + host, source)
        self.assertIn('reverse_proxy 127.0.0.1:18210', source)
        self.assertIn('reverse_proxy 127.0.0.1:18211', source)
        self.assertNotIn('18080', source)
        self.assertNotIn('18100', source)
        self.assertNotIn('Authorization', source)
        self.assertEqual(source.count('forward_auth 127.0.0.1:18680'), 2)
        self.assertIn('X-Test-Host {http.request.host}', source)
        self.assertIn('X-Test-Client-IP {http.request.remote.host}', source)
        self.assertIn('redir https://tph-test.elisprotech.com{uri} 308', source)

    def test_local_tls_never_binds_public(self):
        source = cfg.caddy(local=True)
        self.assertNotIn('192.168.4.239', source)
        self.assertNotIn('bind 0.0.0.0', source)
        self.assertIn('skip_install_trust', source)
        self.assertIn('admin off', source)
        self.assertIn('tls internal', source)

    def test_parallel_asset_loads_queue_below_helper_thread_capacity(self):
        for local in (True, False):
            source = cfg.caddy(local=local)
            # Two hosts each admit twelve checks and four login requests.
            # Excess HTTP/2 asset streams wait in the proxy transport instead
            # of overrunning the helper's shared thirty-two thread bound.
            self.assertEqual(source.count('max_conns_per_host 4'), 2)
            self.assertEqual(source.count('max_conns_per_host 12'), 4)
            self.assertEqual(2 * (12 + 4), 32)


if __name__ == '__main__':
    unittest.main()
