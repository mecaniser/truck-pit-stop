"""Daily rendered-report trip import, dry-run by default and receipt-backed."""

import argparse
import asyncio
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from app.db.models.customer import Customer
from app.db.models.fleet_trip import FleetTrip
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_trip import TripImport
from app.services.fleet_telemetry import active_membership
from scripts.motive_sync.runner import private_json
from scripts.prepare_motive_trip_history import ZONE, normalize, timestamp
from sqlalchemy import func, select

from scripts import import_motive_trips as importer


def validate_source(document, company_label, company_id, stamp):
    """Only a complete, recent, visibly verified company report is eligible."""
    if (
        document.get("company_label") != company_label
        or document.get("company_id") != company_id
        or document.get("company_verified_before") is not True
        or document.get("company_verified_after") is not True
        or document.get("complete") is not True
        or "Eastern Time - New York" not in str(document.get("timezone_evidence", ""))
    ):
        raise ValueError("Incomplete collection or company/timezone mismatch")
    started, finished = (
        timestamp(document["started_at"]),
        timestamp(document["finished_at"]),
    )
    if not stamp - timedelta(hours=2) <= started <= finished <= stamp:
        raise ValueError("Stale, future or reversed collection timestamps")
    vehicles = document.get("vehicles")
    if (
        not isinstance(vehicles, list)
        or not vehicles
        or type(document.get("directory_count")) is not int
        or document["directory_count"] != len(vehicles)
    ):
        raise ValueError("Complete vehicle directory required")
    vins, providers = set(), set()
    for vehicle in vehicles:
        provider, vin = vehicle.get("provider_vehicle_id"), vehicle.get("vin")
        if (
            not isinstance(provider, str)
            or not re.fullmatch(r"[0-9]+", provider)
            or provider in providers
        ):
            raise ValueError("Invalid or duplicate source provider")
        if not isinstance(vehicle.get("unit"), str) or not vehicle["unit"].strip():
            raise ValueError("Source unit required")
        if vin is not None and (
            not isinstance(vin, str)
            or not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin)
            or vin in vins
        ):
            raise ValueError("Invalid or duplicate source VIN")
        providers.add(provider)
        if vin:
            vins.add(vin)
    windows = document.get("windows")
    if not isinstance(windows, list) or not 1 <= len(windows) <= 3:
        raise ValueError("Bounded daily report windows required")
    covered = set()
    today = finished.astimezone(ZONE).date()
    for window in windows:
        start, end = (
            date.fromisoformat(window["start"]),
            date.fromisoformat(window["end"]),
        )
        read = timestamp(window["source_read_at"])
        if (
            not today - timedelta(days=2) <= start <= end <= today
            or not started <= read <= finished
        ):
            raise ValueError("Invalid daily report window or read time")
        rows = window.get("rows")
        count = window.get("expected_total")
        if (
            window.get("status") not in ("captured", "empty")
            or not isinstance(rows, list)
            or type(count) is not int
            or not 0 <= count <= 20000
            or count != len(rows)
            or type(window.get("footerShown")) is not int
            or window.get("footerShown") != count
            or (window["status"] == "empty") != (count == 0)
        ):
            raise ValueError("Incomplete report or missing terminal count evidence")
        covered.update(start + timedelta(days=i) for i in range((end - start).days + 1))
    if covered != {today - timedelta(days=i) for i in range(3)}:
        raise ValueError(
            "Daily reconciliation must cover today and the preceding two days"
        )


def prior_payload(trip):
    """Preserve immutable fields, including original source read and fuel metrics."""
    values = {
        name: getattr(trip, name)
        for name in TripImport.model_fields
        if name not in {"vin", "unit"}
    }
    values.update(vin=trip.verified_vin, unit=trip.provider_unit)
    for name in ("started_at", "ended_at", "source_read_at"):
        values[name] = importer.aware(values[name])
    payload = TripImport.model_validate(values)
    if importer.digest(payload) != trip.request_digest:
        raise ValueError("Stored trip does not match its immutable digest")
    return payload.model_dump(mode="json")


