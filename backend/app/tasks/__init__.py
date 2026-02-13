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
    # Explicitly import task modules so decorators register on worker/beat boot.
    imports=(
        "app.tasks.notifications",
        "app.tasks.invoice_reminders",
        "app.tasks.pending_zelle_reminders",
        "app.tasks.mechanic_timer_maintenance",
    ),
    # Beat schedule for periodic tasks
    beat_schedule={
        "process-invoice-reminders-daily": {
            "task": "process_invoice_reminders",
            "schedule": crontab(hour=9, minute=0),  # Run daily at 9 AM UTC
        },
        "process-pending-zelle-reminders-hourly": {
            "task": "process_pending_zelle_reminders",
            "schedule": crontab(minute=15),  # Run hourly at :15 UTC
        },
        "process-mechanic-timer-maintenance": {
            "task": "process_mechanic_timer_maintenance",
            "schedule": crontab(minute="*/5"),  # Every 5 minutes
        },
    },
)

# Import tasks to register them
celery_app.autodiscover_tasks(["app.tasks"])
