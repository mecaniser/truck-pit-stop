"""Run the idempotent DB-048 settlement baseline for one tenant."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from uuid import UUID

from app.db.session import AsyncSessionLocal
from app.services.invoice_settlement_backfill import backfill_tenant_invoice_settlements


async def _run(tenant_id: UUID, cutoff_at: datetime, batch_size: int) -> None:
    async with AsyncSessionLocal() as db:
        run = await backfill_tenant_invoice_settlements(
            db,
            tenant_id=tenant_id,
            cutoff_at=cutoff_at,
            batch_size=batch_size,
        )
        await db.commit()
        print({
            "run_id": str(run.id),
            "state": run.state,
            "source_counts": run.source_counts,
            "inserted_counts": run.inserted_counts,
            "source_checksums": run.source_checksums,
        })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", type=UUID, required=True)
    parser.add_argument("--cutoff-at", default=datetime.now(timezone.utc).isoformat())
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    cutoff = datetime.fromisoformat(args.cutoff_at.replace("Z", "+00:00"))
    asyncio.run(_run(args.tenant_id, cutoff, args.batch_size))


if __name__ == "__main__":
    main()
