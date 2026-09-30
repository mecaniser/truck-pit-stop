"""Full-scope synthetic provider and durable inbox acceptance; no live calls."""

import hashlib
import hmac
import json
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models.motive_oauth import (
    MotiveFault,
    MotiveHistorySample,
    MotiveRemoteVehicle,
    MotiveWebhookReceipt,
)
from app.services import motive_ingestion as ingest
from app.services import motive_oauth as oauth
from app.services.motive_client import SCOPES, MotiveClient
from tests.test_db036_motive_oauth import Provider, connect, setup

pytestmark = pytest.mark.asyncio
SECRET = "synthetic-webhook-secret-at-least32bytes"


class FullProvider(Provider):
    def __init__(self):
        super().__init__()
        self.device_id = 99
        self.history_rows = []
        self.fault_rows = []
        self.inventory_status = "active"

    async def inventory(self, token):
        return [
            {
                "id": 123,
                "number": "Truck-1",
                "vin": "A" * 17,
                "status": self.inventory_status,
                "eld_device": {"id": self.device_id},
            }
        ]

    async def gateways(self, token):
        return [
            {
                "id": self.device_id,
                "identifier": "Synthetic-gateway",
                "model": "lbb-fixture",
                "vehicle": {"id": 123},
            }
        ]

    async def history(self, *args):
        return self.history_rows

    async def faults(self, *args):
        return self.fault_rows


async def prepared(db, monkeypatch):
    actor, truck, _membership = await setup(db, monkeypatch)
    row = await connect(db, actor, truck)
    provider = FullProvider()
    assert (await oauth.sync(db, row, provider))["status"] == "connected"
    await oauth.bind(db, actor, truck.customer_id, "123", truck.id)
    remote = (await db.execute(select(MotiveRemoteVehicle))).scalar_one()
    remote.mapped_at = oauth.now() - timedelta(hours=1)
    row.next_sync_at = None
    await db.commit()
    return actor, truck, row, remote, provider


def measurement(when, **changes):
    result = {
        "id": "synthetic-location-1",
        "located_at": when.isoformat(),
        "lat": 35.0,
        "lon": -80.0,
        "bearing": 45,
        "speed": 50,
        "odometer": 10000,
        "true_odometer": 10001,
        "engine_hours": 123,
        "true_engine_hours": 124,
        "eld_device": {"id": 99},
    }
    result.update(changes)
    return result


def fault(when, **changes):
    result = {
        "id": 321,
        "vehicle": {"id": 123},
        "code": "P203F",
        "code_label": "P203F",
        "code_description": "Synthetic fault",
        "status": "open",
        "first_observed_at": when.isoformat(),
        "last_observed_at": when.isoformat(),
        "fmi": 5,
    }
    result.update(changes)
    return result


def signed(payload, secret=SECRET):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return body, hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()


async def test_inventory_device_metrics_history_and_fault_close(
    db_session, monkeypatch
):
    _actor, truck, row, remote, provider = await prepared(db_session, monkeypatch)
    when = oauth.now() - timedelta(minutes=2)
    provider.history_rows = [measurement(when)]
    provider.fault_rows = [fault(when)]
    assert (await oauth.sync(db_session, row, provider))["status"] == "connected"
    assert (remote.gateway_id, remote.gateway_model) == ("99", "lbb-fixture")
    assert (
        remote.true_odometer_miles,
        remote.virtual_odometer_miles,
        remote.true_engine_hours,
        remote.virtual_engine_hours,
    ) == (10001, 10000, 124, 123)
    assert remote.speed_mph == 50
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveHistorySample))
        == 1
    )
    stored_fault = (await db_session.execute(select(MotiveFault))).scalar_one()
    assert stored_fault.status == "open" and row.last_reconciled_at
    row.next_sync_at = None
    provider.fault_rows[0]["status"] = "closed"
    assert (await oauth.sync(db_session, row, provider))["status"] == "connected"
    assert stored_fault.status == "closed"
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveHistorySample))
        == 1
    )
    row.next_sync_at = None
    provider.fault_rows[0]["status"] = "open"
    await oauth.sync(db_session, row, provider)
    assert stored_fault.status == "closed"
    await db_session.refresh(truck)
    assert truck.mileage == 100


