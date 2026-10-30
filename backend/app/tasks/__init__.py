from datetime import timedelta

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_init
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
        "app.tasks.sms_recovery",
        "app.tasks.invoice_reminders",
        "app.tasks.pending_zelle_reminders",
        "app.tasks.mechanic_timer_maintenance",
        "app.tasks.fleet_inspection_compliance",
        "app.tasks.description_library_refresh",
        "app.tasks.provider_outbox",
        "app.tasks.quickbooks_sync",
        "app.tasks.google_reviews",
        "app.tasks.motive",
    ),
    # Beat schedule for periodic tasks
    beat_schedule={
        "reconcile-motive": {"task": "reconcile_motive", "schedule": timedelta(minutes=5)},
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
        "process-fleet-financial-wakeups": {
            "task": "process_fleet_financial_wakeups",
            "schedule": timedelta(seconds=10),
        },
        "process-provider-outbox": {
            "task": "process_provider_outbox",
            "schedule": timedelta(seconds=10),
        },
        "process-db048-financial-outbox": {
            "task": "process_db048_financial_outbox",
            "schedule": timedelta(seconds=10),
        },
        "process-db048-settlement-maintenance": {
            "task": "process_db048_settlement_maintenance",
            "schedule": timedelta(minutes=1),
        },
        "capture-shop-history": {"task": "capture_shop_history", "schedule": timedelta(minutes=5)},
        "process-shop-history-webhooks": {
            "task": "process_shop_history_webhooks",
            "schedule": timedelta(seconds=10),
            "options": {"expires": 10},
        },
        "process-paid-invoice-webhooks": {
            "task": "process_paid_invoice_webhooks",
            "schedule": timedelta(seconds=10),
        },
        "purge-callrail-media-cache": {"task": "purge_callrail_media_cache", "schedule": crontab(hour=3, minute=10)},
        "process-conversion-pii-retention-daily": {
            "task": "process_conversion_pii_retention",
            "schedule": crontab(hour=3, minute=15),
        },
        "process-quickbooks-invoice-sync": {
            "task": "process_quickbooks_invoice_sync",
            "schedule": timedelta(seconds=30),
        },
        "reconcile-quickbooks-payments": {
            "task": "reconcile_quickbooks_payments",
            "schedule": crontab(hour=4, minute=30),
        },
        "backfill-quickbooks-cdc": {
            "task": "backfill_quickbooks_cdc",
            "schedule": crontab(hour=5, minute=0),
        },
        "reconcile-google-reviews": {"task": "reconcile_google_reviews", "schedule": crontab(minute="*/15")},
        "publish-google-review-replies": {"task": "publish_google_review_replies", "schedule": timedelta(minutes=1)},
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)

# Register no recovery cadence until explicitly enabled. The task rechecks this
# switch too, so a stale Beat/broker message cannot bypass a rollout pause.
if settings.SMS_RECOVERY_ENABLED:
    celery_app.conf.beat_schedule["process-sms-recovery"] = {
        "task": "process_sms_recovery",
        "schedule": timedelta(seconds=60),
        "options": {"expires": 60},
    }

# Import tasks to register them
celery_app.autodiscover_tasks(["app.tasks"])


def _require_worker_schema(sender=None, **kwargs):
    """Block only this worker lifecycle, never Web task imports."""
    if getattr(sender, "app", None) is not celery_app:
        return
    try:
        from app.commands.worker_schema_readiness import wait_for_worker_schema

        wait_for_worker_schema(settings.DATABASE_URL)
    except Exception:
        # Ordinary receiver exceptions are swallowed by Celery's signal
        # dispatcher. Unexpected gate failures must also stop worker startup.
        import logging

        logging.getLogger(__name__).error("Worker schema readiness failed; startup aborted")
        raise SystemExit(78) from None


worker_init.connect(
    _require_worker_schema,
    weak=False,
    dispatch_uid="dieselbridge-worker-schema-readiness",
)
