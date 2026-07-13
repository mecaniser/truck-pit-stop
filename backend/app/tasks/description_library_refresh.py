"""Weekly refresh of every tenant's AI-canonicalized suggestion libraries.

Repair-order descriptions, service names, and inventory part names/categories
are all cleaned up by an offline Claude call into a canonical library the
autocomplete endpoints query (see app/services/description_library_service.py).
An owner/admin can trigger a refresh manually at any time from the UI, but new
services/parts/repair orders accumulate through the week — this keeps the
libraries from going stale even if nobody remembers to click refresh.

Schedule: weekly. Skips tenants that have never generated a library before
(regeneration is opt-in — a tenant who's never clicked "refresh" once
shouldn't start incurring API cost automatically).
"""
import asyncio
import logging

from sqlalchemy import select, distinct

from app.tasks import celery_app
from app.db.session import AsyncSessionLocal
from app.db.models.description_library import DescriptionLibraryEntry
from app.services.description_library_service import regenerate_all_libraries

logger = logging.getLogger(__name__)


async def _tenants_with_existing_libraries(db) -> list:
    """Only refresh tenants who have opted in by generating at least one
    library before — a tenant who's never clicked "refresh" shouldn't start
    incurring API cost from a background job they don't know exists.
    """
    result = await db.execute(select(distinct(DescriptionLibraryEntry.tenant_id)))
    return [row[0] for row in result.all()]


async def _process_description_library_refresh() -> dict:
    async with AsyncSessionLocal() as db:
        tenant_ids = await _tenants_with_existing_libraries(db)

    results = {}
    for tenant_id in tenant_ids:
        # Fresh session per tenant so one tenant's failure/rollback can't
        # affect another's in-flight work.
        async with AsyncSessionLocal() as db:
            try:
                results[str(tenant_id)] = await regenerate_all_libraries(db, tenant_id)
            except Exception:
                logger.exception(
                    "description_library_weekly_refresh_failed",
                    extra={"tenant_id": str(tenant_id)},
                )
                results[str(tenant_id)] = None
    return results


@celery_app.task(name="process_description_library_refresh")
def process_description_library_refresh():
    """Celery task wrapper — runs the async refresh logic."""
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(_process_description_library_refresh())
        return {"status": "success", "tenants_refreshed": len(results), "results": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}
