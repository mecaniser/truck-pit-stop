"""One-shot independently approved local maintenance. Does not restart public edge.

python3 maintenance/runtime.py PLAN_SHA APPROVAL_SHA
Approval private/maintenance-approval.json 0400; journal private/maintenance-runtime;
marker private/maintenance-started.json; completion private/maintenance-completed.json.
Any existing journal/marker refuses retry. No role create, seeds, migrations or cleanup.
"""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import prepare as p

EDGE={'Caddyfile.public.DISABLED':'f9760eafd918e3240986b1def3677fa17f3b5f9b68e2cda8c913948e78fe37e5',
      'access_gate.py':'8557deef972ad3077221f5c8709141cc9303ec6cb3f366851ef2f96252ee56b0',
      'private/activation.json':'c1d2b75e91d169eabd8f84b1295ce47ac351c15582ab9e1659057badfd1d7d32',
      'private/real-data-cutover-v3/apply-completed.json':'19e2583f90274430cedbb79e98bdc7d256a6ce40dbff3fb3e06513a86463b348'}
GLOBAL_JS="const t=db.getSiblingDB('tph_local_test');print(JSON.stringify({global:t.sitesettings.countDocuments({_id:'global'}),property_leads:t.locationadditionrequests.countDocuments({})}));"

def approval_contract(plan,runner,env):
 return {'version':1,'decision':'approve_readonly_admin_key_maintenance','plan_sha256':plan,'runner_sha256':runner,
         'environment_sha256':env,'ui_completed_sha256':p.UI_SHA,'old_web_cid':p.WEB,'old_gateway_cid':p.GATEWAY,
         'helper_sha256':p.HELPER_SHA,'public_edge_change':False,'role_change':False}

def validate_approval(value,expected):
 p.check(set(value)==set(expected)|{'qa','security','expires_at'} and all(value[k]==v for k,v in expected.items()),'approval_binding')
 rows=[value[k] for k in ('qa','security')]
 p.check(all(set(x)=={'reviewer','reference','decision'} and x['decision']=='GO' and isinstance(x['reviewer'],str)
             and x['reviewer'].strip() and x['reviewer']!='hosting_contract' and isinstance(x['reference'],str) and x['reference'].strip() for x in rows)
         and rows[0]['reviewer']!=rows[1]['reviewer'],'independent_reviews_required')
 now=datetime.datetime.now(datetime.timezone.utc);expiry=datetime.datetime.fromisoformat(value['expires_at'])
 p.check(expiry.tzinfo is not None and now<expiry<=now+datetime.timedelta(hours=24),'approval_expired')

