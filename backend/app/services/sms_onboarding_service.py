"""Shop-scoped, platform-managed review drafts. This module never contacts a provider."""
from datetime import datetime, timezone
import re
import hashlib
from sqlalchemy import select, text
from fastapi import HTTPException
from app.db.models.messaging_business import MessagingBusiness, TenantSMSBinding, SMSConsentEvidence, SMSConfigurationAudit
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.services.communications_service import fail
from app.services.messaging_service import _normalize_for_twilio

DRAFT_FIELDS = ('legal_name','trade_name','website_url','support_email','support_phone','consent_source_url','privacy_url','terms_url','representative_name','representative_email','message_description','sample_messages')
REQUIRED = ('legal_name','trade_name','website_url','support_email','consent_source_url','privacy_url','terms_url','representative_name','representative_email','message_description','sample_messages')


async def draft(db, tenant_id, *, lock=False):
    q = select(MessagingBusiness).where(MessagingBusiness.tenant_id==tenant_id,MessagingBusiness.deleted_at.is_(None))
    if lock:
        q=q.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(q)


def draft_blockers(row):
    return [f'{name}_required' for name in REQUIRED if not row or not getattr(row,name)]


async def onboarding(db,tenant):
    row = await draft(db,tenant.id)
    binding=await db.scalar(select(TenantSMSBinding).where(TenantSMSBinding.tenant_id==tenant.id,TenantSMSBinding.retired_at.is_(None)))
    blockers=draft_blockers(row)
    connection={'status':'not_configured','sender_last4':None,'registration_status':None,'verified_at':None}
    if not binding and tenant.sms_phone_number:
        connection.update(status='legacy_configured',sender_last4=tenant.sms_phone_number[-4:])
    if binding:
        from app.services import tenant_sms_routing as routing
        connection=dict(status='managed_routing_disabled',sender_last4=binding.sender_phone[-4:],registration_status=binding.registration_status,verified_at=binding.verified_at)
        if routing.enabled():
            try:
                await routing.resolve(db,tenant.id,binding.id)
                connection['status']='configured'
            except HTTPException as exc:
                code=exc.detail.get('code','not_connected') if isinstance(exc.detail,dict) else 'not_connected'
                blockers.append(code)
                connection['status']='pending_verification'
        else:
            blockers.append('managed_routing_disabled')
    else:
        blockers.append('provider_registration_required')
        from app.services import tenant_sms_routing as routing
        if routing.enabled():
            try:
                await routing.resolve(db,tenant.id)
            except HTTPException as exc:
                code=exc.detail.get('code','not_connected') if isinstance(exc.detail,dict) else 'not_connected'
                blockers.append(code)
    return dict(version=row.version if row else 0,status=row.status if row else 'draft',submission_enabled=False,fields={k:getattr(row,k) if row else ([] if k=='sample_messages' else None) for k in DRAFT_FIELDS},blockers=blockers,connection=connection,rejection_reason=row.rejection_reason if row else None)


async def save_draft(db,tenant,user,body):
    # Lock tenant even before the first draft exists; concurrent creates serialize.
    await db.scalar(select(Tenant).where(Tenant.id==tenant.id).with_for_update())
    row=await draft(db,tenant.id,lock=True)
    if body.expected_version!=(row.version if row else 0):
        fail('version_conflict','The draft changed. Reload and try again.')
    if row and row.status in {'submitted','in_review','approved','suspended'}:
        fail('registration_locked','Registration is under operator review.')
    if row is None:
        row=MessagingBusiness(tenant_id=tenant.id,version=0,status='draft',sample_messages=[])
        db.add(row)
    for key,value in body.model_dump(exclude={'expected_version'},exclude_unset=True).items():
        setattr(row,key,[] if key=='sample_messages' and value is None else value)
    row.version+=1
    row.status='draft'
    row.updated_by_id=user.id
    row.rejection_reason=None
    db.add(SMSConfigurationAudit(tenant_id=tenant.id,actor_id=user.id,action='draft_saved',business_version=row.version))
    await db.commit()
    return await onboarding(db,tenant)


async def request_review(db,tenant,user,expected_version):
    row=await draft(db,tenant.id,lock=True)
    if not row or row.version!=expected_version:
        fail('version_conflict','The draft changed. Reload and try again.')
    if row.status not in {'draft','rejected','ready_for_review'}:
        fail('registration_locked','Registration is under operator review.')
    blockers=draft_blockers(row)
    if blockers:
        fail('draft_incomplete','Complete the required registration information.')
    row.status='ready_for_review'
    row.version+=1
    row.updated_by_id=user.id
    db.add(SMSConfigurationAudit(tenant_id=tenant.id,actor_id=user.id,action='review_requested',business_version=row.version))
    await db.commit()
    return await onboarding(db,tenant)


async def customer_for(db,tenant_id,customer_id):
    row=await db.scalar(select(Customer).where(Customer.id==customer_id,Customer.tenant_id==tenant_id,Customer.deleted_at.is_(None)))
    if not row:
        fail('not_found','Customer not found.',404)
    return row


