"""Validate rendered health observations through diagnostics and telemetry contracts."""

import hashlib
import json
import re
from datetime import timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from app.db.models.customer import Customer
from app.db.models.user import User
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership
from app.schemas.dashboard_vehicle_binding import BoundTelemetryCapture
from app.schemas.fleet_diagnostic import DiagnosticCapture
from app.schemas.fleet_telemetry import TelemetryCapture
from app.services import fleet_diagnostics as service
from app.services import fleet_telemetry as telemetry
from app.services.fleet_telemetry import active_membership, now
from fastapi import HTTPException
from scripts.motive_health.targets import normalize_targets, resolve, resolve_vitals
from scripts.motive_sync.import_locations import time_value
from sqlalchemy import and_, or_, select


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
        absence = row.get("source_vin_state")
        if absence is not None and (
            vin is not None or absence not in {"not_displayed", "explicitly_empty"}
        ):
            raise ValueError("Conflicting source VIN evidence")
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
        vitals = row.get("vitals")
        if vitals is not None:
            if not isinstance(vitals, dict) or not (
                vin or absence in {"not_displayed", "explicitly_empty"}
            ):
                raise ValueError(
                    "Vitals require verified VIN or reviewed absence proof"
                )
            read = time_value(vitals["source_read_at"])
            if not started <= read <= finished:
                raise ValueError("Vitals time outside collection")
            for field, maximum in (
                ("odometer_miles", 100_000_000),
                ("engine_hours", 10_000_000),
            ):
                value = vitals.get(field)
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0 <= value <= maximum
                ):
                    raise ValueError("Invalid vitals measurement")
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
    reviewed_targets=None,
):
    targets = normalize_targets(reviewed_targets)
    if targets and expected_customer_id is None:
        raise ValueError("Reviewed health targets require a default fleet pin")
    await service.authorize(db, tenant_id, actor_id)
    results, matched = [], set()
    for row in document["vehicles"]:
        vitals = row.get("vitals")
        if vitals and any(
            vitals.get(field) is not None
            for field in ("odometer_miles", "engine_hours")
        ):
            request = uuid5(
                NAMESPACE_URL,
                f"dieselbridge-health-vitals:{tenant_id}:{source_hash(document)}:{row['provider_vehicle_id']}",
            )
            vitals_item = {
                "kind": "vitals",
                "provider_vehicle_id": row["provider_vehicle_id"],
                "client_request_id": str(request),
                "capture_id": None,
            }
            if eligible is not None and str(request) not in eligible:
                results.append({**vitals_item, "status": "excluded"})
            else:
                try:
                    read = time_value(vitals["source_read_at"])
                    vehicle, member, binding = await resolve_vitals(
                        db,
                        tenant_id,
                        row,
                        now(),
                        read,
                        expected_customer_id,
                        targets,
                        company_id,
                        company_label,
                    )
                    if not telemetry.within(member, read):
                        raise ValueError("Vitals outside current membership")
                    actor = await db.get(User, actor_id)
                    values = {
                        "client_request_id": request,
                        "fleet_customer_id": member.fleet_customer_id,
                        "vin": row["vin"],
                        "provider_company_label": company_label,
                        "provider_vehicle_id": row["provider_vehicle_id"],
                        "provider_vehicle_number": row["unit"],
                        "odometer_miles": vitals.get("odometer_miles"),
                        "engine_hours": vitals.get("engine_hours"),
                        "observed_at": None,
                        "evidence_note": json.dumps(
                            {
                                "kind": "motive_health_vitals_v1",
                                "source_read_at": vitals["source_read_at"],
                                "company_id": company_id,
                            }
                        ),
                    }
                    if binding:
                        # Fleet projection revalidates bound captures using the
                        # existing shared camelCase source-time evidence contract.
                        evidence = json.loads(values["evidence_note"])
                        evidence.update(
                            sourceReadTime=vitals["source_read_at"],
                            source_vin_state=row["source_vin_state"],
                        )
                        values.update(
                            dashboard_binding_id=binding.id,
                            source_company_id=company_id,
                            source_read_at=read,
                            source_vin_state=row["source_vin_state"],
                            evidence_note=json.dumps(evidence),
                        )
                    body = (BoundTelemetryCapture if binding else TelemetryCapture)(
                        **values
                    )
                    # Dry-run must exercise the real contract without leaving writes.
                    savepoint = await db.begin_nested() if not apply else None
                    try:
                        saved, created = await telemetry.capture(
                            db, actor, vehicle.id, body
                        )
                        if created:
                            saved.captured_at = read
                            await db.flush()
                        if binding:
                            from app.services import dashboard_vehicle_bindings

                            if (
                                saved.id
                                not in await dashboard_vehicle_bindings.valid_capture_ids(
                                    db, tenant_id, [saved]
                                )
                            ):
                                raise ValueError(
                                    "Bound vitals projection identity unavailable"
                                )
                        matched.add(vehicle.id)
                        vitals_item.update(
                            vehicle_id=str(vehicle.id),
                            capture_id=str(saved.id),
                            status=("created" if apply else "would_create")
                            if created
                            else "unchanged",
                        )
                    finally:
                        if savepoint:
                            await savepoint.rollback()
                    results.append(vitals_item)
                except HTTPException as exc:
                    reason = (
                        exc.detail.get("code") if isinstance(exc.detail, dict) else None
                    )
                    if eligible is None and reason in {
                        "exact_unique_vin_required",
                        "unique_current_membership_required",
                        "reviewed_vehicle_binding_required",
                        "reviewed_vehicle_binding_invalid",
                    }:
                        results.append(
                            {**vitals_item, "status": "excluded", "reason": reason}
                        )
                    else:
                        raise
        item = {
            "provider_vehicle_id": row["provider_vehicle_id"],
            "unit": row.get("unit"),
            "capture_id": None,
            "client_request_id": None,
        }
        if row["state"] == "unavailable":
            if row.get("vin") or row.get("source_vin_state") in {
                "not_displayed",
                "explicitly_empty",
            }:
                try:
                    vehicle, _, _ = await resolve_vitals(
                        db,
                        tenant_id,
                        row,
                        now(),
                        time_value(row["source_read_at"]),
                        expected_customer_id,
                        targets,
                        company_id,
                        company_label,
                    )
                    matched.add(vehicle.id)
                except HTTPException as exc:
                    if exc.status_code != 409 or (
                        isinstance(exc.detail, dict)
                        and exc.detail.get("code") == "reviewed_health_target_mismatch"
                    ):
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
            vehicle, member = await resolve(
                db, tenant_id, row, now(), expected_customer_id, targets
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
                expected_customer_id=member.fleet_customer_id,
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
                    [
                        or_(
                            FleetMembership.fleet_customer_id == expected_customer_id,
                            *[
                                and_(
                                    Vehicle.id == UUID(target["vehicle_id"]),
                                    FleetMembership.fleet_customer_id
                                    == UUID(target["fleet_customer_id"]),
                                )
                                for target in targets.values()
                            ],
                        )
                    ]
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