class Runner:
 def __init__(self,root=p.ROOT):
  self.h=p.load_helper();self.root=root;self.private=root/'private';self.profile=root/p.PROFILE
  self.directory=self.private/'maintenance-runtime';self.marker=self.private/'maintenance-started.json'
  self.r=self.h.Runner(root);self.r.directory=self.directory;self.host_serial=0
 def host(self,args,label,timeout=30,allow_missing=False):
  self.host_serial+=1;prefix=self.directory/('host-%03d-'%self.host_serial+label)
  with prefix.with_suffix('.stdout.private').open('xb') as out,prefix.with_suffix('.stderr.private').open('xb') as err:
   os.fchmod(out.fileno(),0o600);os.fchmod(err.fileno(),0o600)
   done=subprocess.run(args,stdout=out,stderr=err,timeout=timeout)
  if done.returncode:
   p.check(allow_missing and b'Could not find service' in prefix.with_suffix('.stderr.private').read_bytes(),'host_command_failed_'+label)
  return done.returncode,prefix.with_suffix('.stdout.private').read_bytes()
 def files(self):
  h=self.h
  p.check(p.sha(h.private_read(self.root/'.owner'))==p.sha(b'macapps-tph-real-data-v1\n'),'owner')
  p.check(p.sha(h.private_read(self.private/'ui-fix-completed.json'))==p.UI_SHA,'accepted_ui_drift')
  p.check(p.sha(h.private_read(self.profile/'plan.json'))==self.plan_sha,'plan_drift')
  p.check(p.sha(Path(__file__).read_bytes())==self.runner_sha and p.sha(Path(p.__file__).read_bytes())==self.plan['prepare_sha256'],'maintenance_source_drift')
  p.check(p.sha((Path(__file__).parent.parent/'runtime_phase2.py').read_bytes())==p.HELPER_SHA,'helper_drift')
  p.check(p.sha(h.private_read(self.private/'clone.env'))==self.env_sha,'environment_drift')
  approval=h.private_read(self.private/'maintenance-approval.json',immutable=True)
  p.check(p.sha(approval)==self.approval_sha,'approval_drift');validate_approval(json.loads(approval),approval_contract(self.plan_sha,self.runner_sha,self.env_sha))
  for name,digest in self.plan['artifacts_sha256'].items():
   path=self.profile/name;p.check(Path(name).name==name and path.resolve()==path and p.sha(path.read_bytes())==digest,'artifact_drift')
  ui_raw=h.private_read(self.root/'ui-fix-html-v1/plan.json');ui=json.loads(ui_raw)
  p.check(p.sha(ui_raw)==json.loads(h.private_read(self.private/'ui-fix-completed.json'))['plan_sha256'],'ui_plan_drift')
  for name,digest in ui['artifacts_sha256'].items():
   p.check(Path(name).name==name and p.sha(h.private_read(self.root/'ui-fix-html-v1'/name))==digest,'ui_artifact_drift')
  p.check(set(self.plan['artifacts_sha256'])=={'compose.json','nginx.conf','clone-web-auth0.cjs','refreshing_jwks.cjs','public_keys.py','agent.plist'},'maintenance_artifact_membership')
  phase2=json.loads(h.private_read(self.root/'phase2-auth0/plan.json'))
  p.check(p.sha(h.private_read(self.root/'phase2-auth0/plan.json'))==h.PLAN_SHA,'original_profile_plan_drift')
  for name,digest in phase2['artifacts_sha256'].items():
   path=self.root/'phase2-auth0'/name;p.check(path.resolve()==path and p.sha(path.read_bytes())==digest,'original_artifact_drift')
  for name,digest in h.BASELINES.items():p.check(p.sha(h.private_read(Path.home()/'dieselbridge-staging/private'/name))==digest,'baseline_drift')
  for name,digest in EDGE.items():
   path=Path.home()/'mac-hosting/test-public'/name;p.check(path.resolve()==path and p.sha(path.read_bytes())==digest,'public_edge_drift')
  for name,digest in (('mac-hosting/test-deploy/remote.py',h.CONTROLLER_SHA),('mac-hosting/test-stacks/tools/stackctl.py',h.OPERATOR_SHA)):
   path=Path.home()/name;p.check(path.resolve()==path and p.sha(path.read_bytes())==digest,'controller_drift')
 def compose(self,service,spec):
  p.check(service in ('web','gateway'),'service_refused')
  args=['compose','--env-file',str(self.private/'clone.env'),'-p',self.h.PROJECT,'-f',str(self.profile/'compose.json')]
  self.r.command(args+['up','-d','--no-deps','--force-recreate','--wait','--wait-timeout','120',service],service+'-up',timeout=180)
  cid=self.r.command(args+['ps','-q',service],service+'-cid').decode().strip();p.check(self.h.HEX.fullmatch(cid),'new_cid')
  item=self.r.inspect(cid);self.h.validate_runtime(item,spec['services'][service],service,self.r.env);return item
 def javascript(self,web):
  r=self.r;script="const fs=require('fs');console.log(JSON.stringify(fs.readdirSync('/usr/src/app/build').filter(x=>x.endsWith('.js'))))"
  names=json.loads(r.command(['exec',web,'node','-e',script],'js-inventory'))
  p.check(len(names)==172 and len(set(names))==172 and all(re.fullmatch('[A-Za-z0-9_-][A-Za-z0-9._-]*\\.js',n) for n in names),'pinned_js_inventory')
  replacements=[(b'auth.tph.invalid',b'dev-wp1mdcmju5ix3zgt.us.auth0.com'),(b'local-test-client',b'vdyn414odhKwyDvsiNCSssA0In0Lc1i2'),(b'https://tph.invalid',b'https://trucksparkinghub.com/api')]
  rows=[];hits=[0,0,0]
  for name in sorted(names):
   script="process.stdout.write(require('fs').readFileSync("+json.dumps('/usr/src/app/build/'+name)+"))"
   raw=r.command(['exec',web,'node','-e',script],'js-original');p.check(len(raw)<3*1024*1024,'bounded_js')
   expected=raw
   for i,(old,new) in enumerate(replacements):hits[i]+=raw.count(old);expected=expected.replace(old,new)
   status,_,served=r.http('GET','/'+name);p.check(status==200 and served==expected and b'MAC COPY - Real data' not in served,'served_js_corrupt')
   r.command(['exec','-i',web,'node','--check'],'js-parse',input=served)
   rows.append({'file':name,'sha256':p.sha(served),'syntax_valid':True})
  p.check(all(hits),'auth0_substitutions');return rows
 def execute(self,plan_sha,approval_sha):
  h=self.h;r=self.r
  p.check(h.HEX.fullmatch(plan_sha or '') and h.HEX.fullmatch(approval_sha or ''),'explicit_hashes')
  p.check(self.root.resolve()==self.root and not self.directory.exists() and not self.marker.exists()
          and not (self.private/'maintenance-completed.json').exists(),'uncertain_or_already_started')
  self.plan_sha=plan_sha;self.approval_sha=approval_sha;self.runner_sha=p.sha(Path(__file__).read_bytes())
  self.plan=json.loads(h.private_read(self.profile/'plan.json'));self.env_sha=p.sha(h.private_read(self.private/'clone.env'))
  r.env=dict(line.split('=',1) for line in h.private_read(self.private/'clone.env').decode().splitlines());self.files()
  p.check(self.plan['routes']==list(p.ROUTES) and self.plan['role_change'] is False and self.plan['public_edge_change'] is False and self.plan['new_workers']==0,'scope')
  old=json.loads(h.private_read(self.root/'ui-fix-html-v1/compose.json'));spec=json.loads(h.private_read(self.profile/'compose.json'))
  p.check(spec==p.spec_for(old,self.root) and h.private_read(self.profile/'nginx.conf')==p.nginx(h.private_read(self.root/'ui-fix-html-v1/nginx.conf')),'mounts_routes_only')
  loader=importlib.util.spec_from_file_location('maintenance_accepted_remote',Path.home()/'mac-hosting/test-deploy/remote.py')
  remote=importlib.util.module_from_spec(loader);sys.modules[loader.name]=remote;loader.loader.exec_module(remote)
  operator=remote.load_module('maintenance_shared_operator',Path.home()/'mac-hosting/test-stacks/tools/stackctl.py')
  with operator.lock():
   p.check(not self.directory.exists() and not self.marker.exists(),'concurrent_operation');self.directory.mkdir(mode=0o700);self.files()
   _,edge_before=self.host(['/bin/ps','-p','52994,52999,53004','-o','pid=,lstart=,command='],'public-edge-processes-before')
   p.check({int(line.split()[0]) for line in edge_before.decode().splitlines()}=={52994,52999,53004},'public_edge_process_missing')
   before=r.protected(remote.Remote(operator));identities={cid:h.container_identity(r.inspect(cid)) for cid in (p.WEB,p.GATEWAY,h.MONGO)}
   for cid,service in ((p.WEB,'web'),(p.GATEWAY,'gateway')):h.validate_runtime(r.inspect(cid),old['services'][service],service,r.env)
   r.network([p.WEB,p.GATEWAY]);data=r.mongo(h.DATA_JS,'data-before');h.validate_data(data)
   role=r.mongo(h.ROLE_VERIFY_JS,'role-before',reader=True);h.validate_role(role)
   prerequisite=r.mongo(h.AUTH_JS+GLOBAL_JS,'settings-prerequisite');p.check(prerequisite=={'global':1,'property_leads':16},'settings_global_or_property_count_missing_no_changes')
   cache=self.root/'auth0-public-keys';agent=Path.home()/'Library/LaunchAgents'/ (p.LABEL+'.plist')
   log_paths=[self.private/'maintenance-key-refresh.stdout.private',self.private/'maintenance-key-refresh.stderr.private']
   p.check(not cache.exists() and not agent.exists() and not any(path.exists() or path.is_symlink() for path in log_paths),'existing_host_resources_refused')
   uid=str(os.getuid());self.host(['/bin/launchctl','print','gui/'+uid],'gui-domain')
   status,_=self.host(['/bin/launchctl','print','gui/'+uid+'/'+p.LABEL],'agent-absent',allow_missing=True);p.check(status!=0,'existing_agent_refused')
   # A real regular tmpfs file is necessary: nginx cannot seek configuration from stdin.
   r.command(['exec','-i',p.GATEWAY,'sh','-c','umask 077; set -C; cat > /var/cache/nginx/mac-maintenance-v1.conf && nginx -t -c /var/cache/nginx/mac-maintenance-v1.conf'],
             'nginx-syntax',input=h.private_read(self.profile/'nginx.conf'))
   h.write_once(self.directory/'before.json',{'protected':before,'containers':identities,'data':data,'role_sha256':p.sha(h.canonical(role))})
   self.files();p.check(r.protected(remote.Remote(operator))==before and all(h.container_identity(r.inspect(cid))==value for cid,value in identities.items()),'prewrite_drift')
   h.write_once(self.marker,{'plan_sha256':plan_sha,'runner_sha256':self.runner_sha,'approval_sha256':approval_sha,'phase':'host_cache_and_web_gateway_started'})
   cache.mkdir(mode=0o755);os.chmod(cache,0o755)
   self.host(['/opt/homebrew/bin/python3',str(self.profile/'public_keys.py')],'initial-public-key-fetch',timeout=10)
   web=self.compose('web',spec);p.check(web['Id']!=p.WEB,'web_recreate_required')
   gateway=self.compose('gateway',spec);p.check(gateway['Id']!=p.GATEWAY,'gateway_recreate_required');r.network([web['Id'],gateway['Id']])
   http=r.http_checks()
   for route in p.ROUTES:
    p.check(r.http('POST',route,body={})[0]==403,'admin_mutation_exposed')
   for route in ('/api/admin/pins','/api/site-settings/admin','/api/spot-changes/location-addition-requests'):
    p.check(r.http('GET',route)[0]==401,'native_auth_required')
   p.check(r.http('GET','/api/site-settings')[0]==200,'public_settings_unavailable')
   for route in ('/api/profile','/api/admin/operations/summary','/api/admin/hiring/leads','/api/logs','/api/admin/pins/stats'):
    p.check(r.http('GET',route)[0]==403,'quarantined_get_exposed')
   js=self.javascript(web['Id'])
   with agent.open('xb') as out:os.fchmod(out.fileno(),0o600);out.write(h.private_read(self.profile/'agent.plist'));out.flush();os.fsync(out.fileno())
   for path in log_paths:
    with path.open('xb') as out:os.fchmod(out.fileno(),0o600);out.flush();os.fsync(out.fileno())
   self.host(['/bin/launchctl','bootstrap','gui/'+uid,str(agent)],'install-public-keys-agent')
   self.host(['/bin/launchctl','print','gui/'+uid+'/'+p.LABEL],'public-keys-agent-proof')
   p.check(r.mongo(h.DATA_JS,'data-after')==data and r.mongo(h.ROLE_VERIFY_JS,'role-after',reader=True)==role,'data_or_role_drift')
   p.check(h.container_identity(r.inspect(h.MONGO))==identities[h.MONGO] and r.protected(remote.Remote(operator))==before,'protected_or_mongo_drift')
   _,edge_after=self.host(['/bin/ps','-p','52994,52999,53004','-o','pid=,lstart=,command='],'public-edge-processes-after')
   p.check(edge_after==edge_before,'public_edge_process_changed')
   self.files();r.network([web['Id'],gateway['Id']])
   for item,service in ((web,'web'),(gateway,'gateway')):
    current=r.inspect(item['Id']);h.validate_runtime(current,spec['services'][service],service,r.env)
    p.check(h.container_identity(current)==h.container_identity(item),'new_apps_restarted')
   record={'version':1,'plan_sha256':plan_sha,'runner_sha256':self.runner_sha,'approval_sha256':approval_sha,
           'web_cid':web['Id'],'gateway_cid':gateway['Id'],'mongo_cid':h.MONGO,'protected_18_unchanged':True,
           'native_data_and_schema_unchanged':True,'role_unchanged':True,'public_edge_unchanged':True,'new_workers':0,
           'allowed_reads':list(p.ROUTES),'javascript':js,'http':http,'host_public_key_label':p.LABEL,
           'real_user_backend_bearer_tested':False,'requires_browser_acceptance':True}
   h.write_once(self.private/'maintenance-completed.json',record);h.write_once(self.directory/'completed.json',record)
   return {'maintenance_completed':True,'completion_sha256':p.sha(h.private_read(self.private/'maintenance-completed.json')),'requires_browser_acceptance':True}

if __name__=='__main__':
 os.umask(0o077)
 try:
  p.check(len(sys.argv)==3,'explicit_plan_and_approval');print(json.dumps(Runner().execute(*sys.argv[1:])))
 except Exception:raise SystemExit('maintenance_failed_preserve_evidence_no_retry')
