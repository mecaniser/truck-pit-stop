"""No Docker, network, production data, credential reading or runtime startup."""
import copy
import json
import ipaddress
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import prepare


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / 'new-clone'
        self.manifest = {'images': {name: 'sha256:' + letter * 64 for name, letter in
                                   [('web', 'a'), ('mongo', 'b'), ('gateway', 'c')]},
                         'source': prepare.SOURCE, 'token': 'd' * 32}

    def tearDown(self):
        self.temp.cleanup()

    def test_only_fresh_three_service_project_and_internal_app_database(self):
        spec = prepare.specification(self.manifest, self.root)
        self.assertEqual(set(spec['services']), {'mongo', 'web', 'gateway'})
        self.assertEqual(spec['name'], 'macapps-tph-real-data-' + 'd' * 12)
        self.assertTrue(spec['networks']['isolated']['internal'])
        for name in ('mongo', 'web'):
            self.assertEqual(spec['services'][name]['networks'], ['isolated'])
            self.assertNotIn('ports', spec['services'][name])
        self.assertEqual(spec['services']['gateway']['ports'], ['127.0.0.1:18221:8080'])
        self.assertEqual(spec['services']['gateway']['networks'], ['isolated', 'ingress'])
        self.assertTrue(all(s['restart'] == 'no' for s in spec['services'].values()))
        self.assertNotIn('external', json.dumps(spec['networks']))

    def test_v3_explicit_subnets_require_no_default_pool_and_preserve_old_roots(self):
        self.assertEqual(prepare.ROOT, Path.home() / 'mac-hosting/tph-real-data-v3')
        spec = prepare.specification(self.manifest, self.root)
        for kind, expected in [('isolated', '10.240.64.0/24'), ('ingress', '10.240.65.0/24')]:
            self.assertEqual(spec['networks'][kind]['ipam'], {'driver': 'default', 'config': [{'subnet': expected}]})
            self.assertTrue(ipaddress.ip_network(expected).is_private)
            self.assertEqual(ipaddress.ip_network(expected).prefixlen, 24)
        self.assertFalse(ipaddress.ip_network(prepare.SUBNETS['isolated']).overlaps(
                         ipaddress.ip_network(prepare.SUBNETS['ingress'])))
        previous = self.root.parent / 'tph-real-data'
        previous.mkdir(mode=0o700)
        frozen = previous / 'plan.json'
        frozen.write_bytes(b'ORIGINAL_PREPARED_PLAN_DO_NOT_OVERWRITE')
        prepare.prepare(self.manifest, self.root)
        self.assertEqual(frozen.read_bytes(), b'ORIGINAL_PREPARED_PLAN_DO_NOT_OVERWRITE')
        plan = json.loads((self.root / 'plan.json').read_text())
        self.assertEqual(plan['version'], 3)
        self.assertEqual(plan['network_contract']['subnets'], prepare.SUBNETS)
        self.assertIn('REQUIRED', plan['network_contract']['overlap_verification'])
        self.assertFalse(plan['ttl_monitor_enabled'])
        self.assertEqual(spec['services']['mongo']['command'][-2:], ['--setParameter', 'ttlMonitorEnabled=false'])
        previous_v2 = self.root.parent / 'tph-real-data-v2'
        previous_v2.mkdir(mode=0o700)
        (previous_v2 / 'failed-restore.log').write_bytes(b'PRESERVE_TTL_LOSS_EVIDENCE')
        with self.assertRaises(ValueError):
            prepare.prepare(self.manifest, self.root)
        self.assertEqual((previous_v2 / 'failed-restore.log').read_bytes(), b'PRESERVE_TTL_LOSS_EVIDENCE')

    def test_no_live_credentials_or_synthetic_connections(self):
        spec = prepare.specification(self.manifest, self.root)
        env = spec['services']['web']['environment']
        self.assertEqual(env['DISABLE_SCHEDULER'], 'true')
        self.assertEqual(env['SQUARE_ENVIRONMENT'], 'sandbox')
        self.assertTrue(all(env[name] == 'false' for name in prepare.FLAGS_FALSE))
        self.assertEqual(env['AUTH0_DOMAIN'], 'auth.tph.invalid')
        self.assertEqual(env['SQUARE_ACCESS_TOKEN'], 'LOCAL_TEST_INVALID_NOT_A_PROVIDER_CREDENTIAL')
        self.assertIn('clone_reader:', env['MONGO_URI_DEV'])
        self.assertIn('@mongo:27017/tph_local_test?authSource=tph_local_test', env['MONGO_URI_DEV'])
        raw = json.dumps(spec)
        self.assertNotIn('test-stacks', raw)
        self.assertNotIn('dieselbridge-staging', raw)
        self.assertNotIn('railway', raw.lower())
        self.assertNotIn('REDIS_URL', env)

    def test_strict_manifest_and_mutable_image_or_source_refused(self):
        for change in (lambda m: m.update(production_uri='secret'),
                       lambda m: m['images'].update(web='node:latest'),
                       lambda m: m.update(source='f' * 40),
                       lambda m: m.update(token='../existing'),
                       lambda m: m['images'].update(worker='sha256:' + 'e' * 64)):
            manifest = copy.deepcopy(self.manifest)
            change(manifest)
            with self.assertRaises(ValueError):
                prepare.specification(manifest, self.root)

    def test_prepare_only_new_files_preserves_existing_and_hashes_artifacts(self):
        with patch('subprocess.run', side_effect=AssertionError('No runtime command permitted')):
            result = prepare.prepare(self.manifest, self.root)
        self.assertFalse(result['runtime_started'])
        self.assertFalse(result['public_cutover'])
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / 'private/clone.env').stat().st_mode & 0o777, 0o600)
        env = (self.root / 'private/clone.env').read_text()
        secrets = [v.split('=', 1)[1] for v in env.splitlines()]
        self.assertEqual(len(set(secrets)), 5)
        self.assertTrue(all(len(v) == 43 for v in secrets))
        self.assertNotIn(env, json.dumps(result))
        plan = json.loads((self.root / 'plan.json').read_text())
        for name, sha in plan['artifacts_sha256'].items():
            self.assertEqual(prepare.sha((self.root / name).read_bytes()), sha)
        self.assertEqual((self.root / 'clone-web.cjs').stat().st_mode & 0o777, 0o644)
        before = (self.root / 'private/clone.env').read_bytes()
        with self.assertRaises(ValueError):
            prepare.prepare(self.manifest, self.root)
        self.assertEqual((self.root / 'private/clone.env').read_bytes(), before)

    def test_readonly_role_only_pin_update_no_jobs_or_startup_initializer(self):
        script = prepare.role_script()
        self.assertIn("collection:'pins'},actions:['update']", script)
        self.assertNotIn("'insert'", script)
        self.assertNotIn("'remove'", script)
        self.assertNotIn("roles:['readWrite']", script)
        self.assertNotIn("collection:''},actions:['find'", script)
        self.assertNotIn('bookingsessions', script)
        self.assertNotIn('magiclinks', script)
        self.assertNotIn('blogresearchjobs', script)
        self.assertIn("getRole('clone_reader_role')", script)
        self.assertIn('clone_role_existing_or_empty_refused', script)
        spec = prepare.specification(self.manifest, self.root)
        self.assertNotIn('/docker-entrypoint-initdb.d', json.dumps(spec))
        self.assertIn('/run/clone/create-reader-role.js:ro', json.dumps(spec))

    def test_gateway_blocks_provider_mutations_and_uses_local_api_origin(self):
        config = prepare.nginx()
        self.assertIn('default 0;', config)
        self.assertIn('if ($clone_allowed = 0) { return 403; }', config)
        self.assertEqual(config.count('"POST:/api/pin/'), 3)
        self.assertIn('webhooks|booking-auth|auth|customer|payments|stripe|square|jobs|cron|internal', config)
        self.assertNotIn('~^(GET|HEAD): 1;', config)
        self.assertIn('(?!api(?:/|$))', config)
        self.assertIn('/api/spot-changes', config)
        self.assertIn("sub_filter 'https://tph-test.elisprotech.com' 'http://127.0.0.1:18221'", config)
        self.assertIn("connect-src 'self'", config)
        self.assertIn("worker-src 'none'", config)
        self.assertIn('no-store', config)
        self.assertNotIn('proxy_set_header Authorization', config)
        with self.assertRaises(ValueError):
            prepare.nginx('https://trucksparkinghub.com')

    def test_adapter_runs_both_guard_passes_with_generated_environment(self):
        prepare.prepare(self.manifest, self.root)
        spec = json.loads((self.root / 'compose.json').read_text())
        secrets = dict(line.split('=', 1) for line in (self.root / 'private/clone.env').read_text().splitlines())
        env = spec['services']['web']['environment']
        for key, value in env.items():
            for name, secret in secrets.items():
                value = value.replace('${' + name + ':?required}', secret)
            env[key] = value
        # VM stubs only external modules. Real assertions/URL and the full actual
        # adapter execute through preimport+postimport guards without sockets/DB.
        runner = r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8'));let order=[];
