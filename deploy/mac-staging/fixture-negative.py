"""Real committed-import rejection checks, isolated worker fixture database only.

No valid mutation is submitted. Every case calls the real location importer with
commit=True and checks exact expected rejection plus full before/after capture
and Vehicle rows. Run without concurrent fixture writers.
"""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import runpy
from uuid import UUID

common=runpy.run_path(str(Path(__file__).with_name("fixture-common.py")))
helpers=runpy.run_path(str(Path(__file__).with_name("fixture-verify.py")))
require=helpers["require"]


async def state(factory):
    """Compare actual row values, not only cardinality or latest timestamps."""
    from sqlalchemy import select, text
    from app.db.models.fleet_telemetry import FleetTelemetrySnapshot
    from app.db.models.vehicle import Vehicle
    result={}
    async with factory() as db:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        for model in (FleetTelemetrySnapshot,Vehicle):
            rows=(await db.execute(select(model.__table__).order_by(model.id))).mappings().all()
            result[model.__tablename__]=[dict(row) for row in rows]
        await db.rollback()
    return result


def state_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()


async def main(args):
    common["guard"]()
    from app.db.session import AsyncSessionLocal, engine
    from scripts.motive_sync.import_locations import run_import
    cfg=helpers["load_private"](args.manifest)
    require(cfg==common["manifest"](),"Unexpected synthetic manifest")
    source=helpers["load_private"](args.source)
    require(source.get("complete") is True,"A complete actually collected baseline source is required")
    require(source.get("company_id")==common["COMPANY_ID"] and source.get("company_label")==common["COMPANY_LABEL"],"Unexpected source company")
    expected={v["provider_vehicle_id"]:v for v in cfg["vehicles"]}
    require(len(source.get("vehicles",[]))==6,"Six actual fixture vehicle rows required")
    require({v["provider_vehicle_id"] for v in source["vehicles"]}==set(expected),"Unexpected provider directory")
    for row in source["vehicles"]:
        require(row.get("vin")==expected[row["provider_vehicle_id"]]["vin"],"Baseline source VIN differs from fixture")
        require(row.get("status")=="located","Located baseline source required")
    tenant,actor=UUID(cfg["tenant_id"]),UUID(cfg["actor_id"])
    incomplete=deepcopy(source);incomplete["complete"]=False
    wrong_company=deepcopy(source);wrong_company["company_id"]="SYNTHETIC-WRONG-COMPANY"
    conflicting_vin=deepcopy(source)
    conflicting_vin["vehicles"][0]["vin"]=conflicting_vin["vehicles"][1]["vin"]
    cases=[
        ("incomplete",incomplete,tenant,actor,"Incomplete collection or company identity mismatch"),
        ("wrong_company",wrong_company,tenant,actor,"Incomplete collection or company identity mismatch"),
        ("conflicting_source_vin",conflicting_vin,tenant,actor,"Duplicate source VIN or provider vehicle"),
        ("foreign_actor",source,tenant,common["identity"]("foreign-owner"),"Active tenant and owner/admin actor required"),
        ("foreign_tenant",source,UUID(cfg["foreign_tenant_id"]),actor,"Active tenant and owner/admin actor required"),
    ]
    try:
        before=await state(AsyncSessionLocal)
        require(len(before["fleet_telemetry_snapshots"])>=6,"Committed telemetry baseline required before negatives")
        require(len(before["vehicles"])==6,"Only the six synthetic canonical vehicles may exist")
        before_hash=state_hash(before)
        baseline=await run_import(AsyncSessionLocal,deepcopy(source),tenant,actor,common["COMPANY_LABEL"],common["COMPANY_ID"],commit=False)
        require(baseline.get("mode")=="dry_run" and baseline.get("committed") is False,"Authorized baseline dry-run required")
        require(len(baseline.get("rows",[]))==6 and all(row.get("snapshot_id") and row.get("board_verified") is True for row in baseline["rows"]),"Baseline source is not currently accepted with verified projections")
        require(await state(AsyncSessionLocal)==before,"Baseline dry-run changed persisted row values")
        print(json.dumps({"stage":"synthetic_negative_baseline_verified","source_accepted":True,"actor_authorized":True,"full_capture_vehicle_state_unchanged":True}))
        for name,document,target_tenant,target_actor,expected_error in cases:
            rejected=False
            try:
                await run_import(AsyncSessionLocal,deepcopy(document),target_tenant,target_actor,common["COMPANY_LABEL"],common["COMPANY_ID"],commit=True)
            except ValueError as error:
                require(str(error)==expected_error,"Unexpected rejection reason; negative is not proved")
                rejected=True
            require(rejected,"Invalid input was accepted by real importer")
            after=await state(AsyncSessionLocal)
            require(after==before,"Rejected import changed capture or canonical Vehicle row values")
            print(json.dumps({"stage":"synthetic_negative_verified","case":name,"commit_requested":True,"rejected":True,"full_capture_vehicle_state_unchanged":True,"state_sha256":before_hash}))
        print(json.dumps({"stage":"synthetic_negative_suite_verified","cases":len(cases),"production_acceptance":False}))
    finally:
        await engine.dispose()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",default="/data/fixture-manifest.json")
    parser.add_argument("--source",required=True)
    asyncio.run(main(parser.parse_args()))
