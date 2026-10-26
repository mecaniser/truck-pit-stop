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
from app.schemas.fleet_trip import TripImport, DashboardTripImport
from app.services import dashboard_vehicle_bindings as bindings
from app.services.fleet_telemetry import active_membership
from scripts.motive_sync.runner import private_json
from scripts.prepare_motive_trip_history import ZONE, endpoint, normalize, timestamp
from sqlalchemy import func, select

from scripts import import_motive_trips as importer
from scripts.motive_sync import trip_coverage


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
            not (trip_coverage.FLOOR if document.get("plan") else today - timedelta(days=2)) <= start <= end <= today
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
        if window["status"] == "empty":
            if not trip_coverage.valid_empty_proof(window):
                raise ValueError("Settled rendered-date empty proof required")
            if timestamp(window["empty_proof"]["first_observed_at"]) < started:
                raise ValueError("Empty proof predates collection")
        covered.update(start + timedelta(days=i) for i in range((end - start).days + 1))
    if document.get("plan"):
        plan = document["plan"]
        expected = trip_coverage.scope(
            os.environ["MOTIVE_SYNC_TENANT_ID"], os.environ["MOTIVE_SYNC_ACTOR_ID"],
            company_id, company_label, os.environ.get("MOTIVE_TRIPS_BASELINE", "2026-04-01"))
        trip_coverage.validate_plan(plan, expected, today)
        if len(windows) != 1 or windows[0]["start"] != windows[0]["end"] or windows[0]["start"] not in plan["days"]:
            raise ValueError("Source does not match planned daily window")
    elif covered != {today - timedelta(days=i) for i in range(3)}:
        raise ValueError(
            "Daily reconciliation must cover today and the preceding two days"
        )


def prior_payload(trip):
    """Preserve immutable fields, including original source read and fuel metrics."""
    values = {
        name: getattr(trip, name)
        for name in (DashboardTripImport if trip.dashboard_binding_id else TripImport).model_fields
        if name not in {"vin", "unit"}
    }
    values.update(vin=trip.verified_vin, unit=trip.provider_unit)
    for name in ("started_at", "ended_at", "source_read_at"):
        values[name] = importer.aware(values[name])
    payload = (DashboardTripImport if trip.dashboard_binding_id else TripImport).model_validate(values)
    if importer.digest(payload) != trip.request_digest:
        raise ValueError("Stored trip does not match its immutable digest")
    return payload.model_dump(mode="json")


def verify_prior_coverage(windows, previous):
    """A complete overlapping report must still contain every retained identity."""
    source_identities = set()
    for window in windows:
        for raw in window["rows"]:
            try:
                if not isinstance(raw, dict):
                    raise TypeError("invalid_row")
                cells, links = raw.get("cells"), raw.get("links")
                if (
                    not isinstance(cells, list)
                    or len(cells) < 2
                    or not isinstance(cells[1], str)
                    or not isinstance(links, list)
                    or len(links) != 1
                    or not isinstance(links[0], str)
                ):
                    raise ValueError("invalid_identity")
                provider = re.fullmatch(
                    r"(?:https://app\.gomotive\.com/en-US/)?#/fleetview/vehicles/summary/([0-9]+)",
                    links[0],
                )
                if provider is None:
                    raise ValueError("invalid_provider_link")
                departure, _ = endpoint(cells[1])
                source_identities.add((provider.group(1), departure))
            except (ValueError, TypeError, KeyError, OverflowError):
                # New malformed rows remain explicit normalization exclusions.
                # They cannot satisfy coverage for an existing saved identity.
                continue
    stored_identities = {
        (trip.provider_vehicle_id, importer.aware(trip.started_at)) for trip in previous
    }
    covered = len(stored_identities & source_identities)
    missing = len(stored_identities - source_identities)
    if missing:
        raise ValueError(
            f"incomplete_prior_coverage: prior={len(stored_identities)} covered={covered} missing={missing}"
        )
    return {
        "prior_identity_count": len(stored_identities),
        "prior_identity_covered": covered,
    }