async def test_gateway_reassignment_requires_new_mapping(db_session, monkeypatch):
    _, _, row, remote, provider = await prepared(db_session, monkeypatch)
    provider.history_rows = [measurement(oauth.now() - timedelta(minutes=2))]
    await oauth.sync(db_session, row, provider)
    assert remote.true_odometer_miles == 10001
    row.next_sync_at = None
    provider.device_id = 100
    await oauth.sync(db_session, row, provider)
    assert (
        remote.vehicle_id is None
        and remote.mapped_at is None
        and remote.true_odometer_miles is None
    )
    assert remote.gateway_id == "100"
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveHistorySample))
        == 0
    )


async def test_inactive_inventory_and_unmap_clear_data(db_session, monkeypatch):
    actor, truck, row, remote, provider = await prepared(db_session, monkeypatch)
    provider.history_rows = [measurement(oauth.now() - timedelta(minutes=1))]
    provider.fault_rows = [fault(oauth.now() - timedelta(minutes=1))]
    await oauth.sync(db_session, row, provider)
    await oauth.bind(db_session, actor, truck.customer_id, "123", None)
    assert remote.true_engine_hours is None
    assert await db_session.scalar(select(func.count()).select_from(MotiveFault)) == 0
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveHistorySample))
        == 0
    )
    row.next_sync_at = None
    provider.inventory_status = "deactivated"
    await oauth.sync(db_session, row, provider)
    assert remote.provider_status == "deactivated" and remote.located_at is None


async def test_history_stage_rejects_whole_malformed_page_and_cursor_stays(
    db_session, monkeypatch
):
    _, _, row, remote, provider = await prepared(db_session, monkeypatch)
    when = oauth.now() - timedelta(minutes=1)
    provider.history_rows = [
        measurement(when),
        measurement(when, id="other", engine_hours="not-number"),
    ]
    result = await oauth.sync(db_session, row, provider)
    assert (
        result["status"] == "provider_error"
        and row.last_error_code == "invalid_history"
    )
    assert remote.history_cursor_at is None
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveHistorySample))
        == 0
    )


async def test_history_conflict_keeps_first_value_and_partial_stage_rolls_back(
    db_session, monkeypatch
):
    _, _, row, remote, provider = await prepared(db_session, monkeypatch)
    when = oauth.now() - timedelta(minutes=1)
    provider.history_rows = [measurement(when)]
    await oauth.sync(db_session, row, provider)
    cursor = remote.history_cursor_at
    row.next_sync_at = None
    provider.history_rows = [
        measurement(when, id="new"),
        measurement(when, true_odometer=99999),
    ]
    await oauth.sync(db_session, row, provider)
    await db_session.refresh(remote)
    assert row.last_error_code == "history_conflict" and oauth.utc(
        remote.history_cursor_at
    ) == oauth.utc(cursor)
    assert remote.true_odometer_miles == 10001
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveHistorySample))
        == 1
    )


async def test_missing_true_metrics_stay_unknown_zero_preserved(
    db_session, monkeypatch
):
    _, _, row, remote, provider = await prepared(db_session, monkeypatch)
    provider.history_rows = [
        measurement(
            oauth.now() - timedelta(minutes=1),
            true_odometer=None,
            true_engine_hours=None,
            odometer=0,
            engine_hours=0,
        )
    ]
    await oauth.sync(db_session, row, provider)
    assert remote.true_odometer_miles is None and remote.true_engine_hours is None
    assert remote.virtual_odometer_miles == 0 and remote.virtual_engine_hours == 0


async def test_old_scope_requires_reconsent(db_session, monkeypatch):
    _, _, row, _, provider = await prepared(db_session, monkeypatch)
    row.scopes = "companies.read locations.vehicle_locations_list"
    result = await oauth.sync(db_session, row, provider)
    assert (
        result["status"] == "reconnect_required"
        and row.last_error_code == "insufficient_scope"
    )


