"""Validate a complete driver directory before immutable driver-record imports."""

import re
from datetime import timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from app.db.models.customer import Customer
from app.db.models.fleet_driver_record import FleetDriverDirectoryCapture
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.fleet_driver_record import DriverRecordCapture, DriverRecordContent
from app.services import fleet_driver_records as service
from app.services.fleet_diagnostics import authorize, resolve
from app.services.fleet_telemetry import active_membership, now
from fastapi import HTTPException
from scripts.motive_health.import_health import source_hash
from scripts.motive_sync.import_locations import time_value
from sqlalchemy import select


def body_for(document, row, tenant_id):
    request = uuid5(
        NAMESPACE_URL,
        f"dieselbridge-driver-record:{tenant_id}:{source_hash(document)}:{row['provider_driver_id']}",
    )
    return DriverRecordCapture.model_validate(
        {
            **{key: row[key] for key in DriverRecordContent.model_fields if key in row},
            "client_request_id": request,
            "vin": row["vin"],
            "provider_vehicle_id": row["provider_vehicle_id"],
            "provider_driver_id": row["provider_driver_id"],
            "driver_name": row["driver_name"],
            "source_company_id": document["company_id"],
            "source_company_label": document["company_label"],
            "company_verified_before": document["company_verified_before"],
            "company_verified_after": document["company_verified_after"],
            "assignment_verified_before": row["assignment_verified_before"],
            "assignment_verified_after": row["assignment_verified_after"],
            "source_read_at": row["source_read_at"],
        }
    )


def valid_text(value, bound=160):
    return (
        isinstance(value, str)
        and 0 < len(value.strip()) <= bound
        and not any(ord(char) == 0 or 0xD800 <= ord(char) <= 0xDFFF for char in value)
    )


