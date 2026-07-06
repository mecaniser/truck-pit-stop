from typing import Optional, List
from app.core.config import settings
from app.db.models.notification import Notification, NotificationType, NotificationStatus
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import resend

resend.api_key = settings.RESEND_API_KEY


def _format_sender(sender_name: Optional[str] = None) -> str:
    sender_email = settings.RESEND_FROM_EMAIL
    display_name = (sender_name or "").strip()
    if not display_name:
        return sender_email
    safe_name = display_name.replace('"', "'")
    return f'"{safe_name}" <{sender_email}>'


async def send_email(
    db: AsyncSession,
    tenant_id: str,
    to: str,
    subject: str,
    body: str,
    template_name: Optional[str] = None,
    attachments: Optional[List[dict]] = None,
    sender_name: Optional[str] = None,
) -> Notification:
    """Send email via Resend and create notification record.

    attachments: list of {"filename": str, "content": bytes} dicts.
    """
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
            "from": _format_sender(sender_name),
            "to": to,
            "subject": subject,
            "html": body,
        }
        if attachments:
            params["attachments"] = [
                {"filename": a["filename"], "content": list(a["content"])}
                for a in attachments
            ]
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


async def send_password_reset_email(to: str, reset_token: str, shop_name: Optional[str] = None):
    """Send password reset email without database notification (for security)"""
    brand = shop_name or "Your Account"
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #d97706;">Password Reset Request</h2>
        <p>You requested to reset your password for <strong>{brand}</strong>.</p>
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
        <p style="color: #d1d5db; font-size: 11px; margin-top: 6px;">Powered by DieselBridge Network</p>
    </body>
    </html>
    """

    try:
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": to,
            "subject": f"Reset Your Password – {brand}",
            "html": html_body,
        }
        resend.Emails.send(params)
    except Exception as e:
        # Log error but don't reveal to user for security
        print(f"Error sending password reset email: {e}")
        raise Exception("Failed to send password reset email")


async def send_email_verification(to: str, verification_token: str, shop_name: Optional[str] = None):
    """Send email verification link for email change"""
    brand = shop_name or "Your Account"
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 28px;">Verify Your Email</h1>
        </div>
        <div style="background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px;">
            <h2 style="color: #1f2937; margin-top: 0;">Confirm Your Email Change</h2>
            <p style="color: #4b5563; line-height: 1.6;">
                You requested to change your email address on <strong>{brand}</strong>.
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
                    This link will expire in 1 hour
                </p>
                <p style="color: #9ca3af; font-size: 13px; margin: 5px 0;">
                    If you didn't request this change, please ignore this email and your account will remain secure
                </p>
            </div>
            <p style="color: #d1d5db; font-size: 11px; margin-top: 20px; text-align: center;">Powered by DieselBridge Network</p>
        </div>
    </body>
    </html>
    """

    try:
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": to,
            "subject": f"Verify Your Email Address – {brand}",
            "html": html_body,
        }
        resend.Emails.send(params)
    except Exception as e:
        print(f"Error sending email verification: {e}")
        raise Exception("Failed to send verification email")


async def send_email_change_notification(old_email: str, new_email: str, user_name: str, shop_name: Optional[str] = None):
    """Send notification to old email about email change request"""
    brand = shop_name or "Your Account"
    
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
                Someone requested to change the email address for your <strong>{brand}</strong> account from:
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
            This is an automated security notification from {brand}
        </p>
    </body>
    </html>
    """
    
    try:
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": old_email,
            "subject": f"Email Change Request – {brand}",
            "html": html_body,
        }
        resend.Emails.send(params)
    except Exception as e:
        print(f"Error sending email change notification: {e}")
        # Don't fail the request if notification fails


async def send_enrollment_received_email(to: str, garage_name: str, owner_name: str):
    """Send confirmation email to garage owner after enrollment submission"""
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 28px;">Application Received!</h1>
        </div>
        <div style="background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px;">
            <h2 style="color: #1f2937; margin-top: 0;">Welcome, {owner_name}!</h2>
            <p style="color: #4b5563; line-height: 1.6;">
                Thank you for applying to join DieselBridge Network with <strong>{garage_name}</strong>.
            </p>
            <p style="color: #4b5563; line-height: 1.6;">
                Your application is now under review. Our team will verify your information and get back to you within 1-2 business days.
            </p>
            <div style="background: #dbeafe; border-left: 4px solid #3b82f6; padding: 15px; margin: 20px 0; border-radius: 4px;">
                <p style="color: #1e40af; margin: 0; font-weight: bold;">What happens next?</p>
                <ul style="color: #1e40af; margin: 10px 0 0 0; padding-left: 20px;">
                    <li>We'll review your business information</li>
                    <li>You'll receive an email once approved</li>
                    <li>Then you can log in and start managing your shop!</li>
                </ul>
            </div>
            <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
                Questions? Reply to this email and we'll be happy to help.
            </p>
        </div>
    </body>
    </html>
    """
    
    try:
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": to,
            "subject": f"Application Received - {garage_name} | DieselBridge Network",
            "html": html_body,
        }
        resend.Emails.send(params)
    except Exception as e:
        print(f"Error sending enrollment received email: {e}")


