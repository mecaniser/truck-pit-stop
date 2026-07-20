"""Celery entrypoint for durable external-provider delivery."""
from __future__ import annotations

from app.services.provider_outbox_service import process_due_provider_outbox_events
from app.tasks import celery_app
from app.tasks.async_runtime import run_async


@celery_app.task(
    name="process_provider_outbox",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=45,
    time_limit=60,
)
def process_provider_outbox() -> dict[str, int]:
    """Process a small due batch; Celery beat invokes this every ten seconds."""
    return run_async(process_due_provider_outbox_events())
