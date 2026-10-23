import copy
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

module = importlib.util.spec_from_file_location('hostctl', Path(__file__).with_name('hostctl.py'))
h = importlib.util.module_from_spec(module)
module.loader.exec_module(h)


class HostingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'mac-hosting'
        h.initialize(self.root)
        self.spec = {'app': 'demo-app', 'image': 'sha256:' + 'a'*64, 'gateway_image': h.GATEWAY_IMAGE,
                     'revision': 'v1', 'port': 18100, 'container_port': 8080, 'health': '/health'}

    def tearDown(self):
        self.temp.cleanup()

    def test_reserved_and_traversal(self):
        for name in ('../foo', 'a/b', 'production', 'dieselbridge-test', 'staging', 'railway', 'prod-app', '-x', 'UPPER', 'a'*33):
            with self.subTest(name=name), self.assertRaises(h.Refused):
                h.slug(name)

    @patch.object(h, 'run')
    def test_image_declared_volume_refused(self, run):
        run.return_value = json.dumps([{'Id': self.spec['image'], 'Os': 'linux',
                                      'Architecture': 'arm64', 'Config': {'Volumes': {'/data': {}}}}])
        with self.assertRaisesRegex(h.Refused, 'volumes'):
            h.image_id(self.spec['image'])

    def test_mutable_image_and_invalid_fields(self):
        for field, value in [('image', 'app:latest'), ('port', 18080), ('port', 18200), ('container_port', 80),
                             ('health', '/health;id'), ('revision', '../v1')]:
            spec = {**self.spec, field: value}
            with self.subTest(field=field, value=value), self.assertRaises(h.Refused):
                h.validate_spec(spec)

    def test_compose_isolation_and_limits(self):
        cfg = h.compose_spec(self.spec, Path('/private/config'))
        self.assertEqual(cfg['name'], 'macapps-demo-app')
        self.assertTrue(cfg['networks']['isolated']['internal'])
        app, gateway = cfg['services']['app'], cfg['services']['gateway']
        self.assertEqual(app['networks'], ['isolated'])
        self.assertNotIn('ports', app)
        self.assertNotIn('volumes', app)
        self.assertEqual(gateway['ports'], ['127.0.0.1:18100:8080'])
        for service in (app, gateway):
            self.assertTrue(service['read_only'])
            self.assertEqual(service['cap_drop'], ['ALL'])
            self.assertIn('mem_limit', service)
            self.assertNotIn('environment', service)

    def test_root_symlink_and_marker_refused(self):
        link = self.root.parent / 'link'
        link.symlink_to(self.root)
        with self.assertRaises(h.Refused):
            h.check_root(link)
        (self.root / 'apps' / 'escape').symlink_to('/tmp')
        with self.assertRaises(h.Refused):
            h.check_root(self.root)

    @patch.object(h, 'containers')
    def test_unowned_container_refused(self, containers):
        containers.return_value = [{'Config': {'Labels': {}}, 'Name': '/foreign'}]
        for known in (False, True):
            with self.assertRaises(h.Refused):
                h.owned('demo-app', known)

    @patch.object(h, 'owned', return_value=[])
    def test_occupied_port_refused(self, owned):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 18199))
            with self.assertRaises(h.Refused):
                h.available_port(self.root, {**self.spec, 'port': 18199}, None)

    @patch.object(h, 'image_id', side_effect=lambda value: value)
    @patch.object(h, 'owned', return_value=[])
    @patch.object(h, 'available_port')
    @patch.object(h, 'apply')
    @patch.object(h, 'healthy')
    def test_failed_update_restores_accepted_release(self, healthy, apply, port, owned, image):
        healthy.return_value = True
        accepted = h.deploy(self.root, self.spec)
        healthy.side_effect = [False, True]
        newer = {**self.spec, 'revision': 'v2', 'image': 'sha256:'+'c'*64}
        with self.assertRaisesRegex(h.Refused, 'previous_restored'):
            h.deploy(self.root, newer)
        self.assertEqual(json.loads(h.state_path(self.root, 'demo-app').read_text()), accepted)
        self.assertEqual(apply.call_args.args[1], self.spec)
        self.assertFalse((h.state_path(self.root, 'demo-app').parent / 'pending.json').exists())

    @patch.object(h, 'image_id', side_effect=lambda value: value)
    @patch.object(h, 'owned', return_value=[])
    @patch.object(h, 'available_port')
    @patch.object(h, 'apply')
    @patch.object(h, 'healthy')
    def test_failed_rollback_preserves_pending_evidence(self, healthy, apply, port, owned, image):
        healthy.return_value = True
        h.deploy(self.root, self.spec)
        healthy.return_value = False
        with self.assertRaisesRegex(h.Refused, 'pending_preserved'):
            h.deploy(self.root, {**self.spec, 'revision': 'v2'})
        self.assertTrue((h.state_path(self.root, 'demo-app').parent / 'pending.json').exists())
        with self.assertRaisesRegex(h.Refused, 'pending'):
            h.deploy(self.root, self.spec)


if __name__ == '__main__':
    unittest.main()
