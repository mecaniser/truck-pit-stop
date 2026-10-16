"""Fail-closed tenant SMS routing. This module never provisions provider resources."""
from dataclasses import dataclass
import json
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from twilio.http.http_client import TwilioHttpClient
from twilio.rest import Client
from app.core.config import settings


def enabled():
    return settings.SMS_TENANT_ROUTING_ENABLED


def deny(code):
    raise HTTPException(409, detail={'code': code, 'message': 'SMS connection or consent requires review.'})


@dataclass(frozen=True)
class SMSContext:
    binding_id: UUID
    account_sid: str
    messaging_service_sid: str
    sender_phone: str
    credential_ref: str

    def snapshots(self):
        return dict(binding_id=self.binding_id, twilio_account_sid=self.account_sid, messaging_service_sid=self.messaging_service_sid)


def credentials(reference, account_sid):
    try:
        configured = settings.SMS_TENANT_CREDENTIALS_JSON
        entries = json.loads(configured) if isinstance(configured, str) else configured
        if not isinstance(entries, dict) or not isinstance(reference, str):
            raise ValueError()
        secret = entries[reference]
        if not isinstance(secret, dict):
            raise ValueError()
        if secret['account_sid'] != account_sid or not secret['auth_token']:
            raise ValueError()
        return secret
    except (ValueError, TypeError, KeyError):
        deny('credentials_unavailable')


def client_for(context):
    secret = credentials(context.credential_ref, context.account_sid)
    return Client(context.account_sid, secret['auth_token'], http_client=TwilioHttpClient(timeout=25, max_retries=0))


async def resolve(db, tenant_id, binding_id=None):
    from app.db.models.messaging_business import TenantSMSBinding, MessagingBusiness
    from app.db.models.tenant import Tenant
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id).execution_options(populate_existing=True))
    if not tenant or not tenant.is_active or tenant.deleted_at or not tenant.sms_enabled or not tenant.messaging_enabled:
        deny('tenant_disabled')
    binding = await db.scalar(select(TenantSMSBinding).where(TenantSMSBinding.tenant_id == tenant_id, TenantSMSBinding.retired_at.is_(None), TenantSMSBinding.deleted_at.is_(None)).execution_options(populate_existing=True))
    if not binding:
        deny('binding_changed' if binding_id is not None else 'not_connected')
    if not binding.enabled:
        deny('not_connected')
    business = await db.scalar(select(MessagingBusiness).where(MessagingBusiness.id == binding.business_id, MessagingBusiness.deleted_at.is_(None)).execution_options(populate_existing=True))
    if not business or business.status in {'rejected', 'suspended'}:
        deny('registration_required')
    if binding_id is not None and binding.id != binding_id:
        deny('binding_changed')
    if binding.registration_status != 'approved' or not binding.verified_at or not all((binding.account_sid, binding.customer_profile_sid, binding.brand_sid, binding.campaign_sid, binding.messaging_service_sid, binding.sender_sid, binding.sender_phone)):
        deny('registration_required')
    credentials(binding.credential_ref, binding.account_sid)
    return SMSContext(binding.id, binding.account_sid, binding.messaging_service_sid, binding.sender_phone, binding.credential_ref)


async def for_operation(db, op):
    if not op.binding_id or not op.twilio_account_sid or not op.messaging_service_sid:
        deny('binding_changed')
    context = await resolve(db, op.tenant_id, op.binding_id)
    if (context.account_sid, context.messaging_service_sid, context.sender_phone) != (op.twilio_account_sid, op.messaging_service_sid, op.from_number):
        deny('binding_changed')
    return context


async def require_consent(db, tenant_id, kind, recipient_id, phone):
    from app.db.models.messaging_business import SMSConsentEvidence
    row = await db.scalar(select(SMSConsentEvidence).where(SMSConsentEvidence.tenant_id == tenant_id, SMSConsentEvidence.recipient_kind == kind, SMSConsentEvidence.recipient_id == recipient_id, SMSConsentEvidence.phone == phone, SMSConsentEvidence.purpose == 'service_notifications').order_by(SMSConsentEvidence.collected_at.desc(), SMSConsentEvidence.created_at.desc(), SMSConsentEvidence.id.desc()).limit(1))
    if not row or row.status != 'granted':
        deny('consent_required')


async def account_token(db, account_sid):
    """Known retired bindings may authenticate historical delivery receipts."""
    from app.db.models.messaging_business import TenantSMSBinding
    if not account_sid:
        return None
    rows = (await db.scalars(select(TenantSMSBinding).where(TenantSMSBinding.account_sid == account_sid))).all()
    for row in rows:
        try:
            return credentials(row.credential_ref, account_sid)['auth_token']
        except HTTPException:
            continue
    return None


async def inbound_binding(db, account_sid, to_number):
    from app.db.models.messaging_business import TenantSMSBinding
    row = await db.scalar(select(TenantSMSBinding).where(TenantSMSBinding.account_sid == account_sid, TenantSMSBinding.sender_phone == to_number, TenantSMSBinding.retired_at.is_(None)))
    if not row:
        raise HTTPException(404, detail='SMS account and sender not recognized')
    return row


async def require_legacy_tenant(db, tenant_id):
    """A rollout rollback cannot turn an onboarded business into a global sender."""
    from app.db.models.messaging_business import TenantSMSBinding
    if await db.scalar(select(TenantSMSBinding.id).where(TenantSMSBinding.tenant_id == tenant_id).limit(1)):
        deny('routing_disabled')
