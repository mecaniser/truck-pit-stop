"""Explicit, reviewed exceptions to the health worker's default fleet pin."""

import re
from uuid import UUID

from app.services import fleet_diagnostics as diagnostics
from app.services.fleet_telemetry import fail
from fastapi import HTTPException


def normalize_targets(value):
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > 100:
        raise ValueError("Health targets must be a bounded provider mapping")
    result, vehicles = {}, set()
    for provider, target in value.items():
        if (
            not isinstance(provider, str)
            or not re.fullmatch(r"[0-9]{1,120}", provider)
            or not isinstance(target, dict)
            or set(target) != {"vehicle_id", "fleet_customer_id"}
        ):
            raise ValueError("Invalid reviewed health target")
        normalized = {}
        for field in ("vehicle_id", "fleet_customer_id"):
            if not isinstance(target[field], str):
                raise TypeError("Health target IDs must be UUID strings")
            normalized[field] = str(UUID(target[field]))
        if normalized["vehicle_id"] in vehicles:
            raise ValueError("Duplicate reviewed health vehicle")
        vehicles.add(normalized["vehicle_id"])
        result[provider] = normalized
    return dict(sorted(result.items()))


async def resolve(db, tenant_id, row, stamp, default_customer_id, targets):
    target = targets.get(row["provider_vehicle_id"])
    customer_id = UUID(target["fleet_customer_id"]) if target else default_customer_id
    try:
        vehicle, member = await diagnostics.resolve(
            db, tenant_id, row["vin"], stamp, customer_id
        )
    except HTTPException as exc:
        if target and exc.status_code == 409:
            fail(409, "reviewed_health_target_mismatch")
        raise
    if target and str(vehicle.id) != target["vehicle_id"]:
        fail(409, "reviewed_health_target_mismatch")
    return vehicle, member


async def resolve_vitals(
    db,
    tenant_id,
    row,
    stamp,
    source_time,
    default_customer_id,
    targets,
    company_id,
    company_label,
):
    if row.get("vin") is not None:
        vehicle, member = await resolve(
            db, tenant_id, row, stamp, default_customer_id, targets
        )
        return vehicle, member, None
    from app.services import dashboard_vehicle_bindings as bindings

    target = targets.get(row["provider_vehicle_id"])
    customer_id = UUID(target["fleet_customer_id"]) if target else default_customer_id
    try:
        vehicle, member, binding = await bindings.resolve(
            db,
            tenant_id,
            company_id,
            row["provider_vehicle_id"],
            source_time,
            company_label=company_label,
            expected_customer_id=customer_id,
        )
    except HTTPException as exc:
        if target and exc.status_code == 409:
            fail(409, "reviewed_health_target_mismatch")
        raise
    if target and str(vehicle.id) != target["vehicle_id"]:
        fail(409, "reviewed_health_target_mismatch")
    return vehicle, member, binding