@pytest.mark.parametrize(
    "probe",
    [
        b"[vehicle_location_updated]",
        b'["vehicle_location_updated"]',
        b'["fault_code_closed"]',
    ],
)
async def test_signed_activation_probes_no_inventory_data(
    db_session, monkeypatch, probe
):
    actor, truck, row, _, _ = await prepared(db_session, monkeypatch)
    await ingest.configure_webhook(db_session, actor, truck.customer_id, SECRET)
    body, signature = signed(probe)
    assert (
        await ingest.ingest_webhook(
            db_session, row.webhook_id, row.webhook_generation, body, signature
        )
    )["status"] == "verified"
    assert row.webhook_verified_at and row.webhook_last_received_at is None
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveWebhookReceipt))
        == 0
    )


@pytest.mark.parametrize("action", sorted(ingest.ACTIONS))
async def test_supported_events_are_durable_metadata_only(
    db_session, monkeypatch, action
):
    actor, truck, row, _, _ = await prepared(db_session, monkeypatch)
    await ingest.configure_webhook(db_session, actor, truck.customer_id, SECRET)
    payload = {
        "action": action,
        "id": 123,
        "vehicle_id": 123,
        "vehicle": {"id": 123},
        "lat": 35,
        "lon": -80,
        "speed": 9999,
        "driver_name": "Not stored",
    }
    body, signature = signed(payload)
    result = await ingest.ingest_webhook(
        db_session, row.webhook_id, row.webhook_generation, body, signature
    )
    assert result["status"] == "accepted"
    assert (
        await ingest.ingest_webhook(
            db_session, row.webhook_id, row.webhook_generation, body, signature
        )
    )["status"] == "duplicate"
    receipt = (await db_session.execute(select(MotiveWebhookReceipt))).scalar_one()
    assert receipt.status == "pending" and receipt.provider_vehicle_id == "123"
    assert "Not stored" not in repr(receipt.__dict__) and "9999" not in repr(
        receipt.__dict__
    )
    assert "shared_secret" not in ingest.webhook_status(row)


async def test_webhook_bad_signature_rotation_disconnect(db_session, monkeypatch):
    actor, truck, row, _, _ = await prepared(db_session, monkeypatch)
    await ingest.configure_webhook(db_session, actor, truck.customer_id, SECRET)
    old_id, old_generation = row.webhook_id, row.webhook_generation
    body, signature = signed(
        {"action": "vehicle_location_received", "id": "event", "vehicle_id": 123}
    )
    with pytest.raises(HTTPException) as exc:
        await ingest.ingest_webhook(db_session, old_id, old_generation, body, "0" * 40)
    assert exc.value.status_code == 403
    await ingest.ingest_webhook(db_session, old_id, old_generation, body, signature)
    await ingest.configure_webhook(db_session, actor, truck.customer_id, SECRET + "new")
    with pytest.raises(HTTPException) as exc:
        await ingest.ingest_webhook(db_session, old_id, old_generation, body, signature)
    assert exc.value.status_code == 404
    receipt = (await db_session.execute(select(MotiveWebhookReceipt))).scalar_one()
    assert receipt.status == "discarded"
    await oauth.disconnect(db_session, actor, truck.customer_id)
    assert not row.webhook_enabled and row.encrypted_webhook_secret is None
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveRemoteVehicle))
        == 0
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "driver_upserted"},
        {"action": []},
        {"action": "vehicle_location_updated", "id": "event", "vehicle_id": False},
        b"{bad",
        b'["unknown"]',
    ],
)
async def test_invalid_signed_webhooks_rejected(db_session, monkeypatch, payload):
    actor, truck, row, _, _ = await prepared(db_session, monkeypatch)
    await ingest.configure_webhook(db_session, actor, truck.customer_id, SECRET)
    body, signature = signed(payload)
    with pytest.raises(HTTPException) as exc:
        await ingest.ingest_webhook(
            db_session, row.webhook_id, row.webhook_generation, body, signature
        )
    assert exc.value.status_code == 400
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveWebhookReceipt))
        == 0
    )


