"""Durable Google Reviews reconciliation and idempotent publish retries."""
from datetime import timedelta
from sqlalchemy import select
from app.db.models.google_review import GoogleBusinessConnection, GoogleReview, GoogleReviewStatus
from app.db.session import AsyncSessionLocal
from app.services.google_reviews_service import publish_reply, sync_connection
from app.tasks import celery_app
from app.tasks.async_runtime import run_async

async def _reconcile():
    async with AsyncSessionLocal() as db:
        connections = (await db.execute(select(GoogleBusinessConnection).where(GoogleBusinessConnection.status == "connected"))).scalars().all()
        processed = 0
        for connection in connections:
            try: processed += await sync_connection(db, connection); await db.commit()
            except Exception as exc: connection.last_sync_error = str(exc)[:500]; await db.commit()
        return {"reviews": processed}

async def _publish_due():
    async with AsyncSessionLocal() as db:
        reviews = (await db.execute(select(GoogleReview).where(GoogleReview.status.in_([GoogleReviewStatus.NEW.value, GoogleReviewStatus.FAILED.value]), GoogleReview.requires_approval.is_(False), GoogleReview.publish_retry_count < 5))).scalars().all()
        processed = 0
        for review in reviews:
            try: await publish_reply(db, tenant_id=review.tenant_id, review=review); processed += 1
            except Exception: pass
            await db.commit()
        return {"published": processed}

@celery_app.task(name="reconcile_google_reviews", acks_late=True)
def reconcile_google_reviews(): return run_async(_reconcile())
@celery_app.task(name="publish_google_review_replies", acks_late=True)
def publish_google_review_replies(): return run_async(_publish_due())