async def send_enrollment_approved_email(to: str, garage_name: str, owner_name: str):
    """Send approval email to garage owner"""
    login_url = f"{settings.FRONTEND_URL}/login"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 28px;">You're Approved!</h1>
        </div>
        <div style="background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px;">
            <h2 style="color: #1f2937; margin-top: 0;">Congratulations, {owner_name}!</h2>
            <p style="color: #4b5563; line-height: 1.6;">
                Great news! Your application for <strong>{garage_name}</strong> has been approved.
            </p>
            <p style="color: #4b5563; line-height: 1.6;">
                You can now log in and start managing your truck repair shop with DieselBridge Network.
            </p>
            <div style="margin: 30px 0; text-align: center;">
                <a href="{login_url}" 
                   style="background-color: #10b981; color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold; font-size: 16px;">
                    Log In to Your Dashboard
                </a>
            </div>
            <div style="background: #ecfdf5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0; border-radius: 4px;">
                <p style="color: #065f46; margin: 0; font-weight: bold;">Getting Started:</p>
                <ul style="color: #065f46; margin: 10px 0 0 0; padding-left: 20px;">
                    <li>Set up your Stripe account to accept payments</li>
                    <li>Add your team members (technicians, admins)</li>
                    <li>Configure your services and pricing</li>
                    <li>Start taking repair orders!</li>
                </ul>
            </div>
            <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
                Need help getting started? Check out our documentation or contact support.
            </p>
        </div>
    </body>
    </html>
    """
    
    try:
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": to,
            "subject": f"Welcome to DieselBridge Network - {garage_name} Approved!",
            "html": html_body,
        }
        resend.Emails.send(params)
    except Exception as e:
        print(f"Error sending enrollment approved email: {e}")


async def send_enrollment_rejected_email(to: str, garage_name: str, owner_name: str, reason: str):
    """Send rejection email to garage owner"""
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #fef2f2; border-left: 4px solid #ef4444; padding: 20px; border-radius: 6px; margin-bottom: 20px;">
            <h2 style="color: #991b1b; margin: 0 0 10px 0; font-size: 20px;">Application Update</h2>
        </div>
        <div style="background: #f9fafb; padding: 25px; border-radius: 8px;">
            <p style="color: #374151; line-height: 1.6;">
                Hi {owner_name},
            </p>
            <p style="color: #374151; line-height: 1.6;">
                Thank you for your interest in joining DieselBridge Network with <strong>{garage_name}</strong>.
            </p>
            <p style="color: #374151; line-height: 1.6;">
                After reviewing your application, we're unable to approve it at this time.
            </p>
            <div style="background: white; padding: 15px; border-radius: 6px; margin: 20px 0; border: 1px solid #e5e7eb;">
                <p style="margin: 0; color: #6b7280; font-size: 14px;">Reason:</p>
                <p style="margin: 10px 0 0 0; color: #1f2937;">{reason}</p>
            </div>
            <p style="color: #374151; line-height: 1.6;">
                If you believe this was a mistake or have additional information to provide, 
                please reply to this email and we'll be happy to reconsider.
            </p>
        </div>
    </body>
    </html>
    """
    
    try:
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": to,
            "subject": f"Application Status Update - {garage_name} | DieselBridge Network",
            "html": html_body,
        }
        resend.Emails.send(params)
    except Exception as e:
        print(f"Error sending enrollment rejected email: {e}")


async def send_new_enrollment_notification(admin_emails: list, garage_name: str, owner_name: str, owner_email: str):
    """Send notification to super admins about new enrollment"""
    admin_url = f"{settings.FRONTEND_URL}/dashboard/pending-enrollments"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 24px;">New Garage Enrollment</h1>
        </div>
        <div style="background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px;">
            <p style="color: #4b5563; line-height: 1.6;">
                A new garage has applied to join DieselBridge Network:
            </p>
            <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #e5e7eb;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Garage Name:</td>
                        <td style="padding: 8px 0; color: #1f2937; font-weight: bold;">{garage_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Owner:</td>
                        <td style="padding: 8px 0; color: #1f2937;">{owner_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Email:</td>
                        <td style="padding: 8px 0; color: #1f2937;">{owner_email}</td>
                    </tr>
                </table>
            </div>
            <div style="margin: 30px 0; text-align: center;">
                <a href="{admin_url}" 
                   style="background-color: #4f46e5; color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold; font-size: 16px;">
                    Review Application
                </a>
            </div>
        </div>
    </body>
    </html>
    """
    
    for email in admin_emails:
        try:
            params = {
                "from": settings.RESEND_FROM_EMAIL,
                "to": email,
                "subject": f"New Garage Enrollment: {garage_name}",
                "html": html_body,
            }
            resend.Emails.send(params)
        except Exception as e:
            print(f"Error sending enrollment notification to {email}: {e}")