async def test_webhook_db_failure_cannot_acknowledge(monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    class FailedDB:
        async def execute(self, *args):
            raise SQLAlchemyError("synthetic unavailable")

        async def rollback(self):
            pass

    with pytest.raises(HTTPException) as exc:
        await ingest.ingest_webhook(FailedDB(), uuid4(), 1, b"{}", "0" * 40)
    assert exc.value.status_code == 503


async def test_documented_new_transport_shapes_and_units(monkeypatch):
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", True)
    when = oauth.now()

    def handler(request):
        path = request.url.path
        assert request.headers["Authorization"] == "Bearer synthetic"
        if path == "/v1/vehicles":
            return httpx.Response(
                200,
                json={
                    "vehicles": [{"vehicle": {"id": 123, "status": "active"}}],
                    "pagination": {"page_no": 1, "total": 1},
                },
            )
        if path == "/v1/eld_devices":
            return httpx.Response(
                200,
                json={
                    "eld_devices": [{"eld_device": {"id": 99, "vehicle": {"id": 123}}}],
                    "pagination": {"page_no": 1, "total": 1},
                },
            )
        if path == "/v3/vehicle_locations/123":
            assert request.headers["X-Metric-Units"] == "false"
            assert request.url.params["updated_after"]
            return httpx.Response(
                200,
                json={"vehicle_locations": [{"vehicle_location": measurement(when)}]},
            )
        assert (
            path == "/v1/fault_codes" and request.url.params["vehicle_ids[]"] == "123"
        )
        return httpx.Response(
            200,
            json={
                "fault_codes": [{"fault_code": fault(when)}],
                "page_no": 1,
                "total": 1,
            },
        )

    client = MotiveClient(httpx.MockTransport(handler))
    assert len(await client.inventory("synthetic")) == 1
    assert len(await client.gateways("synthetic")) == 1
    assert (
        len(
            await client.history(
                "synthetic",
                "123",
                when - timedelta(hours=1),
                when,
                when - timedelta(hours=1),
            )
        )
        == 1
    )
    assert (
        len(
            await client.faults(
                "synthetic",
                "123",
                when - timedelta(hours=1),
                when,
                when - timedelta(hours=1),
            )
        )
        == 1
    )
    assert {
        "eld_devices.read",
        "fault_codes.read",
        "locations.vehicle_locations_single",
    }.issubset(SCOPES.split())


async def test_cursor_continuation_is_explicit_and_durable(db_session, monkeypatch):
    _, _, row, remote, provider = await prepared(db_session, monkeypatch)
    remote.mapped_at = oauth.now() - timedelta(days=3)
    await db_session.commit()
    result = await oauth.sync(db_session, row, provider)
    assert (
        result["status"] == "connected"
        and row.last_error_code == "reconciliation_incomplete"
    )
    assert remote.history_cursor_at < oauth.now() - timedelta(days=1)
    covered = remote.history_cursor_at
    row.next_sync_at = None
    await oauth.sync(db_session, row, provider)
    assert remote.history_cursor_at > covered


async def test_webhook_worker_processes_only_after_reconciliation(
    db_session, monkeypatch
):
    from contextlib import asynccontextmanager

    from app.tasks import motive as task

    actor, truck, row, _, provider = await prepared(db_session, monkeypatch)
    await ingest.configure_webhook(db_session, actor, truck.customer_id, SECRET)
    body, signature = signed(
        {"action": "fault_code_closed", "id": 321, "vehicle": {"id": 123}}
    )
    await ingest.ingest_webhook(
        db_session, row.webhook_id, row.webhook_generation, body, signature
    )

    @asynccontextmanager
    async def session_factory():
        yield db_session

    real_sync = oauth.sync

    async def synthetic_sync(db, connection):
        return await real_sync(db, connection, provider)

    monkeypatch.setattr(task, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(task.service, "sync", synthetic_sync)
    assert (await task.reconcile())["processed"] == 1
    receipt = (await db_session.execute(select(MotiveWebhookReceipt))).scalar_one()
    assert (
        receipt.status == "processed" and receipt.processed_at and receipt.attempts == 1
    )


async def test_inbox_failures_retry_then_dead(db_session, monkeypatch):
    from contextlib import asynccontextmanager

    from app.tasks import motive as task

    actor, truck, row, _, provider = await prepared(db_session, monkeypatch)
    await ingest.configure_webhook(db_session, actor, truck.customer_id, SECRET)
    body, signature = signed(
        {"action": "vehicle_location_received", "id": "event", "vehicle_id": 123}
    )
    await ingest.ingest_webhook(
        db_session, row.webhook_id, row.webhook_generation, body, signature
    )

    @asynccontextmanager
    async def session_factory():
        yield db_session

    real_sync = oauth.sync
    provider.error = "provider_error"

    async def synthetic_sync(db, connection):
        return await real_sync(db, connection, provider)

    monkeypatch.setattr(task, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(task.service, "sync", synthetic_sync)
    for _ in range(5):
        await db_session.refresh(row)
        row.next_sync_at = None
        receipt = (await db_session.execute(select(MotiveWebhookReceipt))).scalar_one()
        receipt.next_attempt_at = None
        await db_session.commit()
        await task.reconcile()
    receipt = (await db_session.execute(select(MotiveWebhookReceipt))).scalar_one()
    assert (
        receipt.status == "dead"
        and receipt.attempts == 5
        and receipt.error_code == "provider_error"
    )


async def test_full_retention_even_feature_off(db_session, monkeypatch):
    _actor, _truck, row, remote, provider = await prepared(db_session, monkeypatch)
    when = oauth.now() - timedelta(minutes=1)
    provider.history_rows = [measurement(when)]
    provider.fault_rows = [fault(when)]
    await oauth.sync(db_session, row, provider)
    sample = (await db_session.execute(select(MotiveHistorySample))).scalar_one()
    stored_fault = (await db_session.execute(select(MotiveFault))).scalar_one()
    sample.observed_at = stored_fault.received_at = remote.metrics_observed_at = (
        oauth.now() - timedelta(days=31)
    )
    await db_session.commit()
    monkeypatch.setattr(settings, "MOTIVE_ENABLED", False)
    await oauth.purge(db_session)
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveHistorySample))
        == 0
    )
    assert await db_session.scalar(select(func.count()).select_from(MotiveFault)) == 0
    await db_session.refresh(remote)
    assert remote.true_odometer_miles is None


