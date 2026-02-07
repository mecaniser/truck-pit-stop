from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "truck_pit_stop",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Beat schedule for periodic tasks
    beat_schedule={
        "process-invoice-reminders-daily": {
            "task": "process_invoice_reminders",
            "schedule": crontab(hour=9, minute=0),  # Run daily at 9 AM UTC
        },
    },
)

# Import tasks to register them
celery_app.autodiscover_tasks(["app.tasks"])


