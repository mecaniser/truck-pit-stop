"""
Preload default services and inventory for a tenant.

Usage:
    python preload_catalog.py                          # list available tenants
    python preload_catalog.py <slug> load              # load services + inventory
    python preload_catalog.py <slug> clear             # clear services + inventory
    python preload_catalog.py <slug> load --services   # services only
    python preload_catalog.py <slug> load --inventory  # inventory only
    python preload_catalog.py <slug> clear --services  # clear services only
    python preload_catalog.py <slug> clear --inventory # clear inventory only
"""
import asyncio
import sys
from uuid import uuid4

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.db.models.tenant import Tenant
from app.db.models.service import ServiceCategory, Service
from app.db.models.inventory import Inventory
from app.core.default_catalog import DEFAULT_CATEGORIES, DEFAULT_SERVICES, DEFAULT_INVENTORY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def get_tenant(db, slug: str) -> Tenant | None:
    result = await db.execute(select(Tenant).where(Tenant.slug == slug, Tenant.deleted_at.is_(None)))
    return result.scalar_one_or_none()


async def list_tenants(db) -> list[Tenant]:
    result = await db.execute(select(Tenant).where(Tenant.deleted_at.is_(None)).order_by(Tenant.name))
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Load actions
# ---------------------------------------------------------------------------

async def load_services(db, tenant: Tenant) -> tuple[int, int]:
    """Load default service categories and services. Skips existing names."""
    # Fetch existing category names for this tenant
    existing_cats_result = await db.execute(
        select(ServiceCategory.name).where(ServiceCategory.tenant_id == tenant.id, ServiceCategory.deleted_at.is_(None))
    )
    existing_cat_names = {row[0] for row in existing_cats_result.all()}

    # Fetch existing service names for this tenant
    existing_svcs_result = await db.execute(
        select(Service.name).where(Service.tenant_id == tenant.id, Service.deleted_at.is_(None))
    )
    existing_svc_names = {row[0] for row in existing_svcs_result.all()}

    # Create missing categories
    cat_map: dict[str, ServiceCategory] = {}
    cats_added = 0
    for cat_data in DEFAULT_CATEGORIES:
        if cat_data["name"] not in existing_cat_names:
            cat = ServiceCategory(id=uuid4(), tenant_id=tenant.id, **cat_data)
            db.add(cat)
            cat_map[cat_data["name"]] = cat
            cats_added += 1
    await db.flush()

    # Also load existing categories into cat_map for services that reference them
    if len(cat_map) < len(DEFAULT_CATEGORIES):
        existing_cats_result2 = await db.execute(
            select(ServiceCategory).where(ServiceCategory.tenant_id == tenant.id, ServiceCategory.deleted_at.is_(None))
        )
        for cat in existing_cats_result2.scalars().all():
            if cat.name not in cat_map:
                cat_map[cat.name] = cat

    # Create missing services
    svcs_added = 0
    for svc_data in DEFAULT_SERVICES:
        if svc_data["name"] not in existing_svc_names:
            cat = cat_map.get(svc_data["category"])
            svc = Service(
                id=uuid4(),
                tenant_id=tenant.id,
                category_id=cat.id if cat else None,
                name=svc_data["name"],
                description=svc_data["description"],
                duration_minutes=svc_data["duration_minutes"],
                base_price=svc_data["base_price"],
                icon=svc_data["icon"],
                sort_order=svc_data["sort_order"],
            )
            db.add(svc)
            svcs_added += 1

    return cats_added, svcs_added


async def load_inventory(db, tenant: Tenant) -> int:
    """Load default inventory items. Skips existing SKUs."""
    existing_skus_result = await db.execute(
        select(Inventory.sku).where(Inventory.tenant_id == tenant.id, Inventory.deleted_at.is_(None))
    )
    existing_skus = {row[0] for row in existing_skus_result.all()}

    added = 0
    for item_data in DEFAULT_INVENTORY:
        if item_data["sku"] not in existing_skus:
            item = Inventory(id=uuid4(), tenant_id=tenant.id, **item_data)
            db.add(item)
            added += 1

    return added


# ---------------------------------------------------------------------------
# Clear actions
# ---------------------------------------------------------------------------

async def clear_services(db, tenant: Tenant) -> tuple[int, int]:
    """Delete all services and service categories for a tenant."""
    svc_result = await db.execute(
        select(Service).where(Service.tenant_id == tenant.id, Service.deleted_at.is_(None))
    )
    services = svc_result.scalars().all()
    for svc in services:
        await db.delete(svc)

    cat_result = await db.execute(
        select(ServiceCategory).where(ServiceCategory.tenant_id == tenant.id, ServiceCategory.deleted_at.is_(None))
    )
    categories = cat_result.scalars().all()
    for cat in categories:
        await db.delete(cat)

    return len(categories), len(services)


async def clear_inventory(db, tenant: Tenant) -> int:
    """Delete all inventory items for a tenant."""
    result = await db.execute(
        select(Inventory).where(Inventory.tenant_id == tenant.id, Inventory.deleted_at.is_(None))
    )
    items = result.scalars().all()
    for item in items:
        await db.delete(item)
    return len(items)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    args = sys.argv[1:]
    slug = None
    action = None
    do_services = True
    do_inventory = True

    for arg in args:
        if arg in ("load", "clear"):
            action = arg
        elif arg == "--services":
            do_inventory = False
        elif arg == "--inventory":
            do_services = False
        elif not arg.startswith("-"):
            slug = arg

    return slug, action, do_services, do_inventory


async def main():
    slug, action, do_services, do_inventory = parse_args()

    async with AsyncSessionLocal() as db:
        if not slug:
            tenants = await list_tenants(db)
            if not tenants:
                print("No tenants found. Run seed_data.py first.")
                return
            print("Available tenants:")
            for t in tenants:
                print(f"  {t.slug:<30}  {t.name}")
            print(f"\nUsage: python preload_catalog.py <slug> [load|clear] [--services|--inventory]")
            return

        tenant = await get_tenant(db, slug)
        if not tenant:
            print(f"Tenant '{slug}' not found.")
            return

        if not action:
            print(f"Specify an action: load or clear")
            print(f"  python preload_catalog.py {slug} load")
            print(f"  python preload_catalog.py {slug} clear")
            return

        print(f"Tenant: {tenant.name} ({tenant.slug})")

        if action == "load":
            if do_services:
                cats_added, svcs_added = await load_services(db, tenant)
                print(f"  Services: +{cats_added} categories, +{svcs_added} services", end="")
                if cats_added == 0 and svcs_added == 0:
                    print(" (already loaded, nothing new added)", end="")
                print()

            if do_inventory:
                inv_added = await load_inventory(db, tenant)
                print(f"  Inventory: +{inv_added} items", end="")
                if inv_added == 0:
                    print(" (already loaded, nothing new added)", end="")
                print()

            await db.commit()
            print("Done.")

        elif action == "clear":
            confirm = input(f"Clear {'services' if do_services else ''}{'&' if do_services and do_inventory else ''}{'inventory' if do_inventory else ''} for {tenant.name}? [y/N] ").strip().lower()
            if confirm != "y":
                print("Aborted.")
                return

            if do_services:
                cats_del, svcs_del = await clear_services(db, tenant)
                print(f"  Services: removed {svcs_del} services, {cats_del} categories")

            if do_inventory:
                inv_del = await clear_inventory(db, tenant)
                print(f"  Inventory: removed {inv_del} items")

            await db.commit()
            print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