async def test_real_client_history_catchup_with_overlap_is_within_day(
    db_session, monkeypatch
):
    _, _, row, remote, provider = await prepared(db_session, monkeypatch)
    remote.mapped_at = oauth.now() - timedelta(days=4)
    remote.history_cursor_at = oauth.now() - timedelta(days=2)
    captured = []

    def handler(request):
        from datetime import datetime

        start = datetime.fromisoformat(request.url.params["start_date"])
        end = datetime.fromisoformat(request.url.params["end_date"])
        captured.append((start, end))
        assert 0 < (end - start).total_seconds() <= 86400
        return httpx.Response(200, json={"vehicle_locations": []})

    real = MotiveClient(httpx.MockTransport(handler))
    provider.history = real.history
    await db_session.commit()
    await oauth.sync(db_session, row, provider)
    assert captured and row.last_error_code == "reconciliation_incomplete"
    assert oauth.utc(remote.history_cursor_at) == captured[0][1]


async def test_seven_trucks_finish_fixed_sweep_as_clock_advances(
    db_session, monkeypatch
):
    from app.db.models.vehicle import Vehicle
    from app.db.models.vehicle_relationship import FleetMembership

    actor, truck, row, _remote, provider = await prepared(db_session, monkeypatch)
    clock = [oauth.now()]
    monkeypatch.setattr(oauth, "now", lambda: clock[0])
    inventory = await provider.inventory("unused")
    gateways = await provider.gateways("unused")
    for index in range(6):
        vehicle = Vehicle(
            tenant_id=actor.tenant_id,
            customer_id=truck.customer_id,
            make="Fixture",
            model="Truck",
        )
        db_session.add(vehicle)
        await db_session.flush()
        db_session.add(
            FleetMembership(
                tenant_id=actor.tenant_id,
                fleet_customer_id=truck.customer_id,
                vehicle_id=vehicle.id,
                effective_from=clock[0] - timedelta(days=1),
            )
        )
        provider_id = str(124 + index)
        gateway = str(100 + index)
        db_session.add(
            MotiveRemoteVehicle(
                tenant_id=actor.tenant_id,
                connection_id=row.id,
                provider_vehicle_id=provider_id,
                gateway_id=gateway,
                provider_status="active",
                vehicle_id=vehicle.id,
                mapped_at=clock[0] - timedelta(hours=1),
                discovered_at=clock[0],
            )
        )
        inventory.append(
            {
                "id": int(provider_id),
                "number": provider_id,
                "status": "active",
                "eld_device": {"id": int(gateway)},
            }
        )
        gateways.append({"id": int(gateway), "vehicle": {"id": int(provider_id)}})

    async def all_inventory(token):
        return inventory

    async def all_gateways(token):
        return gateways

    provider.inventory, provider.gateways = all_inventory, all_gateways
    await db_session.commit()
    first = await oauth.sync(db_session, row, provider)
    assert first["status"] == "connected" and first["completed_at"] is None
    assert row.last_error_code == "reconciliation_incomplete" and row.failure_count == 0
    cutoff = row.reconciliation_cutoff_at
    clock[0] += timedelta(minutes=20)
    second = await oauth.sync(db_session, row, provider)
    assert second["completed_at"] is not None and row.last_error_code is None
    assert oauth.utc(row.last_reconciled_at) == oauth.utc(cutoff)
    assert row.reconciliation_cutoff_at is None
    remotes = (await db_session.execute(select(MotiveRemoteVehicle))).scalars().all()
    assert len(remotes) == 7 and all(
        oauth.utc(r.history_cursor_at) == oauth.utc(cutoff) for r in remotes
    )


