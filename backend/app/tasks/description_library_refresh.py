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
from app.services.description_library_service import (
    regenerate_all_libraries,
    regenerate_description_library,
    regenerate_service_name_library,
    regenerate_part_name_library,
    regenerate_part_category_library,
    regenerate_part_description_library,
)

logger = logging.getLogger(__name__)

# Maps the library group a "Refresh" button represents to the regeneration
# function(s) it runs — lets the on-demand task share this table with
# whichever endpoint enqueues it, instead of hardcoding per-endpoint logic.
_REGENERATE_FNS_BY_GROUP = {
    "ro_description": [regenerate_description_library],
    "service_name": [regenerate_service_name_library],
    "inventory": [regenerate_part_name_library, regenerate_part_category_library, regenerate_part_description_library],
}


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


async def _process_on_demand_regenerate(tenant_id: str, group: str) -> dict:
    fns = _REGENERATE_FNS_BY_GROUP[group]
    async with AsyncSessionLocal() as db:
        counts = {}
        for fn in fns:
            counts[fn.__name__] = await fn(db, tenant_id)
        return counts


@celery_app.task(name="process_on_demand_library_regenerate")
def process_on_demand_library_regenerate(tenant_id: str, group: str):
    """Owner/admin clicked a "Refresh ... suggestions" button. Runs the same
    regeneration logic as the weekly job, but for one tenant and one library
    group (ro_description | service_name | inventory), triggered on demand.
    The HTTP endpoint that enqueues this returns immediately — the button
    doesn't block on a multi-minute Claude call.
    """
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    try:
        counts = loop.run_until_complete(_process_on_demand_regenerate(tenant_id, group))
        logger.info(
            "description_library_on_demand_regenerate_succeeded",
            extra={"tenant_id": tenant_id, "group": group, "counts": counts},
        )
        return {"status": "success", "counts": counts}
    except Exception as e:
        logger.exception(
            "description_library_on_demand_regenerate_failed",
            extra={"tenant_id": tenant_id, "group": group},
        )
        return {"status": "error", "message": str(e)}
