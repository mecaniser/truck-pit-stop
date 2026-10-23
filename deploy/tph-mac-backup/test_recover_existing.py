import copy
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('recover_existing', Path(__file__).with_name('recover_existing.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'private/state').mkdir(parents=True)
        self.root_patch = patch.object(r, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def seed(self):
        with closing(sqlite3.connect(self.root / 'private/state/control.sqlite3')) as c, c:
            c.executescript('CREATE TABLE authority(site,epoch,phase,watermark,instance_id,authority_id); CREATE TABLE admissions(outcome); CREATE TABLE operations(operation_id,scope,kind,business_id,payload_sha256,provider_receipt,outcome); CREATE TABLE transitions(transition_id);')
            c.execute("INSERT INTO authority VALUES('railway-simulation',5,'active',8,'owner','synthetic-authority')")
            c.executemany('INSERT INTO admissions VALUES(?)', [('accepted',)] * 3 + [('rejected',)])
            for n in range(5):
                c.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?)', (str(n),'scope','payment',str(n),'hash','receipt'+str(n),'accepted'))
        with closing(sqlite3.connect(self.root / 'private/state/provider.sqlite3')) as c, c:
            c.execute('CREATE TABLE effects(operation_id,scope,kind,business_id,payload_sha256,receipt)')
            for n in range(5):
                c.execute('INSERT INTO effects VALUES(?,?,?,?,?,?)', (str(n),'scope','payment',str(n),'hash','receipt'+str(n)))

    def test_readonly_exact_settled_state_and_no_file_change(self):
        self.seed()
        paths = list((self.root / 'private/state').iterdir())
        before = {p: p.read_bytes() for p in paths}
        state = r.database_snapshot()
        self.assertEqual((state['epoch'], state['watermark'], state['accepted_fake_effects']), (5, 8, 5))
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.assertEqual(set(paths), set((self.root / 'private/state').iterdir()))

    def test_unknown_and_receipt_mismatch_refuse(self):
        self.seed()
        with closing(sqlite3.connect(self.root / 'private/state/control.sqlite3')) as c, c:
            c.execute("UPDATE operations SET outcome='unknown' WHERE operation_id='0'")
        with self.assertRaisesRegex(RuntimeError, 'unsettled'):
            r.database_snapshot()
        with closing(sqlite3.connect(self.root / 'private/state/control.sqlite3')) as c, c:
            c.execute("UPDATE operations SET outcome='accepted',provider_receipt='wrong' WHERE operation_id='0'")
        with self.assertRaisesRegex(RuntimeError, 'receipt mismatch'):
            r.database_snapshot()

    def plan(self):
        containers = {s: dict(id=s, image='image', config_sha256='cfg', host_sha256='host', mounts_sha256='mount', running=False, started='old', health='unhealthy') for s in r.SERVICES}
        return {'state': {'instance_id':'railway-simulation','epoch':5,'watermark':8}, 'containers':containers,'protected':{'fixed':'snapshot'}}

    def test_plan_drift_blocks_all_starts(self):
        plan = self.plan()
        with patch.object(r, 'inventory', return_value={}), patch.object(r, 'docker') as docker:
            with self.assertRaisesRegex(RuntimeError, 'no longer matches'):
                r.recover(None, plan)
            docker.assert_not_called()

    def test_existing_attempt_never_retries(self):
        plan = self.plan()
        (self.root/'private/existing-recovery-failed.json').write_text('{}')
        with patch.object(r, 'inventory', return_value=plan), patch.object(r, 'docker') as docker:
            with self.assertRaisesRegex(RuntimeError, 'already attempted'):
                r.recover(None, plan)
            docker.assert_not_called()

    def test_starts_only_three_exact_ids_in_order_and_preserves_state(self):
        from unittest.mock import Mock
        plan = self.plan(); actual = copy.deepcopy(plan['containers']); calls=[]
        op = Mock()
        op.inspect.side_effect=lambda name:{'State':{'Running':actual[name]['running'],'StartedAt':actual[name]['started'],'Health':{'Status':actual[name]['health']}}}
        def start(*args):
            self.assertEqual(args[0], 'start');calls.append(args[1]);actual[args[1]].update(running=True,started='new-'+args[1],health='healthy')
        with patch.object(r,'prove_native_authority'), patch.object(r,'inventory',return_value=plan), patch.object(r,'protected_snapshot',return_value=plan['protected']), patch.object(r,'database_snapshot',return_value=plan['state']), patch.object(r,'container_snapshot',side_effect=lambda _:copy.deepcopy(actual)), patch.object(r,'docker',side_effect=start):
            result=r.recover(op,plan)
        self.assertEqual(calls,list(r.ORDER))
        self.assertFalse(actual['mac-backup']['running'])
        self.assertEqual(result['watermark'],8)
        self.assertTrue((self.root/'private/existing-recovery-completed.json').exists())

    def run_runtime_drift(self, at, mutate):
        from unittest.mock import Mock
        plan=self.plan();actual=copy.deepcopy(plan['containers']);calls=[];observations=0
        op=Mock()
        op.inspect.side_effect=lambda name:{'State':{'Running':actual[name]['running'],'StartedAt':actual[name]['started'],'Health':{'Status':actual[name]['health']}}}
        def start(*args):
            calls.append(args[1]);actual[args[1]].update(running=True,started='new-'+args[1],health='healthy')
        def snapshot(_):
            nonlocal observations
            observations+=1
            if observations==at:mutate(actual)
            return copy.deepcopy(actual)
        with patch.object(r,'prove_native_authority'),patch.object(r,'inventory',return_value=plan),patch.object(r,'protected_snapshot',return_value=plan['protected']),patch.object(r,'database_snapshot',return_value=plan['state']),patch.object(r,'container_snapshot',side_effect=snapshot),patch.object(r,'docker',side_effect=start):
            with self.assertRaises(RuntimeError):r.recover(op,plan)
        self.assertFalse((self.root/'private/existing-recovery-completed.json').exists())
        self.assertTrue((self.root/'private/existing-recovery-failed.json').exists())
        return calls

    def test_inactive_stopped_start_timestamp_drift_refuses(self):
        calls=self.run_runtime_drift(3,lambda rows:rows['mac-backup'].update(started='unauthorized-restart-then-stop'))
        self.assertEqual(calls,['mongo'])

    def test_intervening_active_restart_refuses_before_router_start(self):
        calls=self.run_runtime_drift(5,lambda rows:rows['railway-simulation'].update(started='unauthorized-restart'))
        self.assertEqual(calls,['mongo','railway-simulation'])

    def test_final_unhealthy_service_cannot_record_completion(self):
        calls=self.run_runtime_drift(7,lambda rows:rows['mongo'].update(health='unhealthy'))
        self.assertEqual(calls,list(r.ORDER))

    def test_protected_drift_or_state_drift_blocks_before_start(self):
        from unittest.mock import Mock
        for field in ('protected', 'state'):
            with self.subTest(field=field):
                for p in (self.root/'private').glob('existing-recovery-*.json'):p.unlink()
                plan=self.plan()
                with patch.object(r,'prove_native_authority'), patch.object(r,'inventory',return_value=plan), patch.object(r,'protected_snapshot',return_value={} if field=='protected' else plan['protected']), patch.object(r,'database_snapshot',return_value={} if field=='state' else plan['state']), patch.object(r,'docker') as docker:
                    with self.assertRaises(RuntimeError):r.recover(Mock(),plan)
                    docker.assert_not_called()
                self.assertTrue((self.root/'private/existing-recovery-failed.json').exists())

    def test_partial_failure_preserved_without_restart_or_second_start(self):
        from unittest.mock import Mock
        plan=self.plan();op=Mock();op.inspect.return_value={'State':{'Running':False}}
        with patch.object(r,'inventory',return_value=plan),patch.object(r,'protected_snapshot',return_value=plan['protected']),patch.object(r,'database_snapshot',return_value=plan['state']),patch.object(r,'container_snapshot',return_value=plan['containers']),patch.object(r,'docker') as docker:
            with self.assertRaisesRegex(RuntimeError,'exited'):r.recover(op,plan)
        docker.assert_called_once_with('start','mongo')
        self.assertTrue((self.root/'private/existing-recovery-failed.json').exists())

    def test_status_without_accepted_identity_flag_is_not_proof(self):
        observation=self.root/'baseline.json';observation.write_text(json.dumps({'container_started':{}}))
        status={'configuration_matches':True,'baseline_matches':True,'uncertain_operation':False}
        with patch.object(r,'OBSERVATION',observation),patch.object(r,'OBSERVATION_SHA',r.digest(observation.read_bytes())),patch.object(r.subprocess,'check_output',return_value=json.dumps(status).encode()):
            with self.assertRaisesRegex(RuntimeError,'not accepted'):r.protected_snapshot()


    def sandbox(self, project='project'):
        from unittest.mock import Mock
        op=Mock();op.PROJECT=project
        network=project+'_isolated';items={}
        for name in r.SERVICES:
            mounts=[]
            if name=='mongo':
                mounts=[{'Type':'volume','Name':project+'_'+volume,'Destination':destination} for volume,destination in [('mongo','/data/db'),('mongo_config','/data/configdb')]]
            elif name=='router':mounts=[{'Type':'bind','Source':str(self.root/'private/state'),'Destination':'/state'}]
            items[name]={'Id':name,'Image':'image','Config':{},'State':{'Running':False,'StartedAt':'old','OOMKilled':False},'NetworkSettings':{'Networks':{network:{}}},'Mounts':mounts,'HostConfig':{'NetworkMode':network,'Privileged':False,'PublishAllPorts':False,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true'],'RestartPolicy':{'Name':'no'},'PidsLimit':128,'NanoCpus':500000000,'Memory':(192 if name=='router' else 512)*1024*1024,'ReadonlyRootfs':name!='mongo','PortBindings':{'18310/tcp':[{'HostIp':'127.0.0.1','HostPort':'18310'}]} if name=='router' else {}}}
        op.inspect.side_effect=lambda name:items[name]
        network_data={'Internal':True,'Labels':{'com.docker.compose.project':project},'Containers':{}}
        return op,items,network_data

    def test_internal_network_fixed_mounts_and_sandbox_controls(self):
        op,items,network=self.sandbox()
        with patch.object(r,'docker',return_value=json.dumps([network]).encode()):
            self.assertEqual(set(r.container_snapshot(op)),set(r.SERVICES))
            items['railway-simulation']['NetworkSettings']['Networks']['external']={}
            with self.assertRaisesRegex(RuntimeError,'network attachment'):r.container_snapshot(op)

    def test_foreign_volume_published_port_or_privileged_container_refuse(self):
        for change,reason in [('mount','volume'),('port','published port'),('privileged','Sandbox')]:
            with self.subTest(change=change):
                op,items,network=self.sandbox()
                if change=='mount':items['mongo']['Mounts'][0]['Name']='replacement'
                if change=='port':items['mongo']['HostConfig']['PortBindings']={'27017/tcp':[{'HostIp':'0.0.0.0','HostPort':'27017'}]}
                if change=='privileged':items['mongo']['HostConfig']['Privileged']=True
                with patch.object(r,'docker',return_value=json.dumps([network]).encode()):
                    with self.assertRaisesRegex(RuntimeError,reason):r.container_snapshot(op)

    def actual_mongo_mounts(self):
        project='macapps-tph-backup-rehearsal-v3'
        # Full metadata from read-only Docker inspect of the accepted Mongo.
        return [{'Type':'volume','Name':project+'_'+name,'Source':'/var/lib/docker/volumes/'+project+'_'+name+'/_data','Destination':dest,'Driver':'local','Mode':'rw','RW':True,'Propagation':''} for name,dest in [('mongo','/data/db'),('mongo_config','/data/configdb')]]

    def test_actual_mount_permutation_inventory_expected_runtime_and_recovery(self):
        op,items,network=self.sandbox('macapps-tph-backup-rehearsal-v3')
        items['mongo']['Mounts']=self.actual_mongo_mounts()
        state={'site':'railway-simulation','instance_id':'railway-simulation','epoch':5,'watermark':8}
        (self.root/'private/approved-manifest.json').write_text('{}')
        calls=[]
        def docker(*args):
            if args[0]=='network':return json.dumps([network]).encode()
            self.assertEqual(args[0],'start');calls.append(args[1])
            items[args[1]]['State'].update(Running=True,StartedAt='new-'+args[1],Health={'Status':'healthy'})
        with patch.object(r,'protected_snapshot',return_value={'fixed':'accepted'}),patch.object(r,'database_snapshot',return_value=state),patch.object(r,'prove_native_authority'),patch.object(r,'docker',side_effect=docker):
            before=r.inventory(op)
            items['mongo']['Mounts'].reverse()
            after=r.inventory(op)
            self.assertEqual(before,after)
            r.assert_runtime(after['containers'],before['containers'])
            result=r.recover(op,before)
        self.assertEqual(calls,list(r.ORDER))
        self.assertTrue(result['inactive_still_stopped'])
        self.assertTrue((self.root/'private/existing-recovery-completed.json').exists())

    def test_mount_source_rw_and_extra_metadata_remain_identity(self):
        op,items,network=self.sandbox('macapps-tph-backup-rehearsal-v3')
        items['mongo']['Mounts']=self.actual_mongo_mounts()
        with patch.object(r,'docker',return_value=json.dumps([network]).encode()):
            accepted=r.container_snapshot(op)
            for key,value in [('Source','/different/source'),('RW',False),('Propagation','rshared')]:
                with self.subTest(key=key):
                    old=items['mongo']['Mounts'][0][key];items['mongo']['Mounts'][0][key]=value
                    changed=r.container_snapshot(op)
                    with self.assertRaisesRegex(RuntimeError,'identity/start'):r.assert_runtime(changed,accepted)
                    items['mongo']['Mounts'][0][key]=old

    def test_extra_and_duplicate_mount_destinations_including_cross_type_refuse(self):
        op,items,network=self.sandbox('macapps-tph-backup-rehearsal-v3')
        base=self.actual_mongo_mounts()
        for extra,reason in [(dict(base[0]),'Duplicate'),({'Type':'tmpfs','Destination':'/data/db'},'Duplicate'),({'Type':'volume','Name':'extra','Destination':'/extra','Source':'/extra','RW':True},'Unexpected persistent')]:
            with self.subTest(extra=extra):
                items['mongo']['Mounts']=copy.deepcopy(base)+[extra]
                with patch.object(r,'docker',return_value=json.dumps([network]).encode()):
                    with self.assertRaisesRegex(RuntimeError,reason):r.container_snapshot(op)

    def test_native_authority_probe_is_fixed_get_and_rejects_wrong_checkpoint(self):
        owner={'id':'a'*64}; state={'authority_sha256':r.digest(b'synthetic')}
        proof={'database':'tph_backup_restored','source':'b369e9f5e28584ba99f1cbe35d8f65080a51aeda','watermark':8,'pin_usage':3,'authority_id':'synthetic','instance_prefix':'a'*12}
        with patch.object(r,'docker',return_value=json.dumps(proof).encode()) as docker:
            r.prove_native_authority(owner,state)
            self.assertIn("5051/authority",docker.call_args.args[-1])
            self.assertNotIn('POST',docker.call_args.args[-1])
        proof['pin_usage']=4
        with patch.object(r,'docker',return_value=json.dumps(proof).encode()):
            with self.assertRaisesRegex(RuntimeError,'checkpoint changed'):r.prove_native_authority(owner,state)


if __name__ == '__main__':unittest.main()
