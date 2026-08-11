from app.tasks import celery_app
import app.tasks.provider_outbox  # noqa: F401 - task decorator performs registration


def test_conversion_worker_task_and_beat_schedule_are_registered():
    assert "process_paid_invoice_webhooks" in celery_app.tasks
    schedule = celery_app.conf.beat_schedule["process-paid-invoice-webhooks"]
    assert schedule["task"] == "process_paid_invoice_webhooks"
    assert "process_conversion_pii_retention" in celery_app.tasks
    retention = celery_app.conf.beat_schedule["process-conversion-pii-retention-daily"]
    assert retention["task"] == "process_conversion_pii_retention"
