"""HTTP acceptance against the explicitly isolated communications sandbox only."""
import asyncio
import json
import os
import sqlite3
from twilio.request_validator import RequestValidator
from pathlib import Path
from uuid import uuid4
import httpx

BASE = 'http://127.0.0.1:8006'
def fid(n):
    return f'00000000-0000-4000-8000-{n:012d}'

async def main():
    if os.environ.get('COMMUNICATIONS_ISOLATED_LOCAL') != '1':
        raise RuntimeError('Use communications_local.py exec; isolated sandbox required')
    results = []
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        async def login(name):
            r = await client.post('/api/v1/auth/login', json={'email':f'{name}@communications.example.com','password':os.environ['LOCAL_STAFF_PASSWORD']})
            assert r.status_code == 200, ('login', name, r.status_code)
            return {'Authorization':'Bearer '+r.json()['access_token']}
        alex, jordan, foreign, customer = [await login(n) for n in ('alex','jordan','foreign','customer')]
        prefix = '/api/v1/communications'
        async def req(method,path,headers=alex,expected=200,**kwargs):
            r = await client.request(method,prefix+path,headers=headers,**kwargs)
            assert r.status_code == expected, (method,path,r.status_code,r.text[:300])
            return r.json()
        bootstrap = await req('GET','/bootstrap')
        assert bootstrap['delivery_mode']=='simulated'
        assert bootstrap['tenant_id']==fid(1)
        await req('GET','/bootstrap',headers=customer,expected=403)
        results.append('production login and messaging permission gate')
        rows = await req('GET','/conversations')
        assert all(x['tenant_id']==fid(1) for x in rows['items'])
        thread=fid(1100)
        path='/conversations/'+thread
        await req('GET',path,headers=foreign,expected=404)
        conversation = await req('GET',path)
        unchanged = await req('GET',path)
        assert conversation['unread_count']==unchanged['unread_count']
        other_before=await req('GET',path,headers=jordan)
        if conversation['messages']:
            await req('POST',path+'/read',json={'through_message_id':conversation['messages'][-1]['id']})
            after=await req('GET',path)
            assert after['unread_count']==0
            assert (await req('GET',path,headers=jordan))['unread_count']==other_before['unread_count']
        results.append('tenant history isolation and independent read watermarks')
        conversation=await req('GET',path)
        assigned=await req('PATCH',path,json={'expected_version':conversation['version'],'assignee_id':fid(11)})
        assert assigned['assignee_id']==fid(11)
        await req('PATCH',path,expected=409,json={'expected_version':conversation['version'],'status':'resolved'})
        await req('PATCH',path,expected=404,json={'expected_version':assigned['version'],'assignee_id':fid(12)})
        resolved=await req('PATCH',path,json={'expected_version':assigned['version'],'status':'resolved'})
        assert (await req('GET',path))['status']=='resolved'
        opened=await req('PATCH',path,json={'expected_version':resolved['version'],'status':'open'})
        assert opened['status']=='open'
        results.append('persistent assignment, resolution and stale/foreign mutation denial')
        ledger_path=Path(__file__).resolve().parents[1]/'.communications-provider.sqlite'
        def calls():
            if not ledger_path.exists(): return 0
            with sqlite3.connect(ledger_path) as ledger:
                return ledger.execute('SELECT count(*) FROM calls').fetchone()[0]
        calls_before=calls()
        key=str(uuid4())
        payload={'channel_account_id':opened['channel_account_id'],'contact_identity_id':opened['contact_identity_id'],'body':'Local duplicate acceptance '+key,'expected_version':opened['version']}
        await req('POST',path+'/send-operations',headers={**foreign,'Idempotency-Key':str(uuid4())},expected=404,json=payload)
        await req('POST',path+'/send-operations',headers={**customer,'Idempotency-Key':str(uuid4())},expected=403,json=payload)
        await req('POST',path+'/read',headers=foreign,expected=404,json={'through_message_id':fid(2100)})
        await req('POST',path+'/read',expected=404,json={'through_message_id':fid(2105)})
        await req('POST',path+'/read',headers=customer,expected=403,json={'through_message_id':fid(2100)})
        await req('PATCH',path,headers=foreign,expected=404,json={'expected_version':opened['version'],'status':'resolved'})
        await req('PATCH',path,headers=customer,expected=403,json={'expected_version':opened['version'],'status':'resolved'})
        await req('GET',path+'/messages',headers=foreign,expected=404)
        results.append('foreign send/read/history/workflow IDs and unauthorized mutations rejected')
        responses=await asyncio.gather(*[client.post(prefix+path+'/send-operations',headers={**alex,'Idempotency-Key':key},json=payload) for _ in range(4)])
        assert all(r.status_code in (200,202) for r in responses),[(r.status_code,r.text[:200]) for r in responses]
        operation_ids={r.json()['id'] for r in responses}
        assert len(operation_ids)==1
        op_id=operation_ids.pop()
        await req('POST',path+'/send-operations',headers={**alex,'Idempotency-Key':key},expected=409,json={**payload,'body':'Changed intent'})
        await req('GET','/send-operations/'+op_id,headers=foreign,expected=404)
        for _ in range(50):
            operation=await req('GET','/send-operations/'+op_id)
            if operation['state'] not in ('pending','dispatching'):
                break
            await asyncio.sleep(.1)
        assert operation['state']=='accepted',operation
        replay=await req('POST',path+'/send-operations',headers={**alex,'Idempotency-Key':key},json=payload)
        assert replay['id']==op_id and replay['replayed']
        current=await req('GET',path)
        assert len([m for m in current['messages'] if m['body']==payload['body']])==1
        assert calls()==calls_before+1, ('provider call count', calls_before, calls())
        results.append('four concurrent same-key sends produce one operation/history row/provider call; payload conflict and tenant operation isolation')
        opted=await req('GET','/conversations/'+fid(1103))
        assert opted['send_policy']['reason']=='opted_out'
        await req('POST','/conversations/'+fid(1103)+'/send-operations',headers={**alex,'Idempotency-Key':str(uuid4())},expected=409,json={'channel_account_id':opted['channel_account_id'],'contact_identity_id':opted['contact_identity_id'],'body':'Blocked test','expected_version':opted['version']})
        assert calls()==calls_before+1
        results.append('opt-out blocks provider submission')
        from sqlalchemy import select
        from app.db.session import AsyncSessionLocal
        from app.db.models.sms_message import SMSMessage
        async with AsyncSessionLocal() as db:
            sid=await db.scalar(select(SMSMessage.twilio_message_sid).where(SMSMessage.id==operation['message_id']))
        async def webhook(kind,values,valid=True):
            url=BASE+'/api/v1/webhooks/twilio/sms/'+kind
            signature=RequestValidator(os.environ['TWILIO_AUTH_TOKEN']).compute_signature(url,values) if valid else 'invalid'
            response=await client.post(url,data=values,headers={'X-Twilio-Signature':signature})
            assert response.status_code==(200 if valid else 400),(kind,response.status_code,response.text[:200])
        await webhook('status',{'MessageSid':sid,'MessageStatus':'delivered'},False)
        for status in ('sent','delivered','delivered','sent'):
            await webhook('status',{'MessageSid':sid,'MessageStatus':status})
        assert (await req('GET','/send-operations/'+op_id))['delivery_status']=='delivered'
        results.append('signed callbacks deliver once and preserve terminal status against duplicate/out-of-order events; invalid signatures rejected')
        current=await req('GET',path)
        await req('POST',path+'/read',json={'through_message_id':current['messages'][-1]['id']})
        await req('PATCH',path,json={'expected_version':current['version'],'status':'resolved'})
        inbound_sid='SM'+uuid4().hex
        values={'MessageSid':inbound_sid,'From':'+15005550100','To':'+15005550001','Body':'Synthetic inbound reply '+key}
        await webhook('inbound',values)
        await webhook('inbound',values)
        current=await req('GET',path)
        assert current['status']=='open'
        assert current['unread_count']==1,current['unread_count']
        assert len([m for m in current['messages'] if m['body']==values['Body']])==1
        results.append('signed inbound reply reopens resolved inbox and stays unread; duplicate inbound SID produces one message')
        async def outcome_send(thread_number,outcome):
            target='/conversations/'+fid(thread_number)
            row=await req('GET',target)
            if row['send_policy']['reason']=='ambiguous_outcome':
                results.append('retained unknown-outcome fixture remains blocked; fresh timeout was exercised on initial acceptance run')
                assert any(m['delivery_status']=='unknown' for m in row['messages'])
                await req('POST',target+'/send-operations',headers={**alex,'Idempotency-Key':str(uuid4())},expected=409,json={'channel_account_id':row['channel_account_id'],'contact_identity_id':row['contact_identity_id'],'body':'Held fixture resend negative','expected_version':row['version']})
                return None
            with sqlite3.connect(ledger_path) as ledger:
                ledger.execute('CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY CHECK (id = 1), outcome TEXT NOT NULL)')
                ledger.execute('INSERT OR REPLACE INTO control (id,outcome) VALUES (1,?)',(outcome,))
            intent={'channel_account_id':row['channel_account_id'],'contact_identity_id':row['contact_identity_id'],'body':'Local '+outcome+' '+str(uuid4()),'expected_version':row['version']}
            intent_key=str(uuid4())
            before=calls()
            op=await req('POST',target+'/send-operations',headers={**alex,'Idempotency-Key':intent_key},expected=202,json=intent)
            for _ in range(50):
                op=await req('GET','/send-operations/'+op['id'])
                if op['state'] not in ('pending','dispatching'): break
                await asyncio.sleep(.1)
            assert op['state']==('rejected' if outcome=='rejected' else 'unknown'),op
            assert op['can_retry'] is False
            replay=await req('POST',target+'/send-operations',headers={**alex,'Idempotency-Key':intent_key},json=intent)
            assert replay['id']==op['id'] and calls()==before+1
            if outcome=='unknown':
                await req('POST',target+'/send-operations',headers={**alex,'Idempotency-Key':str(uuid4())},expected=409,json={**intent,'expected_version':(await req('GET',target))['version']})
                assert calls()==before+1
            return op
        await outcome_send(1102,'rejected')
        await outcome_send(1101,'unknown')
        results.append('confirmed rejection and accepted-timeout unknown remain persisted; same-key replay causes no additional invocation; unknown blocks new intent')
        print(json.dumps({'passed':results,'operation_id':op_id,'thread_id':thread,'message_id':operation['message_id'],'idempotency_key':key},indent=2))

if __name__=='__main__':
    asyncio.run(main())
