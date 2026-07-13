"""Offline AI canonicalization of a tenant's messy historical text into a
clean suggestion library.

Four sources feed the same table (DescriptionLibraryEntry, distinguished by
library_type): repair-order descriptions, service names, inventory part
names, and inventory categories. Raw values are messy — typos ("Replce fuel
filter"), compound multi-entry strings ("1. Replace fuel filter housing;
2. computer diagnostic"), near-duplicate phrasing. This periodically sends a
tenant's distinct values to Claude, which splits/cleans/dedupes them into a
canonical library that the fast pg_trgm-backed suggestion endpoints query
instead of raw history.
"""
import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional

import anthropic
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.repair_order import RepairOrder
from app.db.models.service import Service
from app.db.models.inventory import Inventory
from app.db.models.description_library import DescriptionLibraryEntry

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-8"
MAX_SOURCE_VALUES = 2000  # guard against pathological tenants; most shops have far fewer distinct strings

LIBRARY_TYPE_RO_DESCRIPTION = "ro_description"
LIBRARY_TYPE_SERVICE_NAME = "service_name"
LIBRARY_TYPE_PART_NAME = "part_name"
LIBRARY_TYPE_PART_CATEGORY = "part_category"
LIBRARY_TYPE_PART_DESCRIPTION = "part_description"


class _CanonicalEntry(BaseModel):
    text: str = Field(description="A single, clean, correctly-spelled canonical value")
    category: Optional[str] = Field(default=None, description="Short category label, e.g. 'Brakes', 'Engine', 'Electrical'")
    source_line_numbers: List[int] = Field(
        description="The numbered source line(s) this canonical entry was derived from. "
        "Include every source line that maps to this entry (e.g. near-duplicates merged into it)."
    )


class _CanonicalLibrary(BaseModel):
    descriptions: List[_CanonicalEntry]


def _output_schema() -> dict:
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "descriptions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "category": {"type": ["string", "null"]},
                            "source_line_numbers": {"type": "array", "items": {"type": "integer"}},
                        },
                        "required": ["text", "category", "source_line_numbers"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["descriptions"],
            "additionalProperties": False,
        },
    }


RO_DESCRIPTION_SYSTEM_PROMPT = """You clean up a truck repair shop's historical work-order descriptions into a canonical library of clear, correctly-named service descriptions.

You will receive a numbered list of raw, real-world text a shop typed into repair order "work performed" fields. This text is often messy: typos, abbreviations, and compound entries listing multiple unrelated services in one string (e.g. numbered lists, semicolon-separated).

For each input line:
1. Split compound/multi-service entries into separate canonical descriptions, one per distinct service.
2. Fix typos and normalize phrasing into how a mechanic would properly name the service (e.g. "Replce fuel filter housing" -> "Replace fuel filter housing").
3. Merge near-duplicate phrasings that describe the same service into a single canonical entry.
4. Keep each output description short and specific — a phrase a mechanic would pick from a dropdown, not a sentence.
5. Discard entries that are not real service descriptions (blank, placeholder, or garbage text).

For every canonical entry you produce, list the source line number(s) (from the numbered input) it was derived from in source_line_numbers — including every near-duplicate line merged into it. A line that gets split into multiple services should have its number listed under each resulting entry.

Return the full deduped canonical library as structured output."""

SERVICE_NAME_SYSTEM_PROMPT = """You clean up a truck repair shop's catalog of bookable service names into a canonical library of short, clear service names.

You will receive a numbered list of raw service names this shop has used. This text may have typos, inconsistent capitalization, or near-duplicate phrasing for the same service.

For each input line:
1. Fix typos and normalize phrasing into how a mechanic would properly name the service.
2. Merge near-duplicate phrasings that describe the same service into a single canonical entry.
3. Keep each output name short — a catalog label (e.g. "Replace Fuel Filter"), not a sentence.
4. Do NOT split a service name into multiple entries — each input line is already one service.
5. Discard entries that are not real service names (blank, placeholder, or garbage text).

For every canonical entry you produce, list the source line number(s) it was derived from in source_line_numbers, including every near-duplicate merged into it.

Return the full deduped canonical library as structured output."""

PART_NAME_SYSTEM_PROMPT = """You clean up a truck repair shop's inventory of part names into a canonical library of short, clear part names.

You will receive a numbered list of raw part names this shop has used for stocked inventory items. This text may have typos, abbreviations, or near-duplicate phrasing for the same part.

For each input line:
1. Fix typos and normalize phrasing into a clear, specific part name a mechanic would recognize (e.g. "Brk Pad Frt" -> "Brake Pads - Front").
2. Merge near-duplicate phrasings that describe the same part into a single canonical entry.
3. Keep each output name short — a catalog label, not a sentence.
4. Do NOT split a part name into multiple entries — each input line is already one part.
5. Discard entries that are not real part names (blank, placeholder, or garbage text).

For every canonical entry you produce, list the source line number(s) it was derived from in source_line_numbers, including every near-duplicate merged into it.

Return the full deduped canonical library as structured output."""