async def test_equivalent_timezone_event_is_duplicate(db_session, monkeypatch):
    from datetime import timezone

    _, _, row, _remote, provider = await prepared(db_session, monkeypatch)
    when = oauth.now() - timedelta(minutes=1)
    provider.history_rows = [measurement(when)]
    await oauth.sync(db_session, row, provider)
    row.next_sync_at = None
    provider.history_rows = [
        measurement(when.astimezone(timezone(timedelta(hours=-4))))
    ]
    await oauth.sync(db_session, row, provider)
    assert row.last_error_code is None
    assert (
        await db_session.scalar(select(func.count()).select_from(MotiveHistorySample))
        == 1
    )


async def test_authorization_loss_preserves_rotated_tokens_not_data(
    db_session, monkeypatch
):
    from app.core import motive_crypto

    actor, _, row, remote, provider = await prepared(db_session, monkeypatch)
    row.token_expires_at = oauth.now()
    old_cipher = row.encrypted_tokens
    await db_session.commit()

    async def rotated(**kwargs):
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 7200,
        }

    async def revoked(*args):
        raise HTTPException(403, "grant_required")

    provider.tokens = rotated
    provider.inventory_status = "deactivated"
    monkeypatch.setattr(oauth, "authorize", revoked)
    with pytest.raises(HTTPException) as exc:
        await oauth.sync(db_session, row, provider, actor=actor)
    assert exc.value.status_code == 403
    await db_session.rollback()
    await db_session.refresh(row)
    await db_session.refresh(remote)
    assert row.encrypted_tokens != old_cipher
    assert (
        motive_crypto.decrypt(
            row.encrypted_tokens, row.id, row.tenant_id, row.fleet_customer_id
        )["refresh_token"]
        == "new-refresh"
    )
    assert remote.provider_status == "active"
