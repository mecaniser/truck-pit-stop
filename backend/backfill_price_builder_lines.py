#!/usr/bin/env python3
"""
Backfill script for Price Builder migration.

Converts legacy `internal_notes.selected_services` into structured labor lines.
Idempotent: safe to run multiple times.
"""

import asyncio
import json
import os
import sys
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

sys.path.insert(0, ".")

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.db.models.repair_order import RepairOrder, RepairOrderStatus  # noqa: E402
from app.db.models.labor import Labor, LaborLineType  # noqa: E402
from app.services.pricing import get_selected_services_total  # noqa: E402


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _parse_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except Exception:
        return None


def _should_preserve_finalized_totals(env_name: str, status: RepairOrderStatus) -> bool:
    if env_name == "development":
        return False
    return status in {RepairOrderStatus.INVOICED, RepairOrderStatus.PAID}


async def run_backfill(batch_size: int = 200) -> None:
    env_name = os.getenv("ENVIRONMENT", "development")
    migrated_orders = 0
    created_lines = 0
    skipped_preserve = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(RepairOrder.id))
        order_ids = [row[0] for row in result.fetchall()]
        total = len(order_ids)
        print(f"Starting price-builder backfill for {total} repair orders (env={env_name})")

        for i in range(0, total, batch_size):
            chunk = order_ids[i : i + batch_size]
            result = await db.execute(
                select(RepairOrder)
                .where(RepairOrder.id.in_(chunk))
                .options(
                    selectinload(RepairOrder.labor_items),
                    selectinload(RepairOrder.parts_usage),
                )
            )
            orders = result.scalars().all()

            for order in orders:
                notes = order.internal_notes
                selected_services: list[dict] = []
                parsed: dict[str, Any] | None = None

                if notes:
                    try:
                        parsed = json.loads(notes)
                        if isinstance(parsed, dict):
                            raw = parsed.get("selected_services", [])
                            if isinstance(raw, list):
                                selected_services = [svc for svc in raw if isinstance(svc, dict)]
                    except Exception:
                        parsed = None

                if selected_services:
                    for svc in selected_services:
                        svc_name = str(svc.get("name") or "Service")
                        svc_price = _to_decimal(svc.get("base_price", "0"))
                        source_service_id = _parse_uuid(svc.get("id"))

                        exists = any(
                            li.line_type == LaborLineType.FLAT_SERVICE
                            and (
                                (source_service_id and li.source_service_id == source_service_id)
                                or (
                                    not source_service_id
                                    and li.description == svc_name
                                    and Decimal(str(li.hourly_rate)) == svc_price
                                    and Decimal(str(li.hours)) == Decimal("1")
                                )
                            )
                            for li in order.labor_items
                        )
                        if exists:
                            continue

                        db.add(
                            Labor(
                                tenant_id=order.tenant_id,
                                repair_order_id=order.id,
                                service_code=None,
                                description=svc_name,
                                hours=Decimal("1.00"),
                                hourly_rate=svc_price,
                                total_cost=svc_price,
                                line_type=LaborLineType.FLAT_SERVICE,
                                provider=None,
                                provider_operation_id=None,
                                auto_recalc_enabled=True,
                                source_service_id=source_service_id,
                            )
                        )
                        created_lines += 1

                    # Preserve non-pricing notes by removing selected_services only.
                    if isinstance(parsed, dict) and "selected_services" in parsed:
                        parsed.pop("selected_services", None)
                        order.internal_notes = json.dumps(parsed) if parsed else None

                # Recompute totals unless production finalized records should be preserved.
                if _should_preserve_finalized_totals(env_name, order.status):
                    skipped_preserve += 1
                else:
                    parts_total = sum(_to_decimal(pu.total_price) for pu in order.parts_usage)
                    labor_total = sum(_to_decimal(li.total_cost) for li in order.labor_items)
                    if labor_total <= Decimal("0.00"):
                        labor_total = get_selected_services_total(order.internal_notes)
                    order.total_parts_cost = parts_total
                    order.total_labor_cost = labor_total
                    order.total_cost = parts_total + labor_total

                migrated_orders += 1

            await db.commit()
            print(
                f"Processed {min(i + batch_size, total)}/{total} "
                f"(migrated={migrated_orders}, created_lines={created_lines})"
            )

    print("Backfill completed")
    print(f"Orders processed: {migrated_orders}")
    print(f"Labor lines created: {created_lines}")
    print(f"Finalized totals preserved: {skipped_preserve}")


if __name__ == "__main__":
    asyncio.run(run_backfill())