PART_CATEGORY_SYSTEM_PROMPT = """You clean up a truck repair shop's inventory category labels into a canonical, deduped set of category names.

You will receive a numbered list of raw category labels this shop has used to organize stocked parts (e.g. "Brakes", "brake", "BRK", "Filters", "filter"). This text may have typos, inconsistent capitalization, abbreviations, or near-duplicate labels for the same category.

For each input line:
1. Fix typos and normalize into a short, proper-case category name (e.g. "brk" -> "Brakes").
2. Merge near-duplicate or abbreviated labels that mean the same category into a single canonical entry.
3. Keep each output name a single short category word or short phrase — not a sentence, not a specific part.
4. Discard entries that are not real category labels (blank, placeholder, or garbage text).

For every canonical entry you produce, list the source line number(s) it was derived from in source_line_numbers, including every near-duplicate merged into it. Leave "category" null for every entry — these entries ARE the categories.

Return the full deduped canonical library as structured output."""

PART_DESCRIPTION_SYSTEM_PROMPT = """You clean up a truck repair shop's inventory part descriptions into a canonical library of clear, correctly-worded descriptions.

You will receive a numbered list of raw part description text this shop has entered for stocked inventory items (e.g. fitment notes, spec details, or short blurbs about a part). This text may have typos or near-duplicate phrasing for the same description.

For each input line:
1. Fix typos and normalize phrasing into a clear description a mechanic or parts clerk would write.
2. Merge near-duplicate phrasings that describe the same thing into a single canonical entry.
3. Keep each output description short and specific — a phrase, not a paragraph.
4. Discard entries that are not real descriptions (blank, placeholder, or garbage text).

For every canonical entry you produce, list the source line number(s) it was derived from in source_line_numbers, including every near-duplicate merged into it.

Return the full deduped canonical library as structured output."""


async def _regenerate_library(
    db: AsyncSession,
    tenant_id,
    library_type: str,
    system_prompt: str,
    fetch_source_rows: Callable,
) -> int:
    """Shared canonicalization pipeline: fetch distinct (value, count) rows via
    fetch_source_rows, send them to Claude, replace this tenant's rows for
    this library_type. Raises RuntimeError if ANTHROPIC_API_KEY is unset.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    rows = await fetch_source_rows(db, tenant_id)
    if not rows:
        return 0

    # Number each source line so the model can report which line(s) each
    # canonical entry came from — its rewritten text rarely matches the raw
    # string verbatim, so we can't recover usage counts by string lookup.
    count_by_line_number = {i: count for i, (_val, count) in enumerate(rows, start=1)}
    raw_lines = "\n".join(f"{i}. {val}" for i, (val, _count) in enumerate(rows, start=1))

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    with client.messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=system_prompt,
        output_config={"format": _output_schema(), "effort": "medium"},
        messages=[
            {
                "role": "user",
                "content": f"Here are {len(rows)} distinct historical values from this shop:\n\n{raw_lines}",
            }
        ],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to process this shop's history")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("History too large to process in one batch — output was truncated")

    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        raise RuntimeError("No structured output returned")

    library = _CanonicalLibrary.model_validate_json(text_block.text)

    now = datetime.now(timezone.utc)
    await db.execute(
        delete(DescriptionLibraryEntry).where(
            DescriptionLibraryEntry.tenant_id == tenant_id,
            DescriptionLibraryEntry.library_type == library_type,
        )
    )

    seen = set()
    written = 0
    for entry in library.descriptions:
        clean_text = entry.text.strip()
        if not clean_text or clean_text.lower() in seen:
            continue
        seen.add(clean_text.lower())
        source_count = sum(count_by_line_number.get(n, 0) for n in entry.source_line_numbers) or 1
        db.add(
            DescriptionLibraryEntry(
                tenant_id=tenant_id,
                library_type=library_type,
                canonical_text=clean_text,
                category=entry.category,
                source_count=source_count,
                last_regenerated_at=now,
            )
        )
        written += 1

    await db.commit()
    logger.info(
        "description_library_regenerated",
        extra={"tenant_id": str(tenant_id), "library_type": library_type, "entries": written},
    )
    return written


async def _fetch_ro_descriptions(db: AsyncSession, tenant_id):
    result = await db.execute(
        select(RepairOrder.description, func.count(RepairOrder.id).label("count"))
        .where(
            RepairOrder.tenant_id == tenant_id,
            RepairOrder.description.isnot(None),
            RepairOrder.description != "",
        )
        .group_by(RepairOrder.description)
        .order_by(func.count(RepairOrder.id).desc())
        .limit(MAX_SOURCE_VALUES)
    )
    return result.all()


async def _fetch_service_names(db: AsyncSession, tenant_id):
    result = await db.execute(
        select(Service.name, func.count(Service.id).label("count"))
        .where(Service.tenant_id == tenant_id, Service.name.isnot(None), Service.name != "")
        .group_by(Service.name)
        .order_by(func.count(Service.id).desc())
        .limit(MAX_SOURCE_VALUES)
    )
    return result.all()


async def _fetch_part_names(db: AsyncSession, tenant_id):
    result = await db.execute(
        select(Inventory.name, func.count(Inventory.id).label("count"))
        .where(Inventory.tenant_id == tenant_id, Inventory.name.isnot(None), Inventory.name != "")
        .group_by(Inventory.name)
        .order_by(func.count(Inventory.id).desc())
        .limit(MAX_SOURCE_VALUES)
    )
    return result.all()


async def _fetch_part_categories(db: AsyncSession, tenant_id):
    result = await db.execute(
        select(Inventory.category, func.count(Inventory.id).label("count"))
        .where(Inventory.tenant_id == tenant_id, Inventory.category.isnot(None), Inventory.category != "")
        .group_by(Inventory.category)
        .order_by(func.count(Inventory.id).desc())
        .limit(MAX_SOURCE_VALUES)
    )
    return result.all()


async def _fetch_part_descriptions(db: AsyncSession, tenant_id):
    result = await db.execute(
        select(Inventory.description, func.count(Inventory.id).label("count"))
        .where(Inventory.tenant_id == tenant_id, Inventory.description.isnot(None), Inventory.description != "")
        .group_by(Inventory.description)
        .order_by(func.count(Inventory.id).desc())
        .limit(MAX_SOURCE_VALUES)
    )
    return result.all()


async def regenerate_description_library(db: AsyncSession, tenant_id) -> int:
    """Rebuild a tenant's canonical RO-description library from raw RO history."""
    return await _regenerate_library(
        db, tenant_id, LIBRARY_TYPE_RO_DESCRIPTION, RO_DESCRIPTION_SYSTEM_PROMPT, _fetch_ro_descriptions
    )


