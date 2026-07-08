#!/usr/bin/env python3
"""One-time backfill: create a primary Contact row for every existing customer
that has zero contacts, using their own name/email/phone.

Customer.first_name/last_name is a NOT NULL field that sometimes holds a real
individual's name (organic customers created via the app, e.g. "Sergio Acrub"
at "Elis Logistica") and sometimes holds a fragment of the company name itself
(customers created by a bulk import that split company_name in two to satisfy
the NOT NULL constraint, e.g. "ZUBAYR" / "TRUCKING INCORPORATED"). Only the
former is a real person worth surfacing as a named, primary contact — the
latter would just be the company name re-displayed as if it were a person.

Heuristic: if first_name+last_name is a substring of company_name (case
insensitive, whitespace-normalized), treat it as a company-name fragment and
backfill a role-labeled "Main Line" contact instead (no name). Otherwise treat
it as a real name and backfill a named primary contact.

Safe to re-run — only touches customers with no contacts yet.
"""
import asyncio
import re
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models.customer import Customer
from app.db.models.contact import Contact


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())


def looks_like_company_fragment(customer: Customer) -> bool:
    if not customer.company_name:
        return False
    full_name = _normalize(f"{customer.first_name or ''} {customer.last_name or ''}")
    company = _normalize(customer.company_name)
    return bool(full_name) and full_name in company


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Customer))
        customers = result.scalars().all()

        created = 0
        skipped = 0
        for customer in customers:
            existing = await db.execute(
                select(Contact).where(Contact.customer_id == customer.id)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            is_fragment = looks_like_company_fragment(customer)
            contact = Contact(
                tenant_id=customer.tenant_id,
                customer_id=customer.id,
                first_name=None if is_fragment else customer.first_name,
                last_name=None if is_fragment else customer.last_name,
                role="Main Line" if is_fragment else None,
                email=customer.email,
                phone=customer.phone,
                is_primary=True,
                source="backfill_from_customer",
            )
            db.add(contact)
            created += 1

        await db.commit()
        print(f"Created {created} contacts, skipped {skipped} customers that already had contacts.")


if __name__ == "__main__":
    asyncio.run(main())
