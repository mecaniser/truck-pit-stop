from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.email_service import send_email


def _staff_order_url(order_id: UUID) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/repair-orders?selected={order_id}"


async def collect_staff_contacts(
    db: AsyncSession,
    tenant_id: UUID,
) -> tuple[set[str], set[str]]:
    """Collect active staff contacts for payment alerts with tenant fallback."""
    result = await db.execute(
        select(User).where(
            and_(
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                User.role.in_([UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST]),
            )
        )
    )
    users = result.scalars().all()
    emails = {u.email for u in users if u.email}
    phones = {u.phone for u in users if u.phone}

    if not emails or not phones:
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        if tenant:
            if not emails and tenant.email:
                emails.add(tenant.email)
            if not phones and tenant.phone:
                phones.add(tenant.phone)

    return emails, phones


async def _send_staff_alert(
    db: AsyncSession,
    tenant_id: UUID,
    emails: set[str],
    phones: set[str],
    *,
    subject: str,
    email_body: str,
    sms_body: str,
    email_template_name: str,
    sms_template_name: str,
) -> None:
    send_sms_fn = None
    try:
        # Twilio client initialization is import-time in twilio_service.
        # Keep SMS delivery best-effort without failing callers if misconfigured.
        from app.services.twilio_service import send_sms as send_sms_fn
    except Exception:
        send_sms_fn = None

    for email in sorted(emails):
        try:
            await send_email(
                db=db,
                tenant_id=str(tenant_id),
                to=email,
                subject=subject,
                body=email_body,
                template_name=email_template_name,
            )
        except Exception:
            pass

    if send_sms_fn:
        for phone in sorted(phones):
            try:
                await send_sms_fn(
                    db=db,
                    tenant_id=str(tenant_id),
                    to=phone,
                    body=sms_body,
                    template_name=sms_template_name,
                )
            except Exception:
                pass


async def send_pending_zelle_submission_alert(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    order_id: UUID,
    order_number: str,
    invoice_number: str,
    customer_name: str,
    amount: Decimal,
    source_label: str,
    sender_email: Optional[str],
    sender_phone: Optional[str],
) -> None:
    emails, phones = await collect_staff_contacts(db, tenant_id)
    if not emails and not phones:
        return

    sender_parts = []
    if sender_email:
        sender_parts.append(f"email: {sender_email}")
    if sender_phone:
        sender_parts.append(f"phone: {sender_phone}")
    sender_line = ", ".join(sender_parts) if sender_parts else "not provided"
    sender_sms = "; ".join(sender_parts) if sender_parts else "not provided"
    staff_url = _staff_order_url(order_id)

    subject = f"New Zelle submit: Invoice #{invoice_number} awaiting confirmation"
    email_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 640px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #b45309;">Zelle Payment Submitted</h2>
        <p>A customer marked a Zelle payment as submitted and this invoice now needs confirmation.</p>
        <div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 8px; padding: 16px; margin: 16px 0;">
            <p style="margin: 0 0 8px 0;"><strong>Invoice:</strong> {invoice_number}</p>
            <p style="margin: 0 0 8px 0;"><strong>Order:</strong> {order_number}</p>
            <p style="margin: 0 0 8px 0;"><strong>Customer:</strong> {customer_name}</p>
            <p style="margin: 0 0 8px 0;"><strong>Amount:</strong> ${amount:,.2f}</p>
            <p style="margin: 0 0 8px 0;"><strong>Source:</strong> {source_label}</p>
            <p style="margin: 0;"><strong>Sender info:</strong> {sender_line}</p>
        </div>
        <p style="margin: 24px 0;">
            <a href="{staff_url}" style="background: #b45309; color: #fff; text-decoration: none; padding: 10px 16px; border-radius: 6px;">
                Open Repair Order
            </a>
        </p>
    </body>
    </html>
    """
    sms_body = (
        f"Zelle submit: Invoice #{invoice_number} (${amount:,.2f}) from {source_label}. "
        f"Order {order_number}, customer {customer_name}, sender {sender_sms}. {staff_url}"
    )

    await _send_staff_alert(
        db,
        tenant_id,
        emails,
        phones,
        subject=subject,
        email_body=email_body,
        sms_body=sms_body,
        email_template_name="pending_zelle_staff_submit_email",
        sms_template_name="pending_zelle_staff_submit_sms",
    )


async def send_pending_zelle_reminder_alert(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    order_id: UUID,
    order_number: str,
    invoice_number: str,
    customer_name: str,
    amount: Decimal,
    reminder_stage_hours: int,
) -> None:
    emails, phones = await collect_staff_contacts(db, tenant_id)
    if not emails and not phones:
        return

    staff_url = _staff_order_url(order_id)
    subject = f"Action needed: Zelle payment pending confirmation for Invoice #{invoice_number}"
    email_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 640px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #b45309;">Pending Zelle Confirmation</h2>
        <p>
            Zelle payment for <strong>Invoice #{invoice_number}</strong> has not been confirmed after
            <strong>{reminder_stage_hours} hours</strong>.
        </p>
        <div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 8px; padding: 16px; margin: 16px 0;">
            <p style="margin: 0 0 8px 0;"><strong>Order:</strong> {order_number}</p>
            <p style="margin: 0 0 8px 0;"><strong>Customer:</strong> {customer_name}</p>
            <p style="margin: 0;"><strong>Amount:</strong> ${amount:,.2f}</p>
        </div>
        <p>
            Did you receive this Zelle payment? Confirm it in Repair Orders, follow up with the customer, or clear
            pending status if needed.
        </p>
        <p style="margin: 24px 0;">
            <a href="{staff_url}" style="background: #b45309; color: #fff; text-decoration: none; padding: 10px 16px; border-radius: 6px;">
                Open Repair Order
            </a>
        </p>
    </body>
    </html>
    """
    sms_body = (
        f"Zelle pending {reminder_stage_hours}h: Invoice #{invoice_number} "
        f"(${amount:,.2f}) not confirmed. Check RO {order_number}: {staff_url}"
    )

    await _send_staff_alert(
        db,
        tenant_id,
        emails,
        phones,
        subject=subject,
        email_body=email_body,
        sms_body=sms_body,
        email_template_name="pending_zelle_staff_reminder_email",
        sms_template_name="pending_zelle_staff_reminder_sms",
    )
