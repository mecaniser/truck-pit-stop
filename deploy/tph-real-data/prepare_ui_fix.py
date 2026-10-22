"""Prepare immutable HTML-only banner correction; no Docker or public ingress actions."""
import copy
import hashlib
import json
import os
import stat
from pathlib import Path

ROOT = Path.home() / 'mac-hosting/tph-real-data-v3'
PROFILE = 'ui-fix-html-v1'
PHASE2_SHA = '695f276e35f16a54ee8ac6759f63e4196b09d0f99743b0ed53f8ccb53aa95dcf'
COMPLETED_SHA = 'c009f00b2f89c32e3f11ecad69a2728399b0abd193c6d4907d352084657f57c4'
HELPER_SHA = 'd4e9258a65b1f0961567c416315e7a723d45d63121d8569d352ef7d653ad6d4c'
WEB = '5f75768de901dbe971ecb457d49f480d50aa6dafbcd5a7fca76874d48ae15c07'
GATEWAY = '5639ea8bcd64952252c97a0d090b8f2ab1ced43dee1a59895e48e0b5193a8c18'

def check(value, code):
    if not value: raise RuntimeError(code)

def sha(value): return hashlib.sha256(value).hexdigest()
def encoded(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()+b'\n'

def artifact_read(path):
    """Only reviewed public source artifacts may be owner-readable 0644."""
    check(path.is_absolute() and path.resolve()==path and not path.is_symlink(),'artifact_path')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as source:
        before=os.fstat(source.fileno())
        check(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1
              and stat.S_IMODE(before.st_mode) in (0o600,0o644) and before.st_size<=64*1024*1024,'artifact_mode_or_owner')
        raw=source.read();after=os.fstat(source.fileno())
        check(all(getattr(before,k)==getattr(after,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode')),'artifact_read_race')
        return raw

def corrected_nginx(raw):
    text = raw.decode()
    lines = [line for line in text.splitlines() if "sub_filter '<body>' " in line]
    check(len(lines)==1 and lines[0].strip().startswith("sub_filter '<body>' '<body><div ")
          and lines[0].strip().endswith("</div>';"), 'exact_banner_filter_required')
    line=lines[0];replacement=line.strip()[len("sub_filter '<body>' "):-1]
    check(text.count('http {\n')==1 and '$clone_html_body' not in text, 'unmodified_http_required')
    mapping="map $upstream_http_content_type $clone_html_body {\n default '<body>';\n \"~*^text/html(?:;|$)\" "+replacement+";\n}\n"
    return text.replace('http {\n','http {\n'+mapping,1).replace(line,"sub_filter '<body>' $clone_html_body;",1).encode()

def corrected_spec(spec, old_profile, new_profile):
    value=copy.deepcopy(spec)
    old=str(old_profile/'nginx.conf')+':/etc/nginx/nginx.conf:ro'
    new=str(new_profile/'nginx.conf')+':/etc/nginx/nginx.conf:ro'
    check(value['services']['gateway']['volumes']==[old], 'exact_gateway_bind_required')
    value['services']['gateway']['volumes']=[new]
    return value

def prepare(root=ROOT):
    # The frozen helper supplies strict private-file reads; loading has no runtime actions.
    import importlib.util
    helper_path=Path(__file__).with_name('runtime_phase2.py')
    check(sha(helper_path.read_bytes())==HELPER_SHA,'helper_source_drift')
    loader=importlib.util.spec_from_file_location('ui_prepare_frozen_helper',helper_path)
    h=importlib.util.module_from_spec(loader);loader.loader.exec_module(h)
    old=root/'phase2-auth0';new=root/PROFILE
    check(root.resolve()==root and not new.exists(),'profile_already_exists_or_path')
    planraw=h.private_read(old/'plan.json');completion=h.private_read(root/'private/phase2-completed.json')
    check(sha(planraw)==PHASE2_SHA and sha(completion)==COMPLETED_SHA,'phase2_receipt_drift')
    phase2=json.loads(planraw);artifacts={}
    for name,digest in phase2['artifacts_sha256'].items():
        check(Path(name).name==name,'artifact_name')
        raw=(h.private_read(old/name) if name in ('compose.json','nginx.conf','create-reader-role.js') else artifact_read(old/name));check(sha(raw)==digest,'phase2_artifact_drift');artifacts[name]=raw
    nginx=corrected_nginx(artifacts['nginx.conf'])
    spec=corrected_spec(json.loads(artifacts['compose.json']),old,new)
    outputs={'nginx.conf':nginx,'compose.json':encoded(spec)}
    plan={'version':1,'scope':'gateway_html_filter_only','project':h.PROJECT,
          'phase2_plan_sha256':PHASE2_SHA,'phase2_completed_sha256':COMPLETED_SHA,
          'helper_sha256':HELPER_SHA,'base_plan_sha256':h.BASE_SHA,
          'web_cid':WEB,'mongo_cid':h.MONGO,'old_gateway_cid':GATEWAY,
          'old_artifacts_sha256':phase2['artifacts_sha256'],
          'artifacts_sha256':{k:sha(v) for k,v in outputs.items()},
          'prepare_sha256':sha(Path(__file__).read_bytes()),'public_cutover':False,'role_creation':False}
    new.mkdir(mode=0o700)
    for name,raw in {**outputs,'plan.json':encoded(plan)}.items():
        with (new/name).open('xb') as file:
            os.fchmod(file.fileno(),0o600);file.write(raw);file.flush();os.fsync(file.fileno())
    return {'profile':str(new),'plan_sha256':sha(encoded(plan)),'runtime_started':False}

if __name__=='__main__':
    os.umask(0o077)
    try: print(json.dumps(prepare()))
    except Exception: raise SystemExit('ui_profile_refused_preserve_evidence')
