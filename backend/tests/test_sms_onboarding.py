"""Draft/consent isolation acceptance; no outbound provider transport."""
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from app.schemas.sms_onboarding import SMSOnboardingUpdate, SMSConsentCreate


@pytest.mark.parametrize('extra', ['tenant_id','account_sid','credential_ref','enabled','status','tax_id','auth_token'])
def test_draft_rejects_provider_secret_and_approval_injection(extra):
    with pytest.raises(ValidationError):
        SMSOnboardingUpdate(expected_version=0,**{extra:'forbidden'})


@pytest.mark.parametrize('url',['http://repair.example','https://127.0.0.1','https://localhost','https://x.internal','https://' + ':'.join(('synthetic_user', 'synthetic_password')) + '@repair.example'])
def test_public_https_only(url):
    with pytest.raises(ValidationError):
        SMSOnboardingUpdate(expected_version=0,website_url=url)


@pytest_asyncio.fixture
async def isolated():
    if os.getenv('COMMUNICATIONS_ISOLATED_LOCAL')!='1':
        pytest.skip('Dedicated isolated PostgreSQL required')
    from app.db.session import AsyncSessionLocal,engine
    from app.db.models.tenant import Tenant
    from app.db.models.user import User
    from app.db.models.customer import Customer
    async with AsyncSessionLocal() as db:
        tid,uid,cid=uuid4(),uuid4(),uuid4()
        tenant=Tenant(id=tid,name='Onboarding synthetic',slug=f'onboard-{tid}',messaging_enabled=True,sms_enabled=True)
        db.add(tenant)
        await db.flush()
        user=User(id=uid,tenant_id=tid,email=f'{uid}@example.test',first_name='Synthetic',last_name='Owner',role='garage_owner',hashed_password='disabled',is_active=True)
        customer=Customer(id=cid,tenant_id=tid,first_name='Synthetic',last_name='Recipient',email=f'{cid}@example.test',phone='+15005550123')
        db.add_all([user,customer]);await db.commit()
        yield db,tenant,user,customer
        await db.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_draft_version_review_redaction_and_staff_denial(isolated,monkeypatch):
    from app.services import sms_onboarding_service as svc
    from app.services import messaging_service
    db,tenant,user,_=isolated
    monkeypatch.setattr(messaging_service,'_get_twilio_client',lambda:pytest.fail('No provider calls permitted'))
    initial=await svc.onboarding(db,tenant)
    assert initial['version']==0 and initial['submission_enabled'] is False
    body=SMSOnboardingUpdate(expected_version=0,legal_name='Synthetic Repair LLC',trade_name='Synthetic Repair',website_url='https://repair.example',support_email='help@repair.example',consent_source_url='https://repair.example/sms',privacy_url='https://repair.example/privacy',terms_url='https://repair.example/terms',representative_name='Synthetic Owner',representative_email='owner@repair.example',message_description='Repair service updates',sample_messages=['Synthetic Repair: your repair is ready. Reply STOP to unsubscribe.'])
    result=await svc.save_draft(db,tenant,user,body)
    assert result['version']==1 and result['fields']['legal_name']=='Synthetic Repair LLC'
    assert 'credential_ref' not in str(result)
    tid,uid=tenant.id,user.id
    with pytest.raises(HTTPException) as exc:
        await svc.save_draft(db,tenant,user,body)
    assert exc.value.detail['code']=='version_conflict'
    await db.rollback()
    tenant=await db.get(type(tenant),tid);user=await db.get(type(user),uid)
    result=await svc.request_review(db,tenant,user,1)
    assert result['status']=='ready_for_review' and result['version']==2
    assert result['submission_enabled'] is False
    user.role='mechanic'
    with pytest.raises(HTTPException) as exc:
        await svc.owner_tenant(db,user)
    assert exc.value.status_code==403


@pytest.mark.asyncio
async def test_consent_explicit_phone_bound_and_foreign_customer_denied(isolated):
    from app.services import sms_onboarding_service as svc
    db,tenant,user,customer=isolated
    assert (await svc.customer_consents(db,tenant,customer.id))['items']==[]
    body=SMSConsentCreate(customer_id=customer.id,status='granted',source='signed_service_form',disclosure_version='service-v1',collected_at=datetime.now(timezone.utc)-timedelta(seconds=1))
    evidence=await svc.record_customer_consent(db,tenant,user,body)
    assert evidence['phone_last4']=='0123' and evidence['status']=='granted'
    body.status='withdrawn'
    await svc.record_customer_consent(db,tenant,user,body)
    assert len((await svc.customer_consents(db,tenant,customer.id))['items'])==2
    with pytest.raises(HTTPException) as exc:
        await svc.customer_for(db,uuid4(),customer.id)
    assert exc.value.status_code==404


@pytest.mark.asyncio
async def test_binding_versioning_attestation_and_account_ownership(isolated):
    from app.services import sms_onboarding_service as svc
    from app.db.models.messaging_business import MessagingBusiness,TenantSMSBinding
    db,tenant,user,_=isolated
    business=MessagingBusiness(tenant_id=tenant.id,legal_name='Synthetic Repair',sample_messages=[])
    db.add(business);await db.flush()
    values={name:prefix+uuid4().hex for name,prefix in {'account_sid':'AC','customer_profile_sid':'BU','brand_sid':'BN','campaign_sid':'QE','messaging_service_sid':'MG','sender_sid':'PN'}.items()}
    values.update(sender_phone='+1'+str(2000000000+tenant.id.int%7000000000),credential_ref='synthetic_A',registration_status='approved',enabled=True)
    with pytest.raises(HTTPException) as exc:
        await svc.configure_binding(db,tenant_id=tenant.id,business_id=business.id,**values)
    assert exc.value.detail['code']=='provider_verification_required'
    first=await svc.configure_binding(db,tenant_id=tenant.id,business_id=business.id,verification_attested=True,**values)
    second=await svc.configure_binding(db,tenant_id=tenant.id,business_id=business.id,verification_attested=True,**values)
    assert second.revision==2 and second.id!=first.id
    assert first.retired_at is not None and not first.enabled
    assert second.account_sid==values['account_sid']
    await db.commit()

