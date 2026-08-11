"""Rotate conversion webhook secrets to the active key version.

Dry-run is the default. Pass --apply only after every runtime has the complete
old+new keyring and the new active version.
"""
import argparse
import asyncio

from app.db.session import AsyncSessionLocal
from app.services.paid_invoice_webhook_key_rotation import rotate_paid_invoice_webhook_secrets


async def _run(apply: bool) -> None:
    async with AsyncSessionLocal() as db:
        count = await rotate_paid_invoice_webhook_secrets(db, apply=apply)
    mode = "rotated" if apply else "would rotate"
    print(f"{mode} {count} tenant webhook secret(s)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(args.apply))


if __name__ == "__main__":
    main()
