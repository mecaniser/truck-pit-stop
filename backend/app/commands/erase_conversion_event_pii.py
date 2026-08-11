"""Erase conversion-event PII for one tenant/customer privacy request."""
import argparse
import asyncio
from uuid import UUID

from app.db.session import AsyncSessionLocal
from app.services.conversion_pii_retention_service import erase_customer_conversion_event_pii


async def _run(tenant_id: UUID, customer_id: UUID, apply: bool) -> None:
    async with AsyncSessionLocal() as db:
        count = await erase_customer_conversion_event_pii(
            db, tenant_id=tenant_id, customer_id=customer_id, apply=apply,
        )
    mode = "redacted" if apply else "would redact"
    print(f"{mode} {count} conversion event payload(s)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--customer-id", required=True, type=UUID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(args.tenant_id, args.customer_id, args.apply))


if __name__ == "__main__":
    main()
