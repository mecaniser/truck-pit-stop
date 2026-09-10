"""Read-only manifest by default; explicit exact-digest apply, no provider IO.

Run from backend: python -m scripts.historical_export_hold --scope scope.json
Scope: tenant_id, invoice_ids, cutoff (timezone required), reason.
Apply: --apply manifest.json --sha256 <reviewed digest>.
Persist stdout as the external immutable review/audit artifact. No release mode.
"""
import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.services.historical_export_hold import make_manifest, apply_manifest, digest


async def run(args):
    async with AsyncSessionLocal() as db:
        try:
            if args.apply:
                if not args.sha256:
                    raise ValueError("--sha256 is required for apply")
                manifest = json.loads(Path(args.apply).read_text())
                result = await apply_manifest(db, manifest, expected_sha256=args.sha256)
                await db.commit()
                print(json.dumps(result, indent=2))
            else:
                await db.execute(text("SET TRANSACTION READ ONLY"))
                scope = json.loads(Path(args.scope).read_text())
                manifest = await make_manifest(db, tenant_id=UUID(scope["tenant_id"]),
                    invoice_ids=[UUID(value) for value in scope["invoice_ids"]],
                    cutoff=datetime.fromisoformat(scope["cutoff"]), reason=scope["reason"])
                await db.rollback()
                print(json.dumps({"sha256": digest(manifest), "manifest": manifest}, indent=2))
        except BaseException:
            await db.rollback()
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--scope")
    modes.add_argument("--apply")
    parser.add_argument("--sha256")
    asyncio.run(run(parser.parse_args()))