const mongoose={set:(k,v)=>{assert.equal(v,false);order.push(k)}};
const context={URL,process:{env:input.env,exit:()=>{throw Error('exit')}},console:{error:()=>{}},require:(name)=>{
 if(name==='node:assert/strict')return assert;
 if(name==='mongoose')return mongoose;
 if(name==='./backend/server'){assert.deepEqual(order,['autoIndex','autoCreate']);order.push('server');return {app:{},httpServer:{listen:()=>order.push('native-listen')}}}
 if(name==='./backend/config/database')return ()=>Promise.resolve();
 if(name==='node:http')return {createServer:()=>({listen:()=>{order.push('readiness-listen')}})};
 throw Error('unexpected external import');
}};
try{vm.runInNewContext(input.source,context);setImmediate(()=>{assert.ok(order.includes('native-listen'));console.log('guarded-native-bootstrap')})}
catch(e){console.log('guard-refused');process.exitCode=9}
'''
        adapter = Path(prepare.__file__).with_name('clone-web.cjs').read_text()
        def run(environment):
            return subprocess.run(['node', '-e', runner], input=json.dumps({'env': environment, 'source': adapter}),
                                  capture_output=True, text=True, timeout=10)
        result = run(env)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.strip(), 'guarded-native-bootstrap')
        for key in ('WORKOS_API_KEY', 'TWILIO_AUTH_TOKEN', 'RESEND_API_KEY', 'AUTH0_CLIENT_SECRET'):
            with self.subTest(key=key):
                result = run({**env, key: 'NOT_A_REAL_SECRET'})
                self.assertEqual(result.returncode, 9)
                self.assertEqual(result.stdout.strip(), 'guard-refused')

    def test_adapter_preserves_native_auth_and_disables_index_creation(self):
        adapter = Path(prepare.__file__).with_name('clone-web.cjs').read_text()
        self.assertIn("mongoose.set('autoIndex', false)", adapter)
        self.assertIn("mongoose.set('autoCreate', false)", adapter)
        self.assertLess(adapter.index("mongoose.set('autoCreate', false)"), adapter.index("require('./backend/server')"))
        self.assertNotIn('require.cache', adapter)
        self.assertNotIn('synthetic', adapter)
        self.assertNotIn('initializeScheduler', adapter)
        self.assertNotIn('setInterval', adapter)


if __name__ == '__main__':
    unittest.main()
