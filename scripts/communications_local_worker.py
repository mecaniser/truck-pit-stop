"""Isolated Celery/Beat entrypoint: same recovery task with simulated delivery only.

Run via communications_local.py exec with this scripts directory on PYTHONPATH.
This module is intentionally outside backend/app and cannot be a production adapter.
"""
from communications_local_app import sender  # Explicit DB/environment guard + Twilio network denial.
from app.core.config import settings
from app.tasks import celery_app
from app.tasks import sms_recovery

settings.SMS_RECOVERY_ENABLED = True
settings.SMS_RECOVERY_TENANT_IDS = '00000000-0000-4000-8000-000000000001'
sms_recovery.get_sms_sender = lambda: sender
# Keep the sandbox dedicated to SMS; no unrelated periodic tasks are published.
celery_app.conf.beat_schedule = {
    'process-sms-recovery': {
        'task': 'process_sms_recovery',
        'schedule': 2.0,
        'options': {'expires': 60, 'queue': 'communications-local-recovery'},
    },
}
celery_app.conf.task_default_queue = 'communications-local-recovery'