async def prepare(db, document, tenant_id, actor_id, stamp):
    await importer.authorize(db, tenant_id, actor_id)
    mappings, exclusions = [], []
    for source in document["vehicles"]:
        reason = None
        if not source["vin"]:
            reason = "unknown_vin"
        else:
            vehicles = (
                (
                    await db.execute(
                        select(Vehicle)
                        .where(
                            Vehicle.tenant_id == tenant_id,
                            Vehicle.deleted_at.is_(None),
                            func.upper(func.trim(Vehicle.vin)) == source["vin"],
                        )
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            if len(vehicles) != 1:
                reason = "unmatched_or_ambiguous_vin"
            else:
                members = (
                    (
                        await db.execute(
                            select(FleetMembership)
                            .join(
                                Customer,
                                Customer.id == FleetMembership.fleet_customer_id,
                            )
                            .where(
                                FleetMembership.tenant_id == tenant_id,
                                FleetMembership.vehicle_id == vehicles[0].id,
                                Customer.tenant_id == tenant_id,
                                Customer.deleted_at.is_(None),
                                *active_membership(stamp),
                            )
                            .with_for_update()
                        )
                    )
                    .scalars()
                    .all()
                )
                if len(members) != 1:
                    reason = "no_unique_current_membership"
                else:
                    mappings.append(
                        {
                            **{
                                key: source[key]
                                for key in ("provider_vehicle_id", "vin", "unit")
                            },
                            "effective_from": importer.aware(
                                members[0].effective_from
                            ).isoformat(),
                        }
                    )
        if reason:
            exclusions.append(
                {
                    "provider_vehicle_id": source["provider_vehicle_id"],
                    "unit": source["unit"],
                    "reason": reason,
                }
            )
    # Limit prior material to this report's provider IDs and UTC date envelope.
    first = min(date.fromisoformat(w["start"]) for w in document["windows"])
    last = max(date.fromisoformat(w["end"]) for w in document["windows"])
    lower = datetime.combine(first, datetime.min.time(), ZONE)
    upper = datetime.combine(last + timedelta(days=1), datetime.min.time(), ZONE)
    previous = (
        (
            await db.execute(
                select(FleetTrip).where(
                    FleetTrip.tenant_id == tenant_id,
                    FleetTrip.provider_vehicle_id.in_(
                        [s["provider_vehicle_id"] for s in document["vehicles"]]
                    ),
                    FleetTrip.started_at >= lower,
                    FleetTrip.started_at < upper,
                )
            )
        )
        .scalars()
        .all()
    )
    windows = [
        {key: w[key] for key in ("start", "end", "source_read_at", "status", "rows")}
        for w in document["windows"]
    ]
    base = {"tenant_id": str(tenant_id), "company_label": document["company_label"]}
    rows, report = normalize(
        {**base, "windows": windows},
        {**base, "vehicles": mappings},
        {"rows": [prior_payload(trip) for trip in previous]},
        now=stamp,
    )
    report["vehicle_exclusions"] = exclusions
    report["directory_count"] = len(document["vehicles"])
    report["matched_vehicles"] = len(mappings)
    return [
        TripImport.model_validate(row).model_dump(mode="json") for row in rows
    ], report


def immutable_json(path, value):
    """Persist exact retry material before any commit; never replace it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError("Saved normalized retry material differs")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


async def import_batches(db, rows, tenant_id, actor_id, apply):
    result = []
    for offset in range(0, len(rows), 1000):
        batch = importer.parse_rows(
            {"rows": rows[offset : offset + 1000]}, datetime.now(timezone.utc)
        )
        receipt = await importer.run_import(db, batch, tenant_id, actor_id, apply=apply)
        result.extend(receipt["rows"])
    return result


async def run(
    session_factory,
    document,
    tenant_id,
    actor_id,
    company_label,
    company_id,
    receipt_path,
    commit=False,
):
    stamp = datetime.now(timezone.utc)
    validate_source(document, company_label, company_id, stamp)
    checksum = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    async with session_factory() as db:
        rows, report = await prepare(db, document, tenant_id, actor_id, stamp)
        dry = await import_batches(db, rows, tenant_id, actor_id, False)
        await db.rollback()
    normalized = {
        "tenant_id": str(tenant_id),
        "actor_id": str(actor_id),
        "source_sha256": checksum,
        "company_label": company_label,
        "company_id": company_id,
        "rows": rows,
    }
    immutable_json(str(receipt_path) + ".normalized.json", normalized)
    receipt = {
        "mode": "commit" if commit else "dry_run",
        "committed": False,
        "stage": "validated",
        "source_sha256": checksum,
        "tenant_id": str(tenant_id),
        "actor_id": str(actor_id),
        "report": report,
        "normalized_sha256": hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "rows": dry,
    }
    private_json(receipt_path, receipt)
    if not commit:
        return receipt
    return await apply_and_verify(
        session_factory, rows, tenant_id, actor_id, receipt_path, receipt
    )


async def apply_and_verify(
    session_factory, rows, tenant_id, actor_id, receipt_path, receipt
):
    async with session_factory() as db:
        # Revalidate actor and tenant even when no eligible completed trips exist.
        await importer.authorize(db, tenant_id, actor_id)
        applied = await import_batches(db, rows, tenant_id, actor_id, True)
        replay = await import_batches(db, rows, tenant_id, actor_id, True)
        if any(r["action"] != "unchanged" for r in replay):
            raise ValueError("Unchanged replay verification failed")
        # Persist identities before commit so an uncertain response remains reconcilable.
        receipt.update(stage="commit_pending", rows=applied)
        private_json(receipt_path, receipt)
        await db.commit()
    receipt.update(committed=True, stage="committed")
    private_json(receipt_path, receipt)
    async with session_factory() as db:
        await importer.authorize(db, tenant_id, actor_id)
        verified = await import_batches(db, rows, tenant_id, actor_id, False)
        if any(r["action"] != "unchanged" for r in verified) or [
            r["trip_id"] for r in verified
        ] != [r["trip_id"] for r in applied]:
            raise ValueError("Committed readback mismatch")
        await db.rollback()
    receipt.update(
        stage="verified",
        replay_unchanged=len(replay),
        readback_verified=len(verified),
        verified_at=datetime.now(timezone.utc).isoformat(),
    )
    private_json(receipt_path, receipt)
    return receipt


async def recover(
    session_factory,
    document,
    tenant_id,
    actor_id,
    company_label,
    company_id,
    receipt_path,
):
    """Reconcile the exact prior attempt, without representing it as fresh capture."""
    receipt = json.loads(Path(receipt_path).read_text())
    normalized = json.loads(Path(str(receipt_path) + ".normalized.json").read_text())
    source_hash = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    normalized_hash = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        receipt.get("mode") != "commit"
        or receipt.get("stage")
        not in {"validated", "commit_pending", "committed", "verified"}
        or normalized_hash != receipt.get("normalized_sha256")
        or source_hash != receipt.get("source_sha256")
        or source_hash != normalized.get("source_sha256")
        or normalized.get("company_label") != company_label
        or normalized.get("company_id") != company_id
        or any(
            record.get("tenant_id") != str(tenant_id)
            or record.get("actor_id") != str(actor_id)
            for record in (receipt, normalized)
        )
    ):
        raise ValueError(
            "Recovery identity, immutable evidence or committed intent mismatch"
        )
    rows = normalized["rows"]
    if not isinstance(rows, list):
        raise TypeError("Invalid recovery rows")
    async with session_factory() as db:
        await importer.authorize(db, tenant_id, actor_id)
        await import_batches(db, rows, tenant_id, actor_id, False)
        await db.rollback()
    receipt["recovery"] = True
    # All original trip times and source-read times remain exactly as captured.
    return await apply_and_verify(
        session_factory, rows, tenant_id, actor_id, receipt_path, receipt
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument(
        "--recover",
        action="store_true",
        help="Reconcile saved normalized attempt; requires original --input and --commit",
    )
    args = parser.parse_args()
    required = [
        "MOTIVE_SYNC_TENANT_ID",
        "MOTIVE_SYNC_ACTOR_ID",
        "MOTIVE_COMPANY_LABEL",
        "MOTIVE_COMPANY_ID",
    ]
    if any(not os.environ.get(key) for key in required):
        parser.error("Explicit tenant, actor and company configuration required")
    if args.recover and not args.commit:
        parser.error("Recovery requires explicit --commit")
    from app.db.session import AsyncSessionLocal

    operation = recover if args.recover else run
    receipt = asyncio.run(
        operation(
            AsyncSessionLocal,
            json.loads(Path(args.input).read_text()),
            UUID(os.environ[required[0]]),
            UUID(os.environ[required[1]]),
            os.environ[required[2]],
            os.environ[required[3]],
            args.receipt,
            **({} if args.recover else {"commit": args.commit}),
        )
    )
    print(
        json.dumps(
            {
                "mode": receipt["mode"],
                "committed": receipt["committed"],
                "stage": receipt["stage"],
                "rows": len(receipt["rows"]),
                "excluded": len(receipt["report"]["exclusions"]),
            }
        )
    )


if __name__ == "__main__":
    main()
