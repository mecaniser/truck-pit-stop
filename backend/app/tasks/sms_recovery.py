"""Bounded durable SMS recovery; registration and execution are rollout gated."""
from __future__ import annotations
import asyncio
import time
from uuid import UUID, uuid4
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.db.session import AsyncSessionLocal
from app.services.communications_service import get_sms_sender, process_pending_operations
from app.tasks import celery_app
from app.tasks.async_runtime import run_async

logger = get_logger(__name__)
LOCK_KEY = 'sms-recovery:worker-lock:v1'
RELEASE_LOCK = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


def configured_tenants():
    try:
        tenants = sorted({UUID(value.strip()) for value in settings.SMS_RECOVERY_TENANT_IDS.split(',') if value.strip()}, key=str)
    except ValueError:
        raise RuntimeError('SMS recovery tenant allowlist is invalid') from None
    if settings.ENVIRONMENT == 'production' and not tenants:
        raise RuntimeError('Production SMS recovery requires an explicit tenant allowlist')
    return tenants or [None]


async def recover_sms():
    if not settings.SMS_RECOVERY_ENABLED:
        return {'status': 'disabled', 'batches': 0}
    tenants = configured_tenants()
    sender = get_sms_sender()
    if settings.ENVIRONMENT == 'production' and sender.mode != 'live':
        raise RuntimeError('Production SMS recovery requires the live provider adapter')
    if not getattr(sender, 'ready', False):
        raise RuntimeError('SMS recovery provider credentials are unavailable')
    redis = await get_redis()
    token = str(uuid4())
    # Redis suppresses overlapping work. Durable database claims, not this
    # expiring lease, guarantee that an SMS is never dispatched twice.
    if not await redis.set(LOCK_KEY, token, nx=True, ex=110):
        return {'status': 'busy', 'batches': 0}
    started = time.monotonic()
    counters = {'batches': 0}
    try:
        from app.services.automated_sms_service import process_pending_automated_operations
        async def batch(processor, tenant_id):
            remaining = settings.SMS_RECOVERY_BUDGET_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                return False
            async with AsyncSessionLocal() as db:
                result = await asyncio.wait_for(processor(db, sender, limit=settings.SMS_RECOVERY_BATCH_SIZE, tenant_id=tenant_id), timeout=remaining)
            counters['batches'] += 1
            for key, value in (result or {}).items():
                if isinstance(value, int):
                    counters[key] = counters.get(key, 0) + value
            return True
        # Alternate priority each minute so a busy queue cannot indefinitely
        # starve the other type when provider calls consume the wall-clock budget.
        processors = [process_pending_operations, process_pending_automated_operations]
        tick = int(time.time() // 60)
        # Change queue priority once per complete tenant rotation. Using the
        # same parity for both would starve one queue with an even tenant count.
        if (tick // len(tenants)) % 2:
            processors.reverse()
        # Rotate allowlist order for the same fairness property across shops.
        offset = tick % len(tenants)
        for tenant_id in tenants[offset:] + tenants[:offset]:
            for processor in processors:
                if not await batch(processor, tenant_id):
                    logger.warning('sms_recovery_budget_exhausted', **counters)
                    return {'status': 'budget_exhausted', **counters}
        logger.info('sms_recovery_completed', **counters, elapsed_ms=round((time.monotonic()-started)*1000))
        return {'status': 'completed', **counters}
    except asyncio.TimeoutError:
        # Interrupted dispatch remains dispatching; a later tick marks it
        # unknown after its stale deadline. It is NEVER reclaimed for sending.
        logger.warning('sms_recovery_budget_exhausted', **counters)
        return {'status': 'budget_exhausted', **counters}
    except Exception:
        logger.error('sms_recovery_failed', **counters)
        raise  # infrastructure failure must remain a failed task
    finally:
        await redis.eval(RELEASE_LOCK, 1, LOCK_KEY, token)


@celery_app.task(name='process_sms_recovery', acks_late=True, reject_on_worker_lost=True, soft_time_limit=70, time_limit=90)
def process_sms_recovery():
    return run_async(recover_sms())
