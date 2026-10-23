"""Private Docker-exec operator API for the synthetic rehearsal. Never HTTP-exposed."""
import hashlib
import json
import sys
import uuid
from control import Control,DataProof,StoppedProof,Refused,payload_hash
from provider_sink import FakeProvider
from router import auxiliary,checkpoint


def execute(value):
    control=Control('/state/control.sqlite3');command=value['command']
    if command=='init':return control.initialize(value['site'],value['instance_id'],authority_id=value['authority_id'])
    if command=='status':return control.summary()
    if command=='drain':
        state=control.state();control.begin_drain(state['site'],state['epoch']);return control.summary()
    if command=='promote':
        # These observations arrive only from the private, locked host operator,
        # which verifies exact Docker identity and stopped state immediately prior.
        observed=value['stopped'];target=value['target'];cid=value['target_instance_id']
        def stopped(expected):
            if observed.get('id')!=expected or observed.get('running') is not False:raise Refused('old_rehearsal_container_not_stopped')
            return StoppedProof(expected,observed['observation_id'])
        def fresh(authority,watermark,site,instance):
            data=auxiliary(site,'/authority')
            if data['database']!='tph_backup_restored' or data['authority_id']!=authority or data['watermark']!=watermark or data.get('source')!='b369e9f5e28584ba99f1cbe35d8f65080a51aeda' or not instance.startswith(data.get('instance_prefix','INVALID')) or len(data.get('instance_prefix',''))!=12:raise Refused('shared_data_stale_or_unavailable')
            digest=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
            return DataProof(authority,data['watermark'],site,instance,digest)
        return control.promote(target,cid,stopped,fresh)
    if command=='activate-live':return control.activate_live()
    if command=='effect':
        state=control.state();site=value.get('site',state['site']);epoch=value.get('epoch',state['epoch'])
        row=control.claim_operation(site,epoch,value['kind'],value['business_id'],value.get('payload',{}))
        if row['dispatch']:
            authorized=control.authorize_dispatch(row['operation_id'],site,epoch)
            receipt=FakeProvider().accept(authorized)
            if value.get('lose_ack'):
                control.complete_operation(row['operation_id'],'unknown')
            else:
                control.complete_operation(row['operation_id'],'accepted',receipt);checkpoint(control,state['site'])
        return {**control.operation(row['operation_id']),'fake_provider_counts':FakeProvider().counts(),'simulation':True}
    if command=='reconcile':
        state=control.state();row=control.reconcile_operation(value['operation_id'],FakeProvider().lookup)
        checkpoint(control,state['site']);return row
    if command=='pending-test':
        state=control.state();return control.admit(state['site'],state['epoch'],'rehearsal-test-'+uuid.uuid4().hex,{'simulation':'not-dispatched'})
    if command=='cancel-pending-test':
        # Rehearsal-only admissions created without a native request are definitively rejected.
        with control._connection() as db:
            row=db.execute('SELECT request_id,payload_sha256 FROM admissions WHERE admission_id=?',(value['admission_id'],)).fetchone()
        if not row or not row['request_id'].startswith('rehearsal-test-') or row['payload_sha256']!=payload_hash({'simulation':'not-dispatched'}):raise Refused('not_a_synthetic_pending_test')
        return control.complete(value['admission_id'],'rejected')
    if command=='counts':return {'simulation':True,'fake_effects':FakeProvider().counts(),'control':control.summary()}
    raise Refused('unknown_rehearsal_command')


if __name__=='__main__':
    try:
        print(json.dumps(execute(json.load(sys.stdin))))
    except Exception as error:
        print(json.dumps({'refused':str(error) if isinstance(error,Refused) else type(error).__name__}),file=sys.stderr)
        raise SystemExit(1)
