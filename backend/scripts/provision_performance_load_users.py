"""Provision isolated staff accounts for the k6 multi-user capacity profile."""
import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select

# Railway's console runs this file as a script, which otherwise puts only the
# scripts directory on sys.path instead of the backend package root.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import get_password_hash
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.session import AsyncSessionLocal

CONFIRMATION = "seed-performance-data"
ALLOWED_ENVIRONMENTS = {"performance", "development", "test"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default="performance-lab")
    parser.add_argument("--password", required=True)
    parser.add_argument("--count", type=int, default=10)
    return parser.parse_args()


def validate_environment(args: argparse.Namespace) -> None:
    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        raise RuntimeError("Refusing to provision users outside performance, development, or test.")
    if os.getenv("LOAD_TEST_SEED_CONFIRM") != CONFIRMATION:
        raise RuntimeError(f"Set LOAD_TEST_SEED_CONFIRM={CONFIRMATION!r} to continue.")
    if args.count < 1 or args.count > 50:
        raise ValueError("--count must be between 1 and 50")


async def provision(args: argparse.Namespace) -> None:
    validate_environment(args)
    async with AsyncSessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.slug == args.slug))
        if tenant is None:
            raise RuntimeError(f"Performance tenant not found: slug={args.slug}")

        password_hash = get_password_hash(args.password)
        emails: list[str] = []
        for index in range(1, args.count + 1):
            email = f"performance-load-{index:02d}@dieselbridge.com"
            user = await db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    email=email,
                    hashed_password=password_hash,
                    first_name="Performance",
                    last_name=f"Load {index:02d}",
                    role=UserRole.GARAGE_ADMIN,
                    tenant_id=tenant.id,
                    is_active=True,
                    is_verified=True,
                )
                db.add(user)
            else:
                user.hashed_password = password_hash
                user.role = UserRole.GARAGE_ADMIN
                user.tenant_id = tenant.id
                user.is_active = True
                user.is_verified = True
            emails.append(email)

        await db.commit()
        print("Performance load users provisioned successfully.")
        print(f"tenant_slug={tenant.slug}")
        print(f"load_user_count={len(emails)}")
        print(f"first_load_user={emails[0]}")
        print(f"last_load_user={emails[-1]}")


if __name__ == "__main__":
    asyncio.run(provision(parse_args()))
