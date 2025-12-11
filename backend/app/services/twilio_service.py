from typing import Optional
from app.core.config import settings
from app.db.models.notification import Notification, NotificationType, NotificationStatus
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from twilio.rest import Client

client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


async def send_sms(
    db: AsyncSession,
    tenant_id: str,
    to: str,
    body: str,
    template_name: Optional[str] = None,
) -> Notification:
    """Send SMS via Twilio and create notification record"""
    
    notification = Notification(
        tenant_id=tenant_id,
        type=NotificationType.SMS,
        status=NotificationStatus.PENDING,
        recipient_phone=to,
        body=body,
        template_name=template_name,
    )
    
    db.add(notification)
    await db.commit()
    
    try:
        message = client.messages.create(
            body=body,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=to,
        )
        
        notification.status = NotificationStatus.SENT
        notification.external_id = message.sid
        notification.sent_at = datetime.utcnow()
        
    except Exception as e:
        notification.status = NotificationStatus.FAILED
        notification.error_message = str(e)
    
    await db.commit()
    await db.refresh(notification)
    
    return notification