def validate(document, company_label, company_id, *, recovery=False):
    if not isinstance(document, dict) or (
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
    rows, count = document.get("drivers"), document.get("driver_directory_count")
    if (
        not isinstance(rows, list)
        or type(count) is not int
        or count != len(rows)
        or not 0 <= count <= 5000
        or not valid_text(document.get("terminal_evidence"), 255)
    ):
        raise ValueError("Complete driver directory and terminal evidence required")
    footer = re.fullmatch(
        r"Showing (0|[1-9][0-9]*) of (0|[1-9][0-9]*)", document["terminal_evidence"]
    )
    if not footer or int(footer[1]) != count or int(footer[2]) != count:
        raise ValueError(
            "Driver directory terminal count disagrees with complete source"
        )
    ranges = document.get("performance_ranges")
    if not isinstance(ranges, list) or len(ranges) != 3:
        raise ValueError("Verified provider performance ranges required")
    expected_bands = {"Fair": "red", "Good": "yellow", "Excellent": "green"}
    expected_labels = tuple(expected_bands)
    previous_max = 49
    for index, band in enumerate(ranges):
        if (
            not isinstance(band, dict)
            or band.get("label") != expected_labels[index]
            or band.get("band") != expected_bands[band["label"]]
            or type(band.get("min")) is not int
            or type(band.get("max")) is not int
            or not 0 <= band["min"] <= band["max"] <= 100
            or band["min"] != previous_max + 1
        ):
            raise ValueError("Invalid or overlapping provider performance ranges")
        previous_max = band["max"]
    if previous_max != 100:
        raise ValueError(
            "Provider performance ranges must cover the supported 50-100 scale"
        )
    providers, captured_vehicles, captured_vins = set(), set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid source row")  # noqa: TRY004 - uniform document rejection
        provider, vehicle, vin = (
            row.get("provider_driver_id"),
            row.get("provider_vehicle_id"),
            row.get("vin"),
        )
        if (
            not valid_text(provider, 120)
            or provider in providers
            or not valid_text(row.get("driver_name"))
        ):
            raise ValueError("Duplicate or invalid source driver identity")
        providers.add(provider)
        if vehicle is not None and not valid_text(vehicle, 120):
            raise ValueError("Invalid source vehicle identity")
        if row.get("unit") is not None and not valid_text(row["unit"], 120):
            raise ValueError("Invalid source unit label")
        if vin is not None and (
            not isinstance(vin, str) or not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin)
        ):
            raise ValueError("Invalid source VIN")
        if row.get("state") not in {"captured", "unavailable"}:
            raise ValueError("Invalid driver capture state")
        if not started <= time_value(row["source_read_at"]) <= finished:
            raise ValueError("Read time outside collection")
        if row["state"] == "unavailable":
            if not valid_text(row.get("reason"), 255) or any(
                key in row for key in DriverRecordContent.model_fields
            ):
                raise ValueError(
                    "Unavailable source must explain absence without claiming readings"
                )
            continue
        if (
            not vehicle
            or not vin
            or vehicle in captured_vehicles
            or vin in captured_vins
        ):
            raise ValueError(
                "Captured driver requires unique verified vehicle/VIN assignment"
            )
        captured_vehicles.add(vehicle)
        captured_vins.add(vin)
        if row.get("source_timezone") != "America/New_York":
            raise ValueError("Captured driver requires verified source timezone")
        # Validate every nested reading before a database transaction can write.
        capture = body_for(document, row, UUID(int=0))
        if capture.safety.band != "unknown":
            matching = [
                band
                for band in ranges
                if capture.safety.score is not None
                and band["min"] <= capture.safety.score <= band["max"]
            ]
            if (
                len(matching) != 1
                or capture.safety.band != matching[0]["band"]
                or capture.safety.band_label
                != f"{matching[0]['label']} ({matching[0]['min']}–{matching[0]['max']})"
            ):
                raise ValueError(
                    "Safety band disagrees with provider performance ranges"
                )
    return document


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
    if not expected_customer_id:
        raise ValueError("Explicit fleet customer configuration required")
    await authorize(db, tenant_id, actor_id)
    customer = (
        await db.execute(
            select(Customer.id).where(
                Customer.id == expected_customer_id,
                Customer.tenant_id == tenant_id,
                Customer.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not customer:
        raise ValueError("Configured fleet customer is unavailable")
    if apply:
        digest = source_hash(document)
        existing = (
            await db.execute(
                select(FleetDriverDirectoryCapture).where(
                    FleetDriverDirectoryCapture.tenant_id == tenant_id,
                    FleetDriverDirectoryCapture.fleet_customer_id
                    == expected_customer_id,
                    FleetDriverDirectoryCapture.source_sha256 == digest,
                )
            )
        ).scalar_one_or_none()
        if not existing:
            # Even an empty complete directory suppresses formerly assigned drivers.
            db.add(
                FleetDriverDirectoryCapture(
                    tenant_id=tenant_id,
                    fleet_customer_id=expected_customer_id,
                    source_company_id=company_id,
                    source_company_label=company_label,
                    source_read_at=time_value(document["finished_at"]),
                    source_sha256=digest,
                    assignments=[
                        {
                            "provider_driver_id": row["provider_driver_id"],
                            "provider_vehicle_id": row.get("provider_vehicle_id"),
                        }
                        for row in document["drivers"]
                    ],
                )
            )
            await db.flush()
    results, matched = [], set()
    for row in document["drivers"]:
        item = {
            "provider_driver_id": row["provider_driver_id"],
            "provider_vehicle_id": row.get("provider_vehicle_id"),
            "unit": row.get("unit"),
            "capture_id": None,
            "client_request_id": None,
        }
        if row["state"] == "unavailable":
            if row.get("vin"):
                try:
                    vehicle, _ = await resolve(
                        db, tenant_id, row["vin"], now(), expected_customer_id
                    )
                    matched.add(vehicle.id)
                except HTTPException as exc:
                    if exc.status_code != 409:
                        raise
            results.append({**item, "status": "unavailable", "reason": row["reason"]})
            continue
        body = body_for(document, row, tenant_id)
        item["client_request_id"] = str(body.client_request_id)
        if eligible is not None and str(body.client_request_id) not in eligible:
            results.append(
                {**item, "status": "excluded", "reason": "not_in_validated_attempt"}
            )
            continue
        try:
            vehicle, _ = await resolve(
                db, tenant_id, body.vin, now(), expected_customer_id
            )
            matched.add(vehicle.id)
            record, action = await service.capture(
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
                "source_before_driver_assignment_change",
            }:
                results.append({**item, "status": "excluded", "reason": reason})
                continue
            raise
        results.append(
            {
                **item,
                "status": action,
                "capture_id": str(record.id) if record else None,
                "vehicle_id": str(vehicle.id),
            }
        )
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
                FleetMembership.fleet_customer_id == expected_customer_id,
                *active_membership(now()),
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
