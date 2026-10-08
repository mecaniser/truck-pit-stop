"""Bounded daily source fuel reconciliation with immutable, recoverable receipts."""

import argparse
import asyncio
import hashlib
import json
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from app.db.models.customer import Customer
from app.db.models.fleet_fuel import FleetFuelDaily
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_fuel import FuelDailyImport
from app.services.fleet_fuel import visible_query
from app.services.fleet_telemetry import active_membership
from scripts.motive_sync.runner import private_json
from scripts.motive_sync.trip_runner import immutable_json
from sqlalchemy import select

from scripts import import_motive_daily_fuel as importer

MEASUREMENTS = (
    "driving_fuel_gallons",
    "idling_fuel_gallons",
    "reported_total_fuel_gallons",
    "source_distance_miles",
    "source_driving_seconds",
    "source_idling_seconds",
)


def checksum(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def timestamp(value):
    if not isinstance(value, str):
        raise TypeError("Explicit source timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Explicit source timezone required")
    return result.astimezone(timezone.utc)


def completed_dates(stamp, days=3):
    if type(days) is not int or not 1 <= days <= 7:
        raise ValueError("Fuel overlap must be 1 to 7 completed dates")
    stamp = stamp.astimezone(timezone.utc)
    latest = stamp.date() - timedelta(days=1 if stamp.hour >= 12 else 2)
    return [(latest - timedelta(days=i)).isoformat() for i in reversed(range(days))]


def validate_report(report, day, provider):
    if (
        report.get("report_date") != day
        or report.get("filter_start") != day
        or report.get("filter_end") != day
        or report.get("complete") is not True
    ):
        raise ValueError("Incomplete or wrong-date fuel report")
    url = urlsplit(report.get("report_url", ""))
    route, *params = url.fragment.split(";")
    if (
        url.scheme != "https"
        or url.netloc != "app.gomotive.com"
        or url.path != "/en-US/"
        or route != "/reports/vehicle-fuel-performance"
    ):
        raise ValueError("Unexpected source report URL")
    filters = {}
    for pair in params:
        key, separator, value = pair.partition("=")
        if (
            not separator
            or key in filters
            or key
            not in {"start_date", "end_date", "report_id", "report_type", "vehicle_ids"}
        ):
            raise ValueError("Unexpected or duplicate report filter")
        filters[key] = value
    if (
        filters.get("start_date") != day
        or filters.get("end_date") != day
        or filters.get("report_type") != "normal"
        or filters.get("report_id") != "48"
        or filters.get("vehicle_ids") != provider
    ):
        raise ValueError("Source report URL does not match requested date")
    visible = report.get("visible_date_text")
    if (
        not isinstance(visible, str)
        or not visible.strip()
        or not report.get("terminal_evidence")
    ):
        raise ValueError("Visible report date and terminal evidence required")
    count = report.get("row_count")
    if type(count) is not int or count not in (0, 1):
        raise ValueError("Single-provider report requires zero or one row")
    if count == 0 and report.get("explicit_empty") is not True:
        raise ValueError("Empty source report requires explicit empty evidence")
    if count == 1 and report.get("explicit_empty") is not False:
        raise ValueError("Reported source cannot also claim empty")
    return count


def validate_source(document, company_label, company_id, stamp, *, recovery=False):
    if (
        type(document.get("version")) is not int
        or document.get("version") != 1
        or document.get("complete") is not True
        or document.get("company_label") != company_label
        or document.get("company_id") != company_id
        or document.get("company_verified_before") is not True
        or document.get("company_verified_after") is not True
    ):
        raise ValueError("Incomplete collection or company mismatch")
    if "Eastern Time - New York" not in str(document.get("timezone_evidence", "")):
        raise ValueError(
            "Source settings evidence required; report timezone remains unverified"
        )
    start, finish = (
        timestamp(document["started_at"]),
        timestamp(document["finished_at"]),
    )
    if not start <= finish <= stamp or (
        not recovery and start < stamp - timedelta(hours=2)
    ):
        raise ValueError("Stale or future fuel collection")
    days = document.get("report_dates")
    if not isinstance(days, list) or days != completed_dates(start, len(days)):
        raise ValueError("Contiguous completed report dates required")
    reports = document.get("reports")
    if not isinstance(reports, list):
        raise TypeError("Each requested vehicle/date requires complete report proof")
    proofs = {}
    for report in reports:
        key = (report.get("provider_vehicle_id"), report.get("report_date"))
        if key in proofs:
            raise ValueError("Duplicate source report proof")
        proofs[key] = report
    vehicles, count = document.get("vehicles"), document.get("directory_count")
    if (
        not isinstance(vehicles, list)
        or not vehicles
        or type(count) is not int
        or not 1 <= count <= 5000
        or count != len(vehicles)
        or not document.get("terminal_evidence")
    ):
        raise ValueError("Complete vehicle directory required")
    providers, vins = set(), set()
    for vehicle in vehicles:
        pid, vin = vehicle.get("provider_vehicle_id"), vehicle.get("vin")
        if (
            not isinstance(pid, str)
            or not re.fullmatch(r"[0-9]+", pid)
            or pid in providers
            or not isinstance(vehicle.get("unit"), str)
            or not vehicle["unit"].strip()
        ):
            raise ValueError("Unique source provider and unit labels required")
        if vin is not None and (
            not isinstance(vin, str)
            or not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin)
            or vin in vins
        ):
            raise ValueError("Invalid or duplicate source VIN")
        providers.add(pid)
        if vin:
            vins.add(vin)
        records = vehicle.get("records")
        if (
            not isinstance(records, list)
            or [r.get("report_date") for r in records] != days
        ):
            raise ValueError("Every vehicle must account for every report date")
        for record in records:
            read = timestamp(record["source_read_at"])
            day = date.fromisoformat(record["report_date"])
            if (
                not start <= read <= finish
                or datetime.combine(day + timedelta(days=1), time(12), timezone.utc)
                > read
            ):
                raise ValueError(
                    "Source date is not fully completed or read time is invalid"
                )
            state = record.get("state")
            if state not in {"reported", "source_missing", "unavailable"}:
                raise ValueError("Explicit source row state required")
            proof = proofs.pop((pid, record["report_date"]), None)
            if proof is None:
                raise ValueError("Missing vehicle/date report proof")
            report_count = validate_report(proof, record["report_date"], pid)
            if (
                proof.get("selected_unit") != vehicle["unit"]
                or timestamp(proof.get("source_read_at")) != read
            ):
                raise ValueError("Source report selection/read evidence mismatch")
            if state == "reported" and report_count != 1:
                raise ValueError(
                    "Reported source vehicle absent from bound report rows"
                )
            if state != "reported" and any(
                record.get(key) is not None for key in MEASUREMENTS[:3]
            ):
                raise ValueError("Missing source must not contain fabricated readings")
            if state != "reported" and not record.get("reason"):
                raise ValueError("Missing source requires explicit reason")
    if proofs:
        raise ValueError("Report contains unaccounted provider vehicles")


