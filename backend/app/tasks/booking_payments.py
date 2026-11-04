"""Bounded reconciliation/expiry; never initiates another charge or a refund."""
from app.tasks import celery_app
from app.tasks.async_runtime import run_async
from app.db.session import AsyncSessionLocal
from app.services.booking_payments import expire_holds,reconcile_live_attempts

async def run_booking_expiry():
    async with AsyncSessionLocal() as db:
        reconciled=await reconcile_live_attempts(db,limit=50)
        expired=await expire_holds(db,limit=100)
        return {"reconciled":reconciled,"expired":expired}

@celery_app.task(name='expire_booking_holds')
def expire_booking_holds():
    return run_async(run_booking_expiry())
