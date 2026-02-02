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
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": to,
            "subject": subject,
            "html": body,
        }
        email = resend.Emails.send(params)
        
        notification.status = NotificationStatus.SENT
        notification.external_id = email.get("id") if isinstance(email, dict) else getattr(email, "id", None)
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
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": to,
            "subject": "Reset Your Password - Truck Pit Stop",
            "html": html_body,
        }
        resend.Emails.send(params)
    except Exception as e:
        # Log error but don't reveal to user for security
        print(f"Error sending password reset email: {e}")
        raise Exception("Failed to send password reset email")


async def send_email_verification(to: str, verification_token: str):
    """Send email verification link for email change"""
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 28px;">📧 Verify Your Email</h1>
        </div>
        <div style="background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px;">
            <h2 style="color: #1f2937; margin-top: 0;">Confirm Your Email Change</h2>
            <p style="color: #4b5563; line-height: 1.6;">
                You requested to change your email address on Truck Pit Stop. 
                To confirm this change, please click the button below:
            </p>
            <div style="margin: 30px 0; text-align: center;">
                <a href="{verify_url}" 
                   style="background-color: #d97706; color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold; font-size: 16px;">
                    Verify Email Address
                </a>
            </div>
            <p style="color: #6b7280; font-size: 14px;">Or copy and paste this link into your browser:</p>
            <p style="background: white; padding: 12px; border-radius: 6px; word-break: break-all; color: #4b5563; font-size: 13px; border: 1px solid #e5e7eb;">
                {verify_url}
            </p>
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb;">
                <p style="color: #9ca3af; font-size: 13px; margin: 5px 0;">
                    ⏱️ This link will expire in 1 hour
                </p>
                <p style="color: #9ca3af; font-size: 13px; margin: 5px 0;">
                    🔒 If you didn't request this change, please ignore this email and your account will remain secure
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    try:
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": to,
            "subject": "Verify Your Email Address - Truck Pit Stop",
            "html": html_body,
        }
        resend.Emails.send(params)
    except Exception as e:
        print(f"Error sending email verification: {e}")
        raise Exception("Failed to send verification email")


async def send_email_change_notification(old_email: str, new_email: str, user_name: str):
    """Send notification to old email about email change request"""
    
    # Mask part of the new email for security
    email_parts = new_email.split('@')
    if len(email_parts[0]) > 3:
        masked = email_parts[0][:2] + '***' + email_parts[0][-1] + '@' + email_parts[1]
    else:
        masked = '***@' + email_parts[1]
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 20px; border-radius: 6px; margin-bottom: 20px;">
            <h2 style="color: #92400e; margin: 0 0 10px 0; font-size: 20px;">⚠️ Email Change Request</h2>
            <p style="color: #78350f; margin: 0; line-height: 1.6;">
                Hi {user_name},
            </p>
        </div>
        
        <div style="background: #f9fafb; padding: 25px; border-radius: 8px;">
            <p style="color: #374151; line-height: 1.6;">
                Someone requested to change the email address for your Truck Pit Stop account from:
            </p>
            <div style="background: white; padding: 15px; border-radius: 6px; margin: 15px 0; border: 1px solid #e5e7eb;">
                <p style="margin: 0; color: #6b7280; font-size: 14px;">Current Email:</p>
                <p style="margin: 5px 0 0 0; color: #1f2937; font-weight: bold; font-size: 16px;">{old_email}</p>
            </div>
            <div style="text-align: center; color: #9ca3af; margin: 10px 0;">↓</div>
            <div style="background: white; padding: 15px; border-radius: 6px; margin: 15px 0; border: 1px solid #e5e7eb;">
                <p style="margin: 0; color: #6b7280; font-size: 14px;">New Email:</p>
                <p style="margin: 5px 0 0 0; color: #1f2937; font-weight: bold; font-size: 16px;">{masked}</p>
            </div>
            
            <p style="color: #374151; line-height: 1.6; margin-top: 20px;">
                A verification link has been sent to the new email address. 
                <strong>Your email will only change after verification.</strong>
            </p>
            
            <div style="background: #fee2e2; border-left: 3px solid #ef4444; padding: 15px; margin-top: 20px; border-radius: 4px;">
                <p style="color: #991b1b; margin: 0; font-weight: bold; font-size: 14px;">
                    ❗ Didn't request this change?
                </p>
                <p style="color: #991b1b; margin: 8px 0 0 0; font-size: 14px;">
                    If this wasn't you, someone may have access to your account. 
                    Please change your password immediately and contact support.
                </p>
            </div>
        </div>
        
        <p style="color: #9ca3af; font-size: 12px; margin-top: 30px; text-align: center;">
            This is an automated security notification from Truck Pit Stop
        </p>
    </body>
    </html>
    """
    
    try:
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": old_email,
            "subject": "🔔 Email Change Request - Truck Pit Stop",
            "html": html_body,
        }
        resend.Emails.send(params)
    except Exception as e:
        print(f"Error sending email change notification: {e}")
        # Don't fail the request if notification fails

