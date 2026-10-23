"""Read-only exact-generation driver kill/recovery proof in isolated fixture DB.

Before writes a private evidence snapshot; after compares the same journal IDs,
immutable source and full primary capture/directory rows. No database mutation.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import runpy
from uuid import UUID

common=runpy.run_path(str(Path(__file__).with_name("fixture-common.py")))
helpers=runpy.run_path(str(Path(__file__).with_name("fixture-verify.py")))
require=helpers["require"]
load=helpers["load_private"]


def normalized(value):
    return json.loads(json.dumps(value,sort_keys=True,default=str))


def browser_count(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink() and not path.stat().st_mode & 0o077,"Private fixture events required")
    require(path.stat().st_size<16*1024*1024,"Fixture events too large")
    events=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return sum(event.get("event")=="browser_launch" for event in events)


async def main(args):
    common["guard"]()
    from sqlalchemy import select,text
    from app.db.session import AsyncSessionLocal,engine
    from app.db.models.fleet_driver_record import FleetDriverRecordCapture as Capture, FleetDriverDirectoryCapture as Directory
    from scripts.motive_drivers.journal import runs
    from scripts.motive_health.import_health import source_hash
    cfg=load(args.manifest)
    require(cfg==common["manifest"](),"Wrong fixture manifest")
    marker=load(args.marker)
    require(marker.get("stage") in {"staging_first_fleet_verified_kill", "staging_first_fleet_verified_kill_requested"},"Verified-fleet kill marker required")
    # A requested-kill marker records intent only. The release receipt must
    # separately prove actual process exit 137 with OOM=false and --init.
    # Database state proves the commit boundary, not that the OS killed a PID.
    digest=marker.get("source_sha256")
    require(isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),"Invalid marker source hash")
    tenant,primary=UUID(cfg["tenant_id"]),UUID(cfg["fleets"][0])
    before=load(args.snapshot) if args.mode=="after" else None
    if before is not None:
        require(before.get("source_sha256")==digest,"Wrong recovery source generation")
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            journals=(await db.execute(select(runs).where(runs.c.tenant_id==tenant,runs.c.source_sha256==digest).order_by(runs.c.fleet_customer_id))).mappings().all()
            require(len(journals)==3,"Exactly three journals for marker source required")
            require({str(j["fleet_customer_id"]) for j in journals}==set(cfg["fleets"]),"Wrong target fleet set")
            require({str(j["id"]) for j in journals if j["fleet_customer_id"]==primary}=={marker["run_id"]},"Marker run must be exact primary journal")
            for journal in journals:
                require(source_hash(journal["source_document"])==digest,"Journal source hash differs")
                require(journal["actor_id"]==UUID(cfg["actor_id"]) and journal["company_id"]==common["COMPANY_ID"] and journal["mode"]=="commit","Journal identity differs")
            records=(await db.execute(select(Capture.__table__).where(Capture.tenant_id==tenant).order_by(Capture.id))).mappings().all()
            directories=(await db.execute(select(Directory.__table__).where(Directory.tenant_id==tenant,Directory.source_sha256==digest).order_by(Directory.id))).mappings().all()
            # Requests bind records to this exact document, not another source's
            # earlier verified rows already retained in the same fixture DB.
            from scripts.motive_drivers.import_records import request_id
            source=journals[0]["source_document"]
            request_ids={request_id(source,row,tenant) for row in source["drivers"] if row.get("state")=="captured"}
            generation=[r for r in records if r["client_request_id"] in request_ids]
            primary_rows=normalized([dict(r) for r in generation if r["fleet_customer_id"]==primary])
            primary_directories=normalized([dict(d) for d in directories if d["fleet_customer_id"]==primary])
            require(len(primary_rows)==2 and len(primary_directories)==1,"Primary generation requires two records and one directory")
            journal_ids=sorted(str(j["id"]) for j in journals)
            launches=browser_count(args.events)
            require(launches==1,"Recovery probe must have exactly one browser collection")
            if args.mode=="before":
                require(all(j["stage"]==("verified" if j["fleet_customer_id"]==primary else "source_saved") for j in journals),"Expected primary verified and two saved sources")
                require(len(generation)==2 and len(directories)==1,"Later fleet source must not have been projected")
                snapshot={"version":1,"source_sha256":digest,"journal_ids":journal_ids,"primary_records":primary_rows,"primary_directories":primary_directories,"browser_launches":launches,"marker_run_id":marker["run_id"]}
                require(not Path(args.snapshot).exists() and not Path(args.snapshot).is_symlink(),"Refusing to overwrite recovery baseline")
                common["private_json"](args.snapshot,snapshot)
            else:
                require(before.get("version")==1 and before.get("marker_run_id")==marker["run_id"],"Wrong recovery baseline")
                require(all(j["stage"]=="verified" and j["receipts"][-1].get("committed") is True for j in journals),"All target journals must independently verify")
                require(journal_ids==before["journal_ids"],"Recovery created or replaced generation journals")
                require(primary_rows==before["primary_records"] and primary_directories==before["primary_directories"],"Already verified primary rows changed")
                require(launches==before["browser_launches"],"Recovery launched another browser")
                require(len(generation)==6 and len(directories)==3,"Recovered generation requires six records and three directories")
                require(all(sum(r["fleet_customer_id"]==UUID(fleet) for r in generation)==2 for fleet in cfg["fleets"]),"Each target fleet requires two recovered records")
            await db.rollback()
        print(json.dumps({"stage":"synthetic_driver_recovery_audit","mode":args.mode,"source_sha256":digest,"journals":3,"generation_records":len(generation),"generation_directories":len(directories),"browser_launches":launches,"full_primary_rows_unchanged":args.mode=="after","production_acceptance":False}))
    finally:
        await engine.dispose()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["before","after"])
    parser.add_argument("--manifest",default="/data/fixture-manifest.json")
    parser.add_argument("--marker",default="/state/driver-first-fleet-verified.killed")
    parser.add_argument("--events",default="/state/driver-events.jsonl")
    parser.add_argument("--snapshot",default="/state/driver-recovery-before.json")
    asyncio.run(main(parser.parse_args()))
