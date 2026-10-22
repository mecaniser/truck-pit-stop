"""Reviewed, journaled test-edge upstream change. No application or database commands.

Prepare only after private Phase 2 acceptance. Apply/rollback each require an
external receipt binding this source, the prepared plan and independent reviews.
An incomplete transition is retained and must be investigated, never retried.
"""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path.home() / 'mac-hosting/test-public'
JOURNAL = ROOT / 'private/real-data-cutover-v3'
CONFIG = ROOT / 'Caddyfile.public.DISABLED'
ACTIVATION = ROOT / 'private/activation.json'
CLONE = Path.home() / 'mac-hosting/tph-real-data-v3'
DOCKER = ['/Applications/Docker.app/Contents/Resources/bin/docker', '--context', 'desktop-linux']
BASELINES = {'soak-baseline.json': '1e7618809a071feb45cadb84667827c97c483c63f7e3fbf645b92628b4544d1e',
 'observations/20261022T192823Z/soak-baseline.json': '0002ccdd4d0b797e4a79543c1be310cd7a292d8f23b8ecba786031dec16ed328'}
PLIST = Path.home() / 'Library/LaunchAgents/com.macapps.testpublic.edge.plist'
OLD_GATE_SHA = '4572bd8419a07587e998461a2953e7f9c10c0b5fed981c3aafc40a7dfe3fa258'


def check(ok, why):
    if not ok:
        raise RuntimeError(why)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def digest(path):
    check(not path.is_symlink(), 'symlink_refused')
    return sha(path.read_bytes())


def new_configuration(raw):
    check(raw.count(b'reverse_proxy 127.0.0.1:18211 {') == 1, 'upstream_not_unique')
    prefix, block = raw.split(b'https://tph-test.elisprotech.com {', 1)
    check(b'127.0.0.1:18211' not in prefix, 'wrong_host')
    target, suffix = block.split(b'http://tph-test.elisprotech.com {', 1)
    check(b'reverse_proxy 127.0.0.1:18211 {' in target, 'target_block_missing')
    return prefix + b'https://tph-test.elisprotech.com {' + target.replace(
        b'reverse_proxy 127.0.0.1:18211 {', b'reverse_proxy 127.0.0.1:18221 {') + b'http://tph-test.elisprotech.com {' + suffix


def new_gate(raw):
    check(sha(raw)==OLD_GATE_SHA,'original_gate_source_drift')
    substitutions = [
        ('def cookie(name, value, ttl):\n    return f"{name}={value}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age={ttl}"',
         'def cookie(name, value, ttl, host=None):\n    same_site = "Lax" if name == ACCESS and host == "tph-test.elisprotech.com" else "Strict"\n    return f"{name}={value}; Path=/; Secure; HttpOnly; SameSite={same_site}; Max-Age={ttl}"'),
        ('cookie(ACCESS, token, ACCESS_TTL)', 'cookie(ACCESS, token, ACCESS_TTL, host)'),
        ('cookie(ACCESS, "", 0)', 'cookie(ACCESS, "", 0, host)'),
        ('<p>Synthetic data. Test access only.</p>', '<p>{"Real database copy. Read-only access." if host == "tph-test.elisprotech.com" else "Synthetic data. Test access only."}</p>')]
    text=raw.decode()
    for old,new in substitutions:
        check(text.count(old)==1,'gate_patch_ambiguous')
        text=text.replace(old,new)
    compile(text,'reviewed-access-gate.py','exec')
    return text.encode()


def command(args):
    return subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=30)


