"""Idempotently seed only the dedicated, newly-created synthetic local DB."""
import asyncio
import os
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.db.models.user import User, UserRole
from app.db.models.tenant import Tenant
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage, SMSMessageDirection, SMSMessageSource, SMSDeliveryStatus


def fixture_id(n):
    return UUID(f'00000000-0000-4000-8000-{n:012d}')

async def seed():
    if os.environ.get('COMMUNICATIONS_ISOLATED_LOCAL') != '1' or '@127.0.0.1:55460/communications_local' not in settings.DATABASE_URL:
        raise RuntimeError('Refusing to seed anything except isolated communications database')
    async with AsyncSessionLocal() as db:
        if await db.get(Tenant, fixture_id(1)):
            print('Synthetic seed already exists; preserving inbox state')
            return
        for n, name in [(1,'DieselBridge Demo'),(2,'Isolation Test Shop')]:
            db.add(Tenant(id=fixture_id(n), name=name, slug=f'communications-local-{n}', sms_enabled=True, messaging_enabled=True, sms_phone_number=f'+1500555000{n}', enrollment_status='approved'))
        await db.flush()
        for n, tenant, first, role in [(10,1,'Alex',UserRole.GARAGE_OWNER),(11,1,'Jordan',UserRole.RECEPTIONIST),(12,2,'Foreign',UserRole.GARAGE_OWNER),(13,1,'Customer',UserRole.CUSTOMER)]:
            db.add(User(id=fixture_id(n),tenant_id=fixture_id(tenant),first_name=first,last_name='Demo',email=f'{first.lower()}@communications.example.com',hashed_password=get_password_hash(os.environ['LOCAL_STAFF_PASSWORD']),role=role,is_active=True,is_verified=True))
        await db.flush()
        for n, first, last, company, opted, tenant in [(100,'Daniel','Brooks','Northline Transport',False,1),(101,'Maria','Santos','Blue Ridge Freight',False,1),(102,'James','Wilson','Wilson Hauling',False,1),(103,'Ethan','Price','Price Logistics',True,1),(104,'Ava','Reed','Reed Transport',False,1),(105,'Foreign','Customer','Isolation Test',False,2)]:
            phone=f'+15005550{n:03d}'
            customer = Customer(id=fixture_id(n),tenant_id=fixture_id(tenant),first_name=first,last_name=last,company_name=company,email=f'{first.lower()}@example.test',phone=phone,sms_opt_out=opted)
            db.add(customer)
            await db.flush()
            body='Could you send me an update on my truck?'
            thread=MessageThread(id=fixture_id(n+1000),tenant_id=fixture_id(tenant),customer_id=customer.id,customer_phone=phone,last_message_at=datetime.now(timezone.utc),last_message_preview=body,unread_count_staff=1)
            db.add(thread)
            await db.flush()
            db.add(SMSMessage(id=fixture_id(n+2000),tenant_id=fixture_id(tenant),thread_id=thread.id,customer_id=customer.id,direction=SMSMessageDirection.INBOUND,source=SMSMessageSource.INBOUND,body=body,from_number=phone,to_number=f'+1500555000{tenant}',delivery_status=SMSDeliveryStatus.DELIVERED,twilio_message_sid=f'SM{n:032d}'))
        await db.commit()
    print('Created synthetic tenants, staff, contacts, and persisted SMS history; no provider contacted')

if __name__ == '__main__':
    asyncio.run(seed())