def consent_json(row):
    return dict(id=row.id,customer_id=row.recipient_id,phone_last4=row.phone[-4:],purpose=row.purpose,status=row.status,source=row.source,disclosure_version=row.disclosure_version,collected_at=row.collected_at,created_at=row.created_at)


async def customer_consents(db,tenant,customer_id):
    await customer_for(db,tenant.id,customer_id)
    rows=(await db.execute(select(SMSConsentEvidence).where(SMSConsentEvidence.tenant_id==tenant.id,SMSConsentEvidence.recipient_kind=='customer',SMSConsentEvidence.recipient_id==customer_id).order_by(SMSConsentEvidence.collected_at.desc(),SMSConsentEvidence.created_at.desc()))).scalars().all()
    return {'items':[consent_json(row) for row in rows]}


async def record_customer_consent(db,tenant,user,body):
    customer=await customer_for(db,tenant.id,body.customer_id)
    phone=_normalize_for_twilio(customer.phone or '')
    if not re.fullmatch(r'\+[1-9]\d{7,14}',phone or ''):
        fail('invalid_recipient','Customer requires a valid SMS number.',422)
    row=SMSConsentEvidence(tenant_id=tenant.id,recipient_kind='customer',recipient_id=customer.id,phone=phone,purpose='service_notifications',status=body.status,source=body.source,disclosure_version=body.disclosure_version,collected_at=body.collected_at,actor_id=user.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return consent_json(row)


async def configure_binding(db, *, tenant_id, business_id, actor_id=None, ownership_verified=False, verification_attested=False, **values):
    """Operator-only internal mechanism; never exposed to tenant request bodies.

    Caller must independently verify legal ownership and provider associations.
    This function stores that attestation, and performs no provisioning.
    """
    tenant=await db.scalar(select(Tenant).where(Tenant.id==tenant_id,Tenant.deleted_at.is_(None),Tenant.is_active.is_(True)).with_for_update())
    business=await db.get(MessagingBusiness,business_id)
    if not tenant or not business or business.deleted_at is not None:
        fail('not_found','Shop or messaging business not found.',404)
    if business.tenant_id!=tenant.id and not ownership_verified:
        fail('ownership_verification_required','Additional locations require verified legal ownership.')
    required={'account_sid':'AC','customer_profile_sid':'BU','brand_sid':'BN','campaign_sid':'QE','messaging_service_sid':'MG','sender_sid':'PN'}
    for name,prefix in required.items():
        if not re.fullmatch(prefix+r'[a-fA-F0-9]{32}',values.get(name,'') or ''):
            fail('invalid_binding',f'Invalid {name}.',422)
    phone=values.get('sender_phone','')
    if not re.fullmatch(r'\+[1-9]\d{7,14}',phone) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}',values.get('credential_ref','')):
        fail('invalid_binding','Invalid sender or credential reference.',422)
    status=values.get('registration_status','draft')
    if status not in {'draft','submitted','in_review','approved','rejected','suspended'}:
        fail('invalid_binding','Invalid registration state.',422)
    if (values.get('enabled') or status=='approved') and not verification_attested:
        fail('provider_verification_required','Provider associations require independent verification.')
    # Different tenants cannot concurrently assign one provider account to different businesses.
    if db.bind.dialect.name=='postgresql':
        account_lock=int.from_bytes(hashlib.sha256(values['account_sid'].encode()).digest()[:8],'big',signed=True)
        await db.execute(text('SELECT pg_advisory_xact_lock(:lock_id)'),{'lock_id':account_lock})
    accounts=(await db.execute(select(TenantSMSBinding).where(TenantSMSBinding.account_sid==values['account_sid']))).scalars().all()
    if any(b.business_id!=business_id for b in accounts):
        fail('account_business_conflict','Provider account belongs to another legal business.')
    sender=await db.scalar(select(TenantSMSBinding).where(TenantSMSBinding.sender_phone==phone,TenantSMSBinding.retired_at.is_(None),TenantSMSBinding.tenant_id!=tenant_id))
    if sender:
        fail('sender_already_bound','Sender already belongs to another shop.')
    allowed=set(required)|{'sender_phone','credential_ref','registration_status','enabled'}
    if set(values)-allowed:
        fail('invalid_binding','Unknown binding field.',422)
    old=await db.scalar(select(TenantSMSBinding).where(TenantSMSBinding.tenant_id==tenant_id,TenantSMSBinding.retired_at.is_(None)).with_for_update())
    revision=1
    if old:
        revision=old.revision+1
        old.retired_at=datetime.now(timezone.utc)
        old.enabled=False
        await db.flush()
    row=TenantSMSBinding(tenant_id=tenant_id,business_id=business_id,revision=revision,verified_at=datetime.now(timezone.utc) if verification_attested else None,**values)
    db.add(row)
    await db.flush()
    db.add(SMSConfigurationAudit(tenant_id=tenant_id,actor_id=actor_id,action='binding_replaced' if old else 'binding_created',binding_id=row.id))
    if business.tenant_id!=tenant_id:
        db.add(SMSConfigurationAudit(tenant_id=tenant_id,actor_id=actor_id,action='linked_location_ownership_verified',binding_id=row.id))
    return row