def protected_snapshot():
    for name, expected in BASELINES.items():
        check(digest(Path.home() / 'dieselbridge-staging/private' / name) == expected, 'baseline_drift')
    ids = command(DOCKER + ['ps', '-aq']).decode().split()
    check(ids, 'docker_unavailable')
    items = json.loads(command(DOCKER + ['inspect'] + ids))
    result = {}
    for item in items:
        check(not item['State'].get('OOMKilled'), 'container_oom')
        result[item['Id']] = {'image': item['Image'], 'started': item['State']['StartedAt'],
            'running': item['State']['Running'], 'health': item['State'].get('Health', {}).get('Status'),
            'config': sha(canonical(item['Config'])), 'host': sha(canonical(item['HostConfig'])),
            'mounts': sha(canonical(sorted(item['Mounts'], key=lambda m: (m['Destination'],m['Type'])))),
            'networks': sha(canonical(item['NetworkSettings']['Networks']))}
    # Full raw inspect output and environment values are never returned or persisted.
    return result


def service():
    value = plistlib.loads(PLIST.read_bytes())
    check(value['Label'] == 'com.macapps.testpublic.edge' and value['ProgramArguments'] ==
          ['/opt/homebrew/bin/python3', str(ROOT / 'run_edge.py'), 'public'], 'service_contract_drift')
    check(value.get('KeepAlive') == {'SuccessfulExit':False} and value.get('RunAtLoad') is True,
          'unexpected_supervisor_restart_policy')
    return 'gui/' + str(os.getuid()) + '/com.macapps.testpublic.edge'


def process(pid):
    raw = command(['/bin/ps', '-p', str(pid), '-o', 'ppid=', '-o', 'lstart=', '-o', 'command=']).decode().strip()
    check(raw, 'process_missing')
    return raw


def owned_processes():
    raw = command(['/bin/launchctl', 'print', service()]).decode()
    found = re.findall(r'^\s*pid = (\d+)\s*$', raw, re.M)
    check(len(found) == 1, 'runner_missing_or_ambiguous')
    pid = int(found[0]); parent = process(pid)
    python = Path(sys.executable).resolve().parent.parent / 'Resources/Python.app/Contents/MacOS/Python'
    check(parent.endswith(str(python) + ' ' + str(ROOT / 'run_edge.py') + ' public'), 'runner_argv_drift')
    rows = command(['/bin/ps', '-axo', 'pid=,ppid=,lstart=,command=']).decode().splitlines()
    children = {}
    for line in rows:
        fields = line.strip().split(None, 2)
        if len(fields) == 3 and fields[1] == str(pid):
            children[int(fields[0])] = process(int(fields[0]))
    expected = [str(ROOT / 'access_gate.py'), str(Path.home() / 'mac-hosting/bin/caddy') +
                ' run --adapter caddyfile --config ' + str(CONFIG)]
    check(len(children) == 2 and all(sum(row.endswith(suffix) for row in children.values()) == 1 for suffix in expected), 'owned_children_drift')
    return {'pid':pid, 'identity':parent, 'children':children}


def private_ready(port=18221):
    # The old public gateway deliberately hides readiness; its private peer
    # exposes the same reviewed web service at 18201. Never change either.
    readiness_port=18201 if port==18211 else port
    request = urllib.request.Request('http://127.0.0.1:'+str(readiness_port)+'/local-test/ready', headers={'Host':'tph-test.elisprotech.com'})
    with urllib.request.urlopen(request,timeout=5) as response:
        check(response.status == 200, 'private_app_not_ready')
    request = urllib.request.Request('http://127.0.0.1:'+str(port)+'/signin', headers={'Host':'tph-test.elisprotech.com'})
    with urllib.request.urlopen(request,timeout=5) as response:
        body=response.read()
        check(response.status == 200 and (port==18211 or b'MAC COPY - Real data captured October 22' in body), 'real_data_banner_missing')


def reviews(approval):
    identities=[]
    for role in ('qa','security'):
        entry=approval.get(role)
        check(isinstance(entry,dict) and entry.get('decision')=='GO' and
              isinstance(entry.get('reviewer'),str) and len(entry['reviewer'])>3 and
              isinstance(entry.get('reference'),str) and len(entry['reference'])>8,'explicit_independent_go_required')
        expiry=datetime.datetime.fromisoformat(entry['expires_at'])
        check(expiry.tzinfo is not None and datetime.datetime.now(datetime.timezone.utc)<expiry,
              'review_expired')
        identities.append(entry['reviewer'])
    check(len(set(identities))==2,'reviewers_must_be_independent')


