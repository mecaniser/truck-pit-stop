from datetime import timedelta

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
        "app.tasks.fleet_inspection_compliance",
        "app.tasks.description_library_refresh",
        "app.tasks.provider_outbox",
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
        "process-fleet-inspection-compliance-weekly": {
            "task": "process_fleet_inspection_compliance",
            "schedule": crontab(hour=8, minute=0, day_of_week=1),  # Mondays 8 AM UTC
        },
        "process-description-library-refresh-weekly": {
            "task": "process_description_library_refresh",
            "schedule": crontab(hour=6, minute=0, day_of_week=1),  # Mondays 6 AM UTC
        },
        "process-provider-outbox": {
            "task": "process_provider_outbox",
            "schedule": timedelta(seconds=10),
        },
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)

# Import tasks to register them
celery_app.autodiscover_tasks(["app.tasks"])
