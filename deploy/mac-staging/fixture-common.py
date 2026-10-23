"""Shared boundary for synthetic worker fixtures, never production data."""
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

DATABASE = "dieselbridge_worker_fixture"
COMPANY_ID = "KT8934277"
COMPANY_LABEL = "77 CARGO LLC"
VEHICLES = [dict(provider_vehicle_id=str(100+n), vin=f"1M8GDM9AXKP04278{n}", unit=f"FIX-{n}", provider_driver_id=str(200+n), driver_name=f"Synthetic Driver {n}", fleet_ordinal=(n-1)//2) for n in range(1,7)]


def identity(name):
    return uuid5(NAMESPACE_URL, "dieselbridge:isolated-worker-fixture:v1:" + name)


def guard():
    from app.core.config import settings
    from sqlalchemy.engine import make_url
    url = make_url(settings.DATABASE_URL)
    if (settings.ENVIRONMENT, url.host, url.database) != ("staging", "postgres", DATABASE) or url.get_backend_name() != "postgresql":
        raise RuntimeError("Requires the separate isolated staging worker fixture database")
    for key, expected in (("MOTIVE_EMAIL", "fixture@example.invalid"), ("MOTIVE_PASSWORD", "synthetic-not-a-provider-password")):
        if os.environ.get(key) and os.environ[key] != expected:
            raise RuntimeError("Real provider credentials prohibited in fixture runtime")
    if settings.MOTIVE_ENABLED or settings.WORKOS_AUTH_ENABLED:
        raise RuntimeError("External authentication and Motive API must remain disabled")


def manifest():
    tenant, actor = str(identity("tenant")), str(identity("owner"))
    fleets = [str(identity(f"fleet-{n}")) for n in range(3)]
    common = {"MOTIVE_SYNC_TENANT_ID":tenant, "MOTIVE_SYNC_ACTOR_ID":actor,"MOTIVE_COMPANY_LABEL":COMPANY_LABEL,"MOTIVE_COMPANY_ID":COMPANY_ID,"MOTIVE_EMAIL":"fixture@example.invalid","MOTIVE_PASSWORD":"synthetic-not-a-provider-password","MOTIVE_SYNC_COMMIT":"true","MOTIVE_HEALTH_COMMIT":"true","MOTIVE_FUEL_COMMIT":"true","MOTIVE_TRIPS_COMMIT":"true","MOTIVE_DRIVER_COMMIT":"true","MOTIVE_DRIVER_JOURNAL":"database","MOTIVE_DRIVER_JOURNAL_KEY":"staging-synthetic-driver","MOTIVE_DRIVER_FLEET_CUSTOMER_ID":fleets[0],"MOTIVE_DRIVER_ADDITIONAL_FLEET_CUSTOMER_IDS":json.dumps(fleets[1:])}
    return {"version":1,"synthetic":True,"database":DATABASE,"tenant_id":tenant,"actor_id":actor,"foreign_tenant_id":str(identity("foreign-tenant")),"fleets":fleets,"vehicles":[{**v,"vehicle_id":str(identity("vehicle-"+v["provider_vehicle_id"])),"membership_id":str(identity("membership-"+v["provider_vehicle_id"])),"fleet_customer_id":fleets[v["fleet_ordinal"]]} for v in VEHICLES],"environment":common}


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.stat().st_mode & 0o077:
        raise RuntimeError("Fixture manifest parent must be private")
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd,"w") as stream:
        json.dump(value,stream,indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary,path)
