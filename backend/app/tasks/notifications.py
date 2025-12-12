from app.tasks import celery_app
from app.services.email_service import send_email
from app.services.twilio_service import send_sms
from app.db.session import AsyncSessionLocal


@celery_app.task
async def send_notification_email(
    tenant_id: str,
    to: str,
    subject: str,
    body: str,
    template_name: str = None,
):
    """Celery task to send email notification"""
    async with AsyncSessionLocal() as db:
        await send_email(db, tenant_id, to, subject, body, template_name)


@celery_app.task
async def send_notification_sms(
    tenant_id: str,
    to: str,
    body: str,
    template_name: str = None,
):
    """Celery task to send SMS notification"""
    async with AsyncSessionLocal() as db:
        await send_sms(db, tenant_id, to, body, template_name)


