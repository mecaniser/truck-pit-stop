"""HTTP workflow acceptance for the managed, isolated, network-denied SMS harness."""
import asyncio
import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4
import httpx
from sqlalchemy import select
from twilio.request_validator import RequestValidator
from app.db.session import AsyncSessionLocal
from app.db.models.sms_message import SMSMessage

BASE='http://127.0.0.1:8006'
ROOT=Path(__file__).resolve().parents[1]
def fid(n):return f'00000000-0000-4000-8000-{n:012d}'
def account(n):return 'AC'+f'{n:032x}'
def service(n):return 'MG'+f'{n:032x}'
def token(n):return f'local-only-fake-shop-{n}-token'

def calls():
    with sqlite3.connect(ROOT/'.communications-provider.sqlite') as db:
        try:return db.execute('select count(*) from managed_calls').fetchone()[0]
        except sqlite3.OperationalError:return 0

async def main():
    if os.environ.get('COMMUNICATIONS_ISOLATED_LOCAL')!='1':raise RuntimeError('Dedicated local environment required')
    async with httpx.AsyncClient(base_url=BASE,timeout=30) as client:
        async def login(name):
            r=await client.post('/api/v1/auth/login',json={'email':f'{name}@communications.example.com','password':os.environ['LOCAL_STAFF_PASSWORD']});assert r.status_code==200
            return {'Authorization':'Bearer '+r.json()['access_token']}
        a,b,staff=[await login(n) for n in ('alex','foreign','jordan')]
        async def req(method,path,headers=a,expected=200,**kwargs):
            r=await client.request(method,'/api/v1/communications'+path,headers=headers,**kwargs)
            assert r.status_code==expected,(path,r.status_code,r.text[:200])
            return r.json()
        before=calls()
        for n,h in ((1,a),(2,b)):
            current=await req('GET','/sms/onboarding',headers=h)
            data=dict(expected_version=current['version'],legal_name=f'Synthetic Repair {n} LLC',trade_name=f'Synthetic Repair {n}',website_url=f'https://repair{n}.example.com',support_email=f'help@repair{n}.example.com',representative_name='Synthetic Owner',representative_email=f'owner@repair{n}.example.com',consent_source_url=f'https://repair{n}.example.com/sms',privacy_url=f'https://repair{n}.example.com/privacy',terms_url=f'https://repair{n}.example.com/terms',message_description='Customer repair service updates only.',sample_messages=[f'Synthetic Repair {n}: Your vehicle is ready. Reply STOP to opt out.'])
            saved=await req('PUT','/sms/onboarding',headers=h,json=data)
            assert not saved['submission_enabled']
            await req('PUT','/sms/onboarding',headers=h,expected=409,json=data)
            await req('PUT','/sms/onboarding',headers=h,expected=422,json={**data,'account_sid':account(2)})
            review=await req('POST','/sms/onboarding/review',headers=h,json={'expected_version':saved['version']})
            assert review['status']=='ready_for_review'
            package=await req('GET','/sms/onboarding/review-package',headers=h)
            assert package['review_only'] and not package['submission_enabled']
            assert 'credential_ref' not in json.dumps(package) and 'auth_token' not in json.dumps(package)
        await req('GET','/sms/onboarding',headers=staff,expected=403)
        await req('GET','/sms/consents?customer_id='+fid(202),expected=404)
        assert calls()==before
        print('PASS two tenant drafts/review/export, stale and injected fields, role and foreign consent guards; zero provider calls')
        operations=[]
        for n,h in ((1,a),(2,b)):
            path='/conversations/'+fid(1200+n)
            row=await req('GET',path,headers=h)
            assert row['send_policy']['can_send'],row['send_policy']
            key=str(uuid4());payload=dict(channel_account_id=row['channel_account_id'],contact_identity_id=row['contact_identity_id'],body='Isolated managed workflow '+key,expected_version=row['version'])
            responses=await asyncio.gather(*[client.post('/api/v1/communications'+path+'/send-operations',headers={**h,'Idempotency-Key':key},json=payload) for _ in range(3)])
            assert all(r.status_code in (200,202) for r in responses),[(r.status_code,r.text[:100]) for r in responses]
            assert len({r.json()['id'] for r in responses})==1
            op=responses[0].json()
            await req('POST',path+'/send-operations',headers={**h,'Idempotency-Key':key},expected=409,json={**payload,'body':'Changed payload'})
            async with AsyncSessionLocal() as db:
                sms=await db.scalar(select(SMSMessage).where(SMSMessage.id==op['message_id']))
                assert sms.twilio_account_sid==account(n) and sms.messaging_service_sid==service(n)
                operations.append((n,h,path,op,sms.twilio_message_sid))
        assert calls()==before+2
        with sqlite3.connect(ROOT/'.communications-provider.sqlite') as db:
            records=db.execute('select account_sid,service_sid,sender,recipient from managed_calls order by created_at desc, rowid desc limit 2').fetchall()
        assert {r[0] for r in records}=={account(1),account(2)}
        assert {r[3] for r in records}=={'+15005550999'}
        print('PASS same recipient across two businesses, exact fake account/service/sender, concurrent duplicate safety')
        async def webhook(kind,values,n,expected=200,signer=None):
            url=BASE+'/api/v1/webhooks/twilio/sms/'+kind
            sig=RequestValidator(token(signer or n)).compute_signature(url,values)
            r=await client.post(url,data=values,headers={'X-Twilio-Signature':sig})
            assert r.status_code==expected,(kind,r.status_code,r.text[:100])
        for n,h,path,op,sid in operations:
            values={'AccountSid':account(n),'MessagingServiceSid':service(n),'MessageSid':sid,'From':f'+1500555000{n}','MessageStatus':'delivered'}
            await webhook('status',values,n,expected=400,signer=3-n)
            await webhook('status',{**values,'AccountSid':account(3-n)},3-n,expected=503)
            for status in ('sent','delivered','sent'):
                await webhook('status',{**values,'MessageStatus':status},n)
            assert (await req('GET','/send-operations/'+op['id'],headers=h))['delivery_status']=='delivered'
            inbound={'AccountSid':account(n),'MessagingServiceSid':service(n),'MessageSid':'SM'+uuid4().hex,'To':f'+1500555000{n}','From':'+15005550999','Body':'Synthetic shop reply '+str(uuid4())}
            await webhook('inbound',{**inbound,'To':f'+1500555000{3-n}'},n,expected=404)
            await webhook('inbound',inbound,n);await webhook('inbound',inbound,n)
            row=await req('GET',path,headers=h)
            assert len([m for m in row['messages'] if m['body']==inbound['Body']])==1
        assert calls()==before+2
        print('PASS signed account-scoped delivery/reply, wrong-token/account/sender rejection, duplicate inbound and monotonic delivery')
    print('All managed local HTTP checks passed. No real provider network or registration submission; deployment held.')

if __name__=='__main__':asyncio.run(main())
