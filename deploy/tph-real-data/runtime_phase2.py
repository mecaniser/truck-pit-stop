"""One-shot reviewed local clone role/web/gateway activation. Never changes public ingress.

HELD until independent source/plan approval. No automatic retry, cleanup, reset,
restore, migration, provider call or valid-PIN guess. Run exactly:
python3 runtime_phase2.py <PHASE2_PLAN_SHA256> <PRIVATE_APPROVAL_FILE_SHA256>
Approval is private/phase2-runtime-approval.json, mode0400, externally authored;
see approval_contract() for exact binding/reviewer fields. Any started journal
requires investigation; this program never resumes it or deletes its evidence.
"""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path.home() / 'mac-hosting/tph-real-data-v3'
PROFILE = 'phase2-auth0'
PLAN_SHA = '695f276e35f16a54ee8ac6759f63e4196b09d0f99743b0ed53f8ccb53aa95dcf'
BASE_SHA = 'b5b98d067f01e178f7ba85fcc8387ed804924e1aead3c17075d9d7af16d431d1'
PROJECT = 'macapps-tph-real-data-2c0eb4a11903'
MONGO = 'c73ebffa80e5c221d54929ed71c71425bcc726646a172b18e48e23f95ea11a9c'
IMAGE = 'sha256:95df264063f3224f9a2519fd68a99e537f7a8da26d17ff78b5e6a87267a798b0'
CONTROLLER_SHA = '802aef1cc4760868cbe905e88711f1ddbc55d5471ada99ff735e273e7765744e'
OPERATOR_SHA = 'c7faf2b289de7a14b21261005d7964df3526e3db8afba82b46e6cb57eb21252c'
SOURCE = 'b369e9f5e28584ba99f1cbe35d8f65080a51aeda'
COMPARISON_SHA = '510cc1d9b0849226b490db9a283943da9e6698bda04cb7d3071ccea38687c9b0'
TARGET_SHA = '6e301018511d43f96cd56aff18d4b7509dc7a5bc645779d755e9846e5293a7cf'
DIAGNOSTIC = '115e71c2d0db045a2644eb4fcc759a1fc390b99d32fdb1d5b6e36402d2e21767'
V2_MONGO = 'e38bc73c8491ee31f1ea6257b85e51cd240dabf0c9ad8eabbc2a8d6bc4d4c3f4'
DOCKER = ['/Applications/Docker.app/Contents/Resources/bin/docker', '--context', 'desktop-linux']
DOMAIN = 'dev-wp1mdcmju5ix3zgt.us.auth0.com'
READS = ('pins', 'parkingspaces', 'parkingbays', 'Bookings', 'parkingspotchangelogs', 'sitesettings',
         'blogposts', 'landlords', 'spotadditionrequests', 'locationadditionrequests', 'paymentfeeplans')
BASELINES = {'soak-baseline.json': '1e7618809a071feb45cadb84667827c97c483c63f7e3fbf645b92628b4544d1e',
 'observations/20261022T192823Z/soak-baseline.json': '0002ccdd4d0b797e4a79543c1be310cd7a292d8f23b8ecba786031dec16ed328'}
EDGE = {'Caddyfile.local': '300bd104a9c6f0a20d4ba3eb8bf6d98c61bb503c97220cc007952429b9f2887d',
        'Caddyfile.public.DISABLED': 'a2755b8873e0fab07ff5b6234bbba3a49be6e14fbfa9916031ca254d4b1d6e45'}
HEX = re.compile(r'[0-9a-f]{64}\Z')