def listeners(current):
    children=current['children']
    caddy=[p for p,v in children.items() if 'caddy run --adapter' in v]
    gate=[p for p,v in children.items() if v.endswith(str(ROOT/'access_gate.py'))]
    check(len(caddy)==len(gate)==1,'child_roles_ambiguous')
    for port,pid,address in ((8088,caddy[0],'192.168.4.239'),(8443,caddy[0],'192.168.4.239'),(18680,gate[0],'127.0.0.1')):
        raw=command(['/usr/sbin/lsof','-nP','-iTCP:'+str(port),'-sTCP:LISTEN','-Fpn']).decode().splitlines()
        check([line for line in raw if line.startswith('p')]==['p'+str(pid)] and
              [line for line in raw if line.startswith('n')]==['n'+address+':'+str(port)],'foreign_or_wrong_bind_listener')
    check(owned_processes()==current,'owned_process_changed_during_readiness')


def gate_negative_checks():
    # curl verifies trusted TLS with explicit local routing; never prints customer content.
    for host in ('tph-test.elisprotech.com','dieselbridge-test.elisprotech.com'):
        args=['/usr/bin/curl','--silent','--show-error','--max-time','10','--resolve',host+':8443:192.168.4.239','--header','Host: '+host,
              '--output','/dev/null','--write-out','%{http_code}']
        # Existing gate returns 403 for curl's non-navigation Accept */*.
        check(command(args+['https://'+host+':8443/signin']).decode()=='403','unauthenticated_access_not_denied')
        check(command(args+['https://'+host+':8443/api/addresses']).decode()=='403','unauthenticated_api_not_denied')
        check(command(args+['https://'+host+':8443/_test-access']).decode()=='200','access_gate_page_unavailable')


def absent_owned_processes():
    raw=command(['/bin/launchctl','print',service()]).decode()
    check(not re.search(r'^\s*pid = \d+\s*$',raw,re.M),'runner_is_running')
    rows=command(['/bin/ps','-axo','command=']).decode().splitlines()
    check(not any(str(ROOT/'run_edge.py')+' public' in row or str(ROOT/'access_gate.py') in row or
                  str(CONFIG) in row for row in rows),'orphan_edge_process_refused')
    for port in (8088,8443,18680):
        result=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:'+str(port),'-sTCP:LISTEN'],capture_output=True,timeout=10)
        check(result.returncode==1 and not result.stdout,'orphan_listener_refused')


def sources():
    return {str(p):digest(p) for p in (ROOT/'run_edge.py', PLIST,
            Path.home()/'mac-hosting/bin/caddy')}


def put(path, raw):
    temporary = path.with_name(path.name + '.real-copy-new')
    with temporary.open('xb') as output:
        os.fchmod(output.fileno(),0o600);output.write(raw);output.flush();os.fsync(output.fileno())
    os.replace(temporary,path)


