"""Celery entrypoints for QuickBooks accounting and payment recovery."""
from app.services.quickbooks_sync_service import (
    backfill_quickbooks_cdc,
    process_quickbooks_invoice_sync_events,
    reconcile_quickbooks_payments,
)
from app.tasks import celery_app
from app.tasks.async_runtime import run_async


@celery_app.task(name="process_quickbooks_invoice_sync", acks_late=True)
def process_quickbooks_invoice_sync() -> dict[str, int]:
    return run_async(process_quickbooks_invoice_sync_events())


@celery_app.task(name="reconcile_quickbooks_payments", acks_late=True)
def reconcile_quickbooks_payments_task() -> dict[str, int]:
    return run_async(reconcile_quickbooks_payments())


@celery_app.task(name="backfill_quickbooks_cdc", acks_late=True)
def backfill_quickbooks_cdc_task() -> dict[str, int]:
    return run_async(backfill_quickbooks_cdc())
