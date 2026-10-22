"""Prepare a new immutable read-only admin/public-key maintenance profile; no starts."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib

ROOT=Path.home()/'mac-hosting/tph-real-data-v3'
PROFILE='maintenance-v1'
LABEL='com.macapps.tph.auth0-public-keys'
UI_SHA='707781f1ccdd4fd8c3af619a2d7a11d08f56448b9b8591e2e5865e4eada4f8d5'
GATEWAY='291277a93d61a199994cc577517826eb14fb6390d7e82bd93327cd0b19f7a2f7'
WEB='5f75768de901dbe971ecb457d49f480d50aa6dafbcd5a7fca76874d48ae15c07'
HELPER_SHA='d4e9258a65b1f0961567c416315e7a723d45d63121d8569d352ef7d653ad6d4c'
ROUTES=('/api/admin/pins','/api/site-settings','/api/site-settings/admin','/api/spot-changes/location-addition-requests')

def check(value,code):
 if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()+b'\n'
def load_helper():
 path=Path(__file__).parent.parent/'runtime_phase2.py';check(sha(path.read_bytes())==HELPER_SHA,'helper_drift')
 spec=importlib.util.spec_from_file_location('maintenance_frozen_phase2',path);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);return h

def nginx(raw):
 text=raw.decode();needle=' default 0;\n'
 check(text.count(needle)==1 and "sub_filter '<body>' $clone_html_body;" in text,'reviewed_html_profile_required')
 lines=''.join(' "'+method+':'+path+'" 1;\n' for path in ROUTES for method in ('GET','HEAD'))
 return text.replace(needle,needle+lines,1).encode()

def spec_for(old,root):
 result=copy.deepcopy(old);profile=root/PROFILE;web=result['services']['web']
 old_adapter=str(root/'phase2-auth0/clone-web-auth0.cjs')+':/usr/src/app/tph-web.cjs:ro'
 old_snapshot=str(root/'phase2-auth0/auth0-jwks.json')+':/run/clone/auth0-jwks.json:ro'
 check(web['volumes'].count(old_adapter)==1 and web['volumes'].count(old_snapshot)==1,'old_web_mount_profile')
 web['volumes']=[str(profile/'clone-web-auth0.cjs')+':/usr/src/app/tph-web.cjs:ro' if x==old_adapter else
                 str(root/'auth0-public-keys')+':/run/clone/auth0-public-keys:ro' if x==old_snapshot else x for x in web['volumes']]
 web['volumes'].append(str(profile/'refreshing_jwks.cjs')+':/run/clone/refreshing_jwks.cjs:ro')
 check(result['services']['gateway']['volumes']==[str(root/'ui-fix-html-v1/nginx.conf')+':/etc/nginx/nginx.conf:ro'],'old_gateway_mount')
 result['services']['gateway']['volumes']=[str(profile/'nginx.conf')+':/etc/nginx/nginx.conf:ro']
 return result

def launchagent(root):
 profile=root/PROFILE
 return {'Label':LABEL,'ProgramArguments':['/opt/homebrew/bin/python3',str(profile/'public_keys.py')],
         'RunAtLoad':True,'StartInterval':900,'ProcessType':'Background','ExitTimeOut':10,
         'StandardOutPath':str(root/'private/maintenance-key-refresh.stdout.private'),
         'StandardErrorPath':str(root/'private/maintenance-key-refresh.stderr.private')}

def prepare(root=ROOT):
 h=load_helper();profile=root/PROFILE;check(root.resolve()==root and not profile.exists(),'exclusive_profile_required')
 check(sha(h.private_read(root/'private/ui-fix-completed.json'))==UI_SHA,'ui_completion_drift')
 ui_raw=h.private_read(root/'ui-fix-html-v1/plan.json');ui=json.loads(ui_raw)
 check(sha(ui_raw)==json.loads(h.private_read(root/'private/ui-fix-completed.json'))['plan_sha256'],'ui_plan_binding')
 for name,digest in ui['artifacts_sha256'].items():check(Path(name).name==name and sha(h.private_read(root/'ui-fix-html-v1'/name))==digest,'ui_artifact_drift')
 old=json.loads(h.private_read(root/'ui-fix-html-v1/compose.json'))
 adapter_path=root/'phase2-auth0/clone-web-auth0.cjs'
 # Public immutable reviewed source; exact original digest is sealed in Phase2 plan.
 phase2=json.loads(h.private_read(root/'phase2-auth0/plan.json'))
 adapter=adapter_path.read_bytes();check(adapter_path.resolve()==adapter_path and sha(adapter)==phase2['artifacts_sha256']['clone-web-auth0.cjs'],'adapter_drift')
 needle=b"require('/run/clone/auth0_cached_jwks.cjs').install(require);"
 check(adapter.count(needle)==1,'native_preload_exact')
 artifacts={'compose.json':encoded(spec_for(old,root)),'nginx.conf':nginx(h.private_read(root/'ui-fix-html-v1/nginx.conf')),
            'clone-web-auth0.cjs':adapter.replace(needle,b"require('/run/clone/refreshing_jwks.cjs').install(require);"),
            'refreshing_jwks.cjs':Path(__file__).with_name('refreshing_jwks.cjs').read_bytes(),
            'public_keys.py':Path(__file__).with_name('public_keys.py').read_bytes(),
            'agent.plist':plistlib.dumps(launchagent(root),sort_keys=True)}
 plan={'version':1,'scope':'readonly_admin_and_host_public_keys','ui_completed_sha256':UI_SHA,'ui_plan_sha256':sha(ui_raw),
       'old_web_cid':WEB,'old_gateway_cid':GATEWAY,'mongo_cid':h.MONGO,'project':h.PROJECT,
       'routes':list(ROUTES),'artifacts_sha256':{k:sha(v) for k,v in artifacts.items()},'prepare_sha256':sha(Path(__file__).read_bytes()),
       'helper_sha256':HELPER_SHA,'role_change':False,'public_edge_change':False,'new_workers':0}
 profile.mkdir(mode=0o700)
 for name,raw in {**artifacts,'plan.json':encoded(plan)}.items():
  with (profile/name).open('xb') as file:
   os.fchmod(file.fileno(),0o644 if name.endswith('.cjs') else 0o600);file.write(raw);file.flush();os.fsync(file.fileno())
 return {'prepared':True,'plan_sha256':sha(encoded(plan)),'runtime_started':False}

if __name__=='__main__':
 os.umask(0o077)
 try:print(json.dumps(prepare()))
 except Exception:raise SystemExit('maintenance_prepare_refused_preserve_evidence')
