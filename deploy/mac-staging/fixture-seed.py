"""Seed ONLY a separate, migrated, empty synthetic worker PostgreSQL database.

Run with PYTHONPATH=/app. Writes a private manifest; never prints passwords/DSN.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
import secrets

common = runpy.run_path(str(Path(__file__).with_name("fixture-common.py")))


async def seed(output):
    common["guard"]()
    from sqlalchemy import func, select, text
    from app.core.security import get_password_hash
    from app.db.models.tenant import Tenant
    from app.db.models.user import User, UserRole
    from app.db.models.customer import Customer
    from app.db.models.vehicle import Vehicle
    from app.db.models.vehicle_relationship import FleetMembership
    from app.db.session import AsyncSessionLocal, engine
    identity, manifest = common["identity"], common["manifest"]()
    stamp = datetime.now(timezone.utc) - timedelta(days=7)
    try:
        async with AsyncSessionLocal() as db:
            if not await db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1")):
                raise RuntimeError("Fixture schema must be migrated before seed")
            for model in (Tenant, User, Customer, Vehicle, FleetMembership):
                if await db.scalar(select(func.count()).select_from(model)):
                    raise RuntimeError("Populated fixture database; refusing to seed or overwrite")
            tenant = Tenant(id=identity("tenant"),name="Synthetic Worker Lab",slug="synthetic-worker-lab",email="worker-lab@example.com",is_active=True,enrollment_status="approved",invoice_reminders_enabled=False)
            foreign = Tenant(id=identity("foreign-tenant"),name="Synthetic Isolation Sentinel",slug="synthetic-worker-sentinel",email="worker-sentinel@example.com",is_active=True,enrollment_status="approved",invoice_reminders_enabled=False)
            db.add_all([tenant,foreign]); await db.flush()
            actor = User(id=identity("owner"),tenant_id=tenant.id,email="worker-owner@example.com",hashed_password=get_password_hash(secrets.token_urlsafe(32)),first_name="Synthetic",last_name="Worker Owner",role=UserRole.GARAGE_OWNER,is_active=True,is_verified=True)
            foreign_actor = User(id=identity("foreign-owner"),tenant_id=foreign.id,email="worker-sentinel-owner@example.com",hashed_password=get_password_hash(secrets.token_urlsafe(32)),first_name="Synthetic",last_name="Sentinel",role=UserRole.GARAGE_OWNER,is_active=True,is_verified=True)
            db.add_all([actor,foreign_actor]); await db.flush()
            tenant.owner_id=actor.id; foreign.owner_id=foreign_actor.id
            fleets=[]
            for n in range(3):
                customer=Customer(id=identity(f"fleet-{n}"),tenant_id=tenant.id,first_name="Synthetic",last_name=f"Fleet {n+1}",company_name=f"Synthetic Worker Fleet {n+1}",email=f"worker-fleet-{n+1}@example.com",fleet_enabled=True,is_internal_fleet=(n==0),source="isolated_worker_fixture")
                db.add(customer);fleets.append(customer)
            sentinel=Customer(id=identity("foreign-fleet"),tenant_id=foreign.id,first_name="Synthetic",last_name="Sentinel Fleet",company_name="Synthetic Sentinel Fleet",email="worker-sentinel-fleet@example.com",fleet_enabled=True,is_internal_fleet=True)
            db.add(sentinel);await db.flush()
            tenant.default_fleet_authority_customer_id=fleets[0].id
            for item in common["VEHICLES"]:
                provider=item["provider_vehicle_id"]
                customer=fleets[item["fleet_ordinal"]]
                vehicle=Vehicle(id=identity("vehicle-"+provider),tenant_id=tenant.id,customer_id=customer.id,vin=item["vin"],unit_number=item["unit"],make="Synthetic",model="Fixture",mileage=1000,source="isolated_worker_fixture",driver_name=item["driver_name"],driver_assignment_revision=0,driver_assignment_changed_at=stamp)
                db.add(vehicle);await db.flush()
                db.add(FleetMembership(id=identity("membership-"+provider),tenant_id=tenant.id,vehicle_id=vehicle.id,fleet_customer_id=customer.id,effective_from=stamp,notes="Synthetic worker acceptance only"))
            await db.commit()
        common["private_json"](output,manifest)
        print("Synthetic worker fixtures seeded: two tenants, three operating fleets, six vehicles")
    finally:
        await engine.dispose()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",default="/data/fixture-manifest.json")
    args=parser.parse_args()
    asyncio.run(seed(args.manifest))