def prepare():
    check(not JOURNAL.exists(), 'journal_already_exists')
    check((ROOT/'.owner').read_text() == 'macapps-test-public-v1\n', 'owner_refused')
    private_ready()
    phase2 = CLONE/'private/phase2-completed.json'
    check(phase2.exists(), 'phase2_acceptance_missing')
    ui_fix = CLONE/'private/ui-fix-completed.json'
    check(ui_fix.exists(), 'html_only_filter_acceptance_missing')
    old = CONFIG.read_bytes(); proposed = new_configuration(old)
    old_activation = ACTIVATION.read_bytes()
    old_gate=(ROOT/'access_gate.py').read_bytes();proposed_gate=new_gate(old_gate)
    current = json.loads(old_activation)
    check(current['approved_config_sha256'] == sha(old) and current['gates_approved'] is True, 'old_activation_invalid')
    JOURNAL.mkdir(mode=0o700)
    for name, raw in [('old.caddy',old),('new.caddy',proposed),('old.activation.json',old_activation),
                      ('old.access_gate.py',old_gate),('new.access_gate.py',proposed_gate)]:
        with (JOURNAL/name).open('xb') as output:output.write(raw)
    # Adapt only; this never starts an edge process or obtains a certificate.
    adapted = json.loads(command([str(Path.home()/'mac-hosting/bin/caddy'),'adapt','--adapter','caddyfile','--config',str(JOURNAL/'new.caddy')]))
    check(adapted.get('admin',{}).get('disabled') is True,'admin_must_remain_off')
    listeners = {a for s in adapted['apps']['http']['servers'].values() for a in s['listen']}
    check(listeners == {'192.168.4.239:8088','192.168.4.239:8443'}, 'listener_drift')
    plan = {'version':1,'runner_sha256':digest(Path(__file__)), 'sources':sources(),
        'old_config':sha(old),'new_config':sha(proposed),'old_activation':sha(old_activation),
        'old_gate':sha(old_gate),'new_gate':sha(proposed_gate),
        'phase2_completed':digest(phase2),'ui_fix_completed':digest(ui_fix),
        'containers':protected_snapshot(),'processes':owned_processes(),
        'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope':'Only tph-test upstream18211->18221 and its signed access cookie Lax for Auth0 GET return; CSRF/DieselBridge Strict; both test ingress children restart; no Docker/database/Railway action'}
    raw = canonical(plan)
    with (JOURNAL/'plan.json').open('xb') as output:output.write(raw)
    return {'prepared':True,'plan_sha256':sha(raw),'public_changed':False}


