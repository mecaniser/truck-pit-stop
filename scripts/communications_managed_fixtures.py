"""Synthetic multi-shop fixtures; no provider resources are created or submitted."""
import asyncio
import os
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage, SMSMessageDirection, SMSMessageSource, SMSDeliveryStatus
from app.db.models.messaging_business import MessagingBusiness, TenantSMSBinding, SMSConsentEvidence
from app.services.sms_onboarding_service import configure_binding


def fid(n):
    return UUID(f'00000000-0000-4000-8000-{n:012d}')


def secrets_map():
    # Deliberately synthetic, unusable with Twilio; the harness also denies network.
    return {f'local_shop_{n}': {'account_sid': 'AC' + f'{n:032x}', 'auth_token': f'local-only-fake-shop-{n}-token'} for n in (1, 2)}


async def seed():
    if os.environ.get('COMMUNICATIONS_ISOLATED_LOCAL') != '1' or '@127.0.0.1:55460/communications_local' not in settings.DATABASE_URL:
        raise RuntimeError('Dedicated isolated communications database required')
    async with AsyncSessionLocal() as db:
        for n in (1, 2):
            tenant = await db.get(Tenant, fid(n))
            if not tenant:
                raise RuntimeError('Run the existing synthetic communications seed first')
            business = await db.scalar(select(MessagingBusiness).where(MessagingBusiness.tenant_id == tenant.id))
            if not business:
                business = MessagingBusiness(tenant_id=tenant.id, legal_name=f'Synthetic Repair {n} LLC', trade_name=f'Synthetic Repair {n}', sample_messages=[], status='draft', version=1)
                db.add(business)
                await db.flush()
            current = await db.scalar(select(TenantSMSBinding).where(TenantSMSBinding.tenant_id == tenant.id, TenantSMSBinding.retired_at.is_(None)))
            if not current:
                current = await configure_binding(db, tenant_id=tenant.id, business_id=business.id, verification_attested=True,
                    account_sid='AC'+f'{n:032x}', customer_profile_sid='BU'+f'{n:032x}', brand_sid='BN'+f'{n:032x}', campaign_sid='QE'+f'{n:032x}', messaging_service_sid='MG'+f'{n:032x}', sender_sid='PN'+f'{n:032x}', sender_phone=f'+1500555000{n}', credential_ref=f'local_shop_{n}', registration_status='approved', enabled=True)
            customer_id = fid(200+n)
            customer = await db.get(Customer, customer_id)
            if not customer:
                customer = Customer(id=customer_id, tenant_id=tenant.id, first_name='Shared', last_name=f'Test Contact {n}', email=f'managed-{n}@communications.example.com', phone='+15005550999')
                db.add(customer)
                await db.flush()
                thread = MessageThread(id=fid(1200+n), tenant_id=tenant.id, customer_id=customer.id, customer_phone=customer.phone, last_message_at=datetime.now(timezone.utc), last_message_preview='Synthetic multi-shop routing test')
                db.add(thread)
                await db.flush()
                db.add(SMSMessage(tenant_id=tenant.id, thread_id=thread.id, customer_id=customer.id, direction=SMSMessageDirection.INBOUND, source=SMSMessageSource.INBOUND, body='Synthetic multi-shop routing test', from_number=customer.phone, to_number=f'+1500555000{n}', delivery_status=SMSDeliveryStatus.DELIVERED, twilio_message_sid='SM'+f'{200+n:032x}', binding_id=current.id if current else None, twilio_account_sid='AC'+f'{n:032x}', messaging_service_sid='MG'+f'{n:032x}'))
            # Separate explicit synthetic evidence for the same phone in each business.
            evidence = await db.scalar(select(SMSConsentEvidence).where(SMSConsentEvidence.tenant_id==tenant.id,SMSConsentEvidence.recipient_id==customer.id))
            if not evidence:
                db.add(SMSConsentEvidence(tenant_id=tenant.id, recipient_kind='customer', recipient_id=customer.id, phone=customer.phone, purpose='service_notifications', status='granted', source='isolated_fixture', disclosure_version='synthetic-v1', collected_at=datetime.now(timezone.utc), actor_id=fid(10 if n==1 else 12)))
        await db.commit()
    print('Two synthetic businesses/accounts/senders and separately consented same-phone contacts prepared; no provider contacted')

if __name__ == '__main__':
    asyncio.run(seed())