async def prepare(db, document, tenant_id, actor_id, stamp):
    await importer.authorize(db, tenant_id, actor_id)
    mappings, exclusions, membership_scope, bound_vehicle_ids = [], [], [], set()
    for source in document["vehicles"]:
        reason = None
        if not source["vin"] and source.get("source_vin_state"):
            if source["provider_vehicle_id"] != "5981300" or document["company_id"] != "KT8934277":
                raise ValueError("Unreviewed placeholder source")
            before, after = source.get("identity_before"), source.get("identity_after")
            if not isinstance(before, dict) or not isinstance(after, dict):
                raise ValueError("Positive placeholder source checks required")
            state = source["source_vin_state"]
            if state not in {"not_displayed", "explicitly_empty"} or any(proof.get("vin") is not None or proof.get("source_vin_state") != state for proof in (before, after)):
                raise ValueError("Placeholder source identity changed")
            first_read, last_read = timestamp(before["read_at"]), timestamp(after["read_at"])
            if not timestamp(document["started_at"]) <= first_read <= min(timestamp(w["source_read_at"]) for w in document["windows"]) <= max(timestamp(w["source_read_at"]) for w in document["windows"]) <= last_read <= timestamp(document["finished_at"]):
                raise ValueError("Placeholder checks do not bracket source")
            vehicle, member, binding = await bindings.resolve(db, tenant_id, document["company_id"], source["provider_vehicle_id"], last_read, company_label=document["company_label"])
            if binding.placeholder_vin != "PENDING-26":
                raise ValueError("Only the reviewed PENDING-26 trip binding is supported")
            bound_vehicle_ids.add(str(vehicle.id))
            mappings.append({"provider_vehicle_id": source["provider_vehicle_id"], "vin": None, "unit": source["unit"],
                "effective_from": max(importer.aware(member.effective_from), importer.aware(binding.effective_from)).isoformat(),
                "dashboard_binding_id": str(binding.id), "source_company_id": document["company_id"],
                "source_company_label": document["company_label"], "source_vin_state": state})
            membership_scope.append({"provider_vehicle_id": source["provider_vehicle_id"], "vehicle_id": str(vehicle.id), "membership_id": str(member.id),
                "effective_from": importer.aware(member.effective_from).isoformat(), "effective_to": importer.aware(member.effective_to).isoformat() if member.effective_to else None,
                "binding_id": str(binding.id), "binding_from": importer.aware(binding.effective_from).isoformat(), "binding_to": importer.aware(binding.effective_to).isoformat() if binding.effective_to else None})
        elif not source["vin"]:
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
                    membership_scope.append({"provider_vehicle_id": source["provider_vehicle_id"], "membership_id": str(members[0].id), "vehicle_id": str(vehicles[0].id), "effective_from": importer.aware(members[0].effective_from).isoformat(), "effective_to": importer.aware(members[0].effective_to).isoformat() if members[0].effective_to else None})
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
    # Inventory current tenant-authorized trucks independently of the source directory.
    authorized = (await db.execute(select(Vehicle, FleetMembership).join(
        FleetMembership, (FleetMembership.vehicle_id == Vehicle.id) & (FleetMembership.tenant_id == Vehicle.tenant_id)
    ).join(Customer, Customer.id == FleetMembership.fleet_customer_id).where(
        Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None),
        Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None), *active_membership(stamp)
    ))).all()
    source_vins = {v["vin"] for v in document["vehicles"] if v["vin"]}
    missing_vehicles = [{"vehicle_id": str(v.id), "membership_id": str(m.id),
        "vin": v.vin.strip().upper() if v.vin else None,
        "effective_from": importer.aware(m.effective_from).isoformat(),
        "effective_to": importer.aware(m.effective_to).isoformat() if m.effective_to else None,
        "reason": "absent_from_source_directory"} for v, m in authorized
        if str(v.id) not in bound_vehicle_ids and (not v.vin or v.vin.strip().upper() not in source_vins)]
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
    prior_coverage = verify_prior_coverage(document["windows"], previous)
    windows = [
        {key: w[key] for key in ("start", "end", "source_read_at", "status", "rows")}
        for w in document["windows"]
    ]
    base = {"tenant_id": str(tenant_id), "company_label": document["company_label"]}
    rows, report = normalize(
        {**base, "windows": windows},
        {**base, "vehicles": mappings},
        {"rows": [prior_payload(trip) for trip in previous]},
        now=stamp, allow_binding=True,
    )
    report.update(prior_coverage)
    report["vehicle_exclusions"] = exclusions
    report["directory_count"] = len(document["vehicles"])
    report["matched_vehicles"] = len(mappings)
    report["mapping_scope"] = mappings
    if document.get("plan"):
        day = document["windows"][0]["start"]
        providers = []
        global_reasons = []
        reasons = {}
        for exclusion in report["exclusions"]:
            raw = document["windows"][exclusion["window"]]["rows"][exclusion["row"]]
            links = raw.get("links", []) if isinstance(raw, dict) else []
            match = re.fullmatch(r"(?:https://app\.gomotive\.com/en-US/)?#/fleetview/vehicles/summary/([0-9]+)", links[0]) if len(links) == 1 and isinstance(links[0], str) else None
            if match:
                reasons.setdefault(match.group(1), []).append(exclusion["reason"])
            else:
                global_reasons.append(exclusion["reason"])
        for vehicle in document["vehicles"]:
            pid = vehicle["provider_vehicle_id"]
            issues = reasons.get(pid, []) + global_reasons + [e["reason"] for e in exclusions if e["provider_vehicle_id"] == pid]
            count = sum(row["provider_vehicle_id"] == pid for row in rows)
            mapping = next((m for m in mappings if m["provider_vehicle_id"] == pid), None)
            day_start = datetime.combine(date.fromisoformat(day), datetime.min.time(), ZONE)
            day_end = datetime.combine(date.fromisoformat(day) + timedelta(days=1), datetime.min.time(), ZONE)
            eligible_from = timestamp(mapping["effective_from"]) if mapping else None
            eligibility = "unknown" if eligible_from is None else "outside_membership" if eligible_from >= day_end else "partial_day" if eligible_from > day_start else "full_day"
            if eligibility == "outside_membership":
                issues.append("outside_membership")
            providers.append({"provider_vehicle_id": pid, "vin": vehicle["vin"],
                              "eligible_count": count, "exclusions": sorted(set(issues)),
                              "eligibility": eligibility, "eligible_from": mapping["effective_from"] if mapping else None,
                              "status": "ineligible" if eligibility == "outside_membership" and set(issues) <= {"outside_membership"} else "unresolved" if issues else "verified_saved" if count else "verified_empty"})
        providers.extend({"vehicle_id": v["vehicle_id"], "vin": v["vin"],
            "provider_vehicle_id": None, "eligible_count": 0,
            "exclusions": [v["reason"]], "status": "unresolved"} for v in missing_vehicles)
        closed_day = trip_coverage.day_closed(day, document["windows"][0]["source_read_at"])
        if not closed_day:
            for provider in providers:
                if provider["status"] not in {"unresolved", "ineligible"}:
                    provider["status"] = "provisional"
        report["coverage"] = {
            "scope": document["plan"]["scope"], "day": day,
            "status": "provisional" if not closed_day else "examined_with_exclusions" if any(p["exclusions"] for p in providers) else "verified",
            "providers": providers,
            "mapping_sha256": trip_coverage.mapping_digest([{k: v for k, v in source.items() if k not in {"identity_before", "identity_after"}} for source in document["vehicles"]], mappings, membership_scope, missing_vehicles),
        }
    return [
        (DashboardTripImport if row.get("dashboard_binding_id") else TripImport).model_validate(row).model_dump(mode="json") for row in rows
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
            {"rows": rows[offset : offset + 1000]}, datetime.now(timezone.utc), allow_binding=True
        )
        receipt = await importer.run_import(db, batch, tenant_id, actor_id, apply=apply, allow_binding=True)
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
    if document.get("plan"):
        normalized["coverage"] = report["coverage"]
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
    if document.get("plan"):
        receipt["coverage"] = report["coverage"]
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
    if normalized.get("coverage") != receipt.get("coverage"):
        raise ValueError("Recovery coverage mismatch")
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
