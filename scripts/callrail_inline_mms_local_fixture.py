"""Create one idempotent synthetic inbound MMS through the current intake."""
import asyncio
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from app.core.config import settings
from app.db.models.callrail import CallRailNumberBinding
from app.db.models.tenant import Tenant
from app.db.session import AsyncSessionLocal
from app.services.callrail_service import apply_event


async def main():
    if ('@127.0.0.1:55460/communications_local_inline_mms_20261022' not in settings.DATABASE_URL
        or settings.ENVIRONMENT != 'development'
        or any(getattr(settings, name) for name in ('SMS_TENANT_ROUTING_ENABLED',
            'SMS_AUTOMATION_OUTBOX_ENABLED', 'SMS_RECOVERY_ENABLED'))):
        raise RuntimeError('Dedicated MMS synthetic database and false flags required')
    async with AsyncSessionLocal() as db:
        tenant = await db.get(Tenant, UUID('00000000-0000-4000-8000-000000000001'))
        if not tenant or tenant.slug != 'communications-local-1':
            raise RuntimeError('Synthetic tenant required')
        binding = await db.scalar(select(CallRailNumberBinding).where(
            CallRailNumberBinding.account_id == 'ACCsynthetic',
            CallRailNumberBinding.sender_phone == '+15005550011'))
        if not binding:
            binding = CallRailNumberBinding(tenant_id=tenant.id, account_id='ACCsynthetic',
                company_id='COMsynthetic', tracker_id='TRKsynthetic', sender_phone='+15005550011',
                credential_ref='CALLRAIL_LOCAL_API', signing_secret_ref='CALLRAIL_LOCAL_SIGNING',
                enabled=True, accept_new_inquiries=True)
            db.add(binding); await db.flush()
        if (binding.tenant_id != tenant.id or binding.company_id != 'COMsynthetic'
            or binding.credential_ref != 'CALLRAIL_LOCAL_API' or not binding.enabled):
            raise RuntimeError('Unexpected existing synthetic binding; refusing overwrite')
        outcome = await apply_event(db, binding.id, dict(id=17001, resource_id='SCIinlineMmsDemo',
            company_resource_id='COMsynthetic', conversation_id='InlineMmsDemo',
            source_number='+15005550222', destination_number='+15005550011',
            message_type='mms', content='Photo of the truck for the repair.',
            timestamp=datetime.now(timezone.utc).isoformat()), 'received')
        assert outcome['status'] in {'received', 'duplicate'}
        await db.commit()
    print('Synthetic inbound MMS fixture ready; no provider contacted')


if __name__ == '__main__':
    asyncio.run(main())
