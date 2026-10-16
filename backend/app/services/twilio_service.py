from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.notification import Notification
from app.db.models.sms_message import SMSMessageSource
from app.services.messaging_service import send_sms_with_tracking


async def send_sms(
    db: AsyncSession,
    tenant_id: str,
    to: str,
    body: str,
    template_name: Optional[str] = None,
    customer_id: Optional[UUID | str] = None,
    source: SMSMessageSource | str = SMSMessageSource.AUTOMATED,
    created_by_user_id: Optional[UUID | str] = None,
    *,
    domain_event_id: Optional[str] = None,
    template_version: str = '1',
    recipient_user_id: Optional[UUID | str] = None,
    recipient_tenant_contact: bool = False,
) -> Notification:
    """Manual compatibility; automation only enqueues within the caller transaction."""
    if source == SMSMessageSource.AUTOMATED or source == 'automated':
        from app.services.automated_sms_service import enqueue_automated_sms
        operation = await enqueue_automated_sms(
            db, tenant_id=tenant_id, domain_event_id=domain_event_id,
            template_name=template_name, template_version=template_version,
            to=to, body=body, customer_id=customer_id,
            recipient_user_id=recipient_user_id, recipient_tenant_contact=recipient_tenant_contact,
        )
        return await db.get(Notification, operation.notification_id)
    notification, _, _ = await send_sms_with_tracking(
        db=db,
        tenant_id=tenant_id,
        to=to,
        body=body,
        template_name=template_name,
        customer_id=customer_id,
        source=source,
        created_by_user_id=created_by_user_id,
        raise_on_failure=False,
    )
    return notification