@pytest.mark.asyncio
async def test_http_owner_draft_export_injection_and_staff_permissions(isolated):
    from fastapi import FastAPI
    import httpx
    from app.api.v1.endpoints.sms_onboarding import router
    from app.core.dependencies import get_db,get_current_active_user
    db,tenant,user,customer=isolated
    app=FastAPI();app.include_router(router,prefix='/communications/sms')
    async def session():
        yield db
    app.dependency_overrides[get_db]=session
    app.dependency_overrides[get_current_active_user]=lambda:user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated.test') as client:
        response=await client.get('/communications/sms/onboarding')
        assert response.status_code==200 and response.json()['version']==0
        response=await client.put('/communications/sms/onboarding',json={'expected_version':0,'legal_name':'HTTP synthetic LLC','enabled':True})
        assert response.status_code==422
        response=await client.put('/communications/sms/onboarding',json={'expected_version':0,'legal_name':'HTTP synthetic LLC'})
        assert response.status_code==200 and response.json()['version']==1
        response=await client.get('/communications/sms/onboarding/review-package')
        assert response.status_code==200 and response.json()['review_only'] is True
        assert response.json()['submission_enabled'] is False
        response=await client.post('/communications/sms/onboarding/review',json={'expected_version':1})
        assert response.status_code==409 and response.json()['detail']['code']=='draft_incomplete'
        user.role='mechanic'
        assert (await client.get('/communications/sms/onboarding')).status_code==403
        assert (await client.get('/communications/sms/consents',params={'customer_id':str(customer.id)})).status_code==200
        assert (await client.get('/communications/sms/consents',params={'customer_id':str(uuid4())})).status_code==404
        assert (await client.post('/communications/sms/activate')).status_code==404

@pytest.mark.asyncio
async def test_operator_binding_foreign_business_and_sender_reuse_denied(isolated):
    from app.services import sms_onboarding_service as svc
    from app.db.models.messaging_business import MessagingBusiness
    from app.db.models.tenant import Tenant
    db,tenant,user,_=isolated
    other=Tenant(name='Other synthetic',slug=f'other-{uuid4()}',is_active=True)
    db.add(other);await db.flush()
    own=MessagingBusiness(tenant_id=tenant.id,legal_name='Business A',sample_messages=[])
    foreign=MessagingBusiness(tenant_id=other.id,legal_name='Business B',sample_messages=[])
    db.add_all([own,foreign]);await db.flush()
    values={name:prefix+uuid4().hex for name,prefix in {'account_sid':'AC','customer_profile_sid':'BU','brand_sid':'BN','campaign_sid':'QE','messaging_service_sid':'MG','sender_sid':'PN'}.items()}
    values.update(sender_phone='+1'+str(2000000000+tenant.id.int%7000000000),credential_ref='synthetic_A',registration_status='approved',enabled=True)
    with pytest.raises(HTTPException) as exc:
        await svc.configure_binding(db,tenant_id=tenant.id,business_id=foreign.id,verification_attested=True,**values)
    assert exc.value.detail['code']=='ownership_verification_required'
    await svc.configure_binding(db,tenant_id=tenant.id,business_id=own.id,verification_attested=True,**values)
    with pytest.raises(HTTPException) as exc:
        await svc.configure_binding(db,tenant_id=other.id,business_id=foreign.id,verification_attested=True,**values)
    assert exc.value.detail['code']=='account_business_conflict'
    values['account_sid']='AC'+uuid4().hex
    with pytest.raises(HTTPException) as exc:
        await svc.configure_binding(db,tenant_id=other.id,business_id=foreign.id,verification_attested=True,**values)
    assert exc.value.detail['code']=='sender_already_bound'

@pytest.mark.asyncio
async def test_connection_readiness_missing_secret_and_disabled_rollout(isolated,monkeypatch):
    from app.services import sms_onboarding_service as svc
    from app.core.config import settings
    from app.db.models.messaging_business import MessagingBusiness
    db,tenant,user,_=isolated
    business=MessagingBusiness(tenant_id=tenant.id,legal_name='Readiness synthetic',sample_messages=[])
    db.add(business);await db.flush()
    values={name:prefix+uuid4().hex for name,prefix in {'account_sid':'AC','customer_profile_sid':'BU','brand_sid':'BN','campaign_sid':'QE','messaging_service_sid':'MG','sender_sid':'PN'}.items()}
    values.update(sender_phone='+1'+str(2000000000+tenant.id.int%7000000000),credential_ref='missing-secret',registration_status='approved',enabled=True)
    await svc.configure_binding(db,tenant_id=tenant.id,business_id=business.id,verification_attested=True,**values)
    await db.commit()
    monkeypatch.setattr(settings,'SMS_TENANT_ROUTING_ENABLED',True)
    monkeypatch.setattr(settings,'SMS_TENANT_CREDENTIALS_JSON','{}')
    result=await svc.onboarding(db,tenant)
    assert result['connection']['status']=='pending_verification'
    assert 'credentials_unavailable' in result['blockers']
    assert 'missing-secret' not in str(result)
    monkeypatch.setattr(settings,'SMS_TENANT_ROUTING_ENABLED',False)
    result=await svc.onboarding(db,tenant)
    assert result['connection']['status']=='managed_routing_disabled'
    assert 'managed_routing_disabled' in result['blockers']
