#!/usr/bin/env python3
"""One-time backfill: fix Payment.created_at for rows imported from Easy Truck
Shop, which were all stamped with the import run's timestamp instead of the
real payment date. Invoice.paid_at holds the correct historical date for each
of these, since the import preserved that field but not Payment.created_at.

This is what inflated the dashboard's "this month" revenue KPI — every
historical payment landed in the current calendar month because
Payment.created_at (what the revenue query filters on) was the import
timestamp, not the actual paid date.

Safe to re-run — only touches rows where source='easy_truck_shop_import' and
the linked invoice has a paid_at to backfill from.

Usage: python backfill_easy_truck_shop_payment_dates.py [--dry-run]
"""
import asyncio
import sys

from sqlalchemy import select, update

from app.db.session import AsyncSessionLocal
from app.db.models.payment import Payment
from app.db.models.invoice import Invoice


async def main(dry_run: bool) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Payment.id, Payment.created_at, Invoice.paid_at)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                Payment.source == "easy_truck_shop_import",
                Invoice.paid_at.isnot(None),
            )
        )
        rows = result.all()
        print(f"Found {len(rows)} payments to backfill.")

        if dry_run:
            for payment_id, old_created_at, paid_at in rows[:10]:
                print(f"  payment {payment_id}: {old_created_at} -> {paid_at}")
            print("Dry run — no changes made.")
            return

        updated = 0
        for payment_id, _old_created_at, paid_at in rows:
            await session.execute(
                update(Payment).where(Payment.id == payment_id).values(created_at=paid_at)
            )
            updated += 1

        await session.commit()
        print(f"Updated {updated} payment rows.")


if __name__ == "__main__":
    asyncio.run(main(dry_run="--dry-run" in sys.argv))
