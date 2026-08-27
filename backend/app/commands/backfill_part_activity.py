"""CLI for bounded, idempotent DB-045 Activity backfill/reconciliation."""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from uuid import UUID

from app.services.part_activity_backfill import run_activity_backfill


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=UUID)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    return parser


async def _main() -> None:
    args = _parser().parse_args()
    results = await run_activity_backfill(
        tenant_id=args.tenant_id, batch_size=args.batch_size,
        dry_run=args.dry_run, verify_only=args.verify_only,
    )
    print(json.dumps([asdict(result) for result in results], default=str, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
