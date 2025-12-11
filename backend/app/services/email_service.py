from typing import Optional
from app.core.config import settings
from app.db.models.notification import Notification, NotificationType, NotificationStatus
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import resend

resend.api_key = settings.RESEND_API_KEY


async def send_email(
    db: AsyncSession,
    tenant_id: str,
    to: str,
    subject: str,
    body: str,
    template_name: Optional[str] = None,
) -> Notification:
    """Send email via Resend and create notification record"""
    
    notification = Notification(
        tenant_id=tenant_id,
        type=NotificationType.EMAIL,
        status=NotificationStatus.PENDING,
        recipient_email=to,
        subject=subject,
        body=body,
        template_name=template_name,
    )
    
    db.add(notification)
    await db.commit()
    
    try:
        params = resend.Emails.SendParams(
            from_=settings.RESEND_FROM_EMAIL,
            to=to,
            subject=subject,
            html=body,
        )
        email = resend.Emails.send(params)
        
        notification.status = NotificationStatus.SENT
        notification.external_id = email.id
        notification.sent_at = datetime.utcnow()
        
    except Exception as e:
        notification.status = NotificationStatus.FAILED
        notification.error_message = str(e)
    
    await db.commit()
    await db.refresh(notification)
    
    return notification

