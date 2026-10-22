"""No Docker/SSH/providers: authority checks and transactional activation simulations."""
import copy
import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runtime_phase2 as phase
import prepare


def approval():
    return {**phase.approval_contract('a'*64,'b'*64),
            'qa':{'reviewer':'fresh-qa','reference':'qa-source-proof','decision':'GO'},
            'security':{'reviewer':'fresh-security','reference':'security-source-proof','decision':'GO'},
            'expires_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat()}


def role_report():
    rows=[{'resource':{'db':'tph_local_test','collection':name},'actions':['find','listIndexes']} for name in phase.READS]
    rows += [{'resource':{'db':'tph_local_test','collection':''},'actions':['listCollections']},
             {'resource':{'db':'tph_local_test','collection':'pins'},'actions':['update']}]
    own={'role':'clone_reader_role','db':'tph_local_test'}
    return {'role':{**own,'roles':[],'inheritedRoles':[],'privileges':rows,'inheritedPrivileges':copy.deepcopy(rows),'isBuiltin':False},
            'user':{'user':'clone_reader','db':'tph_local_test','roles':[own],'inheritedRoles':[own],'inheritedPrivileges':copy.deepcopy(rows)},
            'denied_explain_count':8,'denied_find_count':3,'counts':{'Bookings':2916,'parkingspaces':47,'pins':2}}


def data():
    return {'collections':78,'documents':136410,'indexes':556,'ttl_enabled':False,'ttl_deleted':0,
            'counts':{'Bookings':2916,'parkingspaces':47,'pins':2},'namespace_counts_sha256':'a'*64,
            'schema_sha256':'b'*64,'pins_sha256':'c'*64}


def item(service,spec,env):
    cid={'mongo':phase.MONGO,'web':'d'*64,'gateway':'e'*64}[service]
    environment={k:phase.re.sub(r'\$\{([A-Z_]+):\?required\}',lambda m:env[m[1]],v)
                 for k,v in spec.get('environment',{}).items()}
    return {'Name':'/'+phase.PROJECT+'-'+service+'-1','Id':cid,'Image':spec['image'],
            'State':{'Running':True,'OOMKilled':False,'ExitCode':0,'StartedAt':'fixed-start','Health':{'Status':'healthy'}},
            'Config':{'Env':[k+'='+v for k,v in environment.items()],'User':'node' if service=='web' else '',
                      'Cmd':spec.get('command',[]),'Labels':{'com.docker.compose.project':phase.PROJECT}},
            'HostConfig':{'PortBindings':{'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'18221'}]} if service=='gateway' else {},
                          'Privileged':False,'ReadonlyRootfs':service!='mongo','Devices':[],'CapAdd':[],
                          'CapDrop':['ALL'] if service=='web' else []},
            'Mounts':[{'Type':'bind','Source':v.split(':')[0],'Destination':v.split(':')[1],'RW':False}
                      for v in spec.get('volumes',[]) if v.startswith('/')],
            'NetworkSettings':{'Networks':{phase.PROJECT+'_isolated':{},**({phase.PROJECT+'_ingress':{}} if service=='gateway' else {})},
                               'Ports':{'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'18221'}]} if service=='gateway' else {}}}


class Simulated(phase.Runner):
    def __init__(self,root):
        super().__init__(root)
        self.events=[];self.started=[];self.broken=None;self.role=role_report();self.values=data()
        self.private.mkdir();self.profile.mkdir();self.directory.mkdir()
        (self.profile/'create-reader-role.js').write_text('EXACT_REVIEWED_PHASE2_ROLE')
        self.env={name:'FRESH_LOCAL_'+'x'*31 for name in ('CLONE_RESTORE_PASSWORD','CLONE_READER_PASSWORD','CLONE_MANAGER_SECRET','CLONE_JWT_SECRET','CLONE_API_SECRET')}
        manifest={'images':{'web':phase.IMAGE,'mongo':'sha256:'+'1'*64,'gateway':'sha256:'+'2'*64},'source':phase.SOURCE,'token':'0'*32}
        self.spec=prepare.specification(manifest,root);self.spec['name']=phase.PROJECT
        self.spec['services']['web']['environment'].update(AUTH0_DOMAIN=phase.DOMAIN,AUTH0_AUDIENCE='https://trucksparkinghub.com/api')
        self.base_spec=copy.deepcopy(self.spec);self.base={'manifest':manifest}
        self.runner_sha='a'*64;self.approval_sha='b'*64
        self.items={phase.MONGO:item('mongo',self.spec['services']['mongo'],self.env)}
        (self.private/'source-target-comparison.json').write_text(json.dumps({'comparison':{'matches':True,'document_count':136410,'namespace_count':78}}))
        (self.private/'target-inventory.json').write_text(json.dumps({'document_count':136410,'namespace_count':78,'namespaces':{'native':{'index_count':556}}}))
        for p in self.private.glob('*.json'):p.chmod(0o600)

    def verify_files(self):
        self.events.append('verify-files')
        if self.broken=='files':raise RuntimeError('artifact drift')

    def protected(self,controller):
        if self.broken=='protected-after-web' and 'web' in self.started:return {'drift':True}
        return {'accepted18':'EXACT_UNCHANGED','retained_extras':'EXACT_UNCHANGED'}

    def mongo(self,script,label,reader=False):
        self.events.append(label)
        if script==phase.DATA_JS:
            result=copy.deepcopy(self.values)
            if self.broken=='startup-data' and 'web' in self.started:result['pins_sha256']='f'*64
            return result
        if script==phase.ROLE_VERIFY_JS:return self.role
        if script=='EXACT_REVIEWED_PHASE2_ROLE':
            self.assert_marker= self.marker.exists()
            return {'rolePrepared':True}
        raise AssertionError('Unexpected script / old mounted script must never execute')

    def command(self,args,label,**kw):
        self.events.append((label,args))
        if args[0]=='inspect':return json.dumps([self.items[args[1]]]).encode()
        if args[:2]==['network','inspect']:
            internal=args[2].endswith('_isolated')
            members={phase.MONGO,*[self.items[x]['Id'] for x in self.items if x!=phase.MONGO]} if internal else {'e'*64}
            return json.dumps([{'Internal':internal,'Driver':'bridge','IPAM':{'Config':[{'Subnet':'10.240.64.0/24' if internal else '10.240.65.0/24'}]},'Containers':{cid:{} for cid in members}}]).encode()
        if args[0]=='ps':return b'EXISTING' if self.broken=='existing' else b''
        if args[:2]==['image','inspect']:
            return json.dumps([{'Id':args[2],'Os':'linux','Architecture':'amd64' if self.broken=='image' else 'arm64'}]).encode()
        if args[0]=='compose':
            service=args[-1]
            if 'up' in args:
                if self.broken=='web-start' and service=='web':raise RuntimeError('start failed')
                self.started.append(service);self.items[{'web':'d'*64,'gateway':'e'*64}[service]]=item(service,self.spec['services'][service],self.env)
                return b''
            return ({'web':'d'*64,'gateway':'e'*64}[service]+'\n').encode()
        if args[0]=='exec':
            if 'example.com' in args[-1]:return b'egress-denied\n'
            return json.dumps({'status':'ready','environment':'real-data-clone','source':phase.SOURCE,
                               'scheduler':'disabled','workers':0}).encode()
        raise AssertionError('Unexpected Docker operation')

    def http(self,method,path,origin=None,body=None):
        self.events.append(('http',method,path,origin))
        if path=='/signin':return 200,{'X-Local-Test':'real-data-copy-read-only-no-business-effects',
             'Content-Security-Policy':"connect-src 'self' https://"+phase.DOMAIN+"; worker-src 'none'"},b'MAC COPY - Real data captured October 22'
        if path=='/api/pin/verify-client' and origin=='https://tph-test.elisprotech.com':return 400,{},b''
        return (200 if self.broken=='http' else 403),{},b''


class Phase2Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.old_umask=os.umask(0o077)

    def tearDown(self):
        os.umask(self.old_umask);self.temp.cleanup()

    def test_approval_exact_hashes_independent_expiry_and_no_self_approval(self):
        value=approval();phase.validate_approval(value,'a'*64,'b'*64)
        for change in (lambda v:v.update(web_image='sha256:'+'f'*64),lambda v:v.update(public_cutover=True),
                       lambda v:v['qa'].update(reviewer='hosting_contract'),lambda v:v['security'].update(reviewer='fresh-qa'),
                       lambda v:v.update(expires_at='2000-01-01T00:00:00+00:00'),lambda v:v.update(unreviewed=True)):
            modified=copy.deepcopy(value);change(modified)
            with self.assertRaises(RuntimeError):phase.validate_approval(modified,'a'*64,'b'*64)

    def test_role_exact_case_privileges_quarantine_and_denial_proofs(self):
        report=role_report();phase.validate_role(report)
        for change in (lambda r:r['role']['privileges'].append({'resource':{'db':'tph_local_test','collection':'users'},'actions':['find']}),
                       lambda r:r['user']['roles'].append({'role':'readWrite','db':'tph_local_test'}),
                       lambda r:r['role']['privileges'][0]['actions'].append('insert'),
                       lambda r:r.update(denied_explain_count=7),lambda r:r['counts'].update(Bookings=0)):
            modified=copy.deepcopy(report);change(modified)
            with self.assertRaises(RuntimeError):phase.validate_role(modified)
        self.assertIn('Bookings',phase.privileges(report['role']['privileges']))
        self.assertNotIn('bookings',phase.privileges(report['role']['privileges']))
        self.assertNotIn('insertOne',phase.ROLE_VERIFY_JS)
        self.assertIn('explain:op',phase.ROLE_VERIFY_JS)
        self.assertIn('_id:{$exists:false}',phase.ROLE_VERIFY_JS)

    def test_rehearsal_exact_live_endpoints_exclude_only_sealed_stopped_actor(self):
        sealed = {name: {'id': letter*64, 'running': running} for name,letter,running in
                  [('mongo','a',True),('railway-simulation','b',True),('mac-backup','c',False),('router','d',True)]}
        network = {'Internal': True, 'Containers': {letter*64: {} for letter in ('a','b','d')}}
        phase.validate_rehearsal_network(network, sealed)
        # The parked actor is still present in the sealed four-container set.
        self.assertEqual(len(sealed), 4)
        for change in (lambda n: n['Containers'].update({'f'*64:{}}),
                       lambda n: n['Containers'].update({'c'*64:{}}),
                       lambda n: n['Containers'].pop('b'*64),
                       lambda n: n.update(Internal=False)):
            changed = copy.deepcopy(network);change(changed)
            with self.assertRaisesRegex(RuntimeError,'rehearsal_network_membership'):
                phase.validate_rehearsal_network(changed, sealed)

    def test_native_data_ttl_and_all_count_index_gates(self):
        phase.validate_data(data())
        for key,value in [('ttl_enabled',True),('ttl_deleted',34),('documents',136376),('indexes',555),('pins_sha256','INVALID')]:
            modified=data();modified[key]=value
            with self.assertRaises(RuntimeError):phase.validate_data(modified)

    def test_success_journals_before_role_starts_only_web_then_gateway(self):
        runner=Simulated(self.root)
        with patch.object(phase.socket,'socket'):
            result=runner.execute_locked(None)
        self.assertTrue(result['phase2_local_started']);self.assertFalse(result['public_cutover'])
        self.assertTrue(runner.assert_marker)
        self.assertEqual(runner.started,['web','gateway'])
        self.assertTrue((runner.private/'phase2-completed.json').exists())
        self.assertTrue(runner.marker.exists())
        self.assertEqual(runner.events.count('role-create'),1)
        commands=[e[1] for e in runner.events if isinstance(e,tuple) and e[0] in ('web-up','gateway-up')]
        self.assertTrue(all('--no-deps' in c and '--wait' in c and '--force-recreate' not in c for c in commands))
        with self.assertRaisesRegex(RuntimeError,'already_started_or_uncertain'):
            runner.execute(phase.PLAN_SHA,'a'*64)

    def test_preexisting_scope_or_image_refuses_before_role(self):
        for failure in ('existing','image','files'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                runner=Simulated(Path(temp).resolve());runner.broken=failure
                with patch.object(phase.socket,'socket'),self.assertRaises(RuntimeError):runner.execute_locked(None)
                self.assertNotIn('role-create',runner.events);self.assertEqual(runner.started,[])
                self.assertFalse(runner.marker.exists())

    def test_uncertain_start_keeps_marker_no_cleanup_or_retry(self):
        runner=Simulated(self.root);runner.broken='web-start'
        with patch.object(phase.socket,'socket'),self.assertRaises(RuntimeError):runner.execute_locked(None)
        self.assertTrue(runner.marker.exists());self.assertFalse((runner.private/'phase2-completed.json').exists())
        self.assertIn('role-create',runner.events)
        self.assertFalse(any(any(v in ('rm','stop','down','restart','prune') for v in e[1]) for e in runner.events if isinstance(e,tuple) and isinstance(e[1],list)))

    def test_protected_or_native_startup_drift_prevents_gateway(self):
        for failure in ('protected-after-web','startup-data'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temp:
                runner=Simulated(Path(temp).resolve());runner.broken=failure
                with patch.object(phase.socket,'socket'),self.assertRaises(RuntimeError):runner.execute_locked(None)
                self.assertEqual(runner.started,['web']);self.assertTrue(runner.marker.exists())
                self.assertFalse((runner.private/'phase2-completed.json').exists())

    def test_private_files_and_immutable_approval_hardlinks_symlinks_refused(self):
        path=self.root/'approval.json';path.write_bytes(b'{}');path.chmod(0o400)
        self.assertEqual(phase.private_read(path,immutable=True),b'{}')
        path.chmod(0o600)
        with self.assertRaises(RuntimeError):phase.private_read(path,immutable=True)
        path.chmod(0o400);os.link(path,self.root/'hardlinked')
        with self.assertRaises(RuntimeError):phase.private_read(path,immutable=True)
        link=self.root/'symlink';link.symlink_to(path)
        with self.assertRaises(RuntimeError):phase.private_read(link,immutable=True)

    def test_runtime_security_and_exact_database_environment(self):
        runner=Simulated(self.root);spec=runner.spec['services']['web'];web=item('web',spec,runner.env)
        phase.validate_runtime(web,spec,'web',runner.env)
        for change in (lambda w:w['HostConfig'].update(Privileged=True),
                       lambda w:w['NetworkSettings']['Networks'].update({'foreign_egress':{}}),
                       lambda w:w['Config']['Env'].append('MONGO_URI_DEV=mongodb://production.invalid/live'),
                       lambda w:w['Mounts'][0].update(RW=True),lambda w:w['Config'].update(User='root')):
            modified=copy.deepcopy(web);change(modified)
            with self.assertRaises(RuntimeError):phase.validate_runtime(modified,spec,'web',runner.env)

    def test_http_negatives_uppercase_and_no_credential_guess(self):
        runner=Simulated(self.root);self.assertFalse(runner.http_checks()['valid_credentials_tested'])
        calls=[e for e in runner.events if isinstance(e,tuple) and e[0]=='http']
        self.assertTrue(any(e[2]=='/API/BOOKINGS/AUTH/SESSION' for e in calls))
        self.assertIsNone(phase.NoRedirect().redirect_request(None,None,302,'',{},'https://production.invalid'))
        runner.broken='http'
        with self.assertRaises(RuntimeError):runner.http_checks()


if __name__=='__main__':unittest.main()