def check(ok, code):
    if not ok:
        raise RuntimeError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def private_read(path, *, immutable=False):
    check(path.is_absolute() and path.resolve() == path and not path.is_symlink(), 'private_path_refused')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        check(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1
              and not (before.st_mode & 0o077) and before.st_size <= 64 * 1024 * 1024
              and (not immutable or stat.S_IMODE(before.st_mode) == 0o400), 'private_artifact_refused')
        raw = source.read()
        after = os.fstat(source.fileno())
        check(all(getattr(before, k) == getattr(after, k) for k in
                  ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode')), 'private_artifact_race')
        return raw


def write_once(path, value):
    with path.open('xb') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(canonical(value) + b'\n')
        output.flush()
        os.fsync(output.fileno())
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def approval_contract(runner_sha, env_sha):
    """External approval must contain these bindings plus qa/security/expires_at.

    decision=approve_phase2_local_only; qa/security each {reviewer,reference,
    decision:'GO'} with different independent people/agents, neither implementer
    'hosting_contract'. expires_at timezone-aware within24h. No approval generator.
    """
    return {'version': 1, 'decision': 'approve_phase2_local_only', 'runner_sha256': runner_sha,
            'phase2_plan_sha256': PLAN_SHA, 'base_plan_sha256': BASE_SHA,
            'comparison_sha256': COMPARISON_SHA, 'target_inventory_sha256': TARGET_SHA,
            'environment_sha256': env_sha, 'mongo_cid': MONGO, 'project': PROJECT,
            'web_image': IMAGE, 'controller_sha256': CONTROLLER_SHA, 'operator_sha256': OPERATOR_SHA, 'public_cutover': False}


def validate_approval(value, runner_sha, env_sha):
    check(set(value) == set(approval_contract(runner_sha, env_sha)) | {'qa', 'security', 'expires_at'}, 'approval_schema')
    check(all(value[k] == v for k, v in approval_contract(runner_sha, env_sha).items()), 'approval_binding')
    reviews = [value[k] for k in ('qa', 'security')]
    check(all(set(v) == {'reviewer', 'reference', 'decision'} and isinstance(v['reviewer'], str)
              and v['reviewer'].strip() and v['reviewer'] != 'hosting_contract' and v['reference']
              and v['decision'] == 'GO' for v in reviews)
          and reviews[0]['reviewer'] != reviews[1]['reviewer'], 'independent_reviews_required')
    expires = datetime.datetime.fromisoformat(value['expires_at'])
    now = datetime.datetime.now(datetime.timezone.utc)
    check(expires.tzinfo is not None and now < expires <= now + datetime.timedelta(hours=24), 'approval_expired')


def privileges(rows):
    result = {}
    for row in rows:
        check(set(row) == {'resource', 'actions'} and set(row['resource']) == {'db', 'collection'}
              and row['resource']['db'] == 'tph_local_test', 'unexpected_privilege_resource')
        key = row['resource']['collection']
        result.setdefault(key, set()).update(row['actions'])
    return {key: sorted(values) for key, values in result.items()}


def validate_role(report):
    expected = {name: ['find', 'listIndexes'] for name in READS}
    expected['pins'].append('update')
    expected[''] = ['listCollections']
    own = {'role': 'clone_reader_role', 'db': 'tph_local_test'}
    role, user = report['role'], report['user']
    check(role['role'] == own['role'] and role['db'] == own['db'] and not role['isBuiltin']
          and role['roles'] == [] and role['inheritedRoles'] == []
          and privileges(role['privileges']) == expected and privileges(role['inheritedPrivileges']) == expected,
          'role_privileges_refused')
    check(user['user'] == 'clone_reader' and user['db'] == own['db'] and user['roles'] == [own]
          and user['inheritedRoles'] == [own] and privileges(user['inheritedPrivileges']) == expected,
          'user_privileges_refused')
    check(report['denied_explain_count'] == 8 and report['denied_find_count'] == 3
          and report['counts'] == {'Bookings': 2916, 'parkingspaces': 47, 'pins': 2}, 'role_runtime_denials_or_counts')


def validate_data(value):
    check(value['collections'] == 78 and value['documents'] == 136410 and value['indexes'] == 556
          and value['ttl_enabled'] is False and value['ttl_deleted'] == 0
          and value['counts'] == {'Bookings': 2916, 'parkingspaces': 47, 'pins': 2}
          and all(HEX.fullmatch(value[k]) for k in ('namespace_counts_sha256', 'schema_sha256', 'pins_sha256')), 'native_data_drift')


AUTH_JS = "const a=db.getSiblingDB('admin').auth(process.env.MONGO_INITDB_ROOT_USERNAME,process.env.MONGO_INITDB_ROOT_PASSWORD);if(!(a===1||a?.ok===1))throw Error('local_auth_refused');"
DATA_JS = AUTH_JS + r'''
const crypto=require('crypto'),t=db.getSiblingDB('tph_local_test');
const digest=x=>crypto.createHash('sha256').update(x).digest('hex');
const json=x=>JSON.stringify(EJSON.serialize(x,{relaxed:false}));
const infos=t.getCollectionInfos().sort((a,b)=>a.name.localeCompare(b.name));
let total=0,indexCount=0,records=[],schemas=[];
for(const info of infos){
 const c=t.getCollection(info.name),count=c.countDocuments({});
 const indexes=c.getIndexes().sort((a,b)=>a.name.localeCompare(b.name));
 records.push([info.name,count]);schemas.push([info.name,info.type,info.options,indexes]);
 total+=count;indexCount+=indexes.length;
}
const ttl=db.getSiblingDB('admin').runCommand({getParameter:1,ttlMonitorEnabled:1});
const metrics=db.getSiblingDB('admin').serverStatus().metrics.ttl;
print(JSON.stringify({collections:infos.length,documents:total,indexes:indexCount,
 namespace_counts_sha256:digest(JSON.stringify(records)),schema_sha256:digest(json(schemas)),
 pins_sha256:digest(json(t.pins.find({}).sort({_id:1}).toArray())),
 counts:{Bookings:t.getCollection('Bookings').countDocuments({}),parkingspaces:t.parkingspaces.countDocuments({}),pins:t.pins.countDocuments({})},
 ttl_enabled:ttl.ttlMonitorEnabled,ttl_deleted:Number(metrics.deletedDocuments)}));
'''
ROLE_VERIFY_JS = AUTH_JS + r'''
const fs=require('fs'),input=JSON.parse(fs.readFileSync(0,'utf8'));
if(Object.keys(input).join(',')!=='password'||!/^[-_a-zA-Z0-9]{43}$/.test(input.password))throw Error('reader_input_refused');
const t=db.getSiblingDB('tph_local_test'),role=t.getRole('clone_reader_role',{showPrivileges:true});
const user=t.runCommand({usersInfo:{user:'clone_reader',db:'tph_local_test'},showPrivileges:true,showCredentials:false}).users[0];
const reader=new Mongo('mongodb://clone_reader:'+encodeURIComponent(input.password)+'@127.0.0.1:27017/tph_local_test?authSource=tph_local_test').getDB('tph_local_test');
let explainDenied=0,findDenied=0;
for(const name of ['Bookings','parkingspaces','blogresearchjobs','paymentlogs']){
 for(const op of [{update:name,updates:[{q:{_id:{$exists:false}},u:{$set:{__clone_forbidden:true}}}]},
                  {delete:name,deletes:[{q:{_id:{$exists:false}},limit:1}]}]){
  let denied=false;try{const result=reader.runCommand({explain:op,verbosity:'queryPlanner'});denied=result.code===13}
  catch(e){if(e.code===13)denied=true;else throw Error('unexpected_explain_failure')}
  if(!denied)throw Error('write_explain_was_not_denied');explainDenied++;
 }
}
for(const name of ['users','logs','blogresearchjobs']){
 let denied=false;try{reader.getCollection(name).find({_id:{$exists:false}}).limit(1).toArray()}catch(e){if(e.code===13)denied=true;else throw Error('unexpected_find_failure')}
 if(!denied)throw Error('quarantine_find_was_not_denied');findDenied++;
}
print(JSON.stringify({role,user,denied_explain_count:explainDenied,denied_find_count:findDenied,
 counts:{Bookings:reader.getCollection('Bookings').countDocuments({}),parkingspaces:reader.parkingspaces.countDocuments({}),pins:reader.pins.countDocuments({})}}));
'''


def validate_rehearsal_network(network, sealed_containers):
    # Stopped actors retain their identity and network attachment configuration,
    # but Docker removes their live endpoint. The sealed receipt decides which
    # exact actors may have live endpoints; never accept a subset or foreign ID.
    running_ids = {row['id'] for row in sealed_containers.values() if row['running'] is True}
    check(network['Internal'] is True and set(network['Containers']) == running_ids,
          'rehearsal_network_membership')


def container_identity(item):
    mounts = sorted(item['Mounts'], key=lambda v: (v['Destination'], v['Type'], canonical(v)))
    check(len({v['Destination'] for v in mounts}) == len(mounts), 'duplicate_mount_destination')
    return {'id': item['Id'], 'image': item['Image'], 'config_sha256': sha(canonical(item['Config'])),
            'host_sha256': sha(canonical(item['HostConfig'])), 'mounts_sha256': sha(canonical(mounts)),
            'networks_sha256': sha(canonical(item['NetworkSettings']['Networks'])),
            'started': item['State']['StartedAt'], 'running': item['State']['Running'],
            'oom': item['State']['OOMKilled'], 'exit_code': item['State']['ExitCode']}


def validate_runtime(item, spec, service, local_env=None):
    check(item['Name'] == '/' + PROJECT + '-' + service + '-1' and HEX.fullmatch(item['Id'])
          and item['Image'] == spec['image'] and item['State']['Running'] and not item['State']['OOMKilled'], 'new_runtime_identity')
    host = item['HostConfig']
    networks = {PROJECT + '_isolated'} | ({PROJECT + '_ingress'} if service == 'gateway' else set())
    check(set(item['NetworkSettings']['Networks']) == networks and not host.get('Privileged')
          and host['ReadonlyRootfs'] and not host.get('Devices') and not host.get('CapAdd'), 'new_runtime_security')
    ports = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '18221'}]} if service == 'gateway' else {}
    check((host.get('PortBindings') or {}) == ports
          and {k:v for k,v in (item['NetworkSettings'].get('Ports') or {}).items() if v is not None} == ports,
          'new_runtime_ports')
    expected = {value.split(':')[1]: value.split(':')[0] for value in spec['volumes']}
    actual = {m['Destination']:m for m in item['Mounts']}
    check(len(actual) == len(item['Mounts']) == len(expected)
          and all(m['Type'] == 'bind' and m['Source'] == expected[target] and m['RW'] is False for target,m in actual.items()),
          'new_runtime_mounts')
    if service == 'web':
        check(item['Config']['User'] == 'node' and host['CapDrop'] == ['ALL']
              and item['Config']['Cmd'] == ['node','tph-web.cjs'] and item['State']['Health']['Status'] == 'healthy', 'web_profile')
        env = dict(v.split('=',1) for v in item['Config']['Env'])
        check(local_env is not None, 'explicit_local_environment_required')
        for key, expected in spec['environment'].items():
            value = re.sub(r'\$\{([A-Z_]+):\?required\}', lambda m: local_env[m[1]], expected)
            check(env.get(key) == value, 'web_exact_environment_binding')
        check(env.get('LOCAL_SOURCE_SHA') == SOURCE and env.get('AUTH0_DOMAIN') == DOMAIN
              and env.get('AUTH0_AUDIENCE') == 'https://trucksparkinghub.com/api'
              and env.get('SQUARE_ENVIRONMENT') == 'sandbox' and env.get('DISABLE_SCHEDULER') == 'true'
              and env.get('SQUARE_ACCESS_TOKEN') == 'LOCAL_TEST_INVALID_NOT_A_PROVIDER_CREDENTIAL'
              and all(env.get(key) == 'false' for key in ('BLOG_STUDIO_ENABLED','BLOG_STUDIO_RUN_IN_WEB',
                  'WORKOS_TENANT_ENABLED','MONTHLY_SUBSCRIPTIONS_ENABLED','MONTHLY_CUSTOM_AUTOPAY_ENABLED',
                  'HIRING_CANDIDATE_SMS_ENABLED','ADMIN_SMS_ENABLED','ADMIN_PAYMENT_SMS_ENABLED','ERROR_ALERTS_ENABLED','ERROR_ALERTS_SMS_ENABLED')),
              'web_provider_or_source_profile')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Runner:
    def __init__(self, root=ROOT):
        self.root = root
        self.private = root / 'private'
        self.profile = root / PROFILE
        self.directory = self.private / 'phase2-runtime'
        self.marker = self.private / 'phase2-started.json'
        self.serial = 0

    def command(self, args, label, *, input=None, timeout=60):
        self.serial += 1
        prefix = self.directory / ('%03d-' % self.serial + label)
        with prefix.with_suffix('.stdout.private').open('xb') as out, prefix.with_suffix('.stderr.private').open('xb') as err:
            os.fchmod(out.fileno(),0o600);os.fchmod(err.fileno(),0o600)
            result = subprocess.run(DOCKER + args, input=input, stdout=out, stderr=err, timeout=timeout)
        check(result.returncode == 0, 'phase2_command_failed_' + label)
        return prefix.with_suffix('.stdout.private').read_bytes()

    def inspect(self, cid):
        return json.loads(self.command(['inspect',cid], 'inspect'))[0]

    def mongo(self, script, label, reader=False):
        value = canonical({'password':self.env['CLONE_READER_PASSWORD']}) if reader else None
        raw = self.command(['exec', *(['-i'] if reader else []), MONGO,'mongosh','--quiet','--eval',script], label,
                           input=value,timeout=180)
        return json.loads(raw.decode().strip().splitlines()[-1])

    def verify_files(self):
        check(private_read(self.root / '.owner') == b'macapps-tph-real-data-v1\n', 'root_owner')
        check(sha(private_read(self.root / 'plan.json')) == BASE_SHA and sha(private_read(self.profile/'plan.json')) == PLAN_SHA,
              'plan_drift')
        for name,digest in self.base['artifacts_sha256'].items():
            check((self.root/name).resolve() == self.root/name and sha((self.root/name).read_bytes()) == digest, 'base_artifact_drift')
        for name,digest in self.plan['artifacts_sha256'].items():
            check(Path(name).name == name and (self.profile/name).resolve() == self.profile/name
                  and sha((self.profile/name).read_bytes()) == digest, 'profile_artifact_drift')
        check(sha(private_read(self.private/'source-target-comparison.json')) == COMPARISON_SHA
              and sha(private_read(self.private/'target-inventory.json')) == TARGET_SHA, 'data_equality_receipt_drift')
        check(sha(private_read(self.private/'clone.env')) == self.env_sha, 'local_environment_drift')
        check(sha(Path(__file__).read_bytes()) == self.runner_sha
              and sha(private_read(self.private/'phase2-runtime-approval.json', immutable=True)) == self.approval_sha,
              'runner_or_approval_drift')
        for relative,digest in (('mac-hosting/test-deploy/remote.py',CONTROLLER_SHA),
                                ('mac-hosting/test-stacks/tools/stackctl.py',OPERATOR_SHA)):
            path=Path.home()/relative
            check(path.resolve()==path and sha(path.read_bytes())==digest,'accepted_helper_drift')
        for rel,digest in BASELINES.items():
            check(sha(private_read(Path.home()/'dieselbridge-staging/private'/rel)) == digest,'baseline_drift')
        for name,digest in EDGE.items():
            check(sha((Path.home()/'mac-hosting/test-public'/name).read_bytes()) == digest,'public_upstream_drift')

    def protected(self, controller):
        state = controller.status()
        check(all(state.get(k) is True for k in ('identity_matches','configuration_matches','baseline_matches'))
              and state.get('uncertain_operation') is False and state.get('uncertain_recovery') is False,'protected_state_drift')
        check(len(state['snapshot']['containers']) == 14 and all(v['running'] and not v['oom'] and v['health'] in (None,'healthy')
              for v in state['snapshot']['containers'].values()),'protected_health')
        check(all(v.get('ready') is True and v.get('matches_accepted_source') is True for v in state['live_runtime'].values()),'protected_source')
        fourteen = {name:container_identity(self.inspect(v['id'])) for name,v in state['snapshot']['containers'].items()}
        receipt = Path.home()/'mac-hosting/tph-backup-rehearsal-v3/private/router-port-completed.json'
        check(sha(private_read(receipt)) == '4df056156893ea1c0a2086e14d1a9e8a238992c9a9c72f84ecdf933e36629a30','rehearsal_receipt_drift')
        expected = json.loads(private_read(receipt))['containers']
        check(set(expected) == {'mongo','railway-simulation','mac-backup','router'},'rehearsal_membership')
        rehearsal = {}
        rehearsal_networks = set()
        for service,old in expected.items():
            item = self.inspect(old['id']);mounts=sorted(item['Mounts'],key=lambda m:(m['Destination'],m['Type']))
            row = {'id':item['Id'],'image':item['Image'],'config_sha256':sha(json.dumps(item['Config'],sort_keys=True).encode()),
                   'host_sha256':sha(canonical(item['HostConfig'])),'mounts_sha256':sha(canonical(mounts)),
                   'running':item['State']['Running'],'started':item['State']['StartedAt'],'health':item['State'].get('Health',{}).get('Status')}
            check(row == old and not item['State']['OOMKilled'],'rehearsal_identity')
            netname = item['Config']['Labels']['com.docker.compose.project'] + '_isolated'
            check(set(item['NetworkSettings']['Networks']) == {netname}, 'rehearsal_network_attachment')
            rehearsal_networks.add(netname)
            rehearsal[service]=container_identity(item)
        check(len(rehearsal_networks) == 1, 'rehearsal_network_scope')
        net = json.loads(self.command(['network','inspect',next(iter(rehearsal_networks))], 'rehearsal-network'))[0]
        validate_rehearsal_network(net, expected)
        extras={name:container_identity(self.inspect(cid)) for name,cid in [('v2_failed_mongo',V2_MONGO),('completed_diagnostic',DIAGNOSTIC)]}
        check(not extras['completed_diagnostic']['running'] and extras['completed_diagnostic']['exit_code']==0,'diagnostic_state')
        return {'accepted_snapshot':state['snapshot'],'fourteen':fourteen,'rehearsal':rehearsal,'retained_extras':extras}

    def network(self, services):
        net=json.loads(self.command(['network','inspect',PROJECT+'_isolated'],'internal-network'))[0]
        check(net['Internal'] is True and net['Driver']=='bridge' and net['IPAM']['Config'][0]['Subnet']=='10.240.64.0/24'
              and set(net['Containers'])=={MONGO,*services},'clone_internal_network')
        if len(services)==2:
            net=json.loads(self.command(['network','inspect',PROJECT+'_ingress'],'ingress-network'))[0]
            check(net['Internal'] is False and net['IPAM']['Config'][0]['Subnet']=='10.240.65.0/24'
                  and set(net['Containers'])=={services[-1]},'clone_ingress_network')

    def compose_up(self, service):
        check(service in ('web','gateway'),'service_start_refused')
        args=['compose','--env-file',str(self.private/'clone.env'),'-p',PROJECT,'-f',str(self.profile/'compose.json')]
        self.command(args+['up','-d','--no-deps','--wait','--wait-timeout','120',service],service+'-up',timeout=180)
        cid=self.command(args+['ps','-q',service],service+'-cid').decode().strip()
        check(HEX.fullmatch(cid),'new_container_cid')
        item=self.inspect(cid);validate_runtime(item,self.spec['services'][service],service,self.env)
        return item

    def http(self, method, path, *, origin=None, body=None):
        headers={'Host':'tph-test.elisprotech.com'}
        if origin:headers['Origin']=origin
        if body is not None:headers['Content-Type']='application/json';body=canonical(body)
        request=urllib.request.Request('http://127.0.0.1:18221'+path,data=body,headers=headers,method=method)
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request,timeout=10) as response:
                return response.status,dict(response.headers),response.read(3*1024*1024)
        except urllib.error.HTTPError as error:
            return error.code,dict(error.headers),error.read(1024*1024)

    def http_checks(self):
        for path in ('/api/bookings/send-otp','/api/payments/process-payment','/api/webhooks/stripe','/api/jobs/run','/api/messages/send'):
            check(self.http('POST',path,body={})[0]==403,'unsafe_http_route_exposed')
        for path in ('/api/bookings/auth/session','/api/bookings/auth/magic-link/validate/INVALID',
                     '/api/bookings/extend/INVALID','/api/bookings/dashboard','/API/BOOKINGS/AUTH/SESSION'):
            check(self.http('GET',path)[0]==403,'copied_capability_route_exposed')
        check(self.http('POST','/api/pin/verify-client',origin='https://not-approved.invalid',body={'pin':'12345'})[0]==403,'wrong_origin_not_denied')
        check(self.http('POST','/api/pin/verify-client',origin='https://tph-test.elisprotech.com',body={'pin':'12345'})[0]==400,'native_pin_format_boundary')
        status,headers,body=self.http('GET','/signin')
        csp=next((v for k,v in headers.items() if k.lower()=='content-security-policy'),'')
        check(status==200 and b'MAC COPY - Real data captured October 22' in body
              and "connect-src 'self' https://"+DOMAIN in csp and 'https://api.stripe.com' not in csp
              and "worker-src 'none'" in csp and headers.get('X-Local-Test')=='real-data-copy-read-only-no-business-effects', 'readonly_banner_or_csp')
        return {'unsafe_posts_denied':5,'copied_capabilities_denied':5,'wrong_origin_denied':True,
                'malformed_pin_denied':True,'signin_banner_and_auth0_csp':True,'valid_credentials_tested':False}

    def execute_locked(self, controller):
        self.verify_files()
        before=self.protected(controller)
        mongo=self.inspect(MONGO)
        check(mongo['Name']=='/'+PROJECT+'-mongo-1' and mongo['Image']==self.base['manifest']['images']['mongo']
              and mongo['State']['Running'] and not mongo['State']['OOMKilled'] and mongo['State']['Health']['Status']=='healthy'
              and not mongo['HostConfig']['PortBindings'] and set(mongo['NetworkSettings']['Networks'])=={PROJECT+'_isolated'},'mongo_identity')
        mongo_before=container_identity(mongo)
        self.network([])
        check(mongo['Config']['Cmd'] == self.base['manifest'].get('mongo_command', self.base_spec['services']['mongo']['command']),
              'mongo_startup_command')
        for service in ('web','gateway'):
            check(not self.command(['ps','-aq','--filter','name=^/'+PROJECT+'-'+service+'-1$'],'absent-'+service).strip(),'existing_application_refused')
        with socket.socket() as listener:listener.bind(('127.0.0.1',18221))
        for image in self.base['manifest']['images'].values():
            rows=json.loads(self.command(['image','inspect',image],'image-proof'))
            check(len(rows)==1 and rows[0]['Id']==image and rows[0]['Os']=='linux' and rows[0]['Architecture']=='arm64','immutable_image_refused')
        original=self.mongo(DATA_JS,'data-before');validate_data(original)
        comparison=json.loads(private_read(self.private/'source-target-comparison.json'))
        target=json.loads(private_read(self.private/'target-inventory.json'))
        check(comparison['comparison']['matches'] is True and comparison['comparison']['document_count']==136410
              and comparison['comparison']['namespace_count']==78 and target['document_count']==136410
              and target['namespace_count']==78 and sum(v['index_count'] for v in target['namespaces'].values())==556,
              'full_inventory_comparison_contract')
        write_once(self.directory/'before.json',{'protected':before,'mongo':mongo_before,'data':original})
        self.verify_files()
        write_once(self.marker,{'phase':'role_create_started','plan_sha256':PLAN_SHA,'runner_sha256':self.runner_sha,
                                'approval_sha256':self.approval_sha,'mongo_cid':MONGO})
        # Exact separately reviewed profile script; never executes the old mounted base role.
        script=(self.profile/'create-reader-role.js').read_text()
        self.mongo(script,'role-create',reader=True)
        role=self.mongo(ROLE_VERIFY_JS,'role-proof',reader=True);validate_role(role)
        check(self.protected(controller)==before,'protected_after_role_drift');self.verify_files()
        web=self.compose_up('web');self.network([web['Id']])
        ready=self.command(['exec',web['Id'],'node','-e',"fetch('http://127.0.0.1:5051/local-test/ready').then(async r=>{if(!r.ok)process.exit(1);console.log(JSON.stringify(await r.json()))}).catch(()=>process.exit(1))"],'native-ready')
        ready=json.loads(ready);check(ready.get('status')=='ready' and ready.get('environment')=='real-data-clone'
            and ready.get('source')==SOURCE and ready.get('scheduler')=='disabled' and ready.get('workers')==0,'native_readiness')
        egress="fetch('https://example.com',{signal:AbortSignal.timeout(2500)}).then(()=>process.exit(9)).catch(()=>{console.log('egress-denied')})"
        check(self.command(['exec',web['Id'],'node','-e',egress],'controlled-egress',timeout=10).strip()==b'egress-denied','app_egress_allowed')
        check(self.protected(controller)==before,'protected_after_web_drift');self.verify_files()
        check(self.mongo(DATA_JS,'data-after-web')==original,'native_startup_data_or_schema_changed')
        gateway=self.compose_up('gateway');self.network([web['Id'],gateway['Id']])
        http=self.http_checks()
        final=self.mongo(DATA_JS,'data-after');validate_data(final);check(final==original,'native_data_or_schema_changed')
        check(container_identity(self.inspect(MONGO))==mongo_before,'mongo_restart_or_config_drift')
        check(self.protected(controller)==before,'protected_post_start_drift')
        self.verify_files()
        self.network([web['Id'],gateway['Id']])
        for service, old in (('web',web),('gateway',gateway)):
            current=self.inspect(old['Id']);validate_runtime(current,self.spec['services'][service],service,self.env)
            check(container_identity(current)==container_identity(old),'new_application_restarted_or_drifted')
        record={'version':1,'local_only':True,'plan_sha256':PLAN_SHA,'base_plan_sha256':BASE_SHA,
                'runner_sha256':self.runner_sha,'approval_sha256':self.approval_sha,
                'mongo_cid':MONGO,'web_cid':web['Id'],'gateway_cid':gateway['Id'],
                'protected_18_unchanged':True,'retained_v2_and_diagnostic_unchanged':True,
                'native_data_and_schema_unchanged':True,
                'native_validation_method':'intake full raw-BSON equality receipt; poststart all namespace counts/index/options and PIN EJSON hashes; exact readonly role',
                'native_snapshot':final,'http':http,
                'public_cutover':False,'valid_credentials_tested':False,'new_workers':0}
        write_once(self.private/'phase2-completed.json',record)
        # Marker remains as a closed, immutable history record; repeat execution still refuses.
        write_once(self.directory/'completed.json',record)
        return {'phase2_local_started':True,'project':PROJECT,'web_cid':web['Id'],'gateway_cid':gateway['Id'],
                'public_cutover':False,'valid_credentials_tested':False,'protected_18_unchanged':True}

    def execute(self, plan_sha, approval_sha):
        check(plan_sha==PLAN_SHA and HEX.fullmatch(approval_sha or ''),'explicit_plan_and_approval_required')
        check(self.root.resolve()==self.root and not self.directory.exists() and not self.marker.exists()
              and not (self.private/'phase2-completed.json').exists(),'phase2_already_started_or_uncertain')
        base_raw=private_read(self.root/'plan.json');plan_raw=private_read(self.profile/'plan.json')
        check(sha(base_raw)==BASE_SHA and sha(plan_raw)==PLAN_SHA,'exact_intake_plan_hashes')
        self.base=json.loads(base_raw);self.plan=json.loads(plan_raw)
        base_spec_raw=private_read(self.root/'compose.json');spec_raw=private_read(self.profile/'compose.json')
        check(sha(base_spec_raw)==self.base['artifacts_sha256']['compose.json']
              and sha(spec_raw)==self.plan['artifacts_sha256']['compose.json'],'exact_intake_compose_hashes')
        self.base_spec=json.loads(base_spec_raw);self.spec=json.loads(spec_raw)
        check(self.plan['project']==PROJECT and self.plan['base_plan_sha256']==BASE_SHA
              and self.spec['name']==PROJECT and self.spec['services']['web']['image']==IMAGE
              and self.base['manifest']['source']==SOURCE and self.plan['role_read_collections']==list(READS)
              and self.plan['role_update_collection']=='pins' and self.plan['public_cutover'] is False,'profile_scope_refused')
        self.runner_sha=sha(Path(__file__).read_bytes())
        self.env_sha=sha(private_read(self.private/'clone.env'))
        raw=private_read(self.private/'phase2-runtime-approval.json',immutable=True)
        check(sha(raw)==approval_sha,'approval_sha_mismatch')
        validate_approval(json.loads(raw),self.runner_sha,self.env_sha);self.approval_sha=approval_sha
        self.env=dict(line.split('=',1) for line in private_read(self.private/'clone.env').decode().splitlines())
        check(re.fullmatch(r'[-_a-zA-Z0-9]{43}',self.env.get('CLONE_READER_PASSWORD','')),'fresh_local_reader_secret')
        for relative,digest in (('mac-hosting/test-deploy/remote.py',CONTROLLER_SHA),
                                ('mac-hosting/test-stacks/tools/stackctl.py',OPERATOR_SHA)):
            path=Path.home()/relative
            check(path.resolve()==path and sha(path.read_bytes())==digest,'accepted_helper_drift')
        spec=importlib.util.spec_from_file_location('phase2_accepted_remote',Path.home()/'mac-hosting/test-deploy/remote.py')
        remote=importlib.util.module_from_spec(spec);sys.modules[spec.name]=remote;spec.loader.exec_module(remote)
        operator=remote.load_module('phase2_shared_operator',Path.home()/'mac-hosting/test-stacks/tools/stackctl.py')
        with operator.lock():
            check(not self.directory.exists() and not self.marker.exists(),'phase2_race_or_uncertain')
            self.directory.mkdir(mode=0o700)
            # Before-role read-only failures also leave exclusive evidence; no blind retry.
            return self.execute_locked(remote.Remote(operator))


if __name__=='__main__':
    os.umask(0o077)
    try:
        check(len(sys.argv)==3,'explicit_plan_and_approval_required')
        print(json.dumps(Runner().execute(sys.argv[1],sys.argv[2])))
    except Exception:
        print('phase2_failed_or_refused_preserve_private_evidence_no_retry_no_public_cutover',file=sys.stderr)
        raise SystemExit(1)
