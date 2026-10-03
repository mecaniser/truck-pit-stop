"""Run reviewed normal Motive imports through Railway SSH; dry run by default.

Private input: {"rows": [TripImport, ...]}. One transaction covers the whole file,
in chunks of at most 1,000. Receipt is atomically saved with mode 0600. No source
payload, remote exception, CLI diagnostic or credential is printed.
"""
import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from uuid import UUID
import zlib

MARKER = "DB036_IMPORT_RECEIPT="
REMOTE = '''import asyncio,base64,json,os,zlib
from uuid import UUID
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.services.fleet_telemetry import now
from scripts.import_motive_trips import parse_rows,run_import,authorize
CONFIG=json.loads(zlib.decompress(base64.b64decode(CONFIG_DATA)))
TENANT=UUID(CONFIG['tenant_id']);ACTOR=UUID(CONFIG['actor_id'])
async def fingerprint(db):
 result={}
 for table in ('vehicles','fleet_telemetry_snapshots','repair_orders'):
  result[table]=(await db.execute(text("SELECT md5(coalesce(string_agg(row_to_json(t)::text, chr(10) ORDER BY id),'')) FROM "+table+" t WHERE tenant_id=:tenant"),{'tenant':TENANT})).scalar_one()
 return result
async def task():
 result={'committed':False,'sha':CONFIG['sha'],'mode':'apply' if CONFIG['apply'] else 'dry_run','status':'failed'}
 commit_started=False
 try:
  if os.environ.get('RAILWAY_GIT_COMMIT_SHA')!=CONFIG['sha']:raise ValueError('sha')
  batches=[parse_rows({'rows':CONFIG['rows'][i:i+1000]},now()) for i in range(0,len(CONFIG['rows']),1000)]
  keys=[(row.provider_vehicle_id,row.started_at) for batch in batches for row in batch]
  if len(keys)!=len(set(keys)):raise ValueError('duplicate')
  mappings={}
  for batch in batches:
   for row in batch:
    if mappings.setdefault(row.provider_vehicle_id,row.vin)!=row.vin:raise ValueError('mapping')
  async with AsyncSessionLocal() as db:
   try:
    await authorize(db,TENANT,ACTOR)
    schema=(await db.execute(text('SELECT version_num FROM alembic_version'))).scalars().all()
    before=await fingerprint(db)
    receipts=[]
    for batch in batches:
     imported=await run_import(db,batch,TENANT,ACTOR,apply=CONFIG['apply'])
     receipts.extend(imported['rows'])
    if before!=await fingerprint(db):raise ValueError('preservation')
    if CONFIG['apply']:
     for batch in batches:
      replay=await run_import(db,batch,TENANT,ACTOR,apply=True)
      if any(row['action']!='unchanged' for row in replay['rows']):raise ValueError('replay')
     if before!=await fingerprint(db):raise ValueError('preservation')
     commit_started=True
     await db.commit()
    else:await db.rollback()
    result.update(status='success',committed=CONFIG['apply'],schema=schema,rows=receipts,preserved=list(before),replay_verified=CONFIG['apply'])
   except Exception:
    await db.rollback()
    raise
 except Exception:
  result.update(status='failed',committed=None if commit_started else False,error='Import did not confirm success; inspect identities, membership, schema and deployment. Retry the exact payload to reconcile an uncertain commit.')
 print('DB036_IMPORT_RECEIPT='+json.dumps(result))
asyncio.run(task())
'''


def validate_input(document):
    if not isinstance(document, dict) or set(document) != {"rows"} or not isinstance(document["rows"], list) or not document["rows"]:
        raise ValueError("Expected nonempty rows")
    # Complete deployed TripImport validation is performed before any remote writes.
    keys = set()
    for row in document["rows"]:
        if not isinstance(row, dict):
            raise ValueError("Invalid row")
        started = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
        if started.tzinfo is None:
            raise ValueError("Timezone required")
        key = (row["provider_vehicle_id"], started.astimezone(timezone.utc))
        if key in keys:
            raise ValueError("Duplicate input identity")
        keys.add(key)
    return document["rows"]


def remote_command(rows, args):
    config = dict(rows=rows, tenant_id=str(UUID(args.tenant_id)), actor_id=str(UUID(args.actor_id)), sha=args.sha, apply=args.apply)
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        raise ValueError("Full deployment SHA required")
    encoded = base64.b64encode(zlib.compress(json.dumps(config, allow_nan=False).encode())).decode()
    command = shlex.join(["python", "-c", REMOTE.replace("CONFIG_DATA", repr(encoded))])
    if len(command.encode()) > 100000:
        raise ValueError("Input exceeds SSH argument bound; split reviewed input into separate runs")
    return [args.railway, "ssh", "-p", args.project, "-e", args.environment, "-s", args.service, "--", command]


def atomic_receipt(path, result):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".motive-receipt-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def execute(args, run=subprocess.run):
    raw = Path(args.input).read_bytes()
    rows = validate_input(json.loads(raw))
    command = remote_command(rows, args)
    path = Path(args.receipt)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Reserve a new receipt before sending any command. Existing receipts survive.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    receipt = dict(version=1, input_sha256=hashlib.sha256(raw).hexdigest(), tenant_id=args.tenant_id,
                   actor_id=args.actor_id, sha=args.sha, mode="apply" if args.apply else "dry_run",
                   requested_rows=len(rows), started_at=datetime.now(timezone.utc).isoformat(),
                   status="pending", committed=None)
    atomic_receipt(path, receipt)
    try:
        completed = run(command, capture_output=True, text=True, timeout=600)
        lines = [line[len(MARKER):] for line in completed.stdout.splitlines() if line.startswith(MARKER)]
        if completed.returncode or len(lines) != 1:
            raise ValueError("No unique successful transport receipt")
        result = json.loads(lines[0])
        if result.get("sha") != args.sha or result.get("mode") != receipt["mode"]:
            raise ValueError("Receipt mismatch")
        if result.get("status") == "success":
            if result.get("committed") is not args.apply or len(result.get("rows", [])) != len(rows):
                raise ValueError("Incomplete receipt")
            allowed = {"created", "unchanged"} if args.apply else {"would_create", "unchanged"}
            if any(row.get("action") not in allowed for row in result["rows"]):
                raise ValueError("Invalid action")
        receipt.update(result)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        receipt.update(status="transport_failed", committed=None,
                       error="Remote outcome unconfirmed. Retry the exact input with a new receipt to reconcile; do not assume rollback.")
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    atomic_receipt(path, receipt)
    counts = dict(Counter(row["action"] for row in receipt.get("rows", [])))
    return {"status": receipt["status"], "committed": receipt["committed"], "requested": len(rows), "actions": counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "tenant-id", "actor-id", "project", "environment", "service", "sha", "receipt"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--railway", default="railway")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit("Import was not started or receipt could not be saved; inspect private paths/input before retry.") from None
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
