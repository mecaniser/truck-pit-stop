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
) -> Notification:
    """Backwards-compatible SMS sender with threaded tracking support."""
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
