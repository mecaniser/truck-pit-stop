"""Read-only source/receipt/database/projection parity for isolated worker runs.

Use the actual collector source.json and its exact receipt.json. Driver mode uses
three database journals for that source instead of a shared file receipt.
"""
import argparse
import asyncio
import json
from pathlib import Path
import runpy
from types import SimpleNamespace
from uuid import UUID

common=runpy.run_path(str(Path(__file__).with_name("fixture-common.py")))


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def load_private(path):
    path=Path(path)
    require(not path.is_symlink() and path.is_file(),"Invalid evidence file")
    require(not path.stat().st_mode & 0o077,"Evidence file must be private")
    require(path.stat().st_size<=16*1024*1024,"Evidence file too large")
    return json.loads(path.read_text())


def same(actual, expected, label):
    require(actual==expected,"Parity failed: "+label)


def aware(value):
    from datetime import datetime, timezone
    if isinstance(value,str):
        return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(timezone.utc)
    return value.astimezone(timezone.utc)


def verify_trip_coverage(document,rows,expected):
    from zoneinfo import ZoneInfo
    windows=document["windows"]
    require(windows and all(w["start"]==w["end"] for w in windows),"Synthetic trip windows must be individual dates")
    dates={w["start"] for w in windows}
    same(len(dates),len(windows),"unique requested trip dates")
    expected_grid={(provider,day) for provider in expected for day in dates}
    actual_grid=[(r["provider_vehicle_id"],aware(r["started_at"]).astimezone(ZoneInfo("America/New_York")).date().isoformat()) for r in rows]
    same(len(actual_grid),len(expected_grid),"six trips per requested date")
    same(set(actual_grid),expected_grid,"complete vehicle/date trip coverage")


