"""Synthetic, offline Motive webhook contract fixtures."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services.motive_events import InvalidMotiveEvent, verify_and_normalize_location

SECRET = "db036-synthetic-test-secret"
TENANT = uuid4()
ACCOUNT = uuid4()


def signed_event(**changes):
    payload = {
        "action": "vehicle_location_updated",
        "id": "synthetic-location-1",
        "vehicle_id": 123,
        "located_at": "2026-09-28T12:00:00Z",
        "lat": 35.1168,
        "lon": -80.7237,
        "speed": 54.5,
        "bearing": 92,
        "odometer": 541190.25,
        "engine_hours": 8123.5,
    }
    payload.update(changes)
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(SECRET.encode(), body, hashlib.sha1).hexdigest()
    return body, signature


def normalize(body, signature, *, tenant_id=TENANT, provider_account_id=ACCOUNT):
    return verify_and_normalize_location(
        body, signature, SECRET, tenant_id=tenant_id, provider_account_id=provider_account_id
    )


def test_signed_location_is_normalized_with_trusted_account_identity():
    body, signature = signed_event()
    event = normalize(body, signature)
    assert (event.tenant_id, event.provider_account_id) == (TENANT, ACCOUNT)
    assert (event.event_id, event.vehicle_id) == ("synthetic-location-1", "123")
    assert (event.lat, event.lng, event.speed_mph, event.bearing_degrees) == (
        35.1168, -80.7237, 54.5, 92.0
    )
    assert event.located_at == datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    assert event.virtual_odometer_miles == 541190.25
    assert event.payload_sha256 == hashlib.sha256(body).hexdigest()


def test_received_action_and_optional_motion_are_supported():
    body, signature = signed_event(action="vehicle_location_received", speed=None, bearing=None)
    event = normalize(body, signature)
    assert event.action == "vehicle_location_received"
    assert event.speed_mph is None and event.bearing_degrees is None


def test_same_external_event_id_keeps_trusted_account_namespace():
    body, signature = signed_event()
    other_tenant, other_account = uuid4(), uuid4()
    first = normalize(body, signature)
    second = normalize(body, signature, tenant_id=other_tenant, provider_account_id=other_account)
    assert first.event_id == second.event_id
    assert (first.tenant_id, first.provider_account_id) != (
        second.tenant_id, second.provider_account_id
    )


@pytest.mark.parametrize("change", [
    {"lat": 91}, {"lon": -181}, {"speed": -1}, {"speed": True},
    {"bearing": 361}, {"odometer": "541190"}, {"vehicle_id": ""},
    {"located_at": "2026-09-28T12:00:00"}, {"action": "vehicle_upserted"},
])
def test_invalid_location_fields_are_rejected(change):
    body, signature = signed_event(**change)
    with pytest.raises(InvalidMotiveEvent):
        normalize(body, signature)


def test_bad_signature_is_rejected_before_json_parsing():
    body, signature = signed_event()
    with pytest.raises(InvalidMotiveEvent, match="signature"):
        normalize(body + b"garbage", signature)


def test_duplicate_json_keys_are_rejected():
    body = b'{"action":"vehicle_location_updated","id":"1","vehicle_id":1,"located_at":"2026-09-28T12:00:00Z","lat":1,"lat":2,"lon":3}'
    signature = hmac.new(SECRET.encode(), body, hashlib.sha1).hexdigest()
    with pytest.raises(InvalidMotiveEvent, match="duplicate JSON key"):
        normalize(body, signature)


def test_trusted_tenant_and_account_are_required():
    body, signature = signed_event()
    with pytest.raises(InvalidMotiveEvent, match="account identity"):
        normalize(body, signature, tenant_id=None)


def test_body_limit_prevents_oversized_fixture():
    body = b" " * (64 * 1024 + 1)
    signature = hmac.new(SECRET.encode(), body, hashlib.sha1).hexdigest()
    with pytest.raises(InvalidMotiveEvent, match="body size"):
        normalize(body, signature)
