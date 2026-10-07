"""Validate rendered health observations and write only through diagnostics service."""

import hashlib
import json
import re
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from app.db.models.customer import Customer
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_diagnostic import DiagnosticCapture
from app.services import fleet_diagnostics as service
from app.services.fleet_telemetry import active_membership, now
from fastapi import HTTPException
from scripts.motive_sync.import_locations import time_value
from sqlalchemy import select


def source_hash(document):
    return hashlib.sha256(
        json.dumps(
            document, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def validate(document, company_label, company_id, *, recovery=False):
    if (
        type(document.get("version")) is not int
        or document.get("version") != 1
        or document.get("complete") is not True
        or document.get("company_label") != company_label
        or document.get("company_id") != company_id
        or document.get("company_verified_before") is not True
        or document.get("company_verified_after") is not True
    ):
        raise ValueError("Incomplete collection or source company mismatch")
    if "Eastern Time - New York" not in str(document.get("timezone_evidence", "")):
        raise ValueError("Missing source timezone evidence")
    started, finished = (
        time_value(document["started_at"]),
        time_value(document["finished_at"]),
    )
    stamp = now()
    if not started <= finished <= stamp or (
        not recovery and started < stamp - timedelta(hours=2)
    ):
        raise ValueError("Stale or future collection")
    vehicles = document.get("vehicles")
    count = document.get("health_directory_count")
    if (
        not isinstance(vehicles, list)
        or type(count) is not int
        or count != len(vehicles)
        or not 0 <= count <= 5000
        or not document.get("terminal_evidence")
    ):
        raise ValueError("Complete health directory and terminal evidence required")
    providers, vins = set(), set()
    for row in vehicles:
        provider, vin = row.get("provider_vehicle_id"), row.get("vin")
        if (
            not isinstance(provider, str)
            or not provider
            or provider in providers
            or (vin is not None and (not isinstance(vin, str) or vin in vins))
        ):
            raise ValueError("Duplicate or invalid source identity")
        if not isinstance(row.get("unit"), str) or not row["unit"].strip():
            raise ValueError("Source unit label required")
        providers.add(provider)
        if vin is not None:
            # Validation below also covers captured rows, but unavailable VINs cannot silently be malformed.
            if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
                raise ValueError("Invalid source VIN")
            vins.add(vin)
        if row.get("state") not in ("captured", "unavailable"):
            raise ValueError("Invalid health capture state")
        read = time_value(row["source_read_at"])
        if not started <= read <= finished:
            raise ValueError("Read time outside collection")
        if row["state"] == "unavailable":
            if row.get("codes") or row.get("explicit_empty"):
                raise ValueError("Unavailable source must not claim health readings")
        elif not vin:
            raise ValueError("Captured health requires verified VIN")
    return document


def body_for(document, row, tenant_id):
    # Stable whole-source identity survives uncertain commits; never recapture old rows.
    request = uuid5(
        NAMESPACE_URL,
        f"dieselbridge-health:{tenant_id}:{source_hash(document)}:{row['provider_vehicle_id']}",
    )
    return DiagnosticCapture.model_validate(
        {
            "client_request_id": request,
            "vin": row["vin"],
            "provider_vehicle_id": row["provider_vehicle_id"],
            "source_company_id": document["company_id"],
            "source_company_label": document["company_label"],
            "company_verified_before": document["company_verified_before"],
            "company_verified_after": document["company_verified_after"],
            "source_read_at": row["source_read_at"],
            "coverage": "complete",
            "explicit_empty": row["explicit_empty"],
            "source_scope": row["source_scope"],
            "count_before": row["count_before"],
            "count_after": row["count_after"],
            "codes": row["codes"],
        }
    )


async def batch(
    db,
    document,
    tenant_id,
    actor_id,
    company_label,
    company_id,
    *,
    apply=False,
    expected_customer_id=None,
    eligible=None,
):
    await service.authorize(db, tenant_id, actor_id)
    results, matched = [], set()
    for row in document["vehicles"]:
        item = {
            "provider_vehicle_id": row["provider_vehicle_id"],
            "unit": row.get("unit"),
            "capture_id": None,
            "client_request_id": None,
        }
        if row["state"] == "unavailable":
            if row.get("vin"):
                try:
                    vehicle, _ = await service.resolve(
                        db, tenant_id, row["vin"], now(), expected_customer_id
                    )
                    matched.add(vehicle.id)
                except HTTPException as exc:
                    if exc.status_code != 409:
                        raise
            results.append(
                {
                    **item,
                    "status": "unavailable",
                    "reason": row.get("reason", "source_unavailable"),
                }
            )
            continue
        body = body_for(document, row, tenant_id)
        item["client_request_id"] = str(body.client_request_id)
        # Immutable eligible set prevents recovery silently dropping previously approved rows.
        if eligible is not None and str(body.client_request_id) not in eligible:
            results.append(
                {**item, "status": "excluded", "reason": "not_in_validated_attempt"}
            )
            continue
        try:
            vehicle, _ = await service.resolve(
                db, tenant_id, body.vin, now(), expected_customer_id
            )
            matched.add(vehicle.id)
            capture, action = await service.capture(
                db,
                tenant_id,
                actor_id,
                body,
                company_label,
                company_id,
                apply=apply,
                expected_customer_id=expected_customer_id,
            )
        except HTTPException as exc:
            reason = exc.detail.get("code") if isinstance(exc.detail, dict) else None
            if eligible is None and reason in {
                "exact_unique_vin_required",
                "unique_current_membership_required",
                "source_outside_current_membership",
            }:
                results.append({**item, "status": "excluded", "reason": reason})
                continue
            raise
        results.append(
            {
                **item,
                "status": action,
                "capture_id": str(capture.id) if capture else None,
                "vehicle_id": str(vehicle.id),
            }
        )
    # Absent source vehicles remain missing, never healthy. Current fleet only.
    members = (
        await db.execute(
            select(Vehicle.id, Vehicle.unit_number)
            .join(FleetMembership, FleetMembership.vehicle_id == Vehicle.id)
            .join(Customer, Customer.id == FleetMembership.fleet_customer_id)
            .where(
                Vehicle.tenant_id == tenant_id,
                Vehicle.deleted_at.is_(None),
                FleetMembership.tenant_id == tenant_id,
                Customer.tenant_id == tenant_id,
                Customer.deleted_at.is_(None),
                *active_membership(now()),
                *(
                    [FleetMembership.fleet_customer_id == expected_customer_id]
                    if expected_customer_id
                    else []
                ),
            )
        )
    ).all()
    for vehicle_id, unit in members:
        if vehicle_id not in matched:
            results.append(
                {
                    "vehicle_id": str(vehicle_id),
                    "unit": unit,
                    "status": "source_missing",
                    "capture_id": None,
                }
            )
    return results
