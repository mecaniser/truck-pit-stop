"""Offline Motive location webhook boundary for the DB-036 fixture sandbox.

This module does not register an HTTP route or contact Motive. Its caller must
resolve the tenant/account and obtain a server-side secret before calling it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

MAX_BODY_BYTES = 64 * 1024
LOCATION_ACTIONS = frozenset({"vehicle_location_updated", "vehicle_location_received"})


class InvalidMotiveEvent(ValueError):
    """A fixture event failed signature or location-contract validation."""


@dataclass(frozen=True)
class MotiveLocationEvent:
    tenant_id: UUID
    provider_account_id: UUID
    event_id: str
    vehicle_id: str
    action: str
    located_at: datetime
    lat: float
    lng: float
    speed_mph: float | None
    bearing_degrees: float | None
    virtual_odometer_miles: float | None
    engine_hours: float | None
    payload_sha256: str


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidMotiveEvent("duplicate JSON key")
        result[key] = value
    return result


def _identifier(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise InvalidMotiveEvent(f"invalid {field}")
    identifier = str(value).strip()
    if not identifier or len(identifier) > 120:
        raise InvalidMotiveEvent(f"invalid {field}")
    return identifier


def _number(value: Any, field: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidMotiveEvent(f"invalid {field}")
    try:
        number = float(value)
    except OverflowError as exc:
        raise InvalidMotiveEvent(f"invalid {field}") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise InvalidMotiveEvent(f"invalid {field}")
    return number


def _optional_number(payload: dict[str, Any], field: str, maximum: float) -> float | None:
    value = payload.get(field)
    if value is None:
        return None
    return _number(value, field, minimum=0, maximum=maximum)


def verify_and_normalize_location(
    raw_body: bytes,
    signature: str,
    shared_secret: str,
    *,
    tenant_id: UUID,
    provider_account_id: UUID,
) -> MotiveLocationEvent:
    """Verify Motive's HMAC-SHA1 over raw bytes, then normalize one location.

    The UUIDs must come from trusted tenant-scoped account lookup, never from
    the webhook body. Replay and latest-point ordering belong to persistence.
    """
    if not isinstance(tenant_id, UUID) or not isinstance(provider_account_id, UUID):
        raise InvalidMotiveEvent("missing trusted account identity")
    if not isinstance(raw_body, bytes) or not 0 < len(raw_body) <= MAX_BODY_BYTES:
        raise InvalidMotiveEvent("invalid body size")
    if not isinstance(shared_secret, str) or not shared_secret:
        raise InvalidMotiveEvent("missing fixture secret")
    if not isinstance(signature, str) or len(signature) != 40:
        raise InvalidMotiveEvent("invalid signature")
    expected = hmac.new(shared_secret.encode("utf-8"), raw_body, hashlib.sha1).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        raise InvalidMotiveEvent("invalid signature")

    try:
        payload = json.loads(raw_body, object_pairs_hook=_unique_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidMotiveEvent("invalid JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidMotiveEvent("expected object")
    action = payload.get("action")
    if action not in LOCATION_ACTIONS:
        raise InvalidMotiveEvent("unsupported action")
    event_id = _identifier(payload.get("id"), "event id")
    vehicle_id = _identifier(payload.get("vehicle_id"), "vehicle id")
    try:
        located_at = datetime.fromisoformat(payload["located_at"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise InvalidMotiveEvent("invalid located_at") from exc
    if located_at.tzinfo is None:
        raise InvalidMotiveEvent("located_at must include timezone")
    located_at = located_at.astimezone(timezone.utc)
    return MotiveLocationEvent(
        tenant_id=tenant_id,
        provider_account_id=provider_account_id,
        event_id=event_id,
        vehicle_id=vehicle_id,
        action=action,
        located_at=located_at,
        lat=_number(payload.get("lat"), "lat", minimum=-90, maximum=90),
        lng=_number(payload.get("lon"), "lon", minimum=-180, maximum=180),
        speed_mph=_optional_number(payload, "speed", 300),
        bearing_degrees=_optional_number(payload, "bearing", 360),
        virtual_odometer_miles=_optional_number(payload, "odometer", 100_000_000),
        engine_hours=_optional_number(payload, "engine_hours", 10_000_000),
        payload_sha256=hashlib.sha256(raw_body).hexdigest(),
    )