def transition(mode, expected_plan, expected_approval):
    plan_path = JOURNAL/'plan.json'; check(digest(plan_path)==expected_plan,'plan_drift')
    plan = json.loads(plan_path.read_text())
    approval_path = JOURNAL/'approval.json';check(digest(approval_path)==expected_approval,'approval_drift')
    approval = json.loads(approval_path.read_text())
    reviews(approval)
    check(approval.get('plan_sha256')==expected_plan and approval.get('runner_sha256')==digest(Path(__file__)) and
          approval.get('allow_test_upstream_and_rollback') is True,'independent_approval_required')
    check(plan['runner_sha256']==digest(Path(__file__)) and plan['sources']==sources(),'source_drift')
    check(protected_snapshot()==plan['containers'],'protected_runtime_drift')
    new_activation=json.loads((JOURNAL/'old.activation.json').read_text())
    new_activation.update(approved_config_sha256=plan['new_config'],real_data_cutover_plan_sha256=expected_plan,
                          real_data_qa=approval['qa'],real_data_security=approval['security'])
    new_activation=canonical(new_activation)
    if mode=='apply':
        check(digest(CLONE/'private/phase2-completed.json')==plan['phase2_completed'],'phase2_receipt_drift')
        check(digest(CLONE/'private/ui-fix-completed.json')==plan['ui_fix_completed'],'ui_fix_receipt_drift')
        private_ready()
        check(digest(CONFIG)==plan['old_config'] and digest(ACTIVATION)==plan['old_activation'],'old_edge_drift')
        check(digest(ROOT/'access_gate.py')==plan['old_gate'],'old_gate_drift')
        check(owned_processes()=={**plan['processes'],'children':{int(k):v for k,v in plan['processes']['children'].items()}},'runner_changed')
        raw=(JOURNAL/'new.caddy').read_bytes();check(sha(raw)==plan['new_config'],'new_config_drift')
        activation=new_activation
        gate=(JOURNAL/'new.access_gate.py').read_bytes();check(sha(gate)==plan['new_gate'],'new_gate_drift')
        owned=owned_processes()
    else:
        started=JOURNAL/'apply-started.json'
        check(started.exists() and json.loads(started.read_text())['plan']==expected_plan,'no_bound_apply_journal')
        check(digest(CONFIG) in (plan['new_config'],plan['old_config']) and
              digest(ACTIVATION) in (sha(new_activation),plan['old_activation']),'rollback_partial_state_drift')
        check(digest(ROOT/'access_gate.py') in (plan['old_gate'],plan['new_gate']),'rollback_gate_drift')
        private_ready(18211)
        raw=(JOURNAL/'old.caddy').read_bytes();activation=(JOURNAL/'old.activation.json').read_bytes()
        check(sha(raw)==plan['old_config'] and sha(activation)==plan['old_activation'],'rollback_archive_drift')
        gate=(JOURNAL/'old.access_gate.py').read_bytes();check(sha(gate)==plan['old_gate'],'rollback_gate_archive_drift')
        if (JOURNAL/'apply-completed.json').exists():
            completed=json.loads((JOURNAL/'apply-completed.json').read_text())
            owned=owned_processes()
            check(owned=={**completed['processes'],'children':{int(k):v for k,v in completed['processes']['children'].items()}},'completed_apply_process_drift')
            check(digest(ACTIVATION)==completed['activation_sha256'],'completed_apply_activation_drift')
        else:
            try:owned=owned_processes()
            except RuntimeError:
                absent_owned_processes();owned=None
    with (JOURNAL/(mode+'-started.json')).open('x') as output:json.dump({'plan':expected_plan,'owned':owned},output)
    put(CONFIG,raw);put(ACTIVATION,activation);put(ROOT/'access_gate.py',gate)
    if owned is not None:
        check(process(owned['pid'])==owned['identity'],'pid_reused_before_signal')
        os.kill(owned['pid'],signal.SIGTERM)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            rows=command(['/bin/ps','-axo','pid=']).decode().split()
            if not {str(owned['pid']),*(str(p) for p in owned['children'])}.intersection(rows):break
            time.sleep(.2)
        else:raise RuntimeError('owned_processes_not_stopped_no_forced_kill')
    subprocess.run(['/bin/launchctl','kickstart',service()],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        try:
            current=owned_processes()
            if owned is None or current['pid']!=owned['pid']:
                listeners(current)
                gate_negative_checks()
                break
        except (RuntimeError,subprocess.SubprocessError):pass
        time.sleep(.3)
    else:raise RuntimeError('new_runner_not_ready')
    check(protected_snapshot()==plan['containers'],'post_transition_runtime_drift')
    check(digest(CONFIG)==sha(raw),'post_transition_config_drift')
    check(digest(ROOT/'access_gate.py')==sha(gate),'post_transition_gate_drift')
    result={'completed':True,'mode':mode,'plan_sha256':expected_plan,'config_sha256':sha(raw),
            'runner_pid':current['pid'],'processes':current,'activation_sha256':digest(ACTIVATION),
            'gate_sha256':sha(gate),
            'protected_containers_unchanged':True,'production_changed':False,
            'external_https_browser_acceptance':'pending'}
    with (JOURNAL/(mode+'-completed.json')).open('x') as output:json.dump(result,output)
    return result


def main():
    os.umask(0o077)
    check(ROOT.resolve()==ROOT and not ROOT.is_symlink(),'root_refused')
    spec=importlib.util.spec_from_file_location('cutover_operator',Path.home()/'mac-hosting/test-stacks/tools/stackctl.py')
    operator=importlib.util.module_from_spec(spec);sys.modules[spec.name]=operator;spec.loader.exec_module(operator)
    with operator.lock():
        if sys.argv[1:]==['prepare']:result=prepare()
        else:
            check(len(sys.argv)==4 and sys.argv[1] in ('apply','rollback'),'command_refused')
            result=transition(*sys.argv[1:])
        print(json.dumps(result))


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('cutover_refused_or_uncertain_preserve_journals_no_retry') from None
