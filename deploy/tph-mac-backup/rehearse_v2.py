"""One-shot, synthetic-only runtime acceptance; preserve every failure and receipt."""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import urllib.request
import urllib.error

spec=importlib.util.spec_from_file_location('backup_operator',Path(__file__).with_name('operator.py'))
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)

def request(path,body=None):
    from relay import exchange
    headers={'Origin':'http://localhost:18310'}
    if body is not None:headers['Content-Type']='application/json'
    status,data,_=exchange('GET' if body is None else 'POST',path,b'' if body is None else json.dumps(body).encode(),headers)
    return status,data

def check(condition,label):
    if not condition:raise RuntimeError('Rehearsal acceptance failed: '+label)
    results.append(label)

def refusal(call,label):
    try:call()
    except RuntimeError:results.append(label);return
    raise RuntimeError('Expected refusal missing: '+label)

def authority(site):
    raw=op.compose('exec','-T',site,'node','-e',"fetch('http://127.0.0.1:5051/authority').then(r=>r.json()).then(x=>console.log(JSON.stringify(x)))")
    return json.loads(raw)

results=[]
def main():
    os.umask(0o077)
    with op.lock():
        op.save('rehearsal-v2-started.json',{'at':op.now(),'synthetic_only':True})
        before=op.protected();initial=op.control({'command':'status'})
        check(initial['site']=='railway-simulation' and initial['phase']=='active' and initial['watermark']==0 and not initial['pending']['blocked'],'starts_on_railway_simulation')
        check(request('/')[0]==200,'native_frontend_200')
        code,body=request('/api/addresses');check(code==200 and b'BACKUP-REHEARSAL-001' in body and b'BACKUP-REHEARSAL-HIDDEN' not in body,'native_public_data_and_hidden_filter')
        for path in ('/api/payments','/api/bookings','/api/send-email','/api/webhooks/square','/api/jobs'):
            check(request(path,{})[0]==403,'native_mutation_blocked_'+path)
        baseline=authority('railway-simulation')
        code,raw=request('/api/pin/verify-client',{'pin':op.credentials()['pin']})
        check(code==200 and json.loads(raw).get('success') is True,'native_pin_accepted_before_switch')
        first=authority('railway-simulation');check(first['pin_usage']==baseline['pin_usage']+1,'native_write_persisted')
        pending=op.control({'command':'pending-test'})
        old=op.inspect('railway-simulation')['Id']
        refusal(lambda:op.switch('mac-backup'),'inflight_switch_refused')
        check(op.inspect('railway-simulation')['State']['Running'],'inflight_refusal_keeps_source_running')
        op.control({'command':'cancel-pending-test','admission_id':pending['admission_id']})
        switched=op.switch('mac-backup');check(switched['site']=='mac-backup','switch_to_mac')
        check(not op.inspect('railway-simulation')['State']['Running'],'exact_old_source_stopped')
        check(authority('mac-backup')['pin_usage']==first['pin_usage'],'all_native_writes_current_after_switch')
        check(b'Mac backup' in request('/')[1],'native_frontend_mac_banner')
        code,raw=request('/api/pin/verify-client',{'pin':op.credentials()['pin']});check(code==200 and json.loads(raw).get('success') is True,'native_pin_accepted_on_mac')
        refusal(lambda:op.control({'command':'effect','site':'railway-simulation','epoch':initial['epoch'],'kind':'payment','business_id':'stale-owner','payload':{}}),'stale_owner_cannot_dispatch')
        effect={'command':'effect','kind':'payment','business_id':'synthetic-booking-001','payload':{'amount':100,'simulation':True}}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:list(pool.map(lambda _:op.control(effect),range(10)))
        for kind in ('email','sms','job'):op.control({**effect,'kind':kind})
        counts=op.control({'command':'counts'});check(sum(counts['fake_effects'].values())==4,'ten_replays_one_effect_per_business_kind')
        unknown=op.control({'command':'effect','kind':'payment','business_id':'synthetic-unknown-001','payload':{'simulation':True},'lose_ack':True})
        refusal(lambda:op.switch('railway-simulation'),'unknown_payment_blocks_failback')
        check(op.inspect('mac-backup')['State']['Running'],'unknown_refusal_keeps_mac_running')
        check(request('/')[0]==503,'unknown_freezes_public_admissions')
        op.control({'command':'reconcile','operation_id':unknown['operation_id']})
        restored=op.switch('railway-simulation');check(restored['site']=='railway-simulation','switch_back_to_railway_simulation')
        check(not op.inspect('mac-backup')['State']['Running'],'mac_source_stopped_before_failback')
        check(authority('railway-simulation')['pin_usage']==first['pin_usage']+1,'mac_writes_preserved_on_return')
        check(b'Railway simulation' in request('/')[1],'native_frontend_return_banner')
        op.docker(['restart',op.inspect('router')['Id']],log='router-persistence-restart')
        op.ready('router')
        op.control(effect)
        final=op.control({'command':'counts'});check(sum(final['fake_effects'].values())==5,'ledger_restart_and_unknown_reconcile_no_duplicate')
        refusal(lambda:op.control({'command':'activate-live'}),'live_activation_always_refused')
        # Independent runtime Security probes cover actual network denials for both app services and router; Mongo isolation is structural.
        op.compare(before)
        receipt={'at':op.now(),'synthetic_only':True,'live_activation':'forbidden','checks':results,'control':final['control'],'fake_effects':final['fake_effects'],'source':op.SOURCE,'existing_fourteen_unchanged':True,'backup_restore':op.load('backup-restore.json')}
        op.save('rehearsal-v2-passed.json',receipt);print(json.dumps(receipt))

if __name__=='__main__':
    try:main()
    except Exception as error:
        op.save('rehearsal-v2-failure.json',{'at':op.now(),'type':type(error).__name__,'passed_checks':results})
        raise SystemExit(str(error) if isinstance(error,RuntimeError) else 'Rehearsal failed; private evidence retained') from None
