from app.tasks import celery_app
from app.services.email_service import send_email
from app.services.automated_sms_service import enqueue_automated_sms
from app.tasks.async_runtime import run_async
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


async def _enqueue_notification_sms(tenant_id, to, body, template_name, *, domain_event_id,
                                    customer_id=None, recipient_user_id=None):
    if not domain_event_id or not template_name or not (customer_id or recipient_user_id):
        raise ValueError("Automated SMS requires a stable event, template and recipient identity")
    async with AsyncSessionLocal() as db:
        operation = await enqueue_automated_sms(
            db, tenant_id=tenant_id, to=to, body=body, template_name=template_name,
            domain_event_id=domain_event_id, customer_id=customer_id,
            recipient_user_id=recipient_user_id,
        )
        await db.commit()
        return {"operation_id": str(operation.id), "status": operation.state}


@celery_app.task
def send_notification_sms(tenant_id: str, to: str, body: str, template_name: str = None,
                          *, domain_event_id: str = None, customer_id: str = None,
                          recipient_user_id: str = None):
    """Queue a caller-identified business event; legacy unidentified tasks fail closed."""
    return run_async(_enqueue_notification_sms(
        tenant_id, to, body, template_name, domain_event_id=domain_event_id,
        customer_id=customer_id, recipient_user_id=recipient_user_id,
    ))
