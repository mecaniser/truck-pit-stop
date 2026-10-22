"""One-shot gateway-only local correction. No public cutover or role replay.

After independent source review: prepare_ui_fix.py; independently approve resulting
plan and this runner, then: python3 runtime_ui_fix.py PLAN_SHA APPROVAL_SHA.
Approval: ROOT/private/ui-fix-approval.json (0400). Completion:
ROOT/private/ui-fix-completed.json. Any journal refuses retry, including failures.
"""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import prepare_ui_fix as p


def helper():
    path=Path(__file__).with_name('runtime_phase2.py')
    p.check(p.sha(path.read_bytes())==p.HELPER_SHA,'frozen_helper_drift')
    spec=importlib.util.spec_from_file_location('ui_frozen_phase2',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def approval_contract(plan_sha, runner_sha, environment_sha):
    return {'version':1,'decision':'approve_gateway_html_fix_local_only','plan_sha256':plan_sha,
            'runner_sha256':runner_sha,'prepare_sha256':p.sha(Path(p.__file__).read_bytes()),
            'environment_sha256':environment_sha,'helper_sha256':p.HELPER_SHA,
            'phase2_completed_sha256':p.COMPLETED_SHA,'old_gateway_cid':p.GATEWAY,
            'web_cid':p.WEB,'public_cutover':False,'role_creation':False}


def validate_approval(value, contract):
    p.check(set(value)==set(contract)|{'qa','security','expires_at'} and
            all(value[k]==v for k,v in contract.items()),'approval_binding')
    reviewers=[]
    for key in ('qa','security'):
        row=value[key]
        p.check(set(row)=={'reviewer','reference','decision'} and row['decision']=='GO'
                and isinstance(row['reference'],str) and row['reference'].strip()
                and isinstance(row['reviewer'],str) and row['reviewer'].strip()
                and row['reviewer']!='hosting_contract','independent_review_required')
        reviewers.append(row['reviewer'])
    p.check(reviewers[0]!=reviewers[1],'independent_review_required')
    now=datetime.datetime.now(datetime.timezone.utc);expiry=datetime.datetime.fromisoformat(value['expires_at'])
    p.check(expiry.tzinfo is not None and now<expiry<=now+datetime.timedelta(hours=24),'approval_expired')


REPLACEMENTS=((b'auth.tph.invalid',b'dev-wp1mdcmju5ix3zgt.us.auth0.com'),
              (b'local-test-client',b'vdyn414odhKwyDvsiNCSssA0In0Lc1i2'),
              (b'https://tph.invalid',b'https://trucksparkinghub.com/api'))
BANNER=b'MAC COPY - Real data captured October 22'


def verify_javascript(raw, served):
    p.check(len(raw)<=16*1024*1024 and len(served)<=16*1024*1024,'javascript_size')
    expected=raw
    for old,new in REPLACEMENTS: expected=expected.replace(old,new)
    p.check(served==expected and BANNER not in served,'javascript_bytes_or_banner_changed')
    return [raw.count(old) for old,new in REPLACEMENTS]


class Runner:
    def __init__(self,root=p.ROOT):
        self.h=helper();self.root=root;self.private=root/'private';self.profile=root/p.PROFILE
        self.directory=self.private/'ui-fix-runtime';self.marker=self.private/'ui-fix-started.json'
        self.r=self.h.Runner(root);self.r.directory=self.directory

    def files(self):
        h=self.h
        p.check(p.sha(Path(__file__).with_name('runtime_phase2.py').read_bytes())==p.HELPER_SHA,'frozen_helper_drift')
        p.check(h.sha(h.private_read(self.root/'.owner'))==h.sha(b'macapps-tph-real-data-v1\n'),'owner')
        p.check(h.sha(h.private_read(self.root/'plan.json'))==h.BASE_SHA,'base_plan_drift')
        p.check(h.sha(h.private_read(self.root/'phase2-auth0/plan.json'))==p.PHASE2_SHA,'phase2_plan_drift')
        p.check(h.sha(h.private_read(self.private/'phase2-completed.json'))==p.COMPLETED_SHA,'phase2_completion_drift')
        p.check(h.sha(h.private_read(self.profile/'plan.json'))==self.plan_sha,'ui_plan_drift')
        p.check(h.sha(Path(__file__).read_bytes())==self.runner_sha and
                h.sha(Path(p.__file__).read_bytes())==self.plan['prepare_sha256'],'source_drift')
        p.check(h.sha(h.private_read(self.private/'clone.env'))==self.env_sha,'env_drift')
        p.check(h.sha(h.private_read(self.private/'ui-fix-approval.json',immutable=True))==self.approval_sha,'approval_drift')
        validate_approval(json.loads(h.private_read(self.private/'ui-fix-approval.json',immutable=True)),
                          approval_contract(self.plan_sha,self.runner_sha,self.env_sha))
        old_plan=json.loads(h.private_read(self.root/'phase2-auth0/plan.json'))
        p.check(self.plan['old_artifacts_sha256']==old_plan['artifacts_sha256']
                and set(self.plan['artifacts_sha256'])=={'nginx.conf','compose.json'},'artifact_membership')
        for name,digest in self.plan['old_artifacts_sha256'].items():
            p.check(Path(name).name==name,'old_artifact_name')
            path=self.root/'phase2-auth0'/name
            raw=h.private_read(path) if name in ('compose.json','nginx.conf','create-reader-role.js') else p.artifact_read(path)
            p.check(h.sha(raw)==digest,'old_artifact_drift')
        for name,digest in self.plan['artifacts_sha256'].items():
            p.check(Path(name).name==name and h.sha(h.private_read(self.profile/name))==digest,'new_artifact_drift')
        for relative,digest in (('source-target-comparison.json',h.COMPARISON_SHA),('target-inventory.json',h.TARGET_SHA)):
            p.check(h.sha(h.private_read(self.private/relative))==digest,'data_receipt_drift')
        for relative,digest in (('mac-hosting/test-deploy/remote.py',h.CONTROLLER_SHA),('mac-hosting/test-stacks/tools/stackctl.py',h.OPERATOR_SHA)):
            path=Path.home()/relative;p.check(path.resolve()==path and h.sha(path.read_bytes())==digest,'controller_source_drift')
        for relative,digest in h.BASELINES.items():
            p.check(h.sha(h.private_read(Path.home()/'dieselbridge-staging/private'/relative))==digest,'baseline_drift')
        for name,digest in h.EDGE.items():
            path=Path.home()/'mac-hosting/test-public'/name
            p.check(path.resolve()==path and h.sha(path.read_bytes())==digest,'public_ingress_drift')

    def nginx_syntax(self):
        return self.r.command(['exec','-i',p.GATEWAY,'nginx','-t','-c','/dev/stdin'],
                              'proposed-nginx-syntax',input=self.h.private_read(self.profile/'nginx.conf'))

    def javascript(self):
        r=self.r;directory='/usr/src/app/build'
        script="const fs=require('fs'),path=require('path'),root="+json.dumps(directory)+";let out=[];function walk(dir){for(const name of fs.readdirSync(dir)){const full=path.join(dir,name),s=fs.lstatSync(full);if(s.isSymbolicLink())throw Error('symlink_refused');if(s.isDirectory())walk(full);else if(s.isFile()&&name.endsWith('.js'))out.push(path.relative(root,full));}}walk(root);console.log(JSON.stringify(out))"
        names=json.loads(r.command(['exec',p.WEB,'node','-e',script],'js-list'))
        p.check(isinstance(names,list) and 0<len(names)<1000 and len(set(names))==len(names)
                and all(isinstance(n,str) and re.fullmatch(r'(?:[A-Za-z0-9_-][A-Za-z0-9._-]*/)*[A-Za-z0-9_-][A-Za-z0-9._-]*\.js',n) for n in names)
                and 'vendor-misc-69904bf9.bfa12a49d8635f04933e.js' in names,'javascript_inventory')
        rows=[];counts=[0,0,0]
        for name in sorted(names):
            script="const fs=require('fs'),p="+json.dumps(directory+'/'+name)+";if(fs.statSync(p).size>16777216)process.exit(1);process.stdout.write(fs.readFileSync(p))"
            raw=r.command(['exec',p.WEB,'node','-e',script],'js-original')
            p.check(len(raw)<3*1024*1024,'served_js_exceeds_frozen_http_read_bound')
            status,headers,served=r.http('GET','/'+name)
            p.check(status==200 and 'javascript' in next((v for k,v in headers.items() if k.lower()=='content-type'),''),'javascript_http')
            hits=verify_javascript(raw,served);counts=[a+b for a,b in zip(counts,hits)]
            r.command(['exec','-i',p.WEB,'node','--check'],'js-syntax',input=served)
            rows.append({'file':name,'original_sha256':p.sha(raw),'served_sha256':p.sha(served),'bytes':len(served),'syntax_valid':True})
        p.check(all(counts),'auth0_substitutions_not_proven')
        return {'files':rows,'file_count':len(rows),'auth0_literal_counts':counts,'banner_in_javascript':False}

    def execute(self,plan_sha,approval_sha):
        h=self.h;r=self.r
        p.check(h.HEX.fullmatch(plan_sha or '') and h.HEX.fullmatch(approval_sha or ''),'explicit_hashes_required')
        p.check(self.root.resolve()==self.root and not self.directory.exists() and not self.marker.exists()
                and not (self.private/'ui-fix-completed.json').exists(),'already_started_or_uncertain')
        self.plan_sha=plan_sha;self.approval_sha=approval_sha;self.runner_sha=p.sha(Path(__file__).read_bytes())
        self.plan=json.loads(h.private_read(self.profile/'plan.json'));self.env_sha=p.sha(h.private_read(self.private/'clone.env'))
        r.env=dict(line.split('=',1) for line in h.private_read(self.private/'clone.env').decode().splitlines())
        self.files()
        old=json.loads(h.private_read(self.root/'phase2-auth0/compose.json'))
        spec=json.loads(h.private_read(self.profile/'compose.json'))
        p.check(spec==p.corrected_spec(old,self.root/'phase2-auth0',self.profile),'gateway_only_spec')
        p.check(h.private_read(self.profile/'nginx.conf')==p.corrected_nginx(h.private_read(self.root/'phase2-auth0/nginx.conf')),'html_only_config')
        expected={'version':1,'scope':'gateway_html_filter_only','project':h.PROJECT,'phase2_plan_sha256':p.PHASE2_SHA,
                  'phase2_completed_sha256':p.COMPLETED_SHA,'helper_sha256':p.HELPER_SHA,'base_plan_sha256':h.BASE_SHA,
                  'web_cid':p.WEB,'mongo_cid':h.MONGO,'old_gateway_cid':p.GATEWAY,'public_cutover':False,'role_creation':False}
        p.check(all(self.plan.get(k)==v for k,v in expected.items()),'scope_binding')
        loader=importlib.util.spec_from_file_location('ui_accepted_controller',Path.home()/'mac-hosting/test-deploy/remote.py')
        remote=importlib.util.module_from_spec(loader);sys.modules[loader.name]=remote;loader.loader.exec_module(remote)
        operator=remote.load_module('ui_shared_operator',Path.home()/'mac-hosting/test-stacks/tools/stackctl.py')
        with operator.lock():
            p.check(not self.directory.exists() and not self.marker.exists(),'concurrent_or_uncertain')
            self.directory.mkdir(mode=0o700);self.files()
            before=r.protected(remote.Remote(operator))
            identities={cid:h.container_identity(r.inspect(cid)) for cid in (p.WEB,h.MONGO,p.GATEWAY)}
            p.check(identities[h.MONGO]['running'] and not identities[h.MONGO]['oom'],'mongo_unhealthy')
            h.validate_runtime(r.inspect(p.WEB),old['services']['web'],'web',r.env)
            h.validate_runtime(r.inspect(p.GATEWAY),old['services']['gateway'],'gateway',r.env)
            r.network([p.WEB,p.GATEWAY]);data=r.mongo(h.DATA_JS,'data-before');h.validate_data(data)
            role=r.mongo(h.ROLE_VERIFY_JS,'role-before',reader=True);h.validate_role(role)
            h.write_once(self.directory/'before.json',{'protected':before,'containers':identities,'data':data,'role_sha256':p.sha(h.canonical(role))})
            self.nginx_syntax()
            self.files();p.check(r.protected(remote.Remote(operator))==before,'prewrite_protected_drift')
            p.check(all(h.container_identity(r.inspect(cid))==identity for cid,identity in identities.items()),'prewrite_clone_drift')
            h.write_once(self.marker,{'plan_sha256':plan_sha,'runner_sha256':self.runner_sha,'approval_sha256':approval_sha,'phase':'gateway_recreate_started'})
            args=['compose','--env-file',str(self.private/'clone.env'),'-p',h.PROJECT,'-f',str(self.profile/'compose.json')]
            r.command(args+['up','-d','--no-deps','--force-recreate','--wait','--wait-timeout','120','gateway'],'gateway-only',timeout=180)
            cid=r.command(args+['ps','-q','gateway'],'gateway-cid').decode().strip()
            p.check(h.HEX.fullmatch(cid) and cid!=p.GATEWAY,'new_gateway_identity')
            gateway=r.inspect(cid);h.validate_runtime(gateway,spec['services']['gateway'],'gateway',r.env)
            r.network([p.WEB,cid]);http=r.http_checks();javascript=self.javascript()
            p.check(r.mongo(h.DATA_JS,'data-after')==data,'native_data_drift')
            p.check(r.mongo(h.ROLE_VERIFY_JS,'role-after',reader=True)==role,'role_drift')
            p.check(all(h.container_identity(r.inspect(c))==identities[c] for c in (p.WEB,h.MONGO)),'web_or_mongo_changed')
            p.check(r.protected(remote.Remote(operator))==before,'protected_after_drift');self.files();r.network([p.WEB,cid])
            p.check(h.container_identity(r.inspect(cid))==h.container_identity(gateway),'gateway_changed')
            receipt={'version':1,'plan_sha256':plan_sha,'runner_sha256':self.runner_sha,'approval_sha256':approval_sha,
                     'phase2_completed_sha256':p.COMPLETED_SHA,'gateway_cid':cid,'old_gateway_cid':p.GATEWAY,
                     'web_cid':p.WEB,'mongo_cid':h.MONGO,'protected_18_unchanged':True,'role_unchanged':True,
                     'native_data_and_schema_unchanged':True,'web_and_mongo_unchanged':True,'public_cutover':False,
                     'javascript':javascript,'http':http}
            h.write_once(self.private/'ui-fix-completed.json',receipt)
            h.write_once(self.directory/'completed.json',receipt)
            return {'local_gateway_fixed':True,'completion_sha256':p.sha(h.private_read(self.private/'ui-fix-completed.json')),'public_cutover':False,'javascript_files_checked':javascript['file_count']}


if __name__=='__main__':
    os.umask(0o077)
    try:
        p.check(len(sys.argv)==3,'explicit_plan_and_approval_required')
        print(json.dumps(Runner().execute(sys.argv[1],sys.argv[2])))
    except Exception:
        raise SystemExit('ui_fix_failed_or_refused_preserve_private_evidence_no_retry')
