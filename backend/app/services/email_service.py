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


async def send_password_reset_email(to: str, reset_token: str):
    """Send password reset email without database notification (for security)"""
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #d97706;">Password Reset Request</h2>
        <p>You requested to reset your password for Truck Pit Stop.</p>
        <p>Click the link below to reset your password:</p>
        <p style="margin: 30px 0;">
            <a href="{reset_url}" 
               style="background-color: #d97706; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                Reset Password
            </a>
        </p>
        <p>Or copy and paste this link into your browser:</p>
        <p style="color: #666; word-break: break-all;">{reset_url}</p>
        <p style="margin-top: 30px; color: #666; font-size: 14px;">
            This link will expire in 1 hour.<br>
            If you didn't request this, please ignore this email.
        </p>
    </body>
    </html>
    """
    
    try:
        params = resend.Emails.SendParams(
            from_=settings.RESEND_FROM_EMAIL,
            to=to,
            subject="Reset Your Password - Truck Pit Stop",
            html=html_body,
        )
        resend.Emails.send(params)
    except Exception as e:
        # Log error but don't reveal to user for security
        print(f"Error sending password reset email: {e}")
        raise Exception("Failed to send password reset email")