def payload(document, vehicle, record):
    return FuelDailyImport.model_validate(
        {
            "vin": vehicle["vin"],
            "unit": vehicle["unit"],
            "provider_vehicle_id": vehicle["provider_vehicle_id"],
            "provider_company_id": document["company_id"],
            "report_date": record["report_date"],
            "source_timezone": None,
            "timezone_status": "unverified",
            "source_read_at": record["source_read_at"],
            "source_receipt_sha256": checksum(record),
            "identity_receipt_sha256": checksum(
                {
                    "company_id": document["company_id"],
                    "provider_vehicle_id": vehicle["provider_vehicle_id"],
                    "vin": vehicle["vin"],
                }
            ),
            **{key: record.get(key) for key in MEASUREMENTS},
        }
    )


def stored_payload(row):
    values = {
        name: getattr(row, name)
        for name in FuelDailyImport.model_fields
        if name not in {"vin", "unit"}
    }
    values.update(
        vin=row.verified_vin,
        unit=row.provider_unit,
        source_read_at=importer.aware(row.source_read_at),
    )
    result = FuelDailyImport.model_validate(values)
    if importer.digest(result) != row.request_digest:
        raise ValueError("Stored fuel evidence digest mismatch")
    return result


def canonical_payload(row):
    result = row.model_dump(mode="json")
    for key in MEASUREMENTS[:4]:
        value = getattr(row, key)
        if value is not None:
            result[key] = format(value.normalize(), "f")
    return result