async def verify(args):
    common["guard"]()
    from sqlalchemy import select, func, text
    from app.db.session import AsyncSessionLocal, engine
    from app.db.models.vehicle import Vehicle
    from app.db.models.fleet_telemetry import FleetTelemetrySnapshot
    from app.db.models.fleet_diagnostic import FleetDiagnosticCapture
    from app.db.models.fleet_driver_record import FleetDriverRecordCapture
    from app.db.models.fleet_trip import FleetTrip
    from app.db.models.fleet_fuel import FleetFuelDaily
    from scripts.motive_health.import_health import source_hash
    cfg=load_private(args.manifest)
    same(cfg,common["manifest"](),"fixed fixture manifest")
    document=load_private(args.source)
    require(document.get("complete") is True,"Incomplete source cannot verify")
    same(document.get("company_id"),common["COMPANY_ID"],"source company")
    same(document.get("company_label"),common["COMPANY_LABEL"],"source company label")
    require(document.get("company_verified_before") is True and document.get("company_verified_after") is True,"Company checks missing")
    tenant,actor=UUID(cfg["tenant_id"]),UUID(cfg["actor_id"])
    expected={v["provider_vehicle_id"]:v for v in cfg["vehicles"]}
    source_rows=document["drivers"] if args.kind=="drivers" else document["vehicles"]
    same({r["provider_vehicle_id"] for r in source_rows},set(expected),"complete six-vehicle source")
    for row in source_rows:
        item=expected[row["provider_vehicle_id"]]
        same(row["vin"],item["vin"],"source VIN")
        same(row["unit"],item["unit"],"source unit")
    receipt=None
    if args.kind!="drivers":
        require(args.receipt is not None,"Exact file receipt required")
        receipt=load_private(args.receipt)
        require(receipt.get("committed") is True and receipt.get("mode")=="commit","Committed receipt required")
        if args.kind!="location":
            same(receipt.get("stage"),"verified","receipt stage")
            same(receipt.get("source_sha256"),source_hash(document),"receipt source hash")
            same(receipt.get("tenant_id"),cfg["tenant_id"],"receipt tenant")
            same(receipt.get("actor_id"),cfg["actor_id"],"receipt actor")
    checked=0
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SET TRANSACTION READ ONLY"))
            # An importer must not create captures in the sentinel or any other tenant.
            for model in (FleetTelemetrySnapshot,FleetDiagnosticCapture,FleetDriverRecordCapture,FleetTrip,FleetFuelDaily):
                same(await db.scalar(select(func.count()).select_from(model).where(model.tenant_id!=tenant)),0,"foreign tenant captures")
            for item in expected.values():
                vehicle=await db.get(Vehicle,UUID(item["vehicle_id"]))
                require(vehicle is not None,"Fixture vehicle missing")
                same(vehicle.tenant_id,tenant,"vehicle tenant")
                same(vehicle.vin,item["vin"],"canonical VIN preserved")
                same(vehicle.mileage,1000,"canonical mileage preserved")
            if args.kind=="location":
                from app.services import fleet_telemetry
                from scripts.motive_sync.import_locations import make_body, projection_matches
                for source in source_rows:
                    item=expected[source["provider_vehicle_id"]]
                    require(source.get("status")=="located","Located source required")
                    body=make_body(source,tenant,UUID(item["fleet_customer_id"]),common["COMPANY_LABEL"],common["COMPANY_ID"])
                    saved=await db.scalar(select(FleetTelemetrySnapshot).where(FleetTelemetrySnapshot.tenant_id==tenant,FleetTelemetrySnapshot.client_request_id==body.client_request_id))
                    require(saved is not None,"Source telemetry capture missing")
                    for key in ("lat","lng","location_label","speed_mph","observed_at"):
                        same(getattr(saved,key),getattr(body,key),"location "+key)
                    same(saved.fleet_membership_id,UUID(item["membership_id"]),"telemetry membership")
                    row_receipt=[r for r in receipt["rows"] if r.get("snapshot_id")==str(saved.id)]
                    require(len(row_receipt)==1 and row_receipt[0].get("saved_receipt_verified") is True and row_receipt[0].get("board_verified_after_commit") is True,"Telemetry receipt readback missing")
                    truck=SimpleNamespace(id=saved.vehicle_id,board_membership_customer_id=saved.fleet_customer_id,telemetry=None)
                    await fleet_telemetry.attach(db,[truck],tenant)
                    require(projection_matches(truck.telemetry,saved,saved.id),"Telemetry projection differs")
                    checked+=1
            elif args.kind=="health":
                from app.services import fleet_diagnostics
                from scripts.motive_health.import_health import body_for
                for source in source_rows:
                    require(source.get("state")=="captured" and source.get("explicit_empty") is True and source.get("count_before")==0 and source.get("count_after")==0 and source.get("codes")==[],"Synthetic health requires six verified explicit zero observations")
                    body=body_for(document,source,tenant)
                    saved=await db.scalar(select(FleetDiagnosticCapture).where(FleetDiagnosticCapture.tenant_id==tenant,FleetDiagnosticCapture.client_request_id==body.client_request_id))
                    require(saved is not None,"Source health capture missing")
                    same(saved.explicit_empty,body.explicit_empty,"health empty")
                    same(saved.codes,[code.model_dump(mode="json") for code in body.codes],"health codes")
                    same(saved.source_read_at,body.source_read_at,"health source time")
                    same(saved.fleet_membership_id,UUID(expected[source["provider_vehicle_id"]]["membership_id"]),"health membership")
                    projection=await fleet_diagnostics.read(db,tenant,saved.vehicle_id)
                    same(projection.capture_id,saved.id,"health projection")
                    same(projection.explicit_empty,body.explicit_empty,"health projected empty")
                    checked+=1
            elif args.kind=="fuel":
                from scripts.motive_sync.fuel_runner import payload,stored_payload,canonical_payload
                from scripts import import_motive_daily_fuel
                normalized=load_private(str(args.receipt)+".normalized.json")
                same(source_hash(normalized),receipt["normalized_sha256"],"fuel normalized hash")
                same(normalized["source_sha256"],source_hash(document),"fuel normalized source")
                require(not receipt["report"]["exclusions"],"Synthetic fuel exclusions forbidden")
                normalized_rows={(r["provider_vehicle_id"],r["report_date"]):r for r in normalized["rows"]}
                for source in source_rows:
                    for record in source["records"]:
                        require(record["state"]=="reported","Reported fuel source required")
                        body=payload(document,source,record)
                        saved=await db.scalar(select(FleetFuelDaily).where(FleetFuelDaily.tenant_id==tenant,FleetFuelDaily.provider_vehicle_id==source["provider_vehicle_id"],FleetFuelDaily.report_date==body.report_date))
                        require(saved is not None,"Source fuel row missing")
                        same(saved.request_digest,import_motive_daily_fuel.digest(body),"fuel current source measures")
                        same(canonical_payload(stored_payload(saved)),normalized_rows[(source["provider_vehicle_id"],record["report_date"])],"fuel retained immutable read model")
                        same(saved.fleet_membership_id,UUID(expected[source["provider_vehicle_id"]]["membership_id"]),"fuel membership")
                        checked+=1
            elif args.kind=="trips":
                from scripts.motive_sync.trip_runner import prior_payload
                normalized=load_private(str(args.receipt)+".normalized.json")
                same(source_hash(normalized),receipt["normalized_sha256"],"trip normalized hash")
                same(normalized["source_sha256"],source_hash(document),"trip normalized source")
                verify_trip_coverage(document,normalized["rows"],expected)
                for row in normalized["rows"]:
                    saved=await db.scalar(select(FleetTrip).where(FleetTrip.tenant_id==tenant,FleetTrip.provider_vehicle_id==row["provider_vehicle_id"],FleetTrip.started_at==aware(row["started_at"])))
                    require(saved is not None,"Source trip missing")
                    same(prior_payload(saved),row,"trip immutable read model")
                    same(saved.fleet_membership_id,UUID(expected[row["provider_vehicle_id"]]["membership_id"]),"trip membership")
                    checked+=1
            elif args.kind=="drivers":
                from scripts.motive_drivers.journal import runs
                from scripts.motive_drivers.import_records import body_for
                from app.schemas.fleet_driver_record import DriverRecordContent
                from app.services import fleet_driver_records
                digest=source_hash(document)
                journals=(await db.execute(select(runs).where(runs.c.tenant_id==tenant,runs.c.source_sha256==digest,runs.c.stage=="verified"))).mappings().all()
                same(len(journals),3,"three independently verified driver journals")
                same({str(j["fleet_customer_id"]) for j in journals},set(cfg["fleets"]),"driver journal fleet set")
                for journal in journals:
                    same(journal["source_document"],document,"same immutable driver source")
                    same(journal["actor_id"],actor,"journal actor")
                    require(journal["receipts"][-1].get("committed") is True,"Driver journal committed receipt missing")
                for source in source_rows:
                    body=body_for(document,source,tenant)
                    saved=await db.scalar(select(FleetDriverRecordCapture).where(FleetDriverRecordCapture.tenant_id==tenant,FleetDriverRecordCapture.client_request_id==body.client_request_id))
                    require(saved is not None,"Source driver capture missing")
                    content=DriverRecordContent.model_validate({k:v for k,v in body.model_dump(mode="json").items() if k in DriverRecordContent.model_fields})
                    same(saved.payload,content.model_dump(mode="json"),"driver payload")
                    same(saved.source_read_at,body.source_read_at,"driver source time")
                    same(saved.fleet_membership_id,UUID(expected[source["provider_vehicle_id"]]["membership_id"]),"driver membership")
                    projection=await fleet_driver_records.read(db,tenant,saved.vehicle_id)
                    require(projection.record is not None,"Driver current projection missing")
                    same(projection.record.capture_id,saved.id,"driver projection capture")
                    same(projection.record.safety_score,body.safety.score,"driver projected score")
                    checked+=1
            await db.rollback()
        print(json.dumps({"stage":"synthetic_fixture_parity_verified","kind":args.kind,"checked":checked,"source_sha256":source_hash(document),"production_acceptance":False}))
    finally:
        await engine.dispose()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind",required=True,choices=["location","health","fuel","trips","drivers"])
    parser.add_argument("--manifest",default="/data/fixture-manifest.json")
    parser.add_argument("--source",required=True)
    parser.add_argument("--receipt")
    asyncio.run(verify(parser.parse_args()))
