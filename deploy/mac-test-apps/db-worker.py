"""Isolated Celery worker adapter: no Beat, no production queues or task imports."""
import asyncio
import json
from pathlib import Path
import time
from celery import Celery
from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.core.config import settings
from app.db.session import AsyncSessionLocal

url = make_url(settings.DATABASE_URL)
if (settings.ENVIRONMENT, url.host, url.database) != ('staging', 'postgres', 'dieselbridge_local_test'):
    raise RuntimeError('Local worker database boundary refused')
if settings.REDIS_URL != 'redis://redis:6379/13':
    raise RuntimeError('Local worker queue boundary refused')
# Same Celery engine used by the app, with a dedicated allowlisted task registry.
# Production task modules/Beat schedules are deliberately not imported.
from app.tasks import celery_app
# Retain the app's schema startup gate; remove all production task imports.
celery_app.conf.update(imports=(), task_default_queue='db-local-test', accept_content=['json'],
                       task_serializer='json', result_serializer='json',
                       worker_prefetch_multiplier=1, task_acks_late=True,
                       beat_schedule={}, task_reject_on_worker_lost=True)


async def record_probe(key):
    if key != 'synthetic-db-probe-v1':
        raise ValueError('Unknown synthetic job')
    async with AsyncSessionLocal() as db:
        # The synthetic table is created by the explicit setup script, never by a worker.
        await db.execute(text('INSERT INTO local_test_receipts (job_key, execution_count) VALUES (:key, 1) ON CONFLICT (job_key) DO NOTHING'), {'key': key})
        count = await db.scalar(text('SELECT count(*) FROM customers'))
        executions = await db.scalar(text('SELECT execution_count FROM local_test_receipts WHERE job_key=:key'), {'key': key})
        await db.commit()
    return {'job_key': key, 'customers': count, 'execution_count': executions, 'synthetic': True}


@celery_app.task(name='localtest.database_probe')
def database_probe(key):
    # A fresh loop-scoped SQLAlchemy pool must not be reused across async runs.
    async def execute():
        from app.db.session import engine
        try:
            return await record_probe(key)
        finally:
            await engine.dispose()
    return asyncio.run(execute())