async def regenerate_service_name_library(db: AsyncSession, tenant_id) -> int:
    """Rebuild a tenant's canonical service-name library from the Services catalog."""
    return await _regenerate_library(
        db, tenant_id, LIBRARY_TYPE_SERVICE_NAME, SERVICE_NAME_SYSTEM_PROMPT, _fetch_service_names
    )


async def regenerate_part_name_library(db: AsyncSession, tenant_id) -> int:
    """Rebuild a tenant's canonical part-name library from Inventory."""
    return await _regenerate_library(
        db, tenant_id, LIBRARY_TYPE_PART_NAME, PART_NAME_SYSTEM_PROMPT, _fetch_part_names
    )


async def regenerate_part_category_library(db: AsyncSession, tenant_id) -> int:
    """Rebuild a tenant's canonical part-category library from Inventory."""
    return await _regenerate_library(
        db, tenant_id, LIBRARY_TYPE_PART_CATEGORY, PART_CATEGORY_SYSTEM_PROMPT, _fetch_part_categories
    )


async def regenerate_part_description_library(db: AsyncSession, tenant_id) -> int:
    """Rebuild a tenant's canonical part-description library from Inventory."""
    return await _regenerate_library(
        db, tenant_id, LIBRARY_TYPE_PART_DESCRIPTION, PART_DESCRIPTION_SYSTEM_PROMPT, _fetch_part_descriptions
    )


async def regenerate_all_libraries(db: AsyncSession, tenant_id) -> dict:
    """Rebuild every canonical library for a tenant — used by the weekly
    scheduled refresh and available for an "all at once" manual trigger.
    Returns counts per library_type; a failure in one library is caught and
    rolled back so it can't leave the shared session dirty for the next one.
    """
    results = {}
    for library_type, fn in (
        (LIBRARY_TYPE_RO_DESCRIPTION, regenerate_description_library),
        (LIBRARY_TYPE_SERVICE_NAME, regenerate_service_name_library),
        (LIBRARY_TYPE_PART_NAME, regenerate_part_name_library),
        (LIBRARY_TYPE_PART_CATEGORY, regenerate_part_category_library),
        (LIBRARY_TYPE_PART_DESCRIPTION, regenerate_part_description_library),
    ):
        try:
            results[library_type] = await fn(db, tenant_id)
        except Exception:
            await db.rollback()
            logger.exception(
                "description_library_regeneration_failed",
                extra={"tenant_id": str(tenant_id), "library_type": library_type},
            )
            results[library_type] = None
    return results
