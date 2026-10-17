"""Explicit reviewed binding CLI. Dry-run by default; never edits vehicle VIN.

Run in the approved backend environment. Manifest contains exact reviewed IDs,
source company/provider identity, existing PENDING reference, expiry and note.
No credentials or raw provider payloads are printed.
"""

import argparse
import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.db.models.dashboard_vehicle_binding import DashboardVehicleBinding
from app.db.session import AsyncSessionLocal
from app.schemas.dashboard_vehicle_binding import BindingManifest
from app.services.dashboard_vehicle_bindings import create
from app.services.fleet_diagnostics import authorize
from app.services.fleet_telemetry import now
from sqlalchemy import select


def verify_evidence(raw, manifest):
    if (
        len(raw) > 8 * 1024 * 1024
        or hashlib.sha256(raw).hexdigest() != manifest.source_evidence_sha256
    ):
        raise ValueError("Reviewed source evidence hash mismatch")
    evidence = json.loads(raw)
    if isinstance(evidence, dict) and "drivers" in evidence:
        # Accept the final collector's untouched source file. Its actual source
        # company and assignment flags replace hand-entered browser assertions.
        from scripts.motive_drivers.import_records import validate

        # New creation enforces freshness in create(); an identical already
        # approved manifest may be retried later without extending its interval.
        validate(
            evidence,
            manifest.source_company_label,
            manifest.source_company_id,
            recovery=True,
        )
        rows = [
            row
            for row in evidence["drivers"]
            if row.get("provider_vehicle_id") == manifest.provider_vehicle_id
        ]
        if (
            len(rows) != 1
            or rows[0]["state"] != "captured"
            or rows[0]["vin"] is not None
            or rows[0].get("source_vin_state") != manifest.source_vin_state
            or datetime.fromisoformat(rows[0]["source_read_at"])
            != manifest.source_evidence_read_at
        ):
            raise ValueError("Reviewed collector vehicle identity mismatch")
        return
    if not isinstance(evidence, dict):
        raise ValueError("Reviewed source evidence must be an object")  # noqa: TRY004 - uniform evidence rejection
    for key, expected in {
        "version": 1,
        "company_id": manifest.source_company_id,
        "company_label": manifest.source_company_label,
        "provider_vehicle_id": manifest.provider_vehicle_id,
        "vin": None,
        "source_vin_state": manifest.source_vin_state,
    }.items():
        if key not in evidence or evidence[key] != expected:
            raise ValueError("Reviewed source identity evidence mismatch")
    for flag in (
        "company_verified_before",
        "company_verified_after",
        "summary_verified_before",
        "summary_verified_after",
    ):
        if evidence.get(flag) is not True:
            raise ValueError("Complete source review proof required")
    before = datetime.fromisoformat(evidence["before_read_at"])
    after = datetime.fromisoformat(evidence["after_read_at"])
    if (
        before.tzinfo is None
        or after.tzinfo is None
        or not before <= after == manifest.source_evidence_read_at
    ):
        raise ValueError("Reviewed source timestamps mismatch")
    for name in ("summary_before_sha256", "summary_after_sha256", "reader_sha256"):
        import re

        if not re.fullmatch(r"[0-9a-f]{64}", evidence.get(name, "")):
            raise ValueError("Source summary and reader hashes required")


async def run(args):
    manifest = None
    if not args.revoke:
        if not args.evidence:
            raise ValueError("Reviewed source evidence file required")
        manifest = BindingManifest.model_validate_json(Path(args.manifest).read_text())
        verify_evidence(Path(args.evidence).read_bytes(), manifest)
    async with AsyncSessionLocal() as db:
        if args.revoke:
            await authorize(db, args.tenant, args.reviewer)
            binding = (
                await db.execute(
                    select(DashboardVehicleBinding)
                    .where(
                        DashboardVehicleBinding.id == args.revoke,
                        DashboardVehicleBinding.tenant_id == args.tenant,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if binding is None:
                raise ValueError("Reviewed binding not found in tenant")
            if args.apply and binding.revoked_at is None:
                binding.revoked_at = now()
                binding.revoked_by_user_id = args.reviewer
                binding.revocation_reason = "operator_revoked"
            action = "revoked" if args.apply else "would_revoke"
        else:
            binding, action = await create(
                db, args.tenant, args.reviewer, manifest, apply=args.apply
            )
        binding_id = str(binding.id) if binding.id else None
        if args.apply:
            await db.commit()
        else:
            await db.rollback()
        print(
            json.dumps(
                {
                    "action": action,
                    "binding_id": binding_id,
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", type=UUID, required=True)
    parser.add_argument("--reviewer", type=UUID, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest")
    mode.add_argument("--revoke", type=UUID)
    parser.add_argument(
        "--evidence", help="Private reviewed source proof JSON for creation"
    )
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args()))