async def prepare(db, document, tenant_id, actor_id):
    stamp = importer.now()
    await importer.authorize(db, tenant_id, actor_id)
    previous = (
        (
            await db.execute(
                select(FleetFuelDaily).where(
                    FleetFuelDaily.tenant_id == tenant_id,
                    FleetFuelDaily.provider_company_id == document["company_id"],
                    FleetFuelDaily.report_date.in_(
                        [date.fromisoformat(day) for day in document["report_dates"]]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    prior = {
        (row.provider_vehicle_id, row.report_date.isoformat()): row for row in previous
    }
    accepted, exclusions = [], []
    for vehicle in document["vehicles"]:
        for record in vehicle["records"]:
            entry = {
                "provider_vehicle_id": vehicle["provider_vehicle_id"],
                "unit": vehicle["unit"],
                "report_date": record["report_date"],
            }
            old = prior.get((vehicle["provider_vehicle_id"], record["report_date"]))
            if not vehicle["vin"]:
                exclusions.append({**entry, "reason": "vin_unavailable"})
                continue
            if record["state"] != "reported":
                exclusions.append(
                    {
                        **entry,
                        "reason": record["reason"],
                        "state": record["state"],
                        "prior_retained": old is not None,
                    }
                )
                continue
            try:
                row = payload(document, vehicle, record)
                # Existing importer validates full date/read membership and historical provider identity.
                importer.parse_rows({"rows": [row.model_dump(mode="json")]}, stamp)
                mapped, member = await importer.resolve_identity(
                    db, row, tenant_id, stamp
                )
            except ValueError as error:
                reason = str(error)
                safe_reason = (
                    reason
                    if reason
                    in {
                        "VIN must match exactly one active truck",
                        "Unique current membership covering source date required",
                        "Membership does not cover source date",
                        "Provider identity conflicts with existing trip history",
                        "Provider identity conflicts with fuel history",
                    }
                    else "invalid_source_reading"
                )
                exclusions.append({**entry, "reason": safe_reason})
                continue
            if old is not None:
                if (
                    old.deleted_at
                    or old.request_digest != importer.digest(row)
                    or old.vehicle_id != mapped.id
                    or old.fleet_membership_id != member.id
                ):
                    exclusions.append(
                        {
                            **entry,
                            "reason": "conflicting_immutable_fuel",
                            "prior_retained": True,
                        }
                    )
                    continue
                row = stored_payload(old)
            accepted.append(canonical_payload(row))
    current = (
        await db.execute(
            select(Vehicle.id, Vehicle.unit_number, Vehicle.vin)
            .join(FleetMembership, FleetMembership.vehicle_id == Vehicle.id)
            .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
            .where(
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
                FleetMembership.tenant_id == tenant_id,
                Customer.tenant_id == tenant_id,
                Customer.deleted_at.is_(None),
                *active_membership(stamp),
            )
        )
    ).all()
    source_vins = {v["vin"] for v in document["vehicles"] if v["vin"]}
    for vehicle_id, unit, vin in current:
        if (vin or "").strip().upper() not in source_vins:
            for day in document["report_dates"]:
                exclusions.append(
                    {
                        "vehicle_id": str(vehicle_id),
                        "unit": unit,
                        "report_date": day,
                        "reason": "source_missing",
                    }
                )
    return accepted, {
        "coverage": "partial",
        "directory_count": document["directory_count"],
        "report_dates": document["report_dates"],
        "accepted": len(accepted),
        "exclusions": exclusions,
    }


async def batches(db, rows, tenant_id, actor_id, apply=False):
    await importer.authorize(db, tenant_id, actor_id)
    result = []
    for offset in range(0, len(rows), 1000):
        parsed = importer.parse_rows(
            {"rows": rows[offset : offset + 1000]}, importer.now()
        )
        result.extend(
            (await importer.run_import(db, parsed, tenant_id, actor_id, apply=apply))[
                "rows"
            ]
        )
    return result


async def apply_verify(factory, rows, tenant_id, actor_id, receipt_path, receipt):
    async with factory() as db:
        applied = await batches(db, rows, tenant_id, actor_id, True)
        replay = await batches(db, rows, tenant_id, actor_id, True)
        if any(row["action"] != "unchanged" for row in replay):
            raise ValueError("Fuel replay changed immutable rows")
        receipt.update(stage="commit_pending", rows=applied)
        private_json(receipt_path, receipt)
        await db.commit()
    receipt.update(committed=True, stage="committed")
    private_json(receipt_path, receipt)
    async with factory() as db:
        verified = await batches(db, rows, tenant_id, actor_id, False)
        if any(row["action"] != "unchanged" for row in verified) or [
            r["fuel_id"] for r in verified
        ] != [r["fuel_id"] for r in applied]:
            raise ValueError("Committed fuel readback mismatch")
        ids = [UUID(row["fuel_id"]) for row in verified]
        visible = (
            (
                await db.execute(
                    visible_query(tenant_id, importer.now()).where(
                        FleetFuelDaily.id.in_(ids)
                    )
                )
            ).all()
            if ids
            else []
        )
        if {row[0].id for row in visible} != set(ids):
            raise ValueError(
                "Saved fuel missing from current-membership API projection"
            )
        await db.rollback()
    receipt.update(
        stage="verified",
        replay_unchanged=len(replay),
        readback_verified=len(verified),
        fleet_projection_verified=len(ids),
    )
    private_json(receipt_path, receipt)
    return receipt


async def run(
    factory,
    document,
    tenant_id,
    actor_id,
    company_label,
    company_id,
    receipt_path,
    *,
    commit=False,
    recovery=False,
):
    validate_source(
        document, company_label, company_id, importer.now(), recovery=recovery
    )
    identity = {
        "tenant_id": str(tenant_id),
        "actor_id": str(actor_id),
        "company_label": company_label,
        "company_id": company_id,
        "source_sha256": checksum(document),
    }
    path = str(receipt_path) + ".normalized.json"
    if recovery:
        if not commit:
            raise ValueError("Recovery requires explicit commit")
        normalized = json.loads(Path(path).read_text())
        receipt = json.loads(Path(receipt_path).read_text())
        if (
            receipt.get("mode") != "commit"
            or receipt.get("stage")
            not in {"validated", "commit_pending", "committed", "verified"}
            or receipt.get("normalized_sha256") != checksum(normalized)
            or any(
                record.get(key) != value
                for record in (normalized, receipt)
                for key, value in identity.items()
            )
        ):
            raise ValueError("Fuel recovery immutable identity or intent mismatch")
        rows = normalized["rows"]
        async with factory() as db:
            await batches(db, rows, tenant_id, actor_id)
            await db.rollback()
        receipt["recovery"] = True
        return await apply_verify(
            factory, rows, tenant_id, actor_id, receipt_path, receipt
        )
    async with factory() as db:
        rows, report = await prepare(db, document, tenant_id, actor_id)
        dry = await batches(db, rows, tenant_id, actor_id)
        await db.rollback()
    normalized = {**identity, "rows": rows}
    immutable_json(path, normalized)
    receipt = {
        **identity,
        "normalized_sha256": checksum(normalized),
        "mode": "commit" if commit else "dry_run",
        "committed": False,
        "stage": "validated",
        "report": report,
        "rows": dry,
    }
    private_json(receipt_path, receipt)
    if not commit:
        return receipt
    return await apply_verify(factory, rows, tenant_id, actor_id, receipt_path, receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    keys = [
        "MOTIVE_SYNC_TENANT_ID",
        "MOTIVE_SYNC_ACTOR_ID",
        "MOTIVE_COMPANY_LABEL",
        "MOTIVE_COMPANY_ID",
    ]
    if any(not os.environ.get(key) for key in keys):
        parser.error("Explicit tenant, actor and company configuration required")
    from app.db.session import AsyncSessionLocal

    result = asyncio.run(
        run(
            AsyncSessionLocal,
            json.loads(Path(args.input).read_text()),
            UUID(os.environ[keys[0]]),
            UUID(os.environ[keys[1]]),
            os.environ[keys[2]],
            os.environ[keys[3]],
            args.receipt,
            commit=args.commit,
            recovery=args.recover,
        )
    )
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "stage": result["stage"],
                "committed": result["committed"],
                "rows": len(result["rows"]),
                "excluded": len(result["report"]["exclusions"]),
            }
        )
    )


if __name__ == "__main__":
    main()
