"""Seed two synthetic tenants into the isolated Mac staging database only.

Run inside the staging web container with credentials supplied on stdin as JSON.
Refuses populated databases; never resets an existing account or changes data.
"""
import asyncio
import json
import sys
from uuid import uuid4

from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.session import AsyncSessionLocal


async def main():
    from sqlalchemy.engine import make_url

    url = make_url(settings.DATABASE_URL)
    if (settings.ENVIRONMENT, url.host, url.database) != (
        "staging", "postgres", "dieselbridge_staging"
    ):
        raise RuntimeError("Seed requires the isolated Mac staging database")
    passwords = json.load(sys.stdin)
    if set(passwords) != {"alpha", "beta"} or any(
        not isinstance(value, str) or len(value) < 24 for value in passwords.values()
    ):
        raise ValueError("Two independently generated strong passwords required")
    if passwords["alpha"] == passwords["beta"]:
        raise ValueError("Tenant passwords must differ")
    async with AsyncSessionLocal() as db:
        for model in (Tenant, User, Customer):
            if await db.scalar(select(func.count()).select_from(model)):
                raise RuntimeError("Database already populated; seed refused")
        for slug, password in passwords.items():
            tenant = Tenant(
                id=uuid4(), name=f"Staging {slug.title()}", slug=f"staging-{slug}",
                email=f"staging-{slug}@example.com", is_active=True,
                enrollment_status="approved", invoice_reminders_enabled=False,
            )
            db.add(tenant)
            await db.flush()
            owner = User(
                id=uuid4(), email=f"staging-{slug}@example.com",
                hashed_password=get_password_hash(password), first_name="Staging",
                last_name=slug.title(), role=UserRole.GARAGE_OWNER,
                tenant_id=tenant.id, is_active=True, is_verified=True,
            )
            db.add(owner)
            await db.flush()
            tenant.owner_id = owner.id
            db.add(Customer(
                id=uuid4(), tenant_id=tenant.id, first_name="Synthetic",
                last_name=slug.title(), email=f"customer-{slug}@example.com",
                company_name=f"Synthetic {slug.title()} Fleet",
            ))
        await db.commit()
    print("Created two synthetic staging tenants")


if __name__ == "__main__":
    asyncio.run(main())
